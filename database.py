from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
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
