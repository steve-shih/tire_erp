from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from backend.database import get_db
from backend.auth import get_current_user
from backend.domain.orders.models import (
    ProductCreate, StockAdjustment, SalesOrderCreate, PurchaseOrderCreate, QuoteCreate
)
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api", tags=["Orders & Products"])

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

def log_action(db, username: str, action: str, entity: str, description: str):
    db["system_logs"].insert_one({
        "username": username,
        "action": action,
        "entity": entity,
        "description": description,
        "timestamp": _now()
    })

# ==================== Products CRUD ====================
@router.post("/products", status_code=201)
def create_product(product: ProductCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["products"].find_one({"product_code": product.product_code, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Product code already exists.")
    doc = product.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["products"].insert_one(doc)
    return {"message": "Product created", "product_code": product.product_code}

@router.get("/products")
def list_products(category: Optional[str] = None, search: Optional[str] = None, page: int = 1, limit: int = 50, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if category:
        q["category"] = category
    if search:
        q["$or"] = [
            {"product_code": {"$regex": search, "$options": "i"}},
            {"brand": {"$regex": search, "$options": "i"}},
            {"spec": {"$regex": search, "$options": "i"}},
            {"pattern": {"$regex": search, "$options": "i"}}
        ]
    total = db["products"].count_documents(q)
    skip = (page - 1) * limit
    result = list(db["products"].find(q).skip(skip).limit(limit))
    for p in result:
        p["_id"] = str(p["_id"])
    return {
        "data": result,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.put("/products/{product_code}")
def update_product(product_code: str, product: ProductCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["products"].find_one({"product_code": product_code, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Product not found")
    data = product.model_dump()
    data.update(_audit_update(current_user["username"]))
    db["products"].update_one({"product_code": product_code, "is_deleted": False}, {"$set": data})
    return {"message": "Product updated"}

@router.delete("/products/{product_code}")
def delete_product(product_code: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if not db["products"].find_one({"product_code": product_code, "is_deleted": False}):
        raise HTTPException(status_code=404, detail="Product not found")
    db["products"].update_one({"product_code": product_code}, {"$set": _audit_delete(current_user["username"])})
    return {"message": "Product deleted"}

@router.post("/products/{product_code}/adjust_stock")
def adjust_stock(product_code: str, adjustment_data: StockAdjustment, current_user: dict = Depends(get_current_user)):
    db = get_db()
    product = db["products"].find_one({"product_code": product_code, "is_deleted": False})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    new_qty = product.get("stock_qty", 0) + adjustment_data.adjustment
    db["products"].update_one(
        {"product_code": product_code, "is_deleted": False},
        {"$set": {"stock_qty": new_qty, **_audit_update(current_user["username"])}}
    )
    
    log_action(db, current_user["username"], "ADJUST_STOCK", "product", 
               f"Adjusted stock for {product_code} by {adjustment_data.adjustment}. Reason: {adjustment_data.reason}. New qty: {new_qty}")
    
    return {"message": "Stock adjusted successfully", "new_qty": new_qty}


# ==================== Sales Orders CRUD ====================
@router.post("/sales", status_code=201)
def create_sales_order(order: SalesOrderCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["sales_orders"].find_one({"order_id": order.order_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Sales Order ID already exists.")
    doc = order.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["sales_orders"].insert_one(doc)
    # Deduct stock
    for item in order.items:
        db["products"].update_one(
            {"product_code": item.product_code, "is_deleted": False},
            {"$inc": {"stock_qty": -item.qty}})
            
    # Auto-create receivable if payment is credit-based
    if order.payment_status in ("應收貨款", "receivable"):
        recv_doc = {
            "receivable_id": _gen_id("RCV"),
            "order_id": order.order_id,
            "date": order.date,
            "customer_id": order.customer_id,
            "customer_name": order.customer_name,
            "plate_number": order.plate_number,
            "amount": order.grand_total,
            "paid_amount": 0.0,
            "balance": order.grand_total,
            "status": "unpaid",
            "due_date": None,
            **_audit_create(current_user["username"])
        }
        db["receivables"].insert_one(recv_doc)
        
    # Auto-create sales invoice (銷項發票) if invoice_number provided
    if order.invoice_number:
        inv_doc = {
            "invoice_id": f"INV-{order.invoice_number}",
            "invoice_number": order.invoice_number,
            "date": order.date,
            "party_id": order.customer_id,
            "party_name": order.customer_name,
            "party_uniform_number": order.customer_uniform_number,
            "invoice_type": "sales",
            "items_summary": ", ".join([f"{i.brand or ''} {i.spec or ''}*{i.qty}" for i in order.items]),
            "qty": sum([i.qty for i in order.items]),
            "price": order.total_amount,
            "amount": order.total_amount,
            "tax": order.tax_amount,
            "grand_total": order.grand_total,
            "payment_method": order.payment_status,
            "is_reported": False,
            "report_period": None,
            "note": order.note,
            **_audit_create(current_user["username"])
        }
        db["invoices"].insert_one(inv_doc)

    log_action(db, current_user["username"], "CREATE", "sales_order", f"Created order {order.order_id}")
    return {"message": "Sales Order created", "order_id": order.order_id}

@router.get("/sales")
def list_sales_orders(department: Optional[str] = None, category: Optional[str] = None,
                      start_date: Optional[str] = None, end_date: Optional[str] = None,
                      page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if department: q["department"] = department
    if category: q["category"] = category
    if start_date or end_date:
        q["date"] = {}
        if start_date: q["date"]["$gte"] = datetime.fromisoformat(start_date)
        if end_date: q["date"]["$lte"] = datetime.fromisoformat(end_date)
    total = db["sales_orders"].count_documents(q)
    skip = (page - 1) * limit
    orders = list(db["sales_orders"].find(q).sort("date", -1).skip(skip).limit(limit))
    for o in orders:
        o["_id"] = str(o["_id"])
    return {
        "data": orders,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.get("/sales/{order_id}")
def get_sales_order(order_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    order = db["sales_orders"].find_one({"order_id": order_id, "is_deleted": False})
    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")
    order["_id"] = str(order["_id"])
    return order


# ==================== Purchase Orders CRUD ====================
@router.post("/purchases", status_code=201)
def create_purchase_order(order: PurchaseOrderCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["purchase_orders"].find_one({"purchase_id": order.purchase_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Purchase Order ID already exists.")
    doc = order.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["purchase_orders"].insert_one(doc)
    # Add stock
    for item in order.items:
        db["products"].update_one(
            {"product_code": item.product_code, "is_deleted": False},
            {"$inc": {"stock_qty": item.qty}})
            
    # Auto-create payable if credit-based
    if order.payment_status in ("應付帳款", "payable"):
        payable_doc = {
            "payable_id": _gen_id("PAY"),
            "purchase_id": order.purchase_id,
            "date": order.date,
            "vendor_id": order.vendor_id,
            "vendor_name": order.vendor_name,
            "invoice_number": order.invoice_number,
            "amount": order.grand_total,
            "paid_amount": 0.0,
            "balance": order.grand_total,
            "status": "unpaid",
            "due_date": None,
            **_audit_create(current_user["username"])
        }
        db["payables"].insert_one(payable_doc)
        
    # Auto-create purchase invoice (進項扣抵) if invoice_number provided
    if order.invoice_number:
        inv_doc = {
            "invoice_id": f"INV-{order.invoice_number}",
            "invoice_number": order.invoice_number,
            "date": order.date,
            "party_id": order.vendor_id,
            "party_name": order.vendor_name,
            "party_uniform_number": order.vendor_uniform_number,
            "invoice_type": "purchase",
            "items_summary": ", ".join([f"{i.brand or ''} {i.spec or ''}*{i.qty}" for i in order.items]),
            "qty": sum([i.qty for i in order.items]),
            "price": order.total_amount,
            "amount": order.total_amount,
            "tax": order.tax_amount,
            "grand_total": order.grand_total,
            "payment_method": order.payment_status,
            "is_reported": False,
            "report_period": None,
            "note": order.note,
            **_audit_create(current_user["username"])
        }
        db["invoices"].insert_one(inv_doc)

    log_action(db, current_user["username"], "CREATE", "purchase_order", f"Created purchase order {order.purchase_id}")
    return {"message": "Purchase Order created", "purchase_id": order.purchase_id}

@router.get("/purchases")
def list_purchases(page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    total = db["purchase_orders"].count_documents(q)
    skip = (page - 1) * limit
    purchases = list(db["purchase_orders"].find(q).sort("date", -1).skip(skip).limit(limit))
    for p in purchases:
        p["_id"] = str(p["_id"])
    return {
        "data": purchases,
        "total": total,
        "page": page,
        "limit": limit
    }


# ==================== Quotes CRUD ====================
@router.post("/quotes", status_code=201)
def create_quote(quote: QuoteCreate, current_user: dict = Depends(get_current_user)):
    db = get_db()
    if db["quotes"].find_one({"quote_id": quote.quote_id, "is_deleted": False}):
        raise HTTPException(status_code=400, detail="Quote ID already exists.")
    doc = quote.model_dump()
    doc.update(_audit_create(current_user["username"]))
    db["quotes"].insert_one(doc)
    log_action(db, current_user["username"], "CREATE", "quote", f"Created quote {quote.quote_id}")
    return {"message": "Quote created", "quote_id": quote.quote_id}

@router.get("/quotes")
def list_quotes(quote_type: Optional[str] = None, page: int = 1, limit: int = 30, current_user: dict = Depends(get_current_user)):
    db = get_db()
    q = {"is_deleted": False}
    if quote_type:
        q["quote_type"] = quote_type
    total = db["quotes"].count_documents(q)
    skip = (page - 1) * limit
    quotes = list(db["quotes"].find(q).sort("date", -1).skip(skip).limit(limit))
    for q_doc in quotes:
        q_doc["_id"] = str(q_doc["_id"])
    return {
        "data": quotes,
        "total": total,
        "page": page,
        "limit": limit
    }

@router.post("/quotes/{quote_id}/convert")
def convert_quote(quote_id: str, payload: dict, current_user: dict = Depends(get_current_user)):
    db = get_db()
    quote = db["quotes"].find_one({"quote_id": quote_id, "is_deleted": False})
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
        
    db["quotes"].update_one({"quote_id": quote_id}, {"$set": {"is_converted": True}})
    
    if quote["quote_type"] == "customer":
        so_doc = {
            "order_id": payload.get("order_id", f"SO-{quote_id}"),
            "department": "truck" if "大車" in quote.get("category", "") else "sedan",
            "category": quote.get("category", "大車店內"),
            "date": _now(),
            "customer_id": quote["party_id"],
            "customer_name": quote["party_name"],
            "customer_phone": quote.get("phone"),
            "customer_uniform_number": quote.get("uniform_number"),
            "customer_address": quote.get("address"),
            "plate_number": quote.get("plate_number"),
            "items": quote["items"],
            "total_amount": quote["total_amount"],
            "tax_amount": quote.get("tax_amount", 0.0),
            "grand_total": quote["grand_total"],
            "payment_status": "應收貨款",
            "invoice_number": None,
            "note": f"Converted from quote {quote_id}",
            **_audit_create(current_user["username"])
        }
        db["sales_orders"].insert_one(so_doc)
        
        # Deduct stock
        for item in quote["items"]:
            db["products"].update_one(
                {"product_code": item["product_code"], "is_deleted": False},
                {"$inc": {"stock_qty": -item["qty"]}}
            )
            
        # Create receivable
        recv_doc = {
            "receivable_id": _gen_id("RCV"),
            "order_id": so_doc["order_id"],
            "date": so_doc["date"],
            "customer_id": so_doc["customer_id"],
            "customer_name": so_doc["customer_name"],
            "plate_number": so_doc["plate_number"],
            "amount": so_doc["grand_total"],
            "paid_amount": 0.0,
            "balance": so_doc["grand_total"],
            "status": "unpaid",
            "due_date": None,
            **_audit_create(current_user["username"])
        }
        db["receivables"].insert_one(recv_doc)
    else:
        po_doc = {
            "purchase_id": payload.get("purchase_id", f"PO-{quote_id}"),
            "date": _now(),
            "vendor_id": quote["party_id"],
            "vendor_name": quote["party_name"],
            "vendor_phone": quote.get("phone"),
            "vendor_uniform_number": quote.get("uniform_number"),
            "vendor_address": quote.get("address"),
            "items": quote["items"],
            "total_amount": quote["total_amount"],
            "tax_amount": quote.get("tax_amount", 0.0),
            "grand_total": quote["grand_total"],
            "payment_status": "應付帳款",
            "invoice_number": None,
            "note": f"Converted from quote {quote_id}",
            **_audit_create(current_user["username"])
        }
        db["purchase_orders"].insert_one(po_doc)
        
        # Add stock
        for item in quote["items"]:
            db["products"].update_one(
                {"product_code": item["product_code"], "is_deleted": False},
                {"$inc": {"stock_qty": item["qty"]}}
            )
            
        # Create payable
        payable_doc = {
            "payable_id": _gen_id("PAY"),
            "purchase_id": po_doc["purchase_id"],
            "date": po_doc["date"],
            "vendor_id": po_doc["vendor_id"],
            "vendor_name": po_doc["vendor_name"],
            "invoice_number": po_doc["invoice_number"],
            "amount": po_doc["grand_total"],
            "paid_amount": 0.0,
            "balance": po_doc["grand_total"],
            "status": "unpaid",
            "due_date": None,
            **_audit_create(current_user["username"])
        }
        db["payables"].insert_one(payable_doc)
        
    return {"message": "Quote converted successfully"}
