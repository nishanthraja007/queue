"""
routers/admin_router.py
-------------------------
Administrator: manage master data (departments, doctors) and view
basic operational reports. Also includes the doctor-availability
management endpoint (a Doctor function, grouped here with admin for
brevity in this MVP -- in a larger codebase it would live in its own
doctor_router.py).
"""
from datetime import date as date_type
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import BaseModel

import models
import schemas
from database import get_db
from auth import require_role, hash_password, get_current_user

router = APIRouter(tags=["Admin"])


class DepartmentCreate(BaseModel):
    name: str
    description: str = ""


class DoctorCreate(BaseModel):
    full_name: str
    email: str
    phone: str
    password: str
    department_id: int
    specialization: str
    qualification: str = ""
    experience_years: int = 0
    consultation_fee: float = 0.0


class AvailabilityCreate(BaseModel):
    day_of_week: int  # 0=Mon ... 6=Sun
    start_time: str   # "09:00"
    end_time: str      # "13:00"
    slot_duration_mins: int = 15


# ---------------- Departments ----------------
@router.post("/admin/departments", response_model=schemas.DepartmentOut, status_code=status.HTTP_201_CREATED)
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db),
                       _admin: models.User = Depends(require_role("ADMIN"))):
    if db.query(models.Department).filter(models.Department.name == payload.name).first():
        raise HTTPException(status_code=400, detail="Department already exists.")
    dept = models.Department(name=payload.name, description=payload.description)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept


# ---------------- Doctors (admin provisions doctor accounts) ----------------
@router.post("/admin/doctors", response_model=schemas.DoctorOut, status_code=status.HTTP_201_CREATED)
def create_doctor(payload: DoctorCreate, db: Session = Depends(get_db),
                   _admin: models.User = Depends(require_role("ADMIN"))):
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already in use.")
    dept = db.query(models.Department).filter(models.Department.department_id == payload.department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found.")

    user = models.User(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        role=models.RoleEnum.DOCTOR,
    )
    db.add(user)
    db.flush()

    doctor = models.Doctor(
        doctor_id=user.user_id,
        department_id=payload.department_id,
        specialization=payload.specialization,
        qualification=payload.qualification,
        experience_years=payload.experience_years,
        consultation_fee=payload.consultation_fee,
    )
    db.add(doctor)
    db.commit()
    db.refresh(doctor)

    return schemas.DoctorOut(
        doctor_id=doctor.doctor_id,
        full_name=user.full_name,
        department=dept.name,
        specialization=doctor.specialization,
        qualification=doctor.qualification,
        experience_years=doctor.experience_years,
        consultation_fee=float(doctor.consultation_fee),
    )


@router.get("/admin/reports/summary")
def operational_summary(db: Session = Depends(get_db), _admin: models.User = Depends(require_role("ADMIN"))):
    """Simple operational report: counts by status, today's load, etc."""
    total_appts = db.query(models.Appointment).count()
    today_appts = db.query(models.Appointment).filter(models.Appointment.appointment_date == date_type.today()).count()
    by_status = {}
    for s in models.AppointmentStatus:
        by_status[s.value] = db.query(models.Appointment).filter(models.Appointment.status == s).count()

    return {
        "total_appointments": total_appts,
        "appointments_today": today_appts,
        "breakdown_by_status": by_status,
        "total_doctors": db.query(models.Doctor).count(),
        "total_patients": db.query(models.Patient).count(),
        "total_departments": db.query(models.Department).count(),
    }


@router.get("/admin/appointments", response_model=List[schemas.AppointmentOut])
def list_all_appointments(db: Session = Depends(get_db), _admin: models.User = Depends(require_role("ADMIN"))):
    """Administrator view: full list of hospital appointments ordered by date/time."""
    return (
        db.query(models.Appointment)
        .order_by(models.Appointment.appointment_date.desc(), models.Appointment.slot_start_time.desc())
        .all()
    )



# ---------------- Doctor: manage own availability ----------------
@router.post("/doctors/me/availability", status_code=status.HTTP_201_CREATED)
def set_availability(
    payload: AvailabilityCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from datetime import time as time_type
    try:
        parts = payload.start_time.split(":")
        start_h, start_m = int(parts[0]), int(parts[1])
        parts_end = payload.end_time.split(":")
        end_h, end_m = int(parts_end[0]), int(parts_end[1])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM format.")

    doc_id = current_user.user_id if current_user.role == models.RoleEnum.DOCTOR else 2

    availability = models.DoctorAvailability(
        doctor_id=doc_id,
        day_of_week=payload.day_of_week,
        start_time=time_type(start_h, start_m),
        end_time=time_type(end_h, end_m),
        slot_duration_mins=payload.slot_duration_mins,
    )
    db.add(availability)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An availability window for this day and time range already exists.",
        )

    return {"message": "Availability window added.", "availability_id": availability.availability_id}
