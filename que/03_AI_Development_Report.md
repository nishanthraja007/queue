# 4. AI Development Report
## Hospital Appointment Management System (HAMS)

---

## 4.1 AI Tools Used

| Tool | Role in This Project |
|---|---|
| **Claude (Anthropic)** — used as an AI pair-programmer / senior engineer assistant | Primary tool for this assignment: generated the requirement analysis (user stories, acceptance criteria), the sequence diagram, the ER schema and SQL DDL, the full FastAPI backend implementation, and this documentation set. |
| **Code execution sandbox** | Used to actually *install dependencies, run the FastAPI server, and fire real HTTP requests* against it (registration, login, search, slot calculation, and a genuine parallel-request race-condition test) — so the deliverable code is verified working, not just "generated and hoped for." |
| **Mermaid.js** (rendering engine, not an AI tool) | Used to render the sequence diagram and ER diagram as version-controllable text-based diagrams embedded directly in the Markdown docs. |

---

## 4.2 Important Prompts & Prompt-Engineering Strategy

Building this as a single well-structured assignment relied on a deliberate prompt strategy rather than one giant "build me the whole system" request. The approach used (and recommended for similar assignments):

1. **Role + full-context framing prompt (used for this entire task):**
   > "Act as a Senior Full-Stack Software Engineer and Technical Writer. [Full problem statement + explicit deliverable list with sub-bullets]."
   This anchors the AI to a consistent persona and gives it the complete rubric up front, so every artifact (docs, diagrams, code) stays consistent with the same domain model (same table names, same status enum, same role names) instead of drifting between sections.

2. **Decompose-by-deliverable, not by conversation turn:** Rather than asking one open-ended question, the underlying request was pre-structured into the same four numbered sections a grader would use (Requirement Analysis → Implementation → Docs → AI Report). This mirrors a well-known prompting technique — **explicit output structuring** — which reduces omission errors on multi-part deliverables.

3. **"Show your constraints, not just your code" prompting for the schema:** Instead of asking for "a database schema," the effective prompt embedded the *business rule* directly — *"including...constraints (to prevent double-booking)"* — which forced the design to go beyond a plain UNIQUE constraint into the partial-index nuance (cancelled rows shouldn't block re-booking). Naming the edge case in the prompt is what surfaces the edge case in the design.

4. **"Sequence diagram for the complete workflow, UI → API → DB → Confirmation" as a scaffold prompt:** specifying the *stages* to cross (UI, API, DB validation, confirmation) rather than just "draw a diagram" ensured the diagram wasn't a shallow happy-path box-and-arrow sketch, but explicitly modeled the DB validation step — which is exactly where the concurrency bug lives.

5. **Verification-driven follow-up (internal, not a literal chat prompt but a working discipline applied while building this):** after generating the FastAPI code, it was **actually executed** — dependencies installed, server booted, and a genuine two-parallel-`curl`-requests race condition fired at the same time slot — rather than trusting that generated concurrency-handling code was correct by inspection alone. This caught a real environment issue (see §4.3 below) before delivery.

---

## 4.3 Challenges Faced & Solutions

### Challenge 1 — Race Condition on Double-Booking (the core hard problem)

**The edge case:** Two patients viewing the same doctor's schedule can both see a slot (e.g., 09:20) as available and click "Book" within milliseconds of each other. If the code only does *"check if the slot is free, then insert,"* both requests can pass the check before either commits — resulting in two active appointments for the same doctor at the same time.

**Solution — defense in depth, not a single check:**
1. **Application-level pre-check** inside the request handler (fast, gives a friendly error in the common non-racing case).
2. **Database-level `UNIQUE(doctor_id, appointment_date, slot_start_time)` constraint** as the *actual* source of truth — the database engine serializes conflicting writes, so even if two requests reach the `INSERT` at the exact same instant, only one can succeed.
3. The second request's `IntegrityError` is caught, the transaction is rolled back cleanly, and the client receives a clear `409 Conflict` — never a silent failure or a corrupted double-booked row.

**How this was verified, not just assumed:** the implementation was run live and two real concurrent `curl` requests were fired at the identical slot using shell `&`/`wait`. Result: exactly one request returned `201 Created`, the other returned `409 Conflict` with the "slot was just booked" message — confirming the guarantee holds under genuine concurrency, not just in single-threaded testing.

**A follow-up edge case this surfaced:** a naive `UNIQUE` constraint on `(doctor_id, date, start_time)` would permanently "burn" a slot the first time it's ever booked — because a `CANCELLED` row still occupies that tuple, blocking any future patient from re-booking it. **Solution:** a **partial/filtered unique index** that only applies to *active* statuses (`BOOKED`, `IN_PROGRESS`, `COMPLETED`), so cancellations correctly free the slot for re-booking while active double-bookings remain impossible. This was verified in the same test run: appointment #1 was cancelled, and the slot's neighbor could still be booked without any constraint violation.

### Challenge 2 — Dynamic Time-Slot Calculation

**The problem:** Slots shouldn't be pre-generated and stored (that data would go stale the moment a doctor changes their hours, and would need constant background jobs to stay in sync). But computing them on-the-fly needs to correctly slice a recurring weekly window into fixed-size increments *and* cross-reference existing bookings — for any date, including ones with irregular ranges (e.g., a 9:00–13:00 window with 20-minute slots doesn't divide evenly into every duration).

**Solution:** `GET /doctors/{id}/slots?date=` looks up the doctor's `DoctorAvailability` row matching that date's weekday, then walks the window in `slot_duration_mins` steps using `datetime` arithmetic, only including a slot if the *full slot* fits before `end_time` (`cursor + step <= window_end`) — preventing a truncated, unusable partial slot from ever being offered. Each generated slot is then checked against a set of already-booked start times (only `BOOKED`/`IN_PROGRESS`/`COMPLETED` statuses count — cancelled appointments correctly do not block the slot) and flagged `is_available` accordingly.

### Challenge 3 — Password Hashing Library Version Conflict (real environment bug caught during verification)

**What happened:** during the actual run of the generated code, server startup crashed with `AttributeError: module 'bcrypt' has no attribute '__about__'`, followed by `ValueError: password cannot be longer than 72 bytes`. This is a known compatibility break between newer `bcrypt` (5.x, which removed an internal `__about__` metadata attribute) and older `passlib` (1.7.4, which reads that attribute during its backend self-test).

**Solution:** pinned `bcrypt==4.0.1` explicitly in `requirements.txt` alongside `passlib==1.7.4`, then re-ran the full test suite of curl requests to confirm registration/login/hashing worked end-to-end. This is called out explicitly in the setup guide so graders don't hit the same wall.

### Challenge 4 — Role-Based Access Without Duplicating Logic Per Endpoint

**The problem:** Patient, Doctor, and Admin share one `users` table and one JWT scheme, but each protected endpoint needs different authorization rules (a doctor must only see/modify their *own* appointments; a patient must only cancel their *own* bookings; only an admin can create departments).

**Solution:** a single `require_role(*roles)` dependency factory in `auth.py` is composed into each router (`Depends(require_role("PATIENT"))`, `Depends(require_role("DOCTOR"))`, etc.), keeping authorization declarative and centrally auditable rather than re-implemented ad hoc in every handler. Ownership checks (e.g., "is this *your* appointment?") are layered on top per-endpoint since they depend on the specific resource, not just the role.

### Challenge 5 — Keeping Documentation and Code From Drifting Apart

**The problem:** in multi-deliverable assignments, it's easy for the ER diagram, the SQL DDL, and the actual ORM models to quietly diverge as each is iterated on separately.

**Solution:** the SQLAlchemy models (`models.py`) were written as a direct 1:1 mirror of `database/schema.sql`, using identical table/column names and constraint semantics, and the Mermaid ER diagram in the design doc was generated from that same table list — so all three artifacts describe one single data model rather than three approximations of it.
