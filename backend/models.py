from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class AuditModel(BaseModel):
    created_by: str = "system"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None
    is_deleted: bool = False
    deleted_by: Optional[str] = None
    deleted_at: Optional[datetime] = None

# --- User Authentication Models ---
class UserBase(BaseModel):
    username: str
    role: str = "staff"  # owner, manager, staff
    is_active: bool = True

class UserCreate(UserBase):
    password: str

class UserInDB(UserBase, AuditModel):
    hashed_password: str

class UserResponse(UserBase):
    username: str
    role: str
    is_active: bool

class LoginRequest(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# --- Customer Models ---
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
    vehicles: List[Vehicle] = []

class CustomerCreate(CustomerBase):
    pass

class CustomerInDB(CustomerBase, AuditModel):
    pass

# --- Product Models ---
class ProductBase(BaseModel):
    product_code: str
    brand: str
    spec: str
    pattern: str
    category: str  # 轎車胎, 卡車胎, 翻修胎
    stock_qty: int = 0
    cost: float = 0.0
    price: float = 0.0

class ProductCreate(ProductBase):
    pass

class ProductInDB(ProductBase, AuditModel):
    pass

# --- Sales Order Models ---
class OrderItem(BaseModel):
    product_code: str
    qty: int
    price: float
    amount: float

class SalesOrderBase(BaseModel):
    order_id: str
    department: str  # truck, sedan
    date: datetime
    customer_id: str
    plate_number: Optional[str] = None
    items: List[OrderItem]
    total_amount: float
    tax_amount: float = 0.0
    grand_total: float
    payment_status: str  # cash, receivable, paid
    invoice_number: Optional[str] = None

class SalesOrderCreate(SalesOrderBase):
    pass

class SalesOrderInDB(SalesOrderBase, AuditModel):
    pass
