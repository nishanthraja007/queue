"""
main.py
-------
Hospital Appointment Management System (HAMS) - FastAPI backend entrypoint.

Run with:
    uvicorn main:app --reload

Interactive API docs (Swagger UI) available at:
    http://127.0.0.1:8000/docs
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import time

from dotenv import load_dotenv
load_dotenv()  # Load .env before anything else reads os.getenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import Base, engine, SessionLocal
import models
from auth import hash_password
from routers import auth_router, doctors_router, appointments_router, admin_router
from sms_queue_monitor import sms_monitor_loop

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: startup → run → shutdown."""
    # ── Startup ──────────────────────────────────────────────
    Base.metadata.create_all(bind=engine)
    seed_demo_data()
    # Start the SMS queue monitor as a background asyncio task
    monitor_task = asyncio.create_task(sms_monitor_loop())
    yield
    # ── Shutdown ─────────────────────────────────────────────
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Hospital Appointment Management System API",
    description="Backend API for patient/doctor/admin appointment scheduling.",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the frontend (any origin, for demo purposes) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(doctors_router.router)
app.include_router(appointments_router.router)
app.include_router(admin_router.router)


import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))

@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "Hospital Appointment Management System API"}


@app.get("/", tags=["Frontend"])
def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "ok", "service": "Hospital Appointment Management System API"}


@app.get("/style.css", include_in_schema=False)
def serve_css():
    css_path = os.path.join(FRONTEND_DIR, "style.css")
    if os.path.exists(css_path):
        return FileResponse(css_path, media_type="text/css")
    return {"error": "Not found"}


@app.get("/app.js", include_in_schema=False)
def serve_js():
    js_path = os.path.join(FRONTEND_DIR, "app.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    return {"error": "Not found"}


if os.path.exists(FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="app")



def seed_demo_data():
    """Populates the DB with a couple of departments/doctors/admin on
    first run so the API is immediately testable end-to-end."""
    db = SessionLocal()
    try:
        if db.query(models.Department).count() > 0:
            return  # already seeded

        cardio = models.Department(name="Cardiology", description="Heart & cardiovascular care")
        derma = models.Department(name="Dermatology", description="Skin, hair & nail care")
        db.add_all([cardio, derma])
        db.flush()

        admin_user = models.User(
            full_name="System Admin",
            email="admin@hams.local",
            phone="9999999999",
            password_hash=hash_password("Admin@123"),
            role=models.RoleEnum.ADMIN,
        )
        db.add(admin_user)

        doc_user = models.User(
            full_name="Dr. Asha Rao",
            email="asha.rao@hams.local",
            phone="9000000001",
            password_hash=hash_password("Doctor@123"),
            role=models.RoleEnum.DOCTOR,
        )
        db.add(doc_user)
        db.flush()

        doctor = models.Doctor(
            doctor_id=doc_user.user_id,
            department_id=cardio.department_id,
            specialization="Interventional Cardiology",
            qualification="MD, DM Cardiology",
            experience_years=12,
            consultation_fee=800,
        )
        db.add(doctor)
        db.flush()

        # Dr. Asha Rao consults Mon-Fri, 09:00-13:00, 20-minute slots
        for weekday in range(0, 5):
            db.add(models.DoctorAvailability(
                doctor_id=doctor.doctor_id,
                day_of_week=weekday,
                start_time=time(9, 0),
                end_time=time(13, 0),
                slot_duration_mins=20,
            ))

        db.commit()
        print(">>> Seed data created: admin@hams.local / Admin@123 | asha.rao@hams.local / Doctor@123")
    finally:
        db.close()


# Startup is now handled by the lifespan context manager above.
