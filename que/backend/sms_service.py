"""
sms_service.py
--------------
Twilio-backed SMS notification service for HAMS.

Responsibilities:
  1. Send SMS when a patient enters the top-N waiting queue position.
  2. Gracefully degrade (log only) when Twilio is not configured or disabled.
  3. Track which notifications have already been sent to avoid spam.
"""
import os
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("hams.sms")

# ── Feature flags ────────────────────────────────────────────────
SMS_ENABLED: bool = os.getenv("SMS_ENABLED", "true").lower() == "true"
TWILIO_ACCOUNT_SID: Optional[str] = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN: Optional[str]  = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER: Optional[str] = os.getenv("TWILIO_PHONE_NUMBER")
TOP_N_THRESHOLD: int = int(os.getenv("SMS_TOP_N_THRESHOLD", "10"))

# Twilio client — lazy-initialised so the app starts even without credentials
_twilio_client = None


def _get_twilio_client():
    """Lazy-init the Twilio REST client. Returns None if not configured."""
    global _twilio_client
    if _twilio_client is not None:
        return _twilio_client

    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN]):
        logger.warning(
            "Twilio credentials not set. SMS notifications will be logged only. "
            "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER in .env"
        )
        return None

    # Twilio Account SIDs must start with "AC" and be at least 32 characters
    if TWILIO_ACCOUNT_SID and len(TWILIO_ACCOUNT_SID) >= 32 and TWILIO_ACCOUNT_SID.startswith("AC"):
        try:
            from twilio.rest import Client
            _twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            logger.info("✅ Twilio SMS client initialised successfully.")
        except Exception as exc:
            logger.error(f"Failed to initialise Twilio client: {exc}")
            _twilio_client = None
    else:
        logger.warning("TWILIO_ACCOUNT_SID in .env is dummy/invalid (must start with 'AC') — SMS operating in Console Log Demo mode.")
        _twilio_client = None
    return _twilio_client


def send_sms(to_phone: str, message: str) -> bool:
    """
    Send an SMS to `to_phone` with `message`.

    Returns True if the message was dispatched (or logged in demo mode),
    False on hard failure.

    Phone numbers must be in E.164 format, e.g. +919876543210.
    """
    if not SMS_ENABLED:
        logger.info(f"[SMS DISABLED] Would send to {to_phone}: {message}")
        return True

    # Ensure E.164 format — normalise Indian 10-digit numbers
    normalised = _normalise_phone(to_phone)
    if not normalised:
        logger.warning(f"Skipping SMS — invalid phone number: {to_phone!r}")
        return False

    client = _get_twilio_client()
    if client is None:
        # Demo / development mode — just log
        logger.info(f"[SMS DEMO MODE] To: {normalised}\n  Message: {message}")
        return True

    try:
        msg = client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=normalised,
        )
        logger.info(f"SMS sent — SID: {msg.sid} | To: {normalised}")
        return True
    except Exception as exc:
        logger.error(f"SMS send failed to {normalised}: {exc}")
        return False


def send_top10_alert(
    patient_name: str,
    patient_phone: str,
    doctor_name: str,
    queue_position: int,
    appointment_date: str,
    slot_time: str,
) -> bool:
    """
    Send the top-10 queue intimation SMS to the patient.
    Called by the background monitor when a patient's position <= TOP_N_THRESHOLD.
    """
    message = (
        f"[PulseCare HAMS] Hi {patient_name}! "
        f"Great news — you are now #{queue_position} in today's queue for "
        f"Dr. {doctor_name} (Appointment: {appointment_date} at {slot_time}). "
        f"Please be ready at the clinic. Reply HELP for support."
    )
    logger.info(
        f"Dispatching Top-{TOP_N_THRESHOLD} SMS → {patient_name} "
        f"(pos #{queue_position}, phone: {patient_phone})"
    )
    return send_sms(patient_phone, message)


def send_booking_confirmation(
    patient_name: str,
    patient_phone: str,
    doctor_name: str,
    department: str,
    appointment_date: str,
    slot_time: str,
    appointment_id: int,
) -> bool:
    """Send a booking confirmation SMS immediately after successful booking."""
    message = (
        f"[PulseCare HAMS] Booking Confirmed! Hi {patient_name}, "
        f"your appointment with Dr. {doctor_name} ({department}) is confirmed "
        f"on {appointment_date} at {slot_time}. "
        f"Appt ID: #{appointment_id}. "
        f"You will receive a reminder when you are in the top {TOP_N_THRESHOLD}. "
        f"— PulseCare HAMS"
    )
    return send_sms(patient_phone, message)


def send_cancellation_notice(
    patient_name: str,
    patient_phone: str,
    doctor_name: str,
    appointment_date: str,
    slot_time: str,
) -> bool:
    """Notify patient their appointment was cancelled."""
    message = (
        f"[PulseCare HAMS] Your appointment with Dr. {doctor_name} on "
        f"{appointment_date} at {slot_time} has been cancelled. "
        f"Hi {patient_name}, book a new slot at any time via PulseCare HAMS."
    )
    return send_sms(patient_phone, message)


# ── Internal helpers ─────────────────────────────────────────────
def _normalise_phone(phone: str) -> Optional[str]:
    """
    Best-effort normalisation to E.164.
    Handles: 9876543210, +919876543210, 919876543210, 0919876543210
    Returns None if the number is clearly invalid.
    """
    if not phone:
        return None

    digits = "".join(c for c in phone if c.isdigit())

    # Already has country code prefix
    if phone.startswith("+"):
        return phone  # trust caller

    # Indian 10-digit number
    if len(digits) == 10 and digits[0] in "6789":
        return f"+91{digits}"

    # Indian number with country code prefix 91
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"

    # Unknown format — return as-is with + prefix and let Twilio validate
    if len(digits) >= 7:
        return f"+{digits}"

    return None
