"""
sms_queue_monitor.py
---------------------
Background daemon that polls the database every N seconds and sends
an SMS whenever a BOOKED patient's queue position drops to or below
the configured TOP_N_THRESHOLD for today's consultation queue.

How queue position is calculated:
  - For a given doctor + date, order all active (BOOKED / IN_PROGRESS)
    appointments by slot_start_time ascending.
  - Each patient's position = their 1-based index in that ordered list.
  - When position <= TOP_N_THRESHOLD and we haven't notified yet → SMS.

To prevent duplicate SMS storms:
  - `sms_notified_positions` table tracks which (appointment_id, threshold)
    combinations have already triggered an SMS.

The monitor runs inside an asyncio background task started at FastAPI startup.
"""
import asyncio
import logging
import os
from datetime import date as date_type

from dotenv import load_dotenv

load_dotenv()

from database import SessionLocal
import models
from sms_service import send_top10_alert, TOP_N_THRESHOLD

logger = logging.getLogger("hams.sms_monitor")

POLL_INTERVAL = int(os.getenv("SMS_POLL_INTERVAL_SECONDS", "30"))

# In-memory set of appointment IDs that have already been SMS-notified
# (persisted across runs via sms_notifications table — see below)
_notified_cache: set[int] = set()


def _get_already_notified_ids(db) -> set:
    """Load all previously SMS-notified appointment IDs from DB."""
    try:
        rows = db.query(models.SmsNotification.appointment_id).all()
        return {r[0] for r in rows}
    except Exception:
        return set()


def _mark_notified(db, appointment_id: int, queue_position: int):
    """Record that an SMS was sent for this appointment."""
    try:
        record = models.SmsNotification(
            appointment_id=appointment_id,
            queue_position_at_notification=queue_position,
        )
        db.add(record)
        db.commit()
        _notified_cache.add(appointment_id)
    except Exception as exc:
        logger.error(f"Failed to persist SMS notification record: {exc}")
        db.rollback()


def check_and_notify_queues():
    """
    Core logic: iterate over every (doctor, date) pair that has active
    BOOKED appointments today, compute queue positions, and fire SMS
    for patients newly entering the top-N window.
    """
    db = SessionLocal()
    try:
        today = date_type.today()

        # Load already-notified IDs (populate cache on first run)
        if not _notified_cache:
            _notified_cache.update(_get_already_notified_ids(db))

        # Fetch all BOOKED appointments for today, ordered by doctor + slot time
        active_appts = (
            db.query(models.Appointment)
            .filter(
                models.Appointment.appointment_date == today,
                models.Appointment.status.in_(
                    [models.AppointmentStatus.BOOKED, models.AppointmentStatus.IN_PROGRESS]
                ),
            )
            .order_by(
                models.Appointment.doctor_id,
                models.Appointment.slot_start_time,
            )
            .all()
        )

        if not active_appts:
            return

        # Group by doctor_id to compute per-doctor queue positions
        queues: dict[int, list] = {}
        for appt in active_appts:
            queues.setdefault(appt.doctor_id, []).append(appt)

        notifications_sent = 0

        for doctor_id, queue in queues.items():
            # Queue is already sorted by slot_start_time (ASC) from the query
            # Position 1 = earliest slot (next in line)
            for position, appt in enumerate(queue, start=1):
                # Skip if already notified
                if appt.appointment_id in _notified_cache:
                    continue

                # Only notify when within the top-N threshold
                if position > TOP_N_THRESHOLD:
                    continue

                # Gather patient contact details
                patient_phone = appt.patient_phone
                patient_name = appt.patient_name or f"Patient #{appt.patient_id}"
                doctor_name = appt.doctor_name or f"Doctor #{appt.doctor_id}"
                slot_time = str(appt.slot_start_time)[:5]  # HH:MM
                appt_date = str(appt.appointment_date)

                if not patient_phone:
                    logger.warning(
                        f"Skipping SMS for appointment #{appt.appointment_id}: no phone on record"
                    )
                    _notified_cache.add(appt.appointment_id)  # don't retry
                    continue

                logger.info(
                    f"🔔 Queue Alert: {patient_name} is #{position} for Dr. {doctor_name} "
                    f"on {appt_date} at {slot_time} — sending SMS to {patient_phone}"
                )

                success = send_top10_alert(
                    patient_name=patient_name,
                    patient_phone=patient_phone,
                    doctor_name=doctor_name,
                    queue_position=position,
                    appointment_date=appt_date,
                    slot_time=slot_time,
                )

                if success:
                    _mark_notified(db, appt.appointment_id, position)
                    notifications_sent += 1

        if notifications_sent:
            logger.info(f"SMS monitor cycle complete — {notifications_sent} notification(s) sent.")

    except Exception as exc:
        logger.error(f"SMS queue monitor error: {exc}", exc_info=True)
    finally:
        db.close()


async def sms_monitor_loop():
    """
    Asyncio coroutine that runs the check loop forever.
    Started as a background task in FastAPI's on_startup event.
    """
    logger.info(
        f"📡 SMS Queue Monitor started — polling every {POLL_INTERVAL}s, "
        f"alerting when position ≤ {TOP_N_THRESHOLD}"
    )
    while True:
        try:
            # Run the blocking DB check in a thread pool to not block the event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, check_and_notify_queues)
        except Exception as exc:
            logger.error(f"Unexpected error in SMS monitor loop: {exc}")
        await asyncio.sleep(POLL_INTERVAL)
