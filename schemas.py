from pydantic import BaseModel
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
