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
import sms_service

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

    # ---- Send booking confirmation SMS (fire-and-forget) ----
    try:
        sms_service.send_booking_confirmation(
            patient_name=appointment.patient_name or current_user.full_name,
            patient_phone=appointment.patient_phone or current_user.phone,
            doctor_name=appointment.doctor_name or "",
            department=appointment.department_name or "",
            appointment_date=str(appointment.appointment_date),
            slot_time=str(appointment.slot_start_time)[:5],
            appointment_id=appointment.appointment_id,
        )
    except Exception:
        pass  # SMS failure must never break booking

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

    # Capture details before commit (lazy-load while session still open)
    patient_name = appt.patient_name or ""
    patient_phone = appt.patient_phone or ""
    doctor_name = appt.doctor_name or ""
    appt_date = str(appt.appointment_date)
    slot_time = str(appt.slot_start_time)[:5]

    appt.status = models.AppointmentStatus.CANCELLED
    db.commit()

    # Notify patient of cancellation
    try:
        sms_service.send_cancellation_notice(
            patient_name=patient_name,
            patient_phone=patient_phone,
            doctor_name=doctor_name,
            appointment_date=appt_date,
            slot_time=slot_time,
        )
    except Exception:
        pass

    return {"message": "Appointment cancelled successfully.", "appointment_id": appointment_id}


@router.get("/doctor/queue", response_model=List[schemas.AppointmentOut])
def doctor_daily_queue(
    on_date: Optional[date_type] = Query(None, alias="date"),
    doctor_id: Optional[int] = Query(None, alias="doctor_id"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Doctor / Admin: view doctor's appointment queue for a given date."""
    doc_id = current_user.user_id if current_user.role == models.RoleEnum.DOCTOR else (doctor_id or 2)

    if on_date is not None:
        target_date = on_date
    else:
        today = date_type.today()
        has_today = db.query(models.Appointment).filter(
            models.Appointment.doctor_id == doc_id,
            models.Appointment.appointment_date == today
        ).first()
        if has_today:
            target_date = today
        else:
            latest_appt = db.query(models.Appointment).filter(
                models.Appointment.doctor_id == doc_id
            ).order_by(models.Appointment.appointment_date.desc()).first()
            target_date = latest_appt.appointment_date if latest_appt else today

    return (
        db.query(models.Appointment)
        .filter(
            models.Appointment.doctor_id == doc_id,
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
    current_user: models.User = Depends(get_current_user),
):
    """Doctor / Admin: update consultation status (BOOKED / WAITING / IN_PROGRESS / COMPLETED / NO_SHOW / CANCELLED)."""
    valid_statuses = {"BOOKED", "WAITING", "IN_PROGRESS", "COMPLETED", "NO_SHOW", "CANCELLED"}
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"status must be one of {valid_statuses}")

    appt = db.query(models.Appointment).filter(models.Appointment.appointment_id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if current_user.role == models.RoleEnum.DOCTOR and appt.doctor_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="You can only update your own appointments.")

    appt.status = models.AppointmentStatus(payload.status)
    db.commit()
    db.refresh(appt)
    return appt


@router.post("/{appointment_id}/send-sms")
def send_manual_sms(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Doctor / Admin: manually trigger an SMS notification to the patient."""
    appt = db.query(models.Appointment).filter(models.Appointment.appointment_id == appointment_id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    patient_name = appt.patient_name or "Patient"
    patient_phone = appt.patient_phone

    if not patient_phone:
        raise HTTPException(status_code=400, detail="Patient phone number is not available.")

    sms_text = (
        f"[PulseCare HAMS] Hi {patient_name}, reminder from Dr. {appt.doctor_name or 'your doctor'}: "
        f"Your consultation is scheduled on {appt.appointment_date} at {str(appt.slot_start_time)[:5]}. "
        f"Status: {appt.status.value}. Please be available at clinic."
    )

    success = sms_service.send_sms(patient_phone, sms_text)

    return {
        "status": "success" if success else "logged",
        "appointment_id": appointment_id,
        "patient_name": patient_name,
        "patient_phone": patient_phone,
        "message": sms_text,
    }


@router.get("/queue-position", tags=["Appointments"])
def get_queue_position(
    appointment_id: int = Query(..., description="The appointment ID to look up"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Return the real-time queue position for a BOOKED appointment today.
    Position 1 = next to be seen by the doctor.
    Returns null position if the appointment is not today or not BOOKED.
    """
    from datetime import date as date_type

    appt = db.query(models.Appointment).filter(
        models.Appointment.appointment_id == appointment_id
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Only patients can query their own position (or admin/doctor can query any)
    if current_user.role == models.RoleEnum.PATIENT and appt.patient_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not your appointment")

    today = date_type.today()
    if appt.appointment_date != today:
        return {
            "appointment_id": appointment_id,
            "queue_position": None,
            "message": "Queue position is only available for today's appointments.",
        }

    if appt.status not in [models.AppointmentStatus.BOOKED, models.AppointmentStatus.IN_PROGRESS]:
        return {
            "appointment_id": appointment_id,
            "queue_position": None,
            "message": f"Appointment status is {appt.status.value}.",
        }

    # Fetch all active appointments for the same doctor today, sorted by slot time
    queue = (
        db.query(models.Appointment)
        .filter(
            models.Appointment.doctor_id == appt.doctor_id,
            models.Appointment.appointment_date == today,
            models.Appointment.status.in_([
                models.AppointmentStatus.BOOKED,
                models.AppointmentStatus.IN_PROGRESS,
            ]),
        )
        .order_by(models.Appointment.slot_start_time.asc())
        .all()
    )

    position = next(
        (idx + 1 for idx, a in enumerate(queue) if a.appointment_id == appointment_id),
        None,
    )
    total = len(queue)
    threshold = sms_service.TOP_N_THRESHOLD

    return {
        "appointment_id": appointment_id,
        "queue_position": position,
        "total_in_queue": total,
        "doctor_name": appt.doctor_name,
        "slot_time": str(appt.slot_start_time)[:5],
        "is_top_n": (position is not None and position <= threshold),
        "top_n_threshold": threshold,
        "message": (
            f"You are #{position} of {total} in the queue."
            if position else "Position unavailable."
        ),
    }
