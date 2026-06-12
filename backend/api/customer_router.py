from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from backend.database import get_db
from backend.auth import get_current_user
from backend.domain.customers.models import CustomerCreate, VendorCreate
from datetime import datetime, timezone

router = APIRouter(prefix="/api", tags=["Customers & Vendors"])

def _now():
    return datetime.now(timezone.utc)

def _audit_create(username: str) -> dict:
    return {"created_by": username, "created_at": _now(), "is_deleted": False,
            "updated_by": None, "updated_at": None, "deleted_by": None, "deleted_at": None}

def _audit_update(username: str) -> dict:
    return {"updated_by": username, "updated_at": _now()}

def _audit_delete(username: str) -> dict:
    return {"is_deleted": True, "deleted_by": username, "deleted_at": _now()}

# ==================== Customers CRUD ====================
@router.post("/customers", status_code=201)
def create_customer(customer: CustomerCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["customers"].find_one({"customer_id": customer.customer_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Customer ID already exists.")
    doc = customer.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["customers"].insert_one(doc)
    return {"message": "Customer created", "customer_id": customer.customer_id}

@router.get("/customers")
def list_customers(search: Optional[str] = None, page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if search:
        # Check both customer fields and plate_number in nested vehicles list
        q["$or"] = [
            {"customer_id": {"$regex": search, "$options": "i"}},
            {"name": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"vehicles.plate_number": {"$regex": search, "$options": "i"}}
        ]
    total = db["customers"].count_documents(q)
    skip = (page - 1) * limit
    result = list(db["customers"].find(q).skip(skip).limit(limit))
    for c in result:
        c["_id"] = str(c["_id"])
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.get("/customers/by-plate/{plate_number}")
def get_customer_by_plate(plate_number: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    c = db["customers"].find_one({"vehicles.plate_number": plate_number, "is_deleted": False})
    if not c:
        raise HTTPException(status_code=404, detail="Customer with this plate number not found")
    c["_id"] = str(c["_id"])
    return c

@router.get("/customers/{customer_id}")
def get_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    c = db["customers"].find_one({"customer_id": customer_id, "is_deleted": False})
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    c["_id"] = str(c["_id"])
    return c

@router.put("/customers/{customer_id}")
def update_customer(customer_id: str, customer: CustomerCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["customers"].find_one({"customer_id": customer_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Customer not found")
    data = customer.model_dump()
    data.update(_audit_update(current_user["username"]))
    db["customers"].update_one({"customer_id": customer_id, "is_deleted": False}, {"$set": data})
    return {"message": "Customer updated"}

@router.delete("/customers/{customer_id}")
def delete_customer(customer_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["customers"].find_one({"customer_id": customer_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Customer not found")
    db["customers"].update_one({"customer_id": customer_id}, {"$set": _audit_delete(current_user["username"])})
    return {"message": "Customer deleted"}


# ==================== Vendors CRUD ====================
@router.post("/api/vendors", status_code=201)  # legacy prefix compatible
@router.post("/vendors", status_code=201)
def create_vendor(vendor: VendorCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["vendors"].find_one({"vendor_id": vendor.vendor_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Vendor ID already exists.")
    doc = vendor.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["vendors"].insert_one(doc)
    return {"message": "Vendor created", "vendor_id": vendor.vendor_id}

@router.get("/vendors")
def list_vendors(search: Optional[str] = None, page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if search:
        q["$or"] = [{"vendor_id": {"$regex": search, "$options": "i"}},
                     {"name": {"$regex": search, "$options": "i"}},
                     {"phone": {"$regex": search, "$options": "i"}}]
    total = db["vendors"].count_documents(q)
    skip = (page - 1) * limit
    result = list(db["vendors"].find(q).skip(skip).limit(limit))
    for v in result:
        v["_id"] = str(v["_id"])
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.get("/vendors/{vendor_id}")
def get_vendor(vendor_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    v = db["vendors"].find_one({"vendor_id": vendor_id, "is_deleted": False})
    if not v:
        raise HTTPException(status_code=404, detail="Vendor not found")
    v["_id"] = str(v["_id"])
    return v

@router.put("/vendors/{vendor_id}")
def update_vendor(vendor_id: str, vendor: VendorCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["vendors"].find_one({"vendor_id": vendor_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Vendor not found")
    data = vendor.model_dump()
    data.update(_audit_update(current_user["username"]))
    db["vendors"].update_one({"vendor_id": vendor_id, "is_deleted": False}, {"$set": data})
    return {"message": "Vendor updated"}

@router.delete("/vendors/{vendor_id}")
def delete_vendor(vendor_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["vendors"].find_one({"vendor_id": vendor_id, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Vendor not found")
    db["vendors"].update_one({"vendor_id": vendor_id}, {"$set": _audit_delete(current_user["username"])})
    return {"message": "Vendor deleted"}
