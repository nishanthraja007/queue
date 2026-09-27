"""
routers/appointments_router.py
--------------------------------
(c) APPOINTMENT BOOKING WITH CONCURRENCY / OVERLAP CHECK

Race-condition scenario this guards against:
  Two patients (A and B) both open the "9:00 AM slot with Dr. X" screen,
  see it as available, and click "Book" within milliseconds of each
  other. Without protection, both requests could pass an "is it free?"
  SELECT check before either has committed an INSERT, resulting in a
  double-booked slot.

Defense in depth used here:
  1. APPLICATION-LEVEL CHECK: query existing active appointments for
     that doctor/date/time inside the same DB transaction.
  2. DATABASE-LEVEL GUARANTEE: a UNIQUE constraint on
     (doctor_id, appointment_date, slot_start_time) means even if two
     requests race past step 1 simultaneously, the database itself will
     reject the second INSERT with an IntegrityError -- so correctness
     never depends on application logic alone.
  3. We catch that IntegrityError and translate it into a clean
     HTTP 409 Conflict for the client, with a rollback so the session
     is left in a consistent state.
"""
from datetime import date as date_type
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from auth import require_role, get_current_user

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def _slot_end_time(db: Session, doctor_id: int, day_of_week: int, start_time):
    """Look up the doctor's configured slot duration to compute end_time."""
    window = (
        db.query(models.DoctorAvailability)
        .filter(
            models.DoctorAvailability.doctor_id == doctor_id,
            models.DoctorAvailability.day_of_week == day_of_week,
            models.DoctorAvailability.start_time <= start_time,
            models.DoctorAvailability.end_time > start_time,
        )
        .first()
    )
    return window


@router.post("", response_model=schemas.AppointmentOut, status_code=status.HTTP_201_CREATED)
def book_appointment(
    payload: schemas.AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("PATIENT")),
):
    doctor = db.query(models.Doctor).filter(models.Doctor.doctor_id == payload.doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    if payload.appointment_date < date_type.today():
        raise HTTPException(status_code=400, detail="Cannot book an appointment in the past.")

    weekday = payload.appointment_date.weekday()
    window = _slot_end_time(db, payload.doctor_id, weekday, payload.slot_start_time)
    if not window:
        raise HTTPException(
            status_code=400,
            detail="Requested time is outside the doctor's working hours for that day.",
        )

    from datetime import datetime, timedelta
    slot_end = (
        datetime.combine(payload.appointment_date, payload.slot_start_time)
        + timedelta(minutes=window.slot_duration_mins)
    ).time()

    # ---- Step 1: application-level pre-check (fast path, good UX) ----
    clash = (
        db.query(models.Appointment)
        .filter(
            models.Appointment.doctor_id == payload.doctor_id,
            models.Appointment.appointment_date == payload.appointment_date,
            models.Appointment.slot_start_time == payload.slot_start_time,
            models.Appointment.status.in_(
                [models.AppointmentStatus.BOOKED, models.AppointmentStatus.IN_PROGRESS,
                 models.AppointmentStatus.COMPLETED]
            ),
        )
        .first()
    )
    if clash:
        raise HTTPException(status_code=409, detail="This slot was just booked by another patient. Please choose a different slot.")

    appointment = models.Appointment(
        patient_id=current_user.user_id,
        doctor_id=payload.doctor_id,
        appointment_date=payload.appointment_date,
        slot_start_time=payload.slot_start_time,
        slot_end_time=slot_end,
        reason=payload.reason,
        status=models.AppointmentStatus.BOOKED,
    )
    db.add(appointment)

    # ---- Step 2: DB-level guarantee (authoritative, race-proof) ----
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This slot was just booked by another patient. Please choose a different slot.",
        )

    db.refresh(appointment)
    return appointment


@router.get("/me", response_model=List[schemas.AppointmentOut])
def my_appointment_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("PATIENT")),
):
    """Patient: view own appointment history (past + upcoming)."""
    return (
        db.query(models.Appointment)
        .filter(models.Appointment.patient_id == current_user.user_id)
        .order_by(models.Appointment.appointment_date.desc(), models.Appointment.slot_start_time.desc())
        .all()
    )


@router.delete("/{appointment_id}", status_code=status.HTTP_200_OK)
def cancel_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("PATIENT")),
):
    """Patient: cancel their own upcoming appointment."""
    appt = db.query(models.Appointment).filter(models.Appointment.appointment_id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.patient_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="You can only cancel your own appointments.")
    if appt.status != models.AppointmentStatus.BOOKED:
        raise HTTPException(status_code=400, detail=f"Cannot cancel an appointment in '{appt.status.value}' state.")

    appt.status = models.AppointmentStatus.CANCELLED
    db.commit()
    return {"message": "Appointment cancelled successfully.", "appointment_id": appointment_id}


@router.get("/doctor/queue", response_model=List[schemas.AppointmentOut])
def doctor_daily_queue(
    on_date: Optional[date_type] = Query(None, alias="date"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("DOCTOR")),
):
    """Doctor: view today's (or a chosen date's) appointment queue."""
    target_date = on_date or date_type.today()
    return (
        db.query(models.Appointment)
        .filter(
            models.Appointment.doctor_id == current_user.user_id,
            models.Appointment.appointment_date == target_date,
        )
        .order_by(models.Appointment.slot_start_time.asc())
        .all()
    )


@router.patch("/{appointment_id}/status", response_model=schemas.AppointmentOut)
def update_consultation_status(
    appointment_id: int,
    payload: schemas.AppointmentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("DOCTOR")),
):
    """Doctor: update consultation status (Completed / In-Progress / No-Show)."""
    valid_statuses = {"COMPLETED", "IN_PROGRESS", "NO_SHOW"}
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"status must be one of {valid_statuses}")

    appt = db.query(models.Appointment).filter(models.Appointment.appointment_id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.doctor_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="You can only update your own appointments.")

    appt.status = models.AppointmentStatus(payload.status)
    db.commit()
    db.refresh(appt)
    return appt
