import base64
from abc import ABC, abstractmethod
from typing import Type
from pydantic import BaseModel
from openai import OpenAI
from utils import log_execution, handle_exceptions
import schemas
import fitz  # PyMuPDF

class BaseExtractor(ABC):
    """Abstract Strategy for Document Extraction"""
    @abstractmethod
    def extract(self, file_bytes: bytes, mime_type: str) -> str:
        pass

class OpenAIGeminiExtractor(BaseExtractor):
    """Concrete Strategy using OpenAI SDK pointed to Gemini API"""
    def __init__(self, api_key: str, schema: Type[BaseModel], model_name: str = "gemini-1.5-flash"):
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        self.schema = schema
        self.model_name = model_name

    @log_execution
    @handle_exceptions
    def extract(self, file_bytes: bytes, mime_type: str) -> str:
        prompt = (
            f"You are an expert OCR and data extraction system. "
            f"Analyze the document image and extract the information exactly matching this JSON schema: "
            f"{self.schema.schema_json()}. "
            f"Return ONLY valid JSON without any markdown formatting blocks."
        )

        content_blocks = [{"type": "text", "text": prompt}]

        if mime_type == "application/pdf":
            # Convert up to the first 5 pages of the PDF to images
            pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
            for page_num in range(min(5, len(pdf_document))):
                page = pdf_document.load_page(page_num)
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                b64_img = base64.b64encode(img_bytes).decode('utf-8')
                content_blocks.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64_img}"}
                })
        else:
            # Standard image handling
            base64_image = base64.b64encode(file_bytes).decode('utf-8')
            content_blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}
            })

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "user",
                    "content": content_blocks
                }
            ],
            temperature=0.0 # Strict and deterministic
        )
        
        return response.choices[0].message.content

class ExtractorFactory:
    """Factory to instantiate the correct extractor pipeline"""
    _schema_map = {
        "Aadhaar Card": schemas.AadhaarSchema,
        "Driving Licence": schemas.DrivingLicenceSchema,
        "Passport": schemas.PassportSchema,
        "Invoice": schemas.InvoiceSchema,
        "Resume": schemas.ResumeSchema
    }

    @staticmethod
    def create(doc_type: str, api_key: str, model_name: str = "gemini-1.5-flash") -> BaseExtractor:
        if doc_type not in ExtractorFactory._schema_map:
            raise ValueError(f"Unsupported document type: {doc_type}")
        
        schema = ExtractorFactory._schema_map[doc_type]
        return OpenAIGeminiExtractor(api_key=api_key, schema=schema, model_name=model_name)
