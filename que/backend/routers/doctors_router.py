"""
routers/doctors_router.py
--------------------------
(b) DOCTOR SEARCH & DEPARTMENT FILTERING
Also implements dynamic available-slot calculation for a given doctor
and date: (weekly availability window) - (already booked slots).
"""
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

import models
import schemas
from database import get_db

router = APIRouter(tags=["Doctors"])


@router.get("/departments", response_model=List[schemas.DepartmentOut])
def list_departments(db: Session = Depends(get_db)):
    return db.query(models.Department).order_by(models.Department.name).all()


@router.get("/doctors", response_model=List[schemas.DoctorOut])
def search_doctors(
    department_id: Optional[int] = Query(None, description="Filter by department/specialty ID"),
    specialization: Optional[str] = Query(None, description="Free-text search on specialization"),
    name: Optional[str] = Query(None, description="Free-text search on doctor name"),
    db: Session = Depends(get_db),
):
    """
    Patient-facing doctor search. Supports filtering by department,
    free-text specialization, and/or doctor name -- all filters are
    combined with AND when multiple are supplied.
    """
    q = db.query(models.Doctor).join(models.User).join(models.Department)

    if department_id is not None:
        q = q.filter(models.Doctor.department_id == department_id)
    if specialization:
        q = q.filter(models.Doctor.specialization.ilike(f"%{specialization}%"))
    if name:
        q = q.filter(models.User.full_name.ilike(f"%{name}%"))

    doctors = q.all()

    return [
        schemas.DoctorOut(
            doctor_id=d.doctor_id,
            full_name=d.user.full_name,
            department=d.department.name,
            specialization=d.specialization,
            qualification=d.qualification,
            experience_years=d.experience_years or 0,
            consultation_fee=float(d.consultation_fee or 0),
        )
        for d in doctors
    ]


@router.get("/doctors/{doctor_id}/slots", response_model=List[schemas.SlotOut])
def get_doctor_slots(doctor_id: int, on_date: date = Query(..., alias="date"), db: Session = Depends(get_db)):
    """
    Dynamically computes bookable time slots for a doctor on a given
    date:
      1. Look up the doctor's recurring availability window for that
         weekday (day_of_week 0=Mon .. 6=Sun).
      2. Slice the window into fixed-size slots (slot_duration_mins).
      3. Cross-reference existing, non-cancelled appointments for that
         doctor/date and mark overlapping slots as unavailable.
    """
    doctor = db.query(models.Doctor).filter(models.Doctor.doctor_id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    weekday = on_date.weekday()  # Monday=0 ... Sunday=6
    availability = (
        db.query(models.DoctorAvailability)
        .filter(
            models.DoctorAvailability.doctor_id == doctor_id,
            models.DoctorAvailability.day_of_week == weekday,
            models.DoctorAvailability.is_active.is_(True),
        )
        .all()
    )
    if not availability:
        return []  # doctor does not consult on this weekday

    # Existing active bookings for that doctor/date, keyed by start time
    booked_starts = {
        a.slot_start_time
        for a in db.query(models.Appointment).filter(
            models.Appointment.doctor_id == doctor_id,
            models.Appointment.appointment_date == on_date,
            models.Appointment.status.in_(
                [models.AppointmentStatus.BOOKED, models.AppointmentStatus.IN_PROGRESS,
                 models.AppointmentStatus.COMPLETED]
            ),
        )
    }

    slots: List[schemas.SlotOut] = []
    for window in availability:
        cursor = datetime.combine(on_date, window.start_time)
        window_end = datetime.combine(on_date, window.end_time)
        step = timedelta(minutes=window.slot_duration_mins)

        while cursor + step <= window_end:
            slot_start = cursor.time()
            slot_end = (cursor + step).time()
            slots.append(
                schemas.SlotOut(
                    start_time=slot_start,
                    end_time=slot_end,
                    is_available=slot_start not in booked_starts,
                )
            )
            cursor += step

    return slots
