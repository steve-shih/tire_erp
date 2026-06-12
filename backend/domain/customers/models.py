from pydantic import BaseModel
from typing import List, Optional

class MailingInfo(BaseModel):
    envelope: Optional[str] = None
    return_envelope: Optional[str] = None
    bulk_mail: Optional[str] = None

class Vehicle(BaseModel):
    plate_number: str
    vehicle_type: Optional[str] = None

class CustomerBase(BaseModel):
    customer_id: str
    name: str
    uniform_number: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    category: Optional[str] = None  # A/B/C等級
    tax_type: Optional[str] = "含稅"  # 含稅 / 未稅 / 稅外
    vehicles: List[Vehicle] = []
    mailing_info: Optional[MailingInfo] = None

class CustomerCreate(CustomerBase):
    pass

class VendorBase(BaseModel):
    vendor_id: str
    name: str
    uniform_number: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    tax_type: Optional[str] = "含稅"  # 含稅 / 未稅 / 稅外
    mailing_info: Optional[MailingInfo] = None

class VendorCreate(VendorBase):
    pass
