import streamlit as st
import json
from database import DatabaseManager
from extractors import ExtractorFactory

def set_custom_style():
    """Applies a colorful and attractive custom CSS theme."""
    css = """
    <style>
    /* Colorful Gradient Background */
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        background: linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%) !important;
    }
    
    /* Transparent Sidebar with Blur */
    [data-testid="stSidebar"] {
        background-color: rgba(255, 255, 255, 0.2) !important;
        backdrop-filter: blur(10px);
    }
    
    /* Make white spaces and containers colorful with Glassmorphism */
    [data-testid="stVerticalBlockBorderWrapper"], .stFileUploader {
        background-color: rgba(255, 255, 255, 0.2) !important;
        backdrop-filter: blur(10px);
        border-radius: 15px;
        border: 1px solid rgba(255, 255, 255, 0.5) !important;
    }

    /* Enhance Text Readability */
    h1, h2, h3, p, label {
        color: #2c3e50 !important;
        text-shadow: 1px 1px 2px rgba(255, 255, 255, 0.6);
    }
    </style>
    """
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
    
    # Apply the new attractive styling
    set_custom_style()

    st.title("✨ 📄 Intelligent Document Extraction Platform 🚀")
    st.markdown("Extract structured data from documents instantly using Gemini via the OpenAI SDK. 🤖💡")

    # Sidebar for configuration
    with st.sidebar:
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
    with st.container(border=True):
        uploaded_file = st.file_uploader(
            "📂 Upload Document (JPG/PNG/PDF)", 
            type=["jpg", "jpeg", "png", "pdf"]
        )

    if uploaded_file is not None:
        col1, col2 = st.columns(2)
        
        with col1:
            with st.container(border=True):
                st.subheader("👁️ Document Preview")
                if uploaded_file.type == "application/pdf":
                    st.info("📄 PDF uploaded. Preview is unavailable, but it will be processed during extraction.")
                else:
                    st.image(uploaded_file, use_container_width=True)

        with col2:
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

                            # Render Results
                            st.balloons()
                            st.success("🎉 Extraction and Database Storage Successful! 🥳")
                            st.json(extracted_dict)

                        except json.JSONDecodeError:
                            st.error(f"Failed to parse output as JSON. Raw output:\n{raw_json_str}")
                        except Exception as e:
                            st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
