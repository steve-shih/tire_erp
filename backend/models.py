from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone

class AuditModel(BaseModel):
    created_by: str = "system"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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

class PasswordUpdate(BaseModel):
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# --- Mailing Info Schema ---
class MailingInfo(BaseModel):
    envelope: Optional[str] = None
    return_envelope: Optional[str] = None
    bulk_mail: Optional[str] = None

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
    mailing_info: Optional[MailingInfo] = None

class CustomerCreate(CustomerBase):
    pass

class CustomerInDB(CustomerBase, AuditModel):
    pass

# --- Vendor Models ---
class VendorBase(BaseModel):
    vendor_id: str
    name: str
    uniform_number: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    mailing_info: Optional[MailingInfo] = None

class VendorCreate(VendorBase):
    pass

class VendorInDB(VendorBase, AuditModel):
    pass

# --- Product Models ---
class ProductBase(BaseModel):
    product_code: str
    brand: str
    spec: str
    pattern: str
    category: str  # 轎車胎, 卡車胎, 翻修胎, 新胎出寄庫
    stock_qty: int = 0
    cost: float = 0.0
    price: float = 0.0
    extra_field_1: Optional[str] = None  # 轎車專用欄位1
    extra_field_2: Optional[str] = None  # 轎車專用欄位2

class ProductCreate(ProductBase):
    pass

class ProductInDB(ProductBase, AuditModel):
    pass

# --- Order/Quote Item Schema ---
class OrderItem(BaseModel):
    product_code: str
    brand: Optional[str] = None
    spec: Optional[str] = None
    pattern: Optional[str] = None
    qty: int
    price: float
    amount: float
    service_type: Optional[str] = None     # 維修內容: 換新胎, 翻修, 定位, 保養
    tire_position: Optional[str] = None    # 輪胎部位: "FL,FR" or "RL1,RL2,RR1,RR2"

class StockAdjustment(BaseModel):
    adjustment: int
    reason: Optional[str] = None

# --- Sales Order Models ---
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

class SalesOrderInDB(SalesOrderBase, AuditModel):
    pass

# --- Purchase Order Models ---
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

class PurchaseOrderInDB(PurchaseOrderBase, AuditModel):
    pass

# --- Quote Models (Customer & Vendor) ---
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

class QuoteInDB(QuoteBase, AuditModel):
    pass

# --- Announcement Model ---
class AnnouncementBase(BaseModel):
    content: str

class AnnouncementInDB(AnnouncementBase):
    updated_by: str
    updated_at: datetime

# =============================================
# 財務模組 Models
# =============================================

# --- 應收帳款 (Accounts Receivable) ---
class ReceivableBase(BaseModel):
    receivable_id: str
    order_id: str              # 關聯出貨單號
    date: datetime
    customer_id: str
    customer_name: Optional[str] = None
    plate_number: Optional[str] = None
    amount: float              # 應收金額
    paid_amount: float = 0.0   # 已收金額
    balance: float             # 餘額 (amount - paid_amount)
    status: str = "unpaid"     # unpaid, partial, paid
    due_date: Optional[datetime] = None

class ReceivableCreate(ReceivableBase):
    pass

class ReceivableInDB(ReceivableBase, AuditModel):
    pass

# --- 應付帳款 (Accounts Payable) ---
class PayableBase(BaseModel):
    payable_id: str
    purchase_id: str           # 關聯進貨單號
    date: datetime
    vendor_id: str
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    amount: float              # 應付金額
    paid_amount: float = 0.0   # 已付金額
    balance: float             # 餘額
    status: str = "unpaid"     # unpaid, partial, paid
    due_date: Optional[datetime] = None

class PayableCreate(PayableBase):
    pass

class PayableInDB(PayableBase, AuditModel):
    pass

# --- 收付款沖帳 (Payment Records) ---
class PaymentBase(BaseModel):
    payment_id: str
    payment_type: str          # receivable (收款) / payable (付款)
    ref_id: str                # 關聯 receivable_id 或 payable_id
    date: datetime
    amount: float
    method: str                # 現金, 轉帳, 票據, 支票
    note: Optional[str] = None

class PaymentCreate(PaymentBase):
    pass

class PaymentInDB(PaymentBase, AuditModel):
    pass

# --- 票據管理 (Notes / Checks) ---
class NoteBase(BaseModel):
    note_id: str
    note_type: str             # receivable (應收票據) / payable (應付票據)
    note_number: str           # 票據號碼
    bank_name: Optional[str] = None
    amount: float
    issue_date: datetime       # 開票日
    due_date: datetime         # 到期日
    party_id: str              # 客戶或廠商 ID
    party_name: Optional[str] = None
    status: str = "pending"    # pending (未兌現), cleared (已兌現), bounced (退票)
    cleared_date: Optional[datetime] = None

class NoteCreate(NoteBase):
    pass

class NoteInDB(NoteBase, AuditModel):
    pass

# --- Settings ---
class SettingsUpdate(BaseModel):
    staff_visible_menus: List[str]

class SystemLog(BaseModel):
    log_id: str
    timestamp: datetime
    username: str
    action: str
    target: str
    details: str

# =============================================
# 人事薪資模組 Models (Payroll)
# =============================================

class EmployeeBase(BaseModel):
    employee_id: str
    name: str
    role: str = "staff"
    base_salary: float
    hire_date: datetime
    phone: Optional[str] = None
    status: str = "active" # active, resigned

class EmployeeCreate(EmployeeBase):
    pass

class EmployeeInDB(EmployeeBase, AuditModel):
    pass

class PayrollRecordBase(BaseModel):
    payroll_id: str
    employee_id: str
    employee_name: str
    year: int
    month: int
    base_salary: float
    bonus: float = 0.0
    commission: float = 0.0
    performance_bonus: float = 0.0
    overtime_pay: float = 0.0
    deduction: float = 0.0
    net_pay: float
    status: str = "unpaid" # unpaid, paid
    note: Optional[str] = None

class PayrollRecordCreate(PayrollRecordBase):
    pass

class PayrollRecordInDB(PayrollRecordBase, AuditModel):
    pass


