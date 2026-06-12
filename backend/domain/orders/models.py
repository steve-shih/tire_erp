from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ProductBase(BaseModel):
    product_code: str
    brand: str
    spec: str
    pattern: str
    category: str  # 轎車胎, 卡車胎, 翻修胎, 新胎出寄庫
    stock_qty: int = 0
    cost: float = 0.0
    price: float = 0.0
    extra_field_1: Optional[str] = None
    extra_field_2: Optional[str] = None

class ProductCreate(ProductBase):
    pass

class OrderItem(BaseModel):
    product_code: str
    brand: Optional[str] = None
    spec: Optional[str] = None
    pattern: Optional[str] = None
    qty: int
    price: float
    amount: float
    service_type: Optional[str] = None     # 維修內容: 換新胎, 翻修, 定位, 補胎 等
    tire_position: Optional[str] = None    # 輪胎部位: "FL(1), FR(2)" 等

class StockAdjustment(BaseModel):
    adjustment: int
    reason: Optional[str] = None

class SalesOrderBase(BaseModel):
    order_id: str
    department: str  # truck, sedan
    category: str  # 大車店內, 大車批發, 轎車店內, 轎車批發
    date: datetime
    customer_id: str
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_uniform_number: Optional[str] = None
    customer_address: Optional[str] = None
    plate_number: Optional[str] = None
    items: List[OrderItem]
    total_amount: float
    tax_amount: float = 0.0
    grand_total: float
    payment_status: str  # 收現, 應收貨款, etc.
    invoice_number: Optional[str] = None
    note: Optional[str] = None

class SalesOrderCreate(SalesOrderBase):
    pass

class PurchaseOrderBase(BaseModel):
    purchase_id: str
    date: datetime
    vendor_id: str
    vendor_name: Optional[str] = None
    vendor_phone: Optional[str] = None
    vendor_uniform_number: Optional[str] = None
    vendor_address: Optional[str] = None
    items: List[OrderItem]
    total_amount: float
    tax_amount: float = 0.0
    grand_total: float
    payment_status: str  # 收現, 應付帳款, etc.
    invoice_number: Optional[str] = None
    note: Optional[str] = None

class PurchaseOrderCreate(PurchaseOrderBase):
    pass

class QuoteBase(BaseModel):
    quote_id: str
    quote_type: str  # customer, vendor
    category: str  # 大車, 轎車
    date: datetime
    party_id: str
    party_name: str
    phone: Optional[str] = None
    uniform_number: Optional[str] = None
    address: Optional[str] = None
    plate_number: Optional[str] = None
    items: List[OrderItem]
    total_amount: float
    tax_amount: float = 0.0
    grand_total: float
    note: Optional[str] = None
    quoted_by: Optional[str] = None
    valid_until: Optional[datetime] = None
    is_converted: bool = False

class QuoteCreate(QuoteBase):
    pass

class AnnouncementBase(BaseModel):
    content: str
