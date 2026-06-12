from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.database import get_db
from backend.auth import get_current_user
from backend.domain.orders.models import AnnouncementBase
from backend.api import auth_router, customer_router, order_router, financial_router, report_router
import os
from datetime import datetime, timezone

app = FastAPI(title="Tire ERP API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers from API presenters
app.include_router(auth_router.router)
app.include_router(customer_router.router)
app.include_router(order_router.router)
app.include_router(financial_router.router)
app.include_router(report_router.router)

# Announcement global routes
@app.get("/api/announcements")
def get_announcement():
    db = get_db()
    ann = db["announcements"].find_one()
    if not ann:
        return {"content": ""}
    return {"content": ann.get("content", "")}

@app.put("/api/announcements")
def update_announcement(payload: AnnouncementBase, current_user: dict = Depends(get_current_user)):
    db = get_db()
    db["announcements"].update_one(
        {},
        {"$set": {"content": payload.content, "updated_by": current_user["username"], "updated_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    return {"message": "Announcement updated"}

# Serve frontend static files
frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend"))

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(frontend_path, "index.html"))

app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
