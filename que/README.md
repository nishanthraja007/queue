# Hospital Appointment Management System (HAMS)
### Complete Assignment Submission

This package contains a full, verified, end-to-end submission for the Hospital Appointment Management System assignment.

## 📁 What's in this submission

| File / Folder | Deliverable Section | Contents |
|---|---|---|
| `01_Requirement_Analysis_and_Design.md` | **1. Requirement Analysis & Design** | User stories + acceptance criteria (Patient/Doctor/Admin), Mermaid sequence diagram for the booking workflow, ER diagram + relational schema design notes |
| `database/schema.sql` | **1. Database Design** | Full executable SQL DDL: tables, PKs, FKs, data types, constraints — including the double-booking-prevention constraint |
| `backend/` | **2. AI-Assisted Development (MVP)** | Complete, working FastAPI backend — login/auth, doctor search & filtering, appointment booking with concurrency-safe overlap checking, plus doctor/admin endpoints |
| `02_Technical_Documentation.md` | **3. Technical Documentation** | Project overview, technology stack, full installation & setup guide |
| `03_AI_Development_Report.md` | **4. AI Development Report** | AI tools used, prompting strategy, challenges & solutions (race conditions, dynamic slot calc, etc.) |

## ✅ Verification note

The backend in `backend/` is not just generated — it was **installed, run, and tested live** during development, including firing two genuine simultaneous booking requests at the same appointment slot to confirm the double-booking guard holds under real concurrency (documented with actual output in `03_AI_Development_Report.md`, §4.3).

## 🚀 Quick Start

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open **http://127.0.0.1:8000/docs** for the interactive Swagger UI, or see `02_Technical_Documentation.md` for the full setup guide and demo credentials.

## 📖 Recommended reading order

1. `01_Requirement_Analysis_and_Design.md` — understand the *what* and *why*
2. `database/schema.sql` + `backend/` — the *implementation*
3. `02_Technical_Documentation.md` — how to run it yourself
4. `03_AI_Development_Report.md` — how it was built and the edge cases handled
