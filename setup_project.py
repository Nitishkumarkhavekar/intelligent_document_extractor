import os

project_files = {
    "requirements.txt": """streamlit==1.32.0
openai==1.14.0
pydantic==2.6.4
sqlalchemy==2.0.29
pymupdf==1.24.1
""",

    "utils.py": """import logging
from functools import wraps

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("DocumentExtractor")

def log_execution(func):
    \"\"\"Aspect-oriented decorator for logging function execution.\"\"\"
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(f"Executing: {func.__name__}")
        result = func(*args, **kwargs)
        logger.info(f"Completed: {func.__name__}")
        return result
    return wrapper

def handle_exceptions(func):
    \"\"\"Aspect-oriented decorator for unified exception handling.\"\"\"
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Exception in {func.__name__}: {str(e)}")
            raise e
    return wrapper
""",

    "database.py": """from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
from utils import log_execution, handle_exceptions

Base = declarative_base()

class DocumentRecord(Base):
    __tablename__ = 'extracted_documents'
    id = Column(Integer, primary_key=True, autoincrement=True)
    document_type = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    extracted_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class DatabaseManager:
    def __init__(self, db_url: str = 'sqlite:///documents.db'):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    @log_execution
    @handle_exceptions
    def save_record(self, doc_type: str, file_name: str, extracted_json: str):
        with self.Session() as session:
            record = DocumentRecord(
                document_type=doc_type,
                file_name=file_name,
                extracted_json=extracted_json
            )
            session.add(record)
            session.commit()
""",

    "schemas.py": """from pydantic import BaseModel
from typing import Optional

class AadhaarSchema(BaseModel):
    full_name: str
    aadhaar_number: str
    dob_or_yob: str
    gender: str
    address: str

class DrivingLicenceSchema(BaseModel):
    full_name: str
    licence_number: str
    dob: str
    valid_till: str
    issuing_authority: str

class PassportSchema(BaseModel):
    passport_number: str
    given_names: str
    surname: str
    nationality: str
    dob: str
    date_of_expiry: str

class InvoiceSchema(BaseModel):
    invoice_number: str
    date: str
    total_amount: str
    vendor_name: str
    line_items: list[str]

class ResumeSchema(BaseModel):
    candidate_name: str
    email: str
    phone: str
    skills: list[str]
    years_of_experience: Optional[str]
""",

    "extractors.py": """import base64
from abc import ABC, abstractmethod
from typing import Type
from pydantic import BaseModel
from openai import OpenAI
from utils import log_execution, handle_exceptions
import schemas
import fitz  # PyMuPDF

class BaseExtractor(ABC):
    \"\"\"Abstract Strategy for Document Extraction\"\"\"
    @abstractmethod
    def extract(self, file_bytes: bytes, mime_type: str) -> str:
        pass

class OpenAIGeminiExtractor(BaseExtractor):
    \"\"\"Concrete Strategy using OpenAI SDK pointed to Gemini API\"\"\"
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
    \"\"\"Factory to instantiate the correct extractor pipeline\"\"\"
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
""",

    "app.py": """import streamlit as st
import json
import os
import base64
from database import DatabaseManager
from extractors import ExtractorFactory

def set_background(image_path):
    \"\"\"Sets a custom background image if it exists.\"\"\"
    if os.path.exists(image_path):
        with open(image_path, "rb") as img_file:
            encoded_string = base64.b64encode(img_file.read()).decode()
        css = f\"\"\"
        <style>
        .stApp {{
            background-image: url("data:image/jpeg;base64,{encoded_string}");
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }}
        </style>
        \"\"\"
        st.markdown(css, unsafe_allow_html=True)
def set_custom_style():
    \"\"\"Applies a colorful and attractive custom CSS theme.\"\"\"
    css = \"\"\"
    <style>
    /* Colorful Gradient Background */
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{
        background: linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%) !important;
    }}
    
    /* Transparent Sidebar with Blur */
    [data-testid="stSidebar"] {{
        background-color: rgba(255, 255, 255, 0.2) !important;
        backdrop-filter: blur(10px);
    }}
    
    /* Make white spaces and containers colorful with Glassmorphism */
    [data-testid="stVerticalBlockBorderWrapper"], .stFileUploader {{
        background-color: rgba(255, 255, 255, 0.2) !important;
        backdrop-filter: blur(10px);
        border-radius: 15px;
        border: 1px solid rgba(255, 255, 255, 0.5) !important;
    }}

    /* Enhance Text Readability */
    h1, h2, h3, p, label {{
        color: #2c3e50 !important;
        text-shadow: 1px 1px 2px rgba(255, 255, 255, 0.6);
    }}
    </style>
    \"\"\"
    st.markdown(css, unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_available_models(api_key):
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        return [m.id for m in client.models.list()]
    except Exception:
        return ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-1.5-flash-8b", "gemini-1.5-pro-001", "gemini-1.5-flash-001"]

def main():
    st.set_page_config(page_title="Intelligent Document Extraction", layout="wide", page_icon="🤖")
    
    # Load the background image named "chatbot.jpg" or "chatbot.png"
    if os.path.exists("chatbot.jpg"):
        set_background("chatbot.jpg")
    elif os.path.exists("chatbot.png"):
        set_background("chatbot.png")
    # Apply the new attractive styling
    set_custom_style()

    st.title("✨ 📄 Intelligent Document Extraction Platform 🚀")
    st.markdown("Extract structured data from documents instantly using Gemini via the OpenAI SDK. 🤖💡")

    # Sidebar for configuration
    with st.sidebar:
        st.header("⚙️ Configuration 🛠️")
        api_key = st.text_input("Enter Gemini API Key", type="password", value="AQ.Ab8RN6KpGVaNvR6RQ3P00xOo6CHgDO5M2KORuCT6WAsAFT7QcQ")
        st.markdown("[Get your Gemini API Key here](https://aistudio.google.com/app/apikey)")
        
        st.header("📁 Document Details")
        doc_type = st.selectbox(
            "Select Document Type",
            ["Aadhaar Card", "Driving Licence", "Passport", "Invoice", "Resume"]
        )
        
        st.header("🧠 Model Settings")
        available_models = get_available_models(api_key) if api_key else ["gemini-1.5-flash"]
        default_index = 0
        for i, m in enumerate(available_models):
            if "gemini-1.5-flash" in m:
                default_index = i
                break
        model_name = st.selectbox(
            "Select Gemini Model",
            available_models,
            index=default_index,
            help="Dynamically fetched models available for your API key."
        )
        with st.container(border=True):
            st.header("⚙️ Configuration 🛠️")
            api_key = st.text_input("Enter Gemini API Key", type="password", value="AQ.Ab8RN6KpGVaNvR6RQ3P00xOo6CHgDO5M2KORuCT6WAsAFT7QcQ")
            st.markdown("[Get your Gemini API Key here](https://aistudio.google.com/app/apikey)")
            
        with st.container(border=True):
            st.header("📁 Document Details")
            doc_type = st.selectbox(
                "Select Document Type",
                ["Aadhaar Card", "Driving Licence", "Passport", "Invoice", "Resume"]
            )
            
        with st.container(border=True):
            st.header("🧠 Model Settings")
            available_models = get_available_models(api_key) if api_key else ["gemini-1.5-flash"]
            default_index = 0
            for i, m in enumerate(available_models):
                if "gemini-1.5-flash" in m:
                    default_index = i
                    break
            model_name = st.selectbox(
                "Select Gemini Model",
                available_models,
                index=default_index,
                help="Dynamically fetched models available for your API key."
            )

    # Main area
    uploaded_file = st.file_uploader(
        "📂 Upload Document (JPG/PNG/PDF)", 
        type=["jpg", "jpeg", "png", "pdf"]
    )
    with st.container(border=True):
        uploaded_file = st.file_uploader(
            "📂 Upload Document (JPG/PNG/PDF)", 
            type=["jpg", "jpeg", "png", "pdf"]
        )

    if uploaded_file is not None:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("👁️ Document Preview")
            if uploaded_file.type == "application/pdf":
                st.info("📄 PDF uploaded. Preview is unavailable, but it will be processed during extraction.")
            else:
                st.image(uploaded_file, use_container_width=True)
            with st.container(border=True):
                st.subheader("👁️ Document Preview")
                if uploaded_file.type == "application/pdf":
                    st.info("📄 PDF uploaded. Preview is unavailable, but it will be processed during extraction.")
                else:
                    st.image(uploaded_file, use_container_width=True)

        with col2:
            st.subheader("📊 Extracted Data")
            if st.button("🚀 Extract Information", type="primary", use_container_width=True):
                if not api_key:
                    st.error("⚠️ Please provide a Gemini API Key in the sidebar.")
                    return
                
                with st.spinner("⏳ Extracting via Gemini OCR/LLM... 🪄✨"):
                    try:
                        # Initialize DB and Extractor
                        db_manager = DatabaseManager()
                        extractor = ExtractorFactory.create(doc_type, api_key, model_name=model_name)
                        
                        # Process Document
                        mime_type = uploaded_file.type
                        file_bytes = uploaded_file.read()
                        raw_json_str = extractor.extract(file_bytes, mime_type)
                        
                        # Clean output just in case LLM added formatting
                        cleaned_json_str = raw_json_str.replace("```json", "").replace("```", "").strip()
                        extracted_dict = json.loads(cleaned_json_str)
            with st.container(border=True):
                st.subheader("📊 Extracted Data")
                if st.button("🚀 Extract Information", type="primary", use_container_width=True):
                    if not api_key:
                        st.error("⚠️ Please provide a Gemini API Key in the sidebar.")
                        return
                    
                    with st.spinner("⏳ Extracting via Gemini OCR/LLM... 🪄✨"):
                        try:
                            # Initialize DB and Extractor
                            db_manager = DatabaseManager()
                            extractor = ExtractorFactory.create(doc_type, api_key, model_name=model_name)
                            
                            # Process Document
                            mime_type = uploaded_file.type
                            file_bytes = uploaded_file.read()
                            raw_json_str = extractor.extract(file_bytes, mime_type)
                            
                            # Clean output just in case LLM added formatting
                            cleaned_json_str = raw_json_str.replace("```json", "").replace("```", "").strip()
                            extracted_dict = json.loads(cleaned_json_str)

                        # Save to Database
                        db_manager.save_record(
                            doc_type=doc_type, 
                            file_name=uploaded_file.name, 
                            extracted_json=json.dumps(extracted_dict)
                        )
                            # Save to Database
                            db_manager.save_record(
                                doc_type=doc_type, 
                                file_name=uploaded_file.name, 
                                extracted_json=json.dumps(extracted_dict)
                            )

                        # Render Results
                        st.balloons()
                        st.success("🎉 Extraction and Database Storage Successful! 🥳")
                        st.json(extracted_dict)
                            # Render Results
                            st.balloons()
                            st.success("🎉 Extraction and Database Storage Successful! 🥳")
                            st.json(extracted_dict)

                    except json.JSONDecodeError:
                        st.error(f"Failed to parse output as JSON. Raw output:\\n{raw_json_str}")
                    except Exception as e:
                        st.error(f"An error occurred: {str(e)}")
                        except json.JSONDecodeError:
                            st.error(f"Failed to parse output as JSON. Raw output:\\n{raw_json_str}")
                        except Exception as e:
                            st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
""",

    "README.md": """# ✨ Intelligent Document Extraction Platform 🚀

A Python-based intelligent document extraction platform that uses Google's Gemini Vision models to scan, process, and extract structured information from various document types. The application is built with a focus on clean architecture, SOLID principles, and modern design patterns, all presented through a beautiful and interactive Streamlit user interface.

## 🌟 Features

-   **Multi-Document Support**: Extract data from various document types:
    -   Aadhaar Card
    -   Driving Licence
    -   Passport
    -   Invoice
    -   Resume
-   **Multi-Format Upload**: Supports `JPG`, `PNG`, and `PDF` file formats.
-   **Advanced OCR & LLM Integration**: Leverages the power of Google Gemini for state-of-the-art OCR and data extraction in a single step.
-   **Dynamic Model Selection**: Automatically fetches and lists available Gemini models to ensure compatibility and prevent errors.
-   **Template-Based Extraction**: Uses Pydantic schemas to define and enforce the structure of the extracted data, making the output fields easily configurable.
-   **Database Storage**: Automatically stores all extracted information in a local SQLite database for persistence and future use.
-   **Engaging UI**: A beautiful, colorful, and responsive user interface built with Streamlit, featuring a "Glassmorphism" theme.
-   **Robust Architecture**:
    -   Follows **SOLID** principles for maintainable and scalable code.
    -   Implements **Design Patterns** like Strategy, Factory, and Decorator.
    -   Uses **Aspect-Oriented Programming** for clean logging and exception handling.

## 🏗️ Project Structure

The project is organized into distinct modules, each with a single responsibility, making it easy to understand and extend.

```
e:\\intelligent-document-extractor\\
│
├── requirements.txt      # Project dependencies
├── README.md             # This file
├── setup_project.py      # Script to generate the project structure
├── utils.py              # Logging and exception handling decorators
├── database.py           # SQLAlchemy models and database manager
├── schemas.py            # Pydantic schemas for document data structures
├── extractors.py         # Strategy & Factory for the extraction logic
└── app.py                # The main Streamlit user interface
```

## 🛠️ Setup and Installation

Follow these steps to get the application running on your local machine.

### 1. Prerequisites

-   Python 3.8+
-   An active Google Gemini API Key.

### 2. Installation

Clone the repository or create the files as provided. Then, navigate to the project directory and install the required dependencies.

```bash
# Navigate to your project folder
cd path/to/intelligent-document-extractor

# Install dependencies
pip install -r requirements.txt
```

### 3. Get Your API Key

-   Visit the Google AI Studio to generate your Gemini API key.
-   The application has a pre-filled key for convenience, but it's recommended to replace it with your own.

### 4. Run the Application

Launch the Streamlit app from your terminal:

```bash
streamlit run app.py
```

Your browser should automatically open a new tab with the running application.

## 🚀 How to Use

1.  **Launch the app**.
2.  The **Gemini API Key** is pre-filled in the sidebar. You can change it if needed.
3.  Select the **Document Type** you wish to extract from the dropdown menu.
4.  Choose a **Gemini Model**. The list is populated dynamically based on what's available for your key. `gemini-1.5-flash` is recommended for speed.
5.  **Upload** your document file (`.jpg`, `.png`, or `.pdf`).
6.  A preview of the document will appear.
7.  Click the **"🚀 Extract Information"** button.
8.  The extracted data will be displayed in a structured JSON format and is automatically saved to the `documents.db` file. A success animation will play!

## 📸 Screenshots

*(This is where you can add your screenshots of the application in action.)*
"""
}
"""}

# Create all files in the current working directory
for filename, content in project_files.items():
    file_path = os.path.join(os.getcwd(), filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Created {filename}")

print("\n🎉 Project setup complete! Now run:")
print("1. pip install -r requirements.txt")
print("2. streamlit run app.py")
