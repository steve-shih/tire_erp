from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from backend.database import get_db
from backend.auth import get_current_user
from backend.domain.financial.models import (
    ReceivableCreate, PayableCreate, PaymentCreate, NoteCreate, EmployeeCreate, PayrollRecordCreate, InvoiceCreate
)
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api", tags=["Financial & Payroll & Invoices"])

def _now():
    return datetime.now(timezone.utc)

def _audit_create(username: str) -> dict:
    return {"created_by": username, "created_at": _now(), "is_deleted": False,
            "updated_by": None, "updated_at": None, "deleted_by": None, "deleted_at": None}

def _audit_update(username: str) -> dict:
    return {"updated_by": username, "updated_at": _now()}

def _audit_delete(username: str) -> dict:
    return {"is_deleted": True, "deleted_by": username, "deleted_at": _now()}

def _gen_id(prefix: str) -> str:
    return f"{prefix}-{_now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"


# ==================== Accounts Receivable ====================
@router.get("/receivables")
def list_receivables(status: Optional[str] = None, page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if status:
        q["status"] = status
    total = db["receivables"].count_documents(q)
    skip = (page - 1) * limit
    result = list(db["receivables"].find(q).sort("date", -1).skip(skip).limit(limit))
    for r in result:
        r["_id"] = str(r["_id"])
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.get("/receivables/summary")
def get_ar_summary(page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    # MongoDB aggregation to group by customer
    pipeline = [
        {"$match": {"is_deleted": False}},
        {"$group": {
            "_id": "$customer_id",
            "customer_name": {"$first": "$customer_name"},
            "total_amount": {"$sum": "$amount"},
            "total_paid": {"$sum": "$paid_amount"},
            "total_balance": {"$sum": "$balance"}
        }},
        {"$sort": {"total_balance": -1}}
    ]
    all_grouped = list(db["receivables"].aggregate(pipeline))
    total = len(all_grouped)
    skip = (page - 1) * limit
    data = all_grouped[skip : skip + limit]
    return {
        "data": data,
        "total": total,
        "page": page,
        "limit": limit
    }


# ==================== Accounts Payable ====================
@router.get("/payables")
def list_payables(status: Optional[str] = None, page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if status:
        q["status"] = status
    total = db["payables"].count_documents(q)
    skip = (page - 1) * limit
    result = list(db["payables"].find(q).sort("date", -1).skip(skip).limit(limit))
    for p in result:
        p["_id"] = str(p["_id"])
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.get("/payables/summary")
def get_ap_summary(page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    pipeline = [
        {"$match": {"is_deleted": False}},
        {"$group": {
            "_id": "$vendor_id",
            "vendor_name": {"$first": "$vendor_name"},
            "total_payable": {"$sum": "$amount"},
            "total_paid": {"$sum": "$paid_amount"},
            "balance": {"$sum": "$balance"}
        }},
        {"$sort": {"balance": -1}}
    ]
    all_grouped = list(db["payables"].aggregate(pipeline))
    total = len(all_grouped)
    skip = (page - 1) * limit
    data = all_grouped[skip : skip + limit]
    return {
        "data": data,
        "total": total,
        "page": page,
        "limit": limit
    }


# ==================== Payments Reconciliation ====================
@router.post("/payments", status_code=201)
def create_payment(payment: PaymentCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    doc = payment.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["payments"].insert_one(doc)
    
    # Update Receivable / Payable balances
    coll_name = "receivables" if payment.payment_type == "receivable" else "payables"
    id_field = "receivable_id" if payment.payment_type == "receivable" else "payable_id"
    
    entity = db[coll_name].find_one({id_field: payment.ref_id, "is_deleted": False})
    if entity:
        new_paid = entity.get("paid_amount", 0.0) + payment.amount
        new_bal = entity["amount"] - new_paid
        new_status = "paid" if new_bal <= 0 else ("partial" if new_paid > 0 else "unpaid")
        db[coll_name].update_one(
            {id_field: payment.ref_id},
            {"$set": {"paid_amount": new_paid, "balance": new_bal, "status": new_status, **_audit_update(current_user["username"])}}
        )
    else:
        # Treat ref_id as customer_id or vendor_id, pay off oldest invoices sequentially
        party_id_field = "customer_id" if payment.payment_type == "receivable" else "vendor_id"
        unpaid_docs = list(db[coll_name].find(
            {party_id_field: payment.ref_id, "status": {"$ne": "paid"}, "is_deleted": False}
        ).sort("date", 1))
        
        remaining_amount = payment.amount
        for doc in unpaid_docs:
            if remaining_amount <= 0:
                break
            pay_this_time = min(remaining_amount, doc["balance"])
            remaining_amount -= pay_this_time
            
            new_paid = doc.get("paid_amount", 0.0) + pay_this_time
            new_bal = doc["amount"] - new_paid
            new_status = "paid" if new_bal <= 0 else ("partial" if new_paid > 0 else "unpaid")
            
            db[coll_name].update_one(
                {"_id": doc["_id"]},
                {"$set": {"paid_amount": new_paid, "balance": new_bal, "status": new_status, **_audit_update(current_user["username"])}}
            )
            
    return {"message": "Payment recorded successfully"}


# ==================== Notes Management ====================
@router.post("/notes", status_code=201)
def create_note(note: NoteCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["notes"].find_one({"note_id": note.note_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Note ID already exists.")
    doc = note.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["notes"].insert_one(doc)
    return {"message": "Note created", "note_id": note.note_id}

@router.get("/notes")
def list_notes(type: Optional[str] = None, status: Optional[str] = None, page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if type:
        q["note_type"] = type
    if status:
        q["status"] = status
    total = db["notes"].count_documents(q)
    skip = (page - 1) * limit
    notes = list(db["notes"].find(q).sort("due_date", 1).skip(skip).limit(limit))
    for n in notes:
        n["_id"] = str(n["_id"])
    return {
        "data": notes,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.put("/notes/{note_id}/clear")
def clear_note(note_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    note = db["notes"].find_one({"note_id": note_id, "is_deleted": False})
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    db["notes"].update_one(
        {"note_id": note_id},
        {"$set": {"status": "cleared", "cleared_date": _now(), **_audit_update(current_user["username"])}}
    )
    return {"message": "Note marked as cleared"}

@router.delete("/notes/{note_id}")
def delete_note(note_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["notes"].find_one({"note_id": note_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Note not found")
    db["notes"].update_one({"note_id": note_id}, {"$set": _audit_delete(current_user["username"])})
    return {"message": "Note deleted"}


# ==================== Invoices Management (New) ====================
@router.post("/invoices", status_code=201)
def create_invoice(invoice: InvoiceCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["invoices"].find_one({"invoice_id": invoice.invoice_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Invoice ID already exists.")
    doc = invoice.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["invoices"].insert_one(doc)
    return {"message": "Invoice created", "invoice_id": invoice.invoice_id}

@router.get("/invoices")
def list_invoices(invoice_type: Optional[str] = None, year: Optional[int] = None, month: Optional[int] = None,
                  is_reported: Optional[bool] = None, page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if invoice_type:
        q["invoice_type"] = invoice_type
    if is_reported is not None:
        q["is_reported"] = is_reported
        
    if year or month:
        start_month = month if month else 1
        end_month = month if month else 12
        start_year = year if year else datetime.utcnow().year
        
        # Estimate date boundaries
        start_date = datetime(start_year, start_month, 1, 0, 0, 0, tzinfo=timezone.utc)
        if end_month == 12:
            end_date = datetime(start_year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        else:
            end_date = datetime(start_year, end_month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            
        q["date"] = {"$gte": start_date, "$lt": end_date}
        
    total = db["invoices"].count_documents(q)
    skip = (page - 1) * limit
    invoices = list(db["invoices"].find(q).sort("date", -1).skip(skip).limit(limit))
    for i in invoices:
        i["_id"] = str(i["_id"])
    return {
        "data": invoices,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.put("/invoices/{invoice_id}/report")
def toggle_invoice_report(invoice_id: str, payload: dict, current_user: dict = Depends(get_current_user)):
    db = get_db()
    inv = db["invoices"].find_one({"invoice_id": invoice_id, "is_deleted": False})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    is_reported = payload.get("is_reported", True)
    report_period = payload.get("report_period")
    
    db["invoices"].update_one(
        {"invoice_id": invoice_id},
        {"$set": {"is_reported": is_reported, "report_period": report_period, **_audit_update(current_user["username"])}}
    )
    return {"message": "Invoice report status updated"}


# ==================== Payroll Management ====================
@router.post("/employees", status_code=201)
def create_employee(employee: EmployeeCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["employees"].find_one({"employee_id": employee.employee_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Employee ID already exists.")
    doc = employee.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["employees"].insert_one(doc)
    return {"message": "Employee created"}

@router.get("/employees")
def list_employees(current_user: dict = Depends(get_current_user)):
    db = get_db()
    emps = list(db["employees"].find({"is_deleted": False}))
    for e in emps:
        e["_id"] = str(e["_id"])
    return emps

@router.delete("/employees/{employee_id}")
def delete_employee(employee_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["employees"].find_one({"employee_id": employee_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Employee not found")
    db["employees"].update_one({"employee_id": employee_id}, {"$set": _audit_delete(current_user["username"])})
    return {"message": "Employee deleted"}

@router.post("/payroll", status_code=201)
def create_payroll(record: PayrollRecordCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["payroll"].find_one({"employee_id": record.employee_id, "year": record.year, "month": record.month, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Payroll record for this month already exists")
    doc = record.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["payroll"].insert_one(doc)
    return {"message": "Payroll record created"}

@router.get("/payroll")
def list_payroll(year: int, month: int, current_user: dict = Depends(get_current_user)):
    db = get_db()
    records = list(db["payroll"].find({"year": year, "month": month, "is_deleted": False}))
    for r in records:
        r["_id"] = str(r["_id"])
    return {
        "data": records,
        "total": len(records),
        "page": 1,
        "limit": 30
    }

@router.put("/payroll/{payroll_id}/pay")
def pay_payroll(payroll_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    rec = db["payroll"].find_one({"payroll_id": payroll_id, "is_deleted": False})
    if not rec:
        raise HTTPException(status_code=404, detail="Payroll record not found")
    db["payroll"].update_one(
        {"payroll_id": payroll_id},
        {"$set": {"status": "paid", **_audit_update(current_user["username"])}}
    )
    return {"message": "Paid successfully"}

@router.delete("/payroll/{payroll_id}")
def delete_payroll(payroll_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["payroll"].find_one({"payroll_id": payroll_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Payroll record not found")
    db["payroll"].update_one({"payroll_id": payroll_id}, {"$set": _audit_delete(current_user["username"])})
    return {"message": "Payroll record deleted"}
