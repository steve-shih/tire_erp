from fastapi import APIRouter, Depends, HTTPException, Query, Response
from typing import Optional, List
from backend.database import get_db
from backend.auth import get_current_user
from backend.excel_engine import (
    create_sales_order_excel, create_purchase_order_excel, create_quote_excel,
    create_envelope_excel, create_address_label_excel
)
from datetime import datetime, timezone

router = APIRouter(prefix="/api", tags=["Printing & Reports"])

@router.get("/print/sales/{order_id}")
def print_sales_order(order_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    order = db["sales_orders"].find_one({"order_id": order_id, "is_deleted": False})
    if not order:
        raise HTTPException(status_code=404, detail="Sales Order not found")
    excel_bytes = create_sales_order_excel(order)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=SalesOrder_{order_id}.xlsx"}
    )

@router.get("/print/purchases/{order_id}")
def print_purchase_order(order_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    order = db["purchase_orders"].find_one({"purchase_id": order_id, "is_deleted": False})
    if not order:
        raise HTTPException(status_code=404, detail="Purchase Order not found")
    excel_bytes = create_purchase_order_excel(order)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=PurchaseOrder_{order_id}.xlsx"}
    )

@router.get("/print/quotes/{quote_id}")
def print_quote(quote_id: str, current_user: dict = Depends(get_current_user)):
    db = get_db()
    order = db["quotes"].find_one({"quote_id": quote_id, "is_deleted": False})
    if not order:
        raise HTTPException(status_code=404, detail="Quote not found")
    excel_bytes = create_quote_excel(order)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=Quote_{quote_id}.xlsx"}
    )

@router.post("/print/envelopes")
def print_envelopes(party_ids: List[str], is_return: bool = False, current_user: dict = Depends(get_current_user)):
    db = get_db()
    parties = list(db["customers"].find({"customer_id": {"$in": party_ids}}))
    parties += list(db["vendors"].find({"vendor_id": {"$in": party_ids}}))
    if not parties:
        raise HTTPException(status_code=404, detail="No parties found")
    excel_bytes = create_envelope_excel(parties[0], is_return=is_return)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=Envelope.xlsx"}
    )

@router.post("/print/labels")
def print_address_labels(party_ids: List[str], current_user: dict = Depends(get_current_user)):
    db = get_db()
    parties = list(db["customers"].find({"customer_id": {"$in": party_ids}}))
    parties += list(db["vendors"].find({"vendor_id": {"$in": party_ids}}))
    excel_bytes = create_address_label_excel(parties)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=AddressLabels.xlsx"}
    )

@router.get("/reports/profit-loss")
def profit_loss_report(year: Optional[int] = None, month: Optional[int] = None, current_user: dict = Depends(get_current_user)):
    db = get_db()
    date_match = {"is_deleted": False}
    if year:
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        if month:
            start = datetime(year, month, 1, tzinfo=timezone.utc)
            end_month = month + 1 if month < 12 else 1
            end_year = year if month < 12 else year + 1
            end = datetime(end_year, end_month, 1, tzinfo=timezone.utc)
        date_match["date"] = {"$gte": start, "$lt": end}

    sales_pipeline = [
        {"$match": date_match},
        {"$group": {"_id": None, "total_revenue": {"$sum": "$grand_total"}, "order_count": {"$sum": 1}}}
    ]
    sales_result = list(db["sales_orders"].aggregate(sales_pipeline))
    revenue = sales_result[0]["total_revenue"] if sales_result else 0
    order_count = sales_result[0]["order_count"] if sales_result else 0

    purchase_pipeline = [
        {"$match": date_match},
        {"$group": {"_id": None, "total_cost": {"$sum": "$grand_total"}, "purchase_count": {"$sum": 1}}}
    ]
    purchase_result = list(db["purchase_orders"].aggregate(purchase_pipeline))
    cost = purchase_result[0]["total_cost"] if purchase_result else 0
    purchase_count = purchase_result[0]["purchase_count"] if purchase_result else 0

    gross_profit = revenue - cost
    margin = (gross_profit / revenue * 100) if revenue > 0 else 0

    monthly_pipeline = [
        {"$match": date_match},
        {"$group": {"_id": {"$month": "$date"}, "revenue": {"$sum": "$grand_total"}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    monthly_revenue = list(db["sales_orders"].aggregate(monthly_pipeline))
    
    monthly_cost_pipeline = [
        {"$match": date_match},
        {"$group": {"_id": {"$month": "$date"}, "cost": {"$sum": "$grand_total"}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    monthly_cost = list(db["purchase_orders"].aggregate(monthly_cost_pipeline))

    return {
        "year": year, "month": month,
        "total_revenue": revenue,
        "total_cost": cost,
        "gross_profit": gross_profit,
        "margin_percent": round(margin, 2),
        "order_count": order_count,
        "purchase_count": purchase_count,
        "monthly_revenue": monthly_revenue,
        "monthly_cost": monthly_cost
    }

@router.get("/reports/customer-abc")
def customer_abc_report(year: Optional[int] = None, current_user: dict = Depends(get_current_user)):
    db = get_db()
    match = {"is_deleted": False}
    if year:
        match["date"] = {"$gte": datetime(year, 1, 1, tzinfo=timezone.utc),
                         "$lt": datetime(year + 1, 1, 1, tzinfo=timezone.utc)}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$customer_id",
            "customer_name": {"$first": "$customer_name"},
            "total_amount": {"$sum": "$grand_total"},
            "order_count": {"$sum": 1}
        }},
        {"$sort": {"total_amount": -1}}
    ]
    customers = list(db["sales_orders"].aggregate(pipeline))
    total = len(customers)
    for i, c in enumerate(customers):
        if i < total * 0.2:
            c["rating"] = "A"
        elif i < total * 0.5:
            c["rating"] = "B"
        else:
            c["rating"] = "C"
    return customers

@router.get("/reports/vendor-abc")
def vendor_abc_report(year: Optional[int] = None, current_user: dict = Depends(get_current_user)):
    db = get_db()
    match = {"is_deleted": False}
    if year:
        match["date"] = {"$gte": datetime(year, 1, 1, tzinfo=timezone.utc),
                         "$lt": datetime(year + 1, 1, 1, tzinfo=timezone.utc)}
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id": "$vendor_id",
            "vendor_name": {"$first": "$vendor_name"},
            "total_amount": {"$sum": "$grand_total"},
            "purchase_count": {"$sum": 1}
        }},
        {"$sort": {"total_amount": -1}}
    ]
    vendors = list(db["purchase_orders"].aggregate(pipeline))
    total = len(vendors)
    for i, v in enumerate(vendors):
        if i < total * 0.2:
            v["rating"] = "A"
        elif i < total * 0.5:
            v["rating"] = "B"
        else:
            v["rating"] = "C"
    return vendors
