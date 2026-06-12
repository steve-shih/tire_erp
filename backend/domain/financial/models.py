from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

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
    status: str = "pending"    # pending, cleared, bounced
    cleared_date: Optional[datetime] = None

class NoteCreate(NoteBase):
    pass

class EmployeeBase(BaseModel):
    employee_id: str
    name: str
    role: str = "staff"
    base_salary: float
    parent_company: Optional[str] = None
    hire_date: datetime
    phone: Optional[str] = None
    status: str = "active" # active, resigned

class EmployeeCreate(EmployeeBase):
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

# --- Invoice Model (New requirement) ---
class InvoiceBase(BaseModel):
    invoice_id: str
    invoice_number: str
    date: datetime
    party_id: str
    party_name: Optional[str] = None
    party_uniform_number: Optional[str] = None
    invoice_type: str          # sales (銷項) / purchase (進項-扣抵) / receipt (收據)
    items_summary: Optional[str] = None
    qty: int = 1
    price: float = 0.0
    amount: float = 0.0
    tax: float = 0.0
    grand_total: float = 0.0
    payment_method: Optional[str] = None
    is_reported: bool = False  # 申報狀態
    report_period: Optional[str] = None  # 申報期 (例: 115-05~06)
    note: Optional[str] = None

class InvoiceCreate(InvoiceBase):
    pass
