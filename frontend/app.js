/**
 * PulseCare HAMS — Frontend Application Logic
 * Integrates seamlessly with FastAPI REST backend & SQLite database.
 */

const API_BASE = (window.location.protocol.startsWith('http')) 
  ? (window.location.port === '3000' 
      ? `${window.location.protocol}//${window.location.hostname}:8000` 
      : window.location.origin) 
  : "http://127.0.0.1:8000";

class HAMSApp {
  constructor() {
    this.token = localStorage.getItem("hams_token") || null;
    this.currentUser = JSON.parse(localStorage.getItem("hams_user") || "null");
    this.currentView = "browse";
    this.doctors = [];
    this.departments = [];
    this.selectedDoctor = null;
    this.selectedDeptId = null;
    this.selectedSlot = null;
    this.searchQuery = "";

    this.init();
  }

  async init() {
    this.bindEvents();
    this.updateUserUI();
    this.checkBackendHealth();
    await this.loadDepartments();
    await this.loadDoctors();
    
    // Auto-refresh health every 15s
    setInterval(() => this.checkBackendHealth(), 15000);
  }

  bindEvents() {
    // Esc key closes modals
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        document.querySelectorAll(".modal-backdrop.active").forEach((m) => {
          m.classList.remove("active");
        });
      }
    });

    // Close modal on backdrop click
    document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) {
          backdrop.classList.remove("active");
        }
      });
    });
  }

  // -------------------------------------------------------------
  // Backend Health Ping
  // -------------------------------------------------------------
  async checkBackendHealth() {
    const statusPill = document.getElementById("system-status");
    const statusText = document.getElementById("status-text");

    try {
      const res = await fetch(`${API_BASE}/health`, { method: "GET" });
      if (res.ok) {
        statusPill.style.borderColor = "rgba(16, 185, 129, 0.35)";
        statusPill.style.background = "rgba(16, 185, 129, 0.1)";
        statusText.innerHTML = "Connected • <strong>SQLite Active</strong>";
        statusText.style.color = "#34d399";
      } else {
        throw new Error("Degraded");
      }
    } catch (err) {
      statusPill.style.borderColor = "rgba(244, 63, 94, 0.4)";
      statusPill.style.background = "rgba(244, 63, 94, 0.1)";
      statusText.innerHTML = "Connecting to API...";
      statusText.style.color = "#fb7185";
    }
  }

  // -------------------------------------------------------------
  // View Switcher
  // -------------------------------------------------------------
  switchView(viewName) {
    this.currentView = viewName;

    // Update Nav buttons
    document.querySelectorAll(".nav-btn").forEach((btn) => btn.classList.remove("active"));
    const activeNav = document.getElementById(`nav-${viewName}`);
    if (activeNav) activeNav.classList.add("active");

    // Toggle View Sections
    document.querySelectorAll(".view-section").forEach((sec) => sec.classList.remove("active"));
    const targetSection = document.getElementById(`view-${viewName}`);
    if (targetSection) targetSection.classList.add("active");

    // View-specific data fetching
    if (viewName === "browse") {
      this.loadDoctors();
    } else if (viewName === "appointments") {
      this.loadMyAppointments();
    } else if (viewName === "queue") {
      this.loadDoctorQueue();
    } else if (viewName === "admin") {
      this.loadAdminData();
    }
  }

  // -------------------------------------------------------------
  // Authentication & Session Management
  // -------------------------------------------------------------
  updateUserUI() {
    const userBadge = document.getElementById("user-badge");
    const btnOpenLogin = document.getElementById("btn-open-login");
    const avatarEl = document.getElementById("user-avatar");
    const nameEl = document.getElementById("user-display-name");
    const roleEl = document.getElementById("user-display-role");

    if (this.currentUser && this.token) {
      userBadge.style.display = "flex";
      btnOpenLogin.style.display = "none";

      const initials = (this.currentUser.full_name || "U")
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2);

      avatarEl.textContent = initials;
      nameEl.textContent = this.currentUser.full_name || "User";
      roleEl.textContent = this.currentUser.role || "PATIENT";
    } else {
      userBadge.style.display = "none";
      btnOpenLogin.style.display = "inline-flex";
    }
  }

  openAuthModal(tab = "login") {
    this.switchAuthTab(tab);
    document.getElementById("modal-auth").classList.add("active");
  }

  switchAuthTab(tab) {
    const tabLogin = document.getElementById("tab-login");
    const tabRegister = document.getElementById("tab-register");
    const formLogin = document.getElementById("form-login");
    const formRegister = document.getElementById("form-register");

    if (tab === "login") {
      tabLogin.classList.add("active");
      tabRegister.classList.remove("active");
      formLogin.style.display = "block";
      formRegister.style.display = "none";
    } else {
      tabLogin.classList.remove("active");
      tabRegister.classList.add("active");
      formLogin.style.display = "none";
      formRegister.style.display = "block";
    }
  }

  async handleLoginSubmit(event) {
    event.preventDefault();
    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-password").value;

    const btn = document.getElementById("btn-login-submit");
    btn.disabled = true;
    btn.textContent = "Signing In...";

    try {
      const formData = new URLSearchParams();
      formData.append("username", email);
      formData.append("password", password);

      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData.toString(),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Authentication failed");
      }

      this.token = data.access_token;
      localStorage.setItem("hams_token", this.token);

      // Fetch user profile if needed
      await this.fetchCurrentUserProfile(data);

      this.closeModal("modal-auth");
      this.showToast(`Welcome back, ${this.currentUser.full_name}!`, "success");
      this.updateUserUI();

      // Refresh view
      this.switchView(this.currentView);
    } catch (err) {
      this.showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Sign In to HAMS";
    }
  }

  async fetchCurrentUserProfile(tokenData) {
    try {
      const res = await fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${this.token}` },
      });
      if (res.ok) {
        this.currentUser = await res.json();
      } else {
        this.currentUser = {
          user_id: tokenData.user_id,
          role: tokenData.role,
          full_name: tokenData.full_name || tokenData.username || "User",
        };
      }
      localStorage.setItem("hams_user", JSON.stringify(this.currentUser));
    } catch {
      this.currentUser = {
        user_id: tokenData.user_id,
        role: tokenData.role,
        full_name: tokenData.full_name || "User",
      };
      localStorage.setItem("hams_user", JSON.stringify(this.currentUser));
    }
  }

  async handleRegisterSubmit(event) {
    event.preventDefault();
    const btn = document.getElementById("btn-reg-submit");
    btn.disabled = true;
    btn.textContent = "Registering...";

    const payload = {
      full_name: document.getElementById("reg-name").value.trim(),
      email: document.getElementById("reg-email").value.trim(),
      phone: document.getElementById("reg-phone").value.trim(),
      password: document.getElementById("reg-password").value,
      date_of_birth: document.getElementById("reg-dob").value || null,
      gender: document.getElementById("reg-gender").value || null,
    };

    try {
      const res = await fetch(`${API_BASE}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Registration failed");
      }

      this.showToast("Account created successfully! Logging you in...", "success");

      // Auto login
      document.getElementById("login-email").value = payload.email;
      document.getElementById("login-password").value = payload.password;
      this.switchAuthTab("login");
      await this.handleLoginSubmit(new Event("submit"));
    } catch (err) {
      this.showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Create Patient Account";
    }
  }

  // 1-Click Quick Demo Switcher
  async quickLogin(role) {
    let email = "";
    let pass = "";

    if (role === "admin") {
      email = "admin@hams.local";
      pass = "Admin@123";
    } else if (role === "doctor") {
      email = "asha.rao@hams.local";
      pass = "Doctor@123";
    } else if (role === "patient") {
      email = "john@test.com";
      pass = "Pass@123";
    }

    try {
      const formData = new URLSearchParams();
      formData.append("username", email);
      formData.append("password", pass);

      let res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: formData.toString(),
      });

      // If demo patient doesn't exist yet, auto register first
      if (!res.ok && role === "patient") {
        await fetch(`${API_BASE}/auth/register`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            full_name: "John Doe (Patient)",
            email: "john@test.com",
            phone: "9876543210",
            password: "Pass@123",
          }),
        });

        // Retry login
        res = await fetch(`${API_BASE}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: formData.toString(),
        });
      }

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Quick login failed");

      this.token = data.access_token;
      localStorage.setItem("hams_token", this.token);
      await this.fetchCurrentUserProfile(data);

      this.updateUserUI();
      this.showToast(`Switched to ${this.currentUser.full_name} (${this.currentUser.role})`, "info");

      // Automatically switch to the relevant view for this role
      if (role === "doctor") {
        this.switchView("queue");
      } else if (role === "admin") {
        this.switchView("admin");
      } else {
        this.switchView("browse");
      }
    } catch (err) {
      this.showToast(err.message, "error");
    }
  }

  logout() {
    this.token = null;
    this.currentUser = null;
    localStorage.removeItem("hams_token");
    localStorage.removeItem("hams_user");
    this.updateUserUI();
    this.showToast("Signed out successfully", "info");
    this.switchView("browse");
  }

  // -------------------------------------------------------------
  // Browse Doctors & Departments
  // -------------------------------------------------------------
  async loadDepartments() {
    try {
      const res = await fetch(`${API_BASE}/departments`);
      if (res.ok) {
        this.departments = await res.json();
        this.renderDepartmentPills();
        this.populateDeptDropdowns();

        const deptCountEl = document.getElementById("hero-dept-count");
        if (deptCountEl) deptCountEl.textContent = this.departments.length;
      }
    } catch (err) {
      console.error("Failed to load departments:", err);
    }
  }

  renderDepartmentPills() {
    const container = document.getElementById("dept-pills");
    if (!container) return;

    let html = `
      <button class="dept-pill ${this.selectedDeptId === null ? "active" : ""}" 
        onclick="app.filterByDept(null)">All Departments</button>
    `;

    this.departments.forEach((dept) => {
      const activeClass = this.selectedDeptId === dept.department_id ? "active" : "";
      html += `
        <button class="dept-pill ${activeClass}" 
          onclick="app.filterByDept(${dept.department_id})">${dept.name}</button>
      `;
    });

    container.innerHTML = html;
  }

  populateDeptDropdowns() {
    const docNewDept = document.getElementById("doc-new-dept");
    if (docNewDept) {
      docNewDept.innerHTML = this.departments
        .map((d) => `<option value="${d.department_id}">${d.name}</option>`)
        .join("");
    }
  }

  filterByDept(deptId) {
    this.selectedDeptId = deptId;
    this.renderDepartmentPills();
    this.loadDoctors();
  }

  handleSearchInput() {
    this.searchQuery = document.getElementById("filter-search").value.trim();
    clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => {
      this.loadDoctors();
    }, 250);
  }

  async loadDoctors() {
    const container = document.getElementById("doctors-list");
    if (!container) return;

    container.innerHTML = `
      <div class="loading-state">
        <div class="spinner"></div>
        <p>Loading medical specialists...</p>
      </div>
    `;

    try {
      const params = new URLSearchParams();
      if (this.selectedDeptId !== null) params.append("department_id", this.selectedDeptId);
      if (this.searchQuery) params.append("name", this.searchQuery);

      const url = `${API_BASE}/doctors${params.toString() ? "?" + params.toString() : ""}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Failed to load doctors");

      this.doctors = await res.json();
      this.renderDoctorsList();

      const docCountEl = document.getElementById("hero-doc-count");
      if (docCountEl) docCountEl.textContent = this.doctors.length;
    } catch (err) {
      container.innerHTML = `
        <div class="loading-state text-danger">
          <p>⚠️ Could not connect to API or load doctors.</p>
          <button class="btn btn-outline btn-sm mt-3" onclick="app.loadDoctors()">Try Again</button>
        </div>
      `;
    }
  }

  renderDoctorsList() {
    const container = document.getElementById("doctors-list");
    if (!container) return;

    if (this.doctors.length === 0) {
      container.innerHTML = `
        <div class="loading-state">
          <p>No specialists found matching your search criteria.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = this.doctors
      .map((doc) => {
        const initials = doc.full_name
          .replace("Dr. ", "")
          .split(" ")
          .map((n) => n[0])
          .join("")
          .slice(0, 2);

        return `
        <div class="doctor-card" id="doc-card-${doc.doctor_id}">
          <div class="doctor-card-top">
            <div class="doc-avatar">${initials}</div>
            <div class="doc-info">
              <span class="doc-dept-badge">${doc.department}</span>
              <h3 class="doc-name">${doc.full_name}</h3>
              <p class="doc-spec">${doc.specialization}</p>
              <p class="doc-qual">${doc.qualification || "General Practice"}</p>
            </div>
          </div>

          <div class="doctor-card-meta">
            <div class="meta-block">
              <span class="meta-label">Experience</span>
              <span class="meta-val text-cyan">${doc.experience_years} Years</span>
            </div>
            <div class="meta-block">
              <span class="meta-label">Consultation Fee</span>
              <span class="meta-val text-emerald">₹${doc.consultation_fee}</span>
            </div>
          </div>

          <div class="doctor-card-action">
            <button class="btn btn-primary btn-block btn-sm" onclick="app.selectDoctorForBooking(${doc.doctor_id})">
              Check Slots & Book
            </button>
          </div>
        </div>
      `;
      })
      .join("");
  }

  // -------------------------------------------------------------
  // Live Slot Booking & Concurrency Guard
  // -------------------------------------------------------------
  selectDoctorForBooking(doctorId) {
    this.selectedDoctor = this.doctors.find((d) => d.doctor_id === doctorId);
    if (!this.selectedDoctor) return;

    const drawer = document.getElementById("slot-booking-card");
    drawer.style.display = "block";
    drawer.scrollIntoView({ behavior: "smooth", block: "nearest" });

    // Populate drawer header
    document.getElementById("selected-doc-dept").textContent = this.selectedDoctor.department;
    document.getElementById("selected-doc-name").textContent = this.selectedDoctor.full_name;
    document.getElementById("selected-doc-meta").textContent = `${this.selectedDoctor.specialization} • ₹${this.selectedDoctor.consultation_fee} fee`;
    document.getElementById("selected-doc-avatar").textContent = this.selectedDoctor.full_name
      .replace("Dr. ", "")
      .slice(0, 2)
      .toUpperCase();

    // Default date to tomorrow if today is weekend or next business day
    const dateInput = document.getElementById("slot-date-input");
    const today = new Date();
    // Default to today or next weekday
    const dateStr = today.toISOString().split("T")[0];
    dateInput.min = dateStr;
    if (!dateInput.value || dateInput.value < dateStr) {
      dateInput.value = dateStr;
    }

    this.fetchSlotsForSelectedDoctor();
  }

  closeSlotDrawer() {
    const drawer = document.getElementById("slot-booking-card");
    if (drawer) drawer.style.display = "none";
  }

  async fetchSlotsForSelectedDoctor() {
    if (!this.selectedDoctor) return;

    const dateVal = document.getElementById("slot-date-input").value;
    const grid = document.getElementById("slots-grid");
    const weekdayLabel = document.getElementById("slots-weekday-label");

    if (!dateVal) return;

    const chosenDate = new Date(dateVal + "T00:00:00");
    const dayNames = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
    weekdayLabel.textContent = `${dayNames[chosenDate.getDay()]}, ${dateVal}`;

    grid.innerHTML = `
      <div class="loading-state py-4" style="grid-column: 1 / -1;">
        <div class="spinner"></div>
        <p>Calculating live availability windows...</p>
      </div>
    `;

    try {
      const res = await fetch(`${API_BASE}/doctors/${this.selectedDoctor.doctor_id}/slots?date=${dateVal}`);
      if (!res.ok) throw new Error("Could not fetch slots");

      const slots = await res.json();
      if (slots.length === 0) {
        grid.innerHTML = `
          <div class="text-center py-4 text-muted" style="grid-column: 1 / -1;">
            Doctor has no consulting hours scheduled on this weekday. Please select another date.
          </div>
        `;
        return;
      }

      grid.innerHTML = slots
        .map((s) => {
          const startTimeFormatted = s.start_time.slice(0, 5);
          const endTimeFormatted = s.end_time.slice(0, 5);

          if (s.is_available) {
            return `
            <button class="slot-pill" onclick="app.openBookingConfirmModal('${s.start_time}', '${dateVal}')">
              ${startTimeFormatted} - ${endTimeFormatted}
            </button>
          `;
          } else {
            return `
            <button class="slot-pill booked" disabled title="Already reserved">
              ${startTimeFormatted} (Booked)
            </button>
          `;
          }
        })
        .join("");
    } catch (err) {
      grid.innerHTML = `
        <div class="text-center py-4 text-danger" style="grid-column: 1 / -1;">
          Failed to load available slots.
        </div>
      `;
    }
  }

  openBookingConfirmModal(slotStartTime, dateVal) {
    if (!this.token) {
      this.showToast("Please sign in or use 1-Click Patient Demo to book.", "info");
      this.openAuthModal("login");
      return;
    }

    if (this.currentUser && this.currentUser.role !== "PATIENT") {
      this.showToast(`Logged in as ${this.currentUser.role}. Please switch to Patient to book appointments.`, "error");
      return;
    }

    this.selectedSlot = {
      doctor_id: this.selectedDoctor.doctor_id,
      appointment_date: dateVal,
      slot_start_time: slotStartTime,
    };

    document.getElementById("modal-book-doc-name").textContent = this.selectedDoctor.full_name;
    document.getElementById("modal-book-doc-dept").textContent = this.selectedDoctor.department;
    document.getElementById("modal-book-date").textContent = dateVal;
    document.getElementById("modal-book-slot").textContent = slotStartTime.slice(0, 5);
    document.getElementById("modal-book-fee").textContent = `₹${this.selectedDoctor.consultation_fee}`;
    document.getElementById("book-reason-input").value = "";

    document.getElementById("modal-booking").classList.add("active");
  }

  async submitBooking() {
    if (!this.selectedSlot) return;

    const btn = document.getElementById("btn-confirm-booking");
    btn.disabled = true;
    btn.textContent = "Locking Slot...";

    const reason = document.getElementById("book-reason-input").value.trim();

    const payload = {
      doctor_id: this.selectedSlot.doctor_id,
      appointment_date: this.selectedSlot.appointment_date,
      slot_start_time: this.selectedSlot.slot_start_time,
      reason: reason || "General Consultation",
    };

    try {
      const res = await fetch(`${API_BASE}/appointments`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`,
        },
        body: JSON.stringify(payload),
      });

      const data = await res.json();

      if (res.status === 409) {
        // High concurrency catch!
        this.showToast(
          "⚠️ Slot Conflict: This slot was just reserved by another request. Concurrency guard preserved integrity!",
          "error"
        );
        this.closeModal("modal-booking");
        this.fetchSlotsForSelectedDoctor();
        return;
      }

      if (!res.ok) {
        throw new Error(data.detail || "Booking failed");
      }

      this.closeModal("modal-booking");
      this.showToast("🎉 Appointment booked successfully!", "success");

      // Refresh slots
      this.fetchSlotsForSelectedDoctor();

      // Show in My Bookings
      setTimeout(() => {
        this.switchView("appointments");
      }, 500);
    } catch (err) {
      this.showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Confirm & Book Slot";
    }
  }

  // -------------------------------------------------------------
  // Patient View: My Appointments
  // -------------------------------------------------------------
  async loadMyAppointments() {
    const noticeEl = document.getElementById("patient-auth-notice");
    const wrapperEl = document.getElementById("patient-appointments-wrapper");
    const tbody = document.getElementById("patient-appts-body");

    if (!this.token || (this.currentUser && this.currentUser.role !== "PATIENT")) {
      noticeEl.style.display = "block";
      wrapperEl.style.display = "none";
      return;
    }

    noticeEl.style.display = "none";
    wrapperEl.style.display = "block";

    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="text-center py-4">
          <div class="spinner"></div>
          <p class="text-muted mt-3">Loading your bookings...</p>
        </td>
      </tr>
    `;

    try {
      const res = await fetch(`${API_BASE}/appointments/me`, {
        headers: { Authorization: `Bearer ${this.token}` },
      });

      if (!res.ok) throw new Error("Could not fetch appointments");

      const list = await res.json();
      const countBadge = document.getElementById("my-bookings-count");
      if (countBadge) {
        countBadge.style.display = list.length > 0 ? "inline-block" : "none";
        countBadge.textContent = list.length;
      }

      if (list.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="8" class="text-center py-4 text-muted">
              You have no scheduled appointments yet. Find a doctor to book your first consultation!
            </td>
          </tr>
        `;
        return;
      }

      const today = this.formatLocalDate();

      // Calculate Token numbers for patient appointments
      list.forEach((a, idx) => {
        a.tokenNum = idx + 1;
      });

      // Populate Live Patient Token Hero Card
      const heroCard = document.getElementById("patient-token-hero");
      if (list.length > 0 && heroCard) {
        heroCard.style.display = "flex";
        const activeAppt = list.find((a) => a.status === "BOOKED" || a.status === "IN_PROGRESS") || list[0];
        const activeDocName = activeAppt.doctor_name || "Dr. Asha Rao";

        document.getElementById("patient-my-token-num").textContent = `TOKEN #${activeAppt.tokenNum}`;
        document.getElementById("patient-my-token-time").textContent = `Slot: ${activeAppt.slot_start_time.slice(0, 5)}`;

        const inProgressAppt = list.find((a) => a.status === "IN_PROGRESS");
        if (inProgressAppt) {
          document.getElementById("patient-now-token-num").textContent = `TOKEN #${inProgressAppt.tokenNum}`;
          document.getElementById("patient-now-doctor-name").textContent = activeDocName;
        } else {
          document.getElementById("patient-now-token-num").textContent = `TOKEN #—`;
          document.getElementById("patient-now-doctor-name").textContent = `${activeDocName} (Room Available)`;
        }

        const statusTextEl = document.getElementById("patient-queue-status-text");
        const estTextEl = document.getElementById("patient-queue-est-text");

        if (activeAppt.status === "IN_PROGRESS") {
          statusTextEl.className = "p-token-status-text text-emerald";
          statusTextEl.textContent = "⚡ You are NOW consulting with doctor!";
          estTextEl.textContent = "Inside consultation room";
        } else if (inProgressAppt && activeAppt.tokenNum === inProgressAppt.tokenNum + 1) {
          statusTextEl.className = "p-token-status-text text-amber";
          statusTextEl.textContent = "🚨 You're NEXT! Please stand by at door.";
          estTextEl.textContent = "1 Patient ahead of you";
        } else {
          statusTextEl.className = "p-token-status-text text-cyan";
          statusTextEl.textContent = "⏳ Scheduled & Ready in Queue";
          estTextEl.textContent = "Please arrive 10 mins before slot time";
        }
      }

      tbody.innerHTML = list
        .map((a, idx) => {
          const tokenNum = idx + 1;
          const docName = a.doctor_name || `Doctor #${a.doctor_id}`;
          const deptName = a.department_name || "General";
          const slotDisplay = `${a.slot_start_time.slice(0, 5)} - ${a.slot_end_time.slice(0, 5)}`;
          const statusClass = a.status.toLowerCase();
          const isToday = a.appointment_date === today;
          const isBooked = a.status === "BOOKED" || a.status === "IN_PROGRESS";
          const canCancel = a.status === "BOOKED";

          // Queue position badge (only for today's active appointments)
          const queueBadge = isToday && isBooked
            ? `<span id="queue-pos-${a.appointment_id}" class="queue-badge loading" title="Click to refresh position" onclick="app.checkQueuePosition(${a.appointment_id})">
                <span class="queue-spinner"></span> Queue…
              </span>`
            : `<span class="text-muted">—</span>`;

          return `
          <tr class="${a.status === 'IN_PROGRESS' ? 'row-in-progress' : ''}">
            <td><span class="token-cell-badge ${a.status === 'IN_PROGRESS' ? 'in-progress' : ''}">Token #${tokenNum}</span></td>
            <td class="font-bold">#${a.appointment_id}</td>
            <td><strong>${docName}</strong></td>
            <td><span class="doc-dept-badge">${deptName}</span></td>
            <td>${a.appointment_date}</td>
            <td class="text-cyan font-bold">${slotDisplay}</td>
            <td>${a.reason || "—"}</td>
            <td><span class="status-badge ${statusClass}">${a.status}</span></td>
            <td>
              ${
                canCancel
                  ? `<button class="btn btn-danger btn-sm" onclick="app.cancelAppointment(${a.appointment_id})">Cancel</button>`
                  : `<span class="text-muted">—</span>`
              }
            </td>
          </tr>
        `;
        })
        .join("");

      // Auto-fetch queue positions for today's booked appointments
      const todaysBooked = list.filter(
        (a) => a.appointment_date === today && (a.status === "BOOKED" || a.status === "IN_PROGRESS")
      );
      todaysBooked.forEach((a) => this.checkQueuePosition(a.appointment_id));

    } catch (err) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" class="text-center py-4 text-danger">Failed to load appointments.</td>
        </tr>
      `;
    }
  }


  async cancelAppointment(appointmentId) {
    if (!confirm("Are you sure you want to cancel this appointment?")) return;

    try {
      const res = await fetch(`${API_BASE}/appointments/${appointmentId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${this.token}` },
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Cancellation failed");

      this.showToast("Appointment cancelled successfully.", "info");
      this.loadMyAppointments();
    } catch (err) {
      this.showToast(err.message, "error");
    }
  }

  // -------------------------------------------------------------
  // Real-Time Queue Position (SMS top-10 notification system)
  // -------------------------------------------------------------
  async checkQueuePosition(appointmentId) {
    const badge = document.getElementById(`queue-pos-${appointmentId}`);
    if (!badge) return;

    // Set loading state
    badge.className = "queue-badge loading";
    badge.innerHTML = `<span class="queue-spinner"></span> Queue…`;

    try {
      const res = await fetch(
        `${API_BASE}/appointments/queue-position?appointment_id=${appointmentId}`,
        { headers: { Authorization: `Bearer ${this.token}` } }
      );
      const data = await res.json();

      if (!res.ok || data.queue_position === null) {
        badge.className = "queue-badge inactive";
        badge.innerHTML = `<span class="queue-icon">📅</span> ${data.message || "N/A"}`;
        return;
      }

      const pos = data.queue_position;
      const total = data.total_in_queue;
      const isTopN = data.is_top_n;
      const threshold = data.top_n_threshold;

      if (pos === 1) {
        badge.className = "queue-badge urgent";
        badge.innerHTML = `<span class="queue-icon">🚨</span> #${pos} — You're NEXT!`;
      } else if (isTopN) {
        badge.className = "queue-badge top-n";
        badge.innerHTML = `<span class="queue-icon">🔔</span> #${pos} of ${total} — Top ${threshold}! SMS sent`;
      } else {
        badge.className = "queue-badge waiting";
        badge.innerHTML = `<span class="queue-icon">⏳</span> #${pos} of ${total} in queue`;
      }

      // Allow clicking to manually refresh
      badge.title = `Click to refresh. SMS will be sent when you reach top ${threshold}.`;
    } catch (err) {
      badge.className = "queue-badge inactive";
      badge.innerHTML = `<span class="queue-icon">⚠️</span> Retry`;
    }
  }

  // -------------------------------------------------------------
  // Doctor View: Daily Queue & Status Updates
  // -------------------------------------------------------------
  formatLocalDate(d = new Date()) {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  getOrdinalSuffix(n) {
    const s = ["th", "st", "nd", "rd"];
    const v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }

  getPatientQueueNotice(patientTokenNum, consultingTokenNum) {
    const activeNum = consultingTokenNum || 0;
    if (patientTokenNum === activeNum) {
      return {
        statusText: "⚡ You are NOW consulting with doctor!",
        subText: "Inside consultation room",
        badgeText: "NOW CONSULTING",
        class: "text-emerald"
      };
    }
    if (activeNum > 0 && patientTokenNum < activeNum) {
      return {
        statusText: "✅ Consultation Completed",
        subText: "Thank you for visiting PulseCare",
        badgeText: "COMPLETED",
        class: "text-subtle"
      };
    }

    const diff = activeNum > 0 ? (patientTokenNum - activeNum) : patientTokenNum;

    if (diff === 1) {
      return {
        statusText: "🚨 You are NEXT (1st in line)!",
        subText: "Please stand by at consultation room door",
        badgeText: "NEXT IN LINE",
        class: "text-amber"
      };
    }

    const ordinal = this.getOrdinalSuffix(diff);
    return {
      statusText: `⏳ You are ${ordinal} NEXT`,
      subText: `${diff} Patients ahead in queue`,
      badgeText: `${ordinal} NEXT`,
      class: "text-cyan"
    };
  }

  async loadDoctorQueue() {
    const noticeEl = document.getElementById("doctor-auth-notice");
    const wrapperEl = document.getElementById("doctor-queue-wrapper");
    const tbody = document.getElementById("doctor-queue-body");
    const dateInput = document.getElementById("queue-date-input");

    if (!this.token || (this.currentUser && this.currentUser.role !== "DOCTOR" && this.currentUser.role !== "ADMIN")) {
      noticeEl.style.display = "block";
      wrapperEl.style.display = "none";
      return;
    }

    noticeEl.style.display = "none";
    wrapperEl.style.display = "block";

    let selectedDate = dateInput.value;

    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="text-center py-4">
          <div class="spinner"></div>
          <p class="text-muted mt-3">Loading consultation queue...</p>
        </td>
      </tr>
    `;

    try {
      const url = selectedDate 
        ? `${API_BASE}/appointments/doctor/queue?date=${selectedDate}`
        : `${API_BASE}/appointments/doctor/queue`;

      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${this.token}` },
      });

      if (!res.ok) {
        let msg = "Could not load queue";
        try {
          const errObj = await res.json();
          msg = errObj.detail || msg;
        } catch (e) {}
        throw new Error(msg);
      }

      const queue = await res.json();

      // Update date picker input to match the date of appointments returned
      if (queue.length > 0 && queue[0].appointment_date) {
        dateInput.value = queue[0].appointment_date;
      } else if (!dateInput.value) {
        dateInput.value = this.formatLocalDate();
      }

      selectedDate = dateInput.value;

      // Calculate Token Numbers and identify Active Consulting / Next up
      let activeConsulting = null;
      let nextUp = null;
      let booked = 0, inprogress = 0, completed = 0;

      queue.forEach((q, idx) => {
        q.tokenNum = idx + 1;
        if (q.status === "BOOKED" || q.status === "WAITING") booked++;
        if (q.status === "IN_PROGRESS") inprogress++;
        if (q.status === "COMPLETED") completed++;

        if (!activeConsulting && q.status === "IN_PROGRESS") {
          activeConsulting = q;
        }
        if (!nextUp && (q.status === "BOOKED" || q.status === "WAITING")) {
          nextUp = q;
        }
      });

      const countTotal = document.getElementById("queue-count-total");
      const countBooked = document.getElementById("queue-count-booked");
      const countProgress = document.getElementById("queue-count-inprogress");
      const countCompleted = document.getElementById("queue-count-completed");

      if (countTotal) countTotal.textContent = queue.length;
      if (countBooked) countBooked.textContent = booked;
      if (countProgress) countProgress.textContent = inprogress;
      if (countCompleted) countCompleted.textContent = completed;

      // Update Doctor Live Token Banner Cards (safely with null checks)
      const nowNumEl = document.getElementById("doc-token-now-num");
      const nowNameEl = document.getElementById("doc-token-now-name");
      const nowSlotEl = document.getElementById("doc-token-now-slot");

      if (nowNumEl) {
        if (activeConsulting) {
          nowNumEl.textContent = `Token #${activeConsulting.tokenNum}`;
          if (nowNameEl) nowNameEl.textContent = activeConsulting.patient_name || `Patient #${activeConsulting.patient_id}`;
          if (nowSlotEl) nowSlotEl.textContent = `Slot: ${activeConsulting.slot_start_time.slice(0, 5)} - ${activeConsulting.slot_end_time.slice(0, 5)}`;
        } else {
          nowNumEl.textContent = "Token #—";
          if (nowNameEl) nowNameEl.textContent = "No Active Consultation";
          if (nowSlotEl) nowSlotEl.textContent = "Room Available";
        }
      }

      const nextNumEl = document.getElementById("doc-token-next-num");
      const nextNameEl = document.getElementById("doc-token-next-name");
      const nextSlotEl = document.getElementById("doc-token-next-slot");

      if (nextNumEl) {
        if (nextUp) {
          nextNumEl.textContent = `Token #${nextUp.tokenNum}`;
          if (nextNameEl) nextNameEl.textContent = nextUp.patient_name || `Patient #${nextUp.patient_id}`;
          if (nextSlotEl) nextSlotEl.textContent = `Slot: ${nextUp.slot_start_time.slice(0, 5)}`;
        } else {
          nextNumEl.textContent = "Token #—";
          if (nextNameEl) nextNameEl.textContent = "No Patient Waiting";
          if (nextSlotEl) nextSlotEl.textContent = "Queue Clear";
        }
      }

      const totNumEl = document.getElementById("doc-token-total-num");
      const statsSubEl = document.getElementById("doc-token-stats-sub");
      if (totNumEl) totNumEl.textContent = queue.length;
      if (statsSubEl) statsSubEl.textContent = `${booked} Waiting • ${completed} Completed`;

      if (queue.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="7" class="text-center py-4 text-muted">
              No consultations scheduled for ${selectedDate}.<br/>
              <small style="opacity: 0.7; margin-top: 6px; display: inline-block;">(Select another date using the date picker above to view scheduled appointments)</small>
            </td>
          </tr>
        `;
        return;
      }

      const consultingTokenNum = activeConsulting ? activeConsulting.tokenNum : 0;

      tbody.innerHTML = queue
        .map((q, idx) => {
          const tokenNum = idx + 1;
          const slotDisplay = `${q.slot_start_time.slice(0, 5)} - ${q.slot_end_time.slice(0, 5)}`;
          const patientName = q.patient_name || `Patient #${q.patient_id}`;
          const patientPhone = q.patient_phone || "—";
          const statusClass = q.status.toLowerCase().replace('_', '-');
          const isConsulting = q.status === "IN_PROGRESS";
          const notice = this.getPatientQueueNotice(tokenNum, consultingTokenNum);

          let badgeSub = notice.badgeText;

          return `
          <tr class="${isConsulting ? 'row-in-progress' : ''}">
            <td>
              <div style="display: flex; flex-direction: column; gap: 2px;">
                <span class="token-cell-badge ${isConsulting ? 'in-progress' : ''}">Token #${tokenNum}</span>
                <span style="font-size: 0.72rem; font-weight: 700; color: ${isConsulting ? '#34d399' : '#06b6d4'}; font-family: var(--font-heading);">${badgeSub}</span>
              </div>
            </td>
            <td class="font-bold text-cyan">${slotDisplay}</td>
            <td><strong>${patientName}</strong></td>
            <td>${patientPhone}</td>
            <td>${q.reason || "Checkup"}</td>
            <td><span class="status-badge ${statusClass}">${q.status}</span></td>
            <td>
              <div class="queue-actions-cell">
                ${q.status === 'BOOKED' ? `
                  <button class="btn btn-outline btn-sm" title="Mark Arrived" onclick="app.updateApptStatus(${q.appointment_id}, 'WAITING')">
                    Arrived
                  </button>
                ` : ''}
                <button class="btn btn-outline btn-sm ${q.status === 'IN_PROGRESS' ? 'active' : ''}" onclick="app.updateApptStatus(${q.appointment_id}, 'IN_PROGRESS')">
                  Start
                </button>
                <button class="btn btn-primary btn-sm ${q.status === 'COMPLETED' ? 'active' : ''}" onclick="app.updateApptStatus(${q.appointment_id}, 'COMPLETED')">
                  Complete
                </button>
                <button class="btn btn-danger btn-sm ${q.status === 'NO_SHOW' ? 'active' : ''}" onclick="app.updateApptStatus(${q.appointment_id}, 'NO_SHOW')">
                  No-Show
                </button>
                <button class="btn btn-outline btn-sm btn-sms" style="border-color: #06b6d4; color: #06b6d4;" title="Send SMS alert to patient" onclick="app.sendManualSms(${q.appointment_id}, '${patientName.replace(/'/g, "\\'")}', '${patientPhone}')">
                  📲 Send SMS
                </button>
              </div>
            </td>
          </tr>
        `;
        })
        .join("");
    } catch (err) {
      console.error("loadDoctorQueue error:", err);
      tbody.innerHTML = `
        <tr>
          <td colspan="7" class="text-center py-4 text-danger">
            Failed to load doctor queue (${err.message}).<br/>
            <button class="btn btn-outline btn-sm mt-2" onclick="app.loadDoctorQueue()">Retry</button>
          </td>
        </tr>
      `;
    }
  }

  async sendManualSms(appointmentId, patientName, patientPhone) {
    try {
      const res = await fetch(`${API_BASE}/appointments/${appointmentId}/send-sms`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`,
        },
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to send SMS");
      }

      const data = await res.json();
      this.showToast(`📲 SMS notification sent to ${patientName} (${patientPhone})!`, "success");
    } catch (err) {
      this.showToast(err.message, "error");
    }
  }

  async updateApptStatus(appointmentId, newStatus) {
    try {
      const res = await fetch(`${API_BASE}/appointments/${appointmentId}/status`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`,
        },
        body: JSON.stringify({ status: newStatus }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Status update failed");
      }

      this.showToast(`Consultation marked as ${newStatus}`, "success");
      this.loadDoctorQueue();
    } catch (err) {
      this.showToast(err.message, "error");
    }
  }

  openAvailabilityModal() {
    document.getElementById("modal-add-avail").classList.add("active");
  }

  async submitDoctorAvailability(event) {
    event.preventDefault();
    const payload = {
      day_of_week: parseInt(document.getElementById("avail-day").value, 10),
      start_time: document.getElementById("avail-start").value,
      end_time: document.getElementById("avail-end").value,
      slot_duration_mins: parseInt(document.getElementById("avail-duration").value, 10),
    };

    try {
      const res = await fetch(`${API_BASE}/doctors/me/availability`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        let errorMsg = "Failed to add availability window";
        try {
          const err = await res.json();
          errorMsg = err.detail || errorMsg;
        } catch (_) {
          errorMsg = `Server error (${res.status})`;
        }
        throw new Error(errorMsg);
      }

      this.closeModal("modal-add-avail");
      this.showToast("Availability window registered successfully!", "success");
    } catch (err) {
      this.showToast(err.message, "error");
    }
  }

  // -------------------------------------------------------------
  // Admin Operations & Reports
  // -------------------------------------------------------------
  async loadAdminData() {
    const noticeEl = document.getElementById("admin-auth-notice");
    const wrapperEl = document.getElementById("admin-dashboard-wrapper");

    if (!this.token || (this.currentUser && this.currentUser.role !== "ADMIN")) {
      noticeEl.style.display = "block";
      wrapperEl.style.display = "none";
      return;
    }

    noticeEl.style.display = "none";
    wrapperEl.style.display = "block";

    // 1. Load operational metrics summary
    try {
      const res = await fetch(`${API_BASE}/admin/reports/summary`, {
        headers: { Authorization: `Bearer ${this.token}` },
      });

      if (res.ok) {
        const data = await res.json();
        document.getElementById("kpi-total-appts").textContent = data.total_appointments || 0;
        document.getElementById("kpi-today-appts").textContent = data.appointments_today || 0;
        document.getElementById("kpi-total-docs").textContent = data.total_doctors || 0;
        document.getElementById("kpi-total-patients").textContent = data.total_patients || 0;

        // Render Distribution Bars
        const barsEl = document.getElementById("admin-status-bars");
        const total = data.total_appointments || 1;
        const breakdown = data.breakdown_by_status || {};

        const statusColors = {
          BOOKED: "linear-gradient(90deg, #0284c7, #06b6d4)",
          IN_PROGRESS: "linear-gradient(90deg, #d97706, #f59e0b)",
          COMPLETED: "linear-gradient(90deg, #059669, #10b981)",
          CANCELLED: "linear-gradient(90deg, #e11d48, #f43f5e)",
          NO_SHOW: "linear-gradient(90deg, #475569, #64748b)",
        };

        barsEl.innerHTML = Object.entries(breakdown)
          .map(([status, count]) => {
            const pct = Math.round((count / total) * 100);
            return `
            <div class="dist-item">
              <div class="dist-meta">
                <span class="font-bold">${status}</span>
                <span class="text-muted">${count} (${pct}%)</span>
              </div>
              <div class="dist-bar-track">
                <div class="dist-bar-fill" style="width: ${pct}%; background: ${
              statusColors[status] || "#06b6d4"
            };"></div>
              </div>
            </div>
          `;
          })
          .join("");
      }
    } catch (err) {
      console.error("Summary fetch error:", err);
    }

    // 2. Load master appointment stream
    const tbody = document.getElementById("admin-appts-body");
    try {
      const res = await fetch(`${API_BASE}/admin/appointments`, {
        headers: { Authorization: `Bearer ${this.token}` },
      });

      if (res.ok) {
        const appts = await res.json();
        if (appts.length === 0) {
          tbody.innerHTML = `
            <tr>
              <td colspan="8" class="text-center py-4 text-muted">No appointments recorded yet.</td>
            </tr>
          `;
        } else {
          tbody.innerHTML = appts
            .map((a) => {
              const statusClass = a.status.toLowerCase();
              return `
              <tr>
                <td class="font-bold">#${a.appointment_id}</td>
                <td><strong>${a.patient_name || `Patient #${a.patient_id}`}</strong></td>
                <td>${a.doctor_name || `Doctor #${a.doctor_id}`}</td>
                <td><span class="doc-dept-badge">${a.department_name || "General"}</span></td>
                <td>${a.appointment_date}</td>
                <td class="text-cyan font-bold">${a.slot_start_time.slice(0, 5)}</td>
                <td>${a.reason || "—"}</td>
                <td><span class="status-badge ${statusClass}">${a.status}</span></td>
              </tr>
            `;
            })
            .join("");
        }
      }
    } catch (err) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" class="text-center py-4 text-danger">Failed to load master appointments.</td>
        </tr>
      `;
    }
  }

  openAddDoctorModal() {
    this.populateDeptDropdowns();
    document.getElementById("modal-add-doctor").classList.add("active");
  }

  async submitNewDoctor(event) {
    event.preventDefault();
    const payload = {
      full_name: document.getElementById("doc-new-name").value.trim(),
      department_id: parseInt(document.getElementById("doc-new-dept").value, 10),
      email: document.getElementById("doc-new-email").value.trim(),
      phone: document.getElementById("doc-new-phone").value.trim(),
      password: document.getElementById("doc-new-password").value,
      specialization: document.getElementById("doc-new-spec").value.trim(),
      qualification: document.getElementById("doc-new-qual").value.trim(),
      experience_years: parseInt(document.getElementById("doc-new-exp").value || "0", 10),
      consultation_fee: parseFloat(document.getElementById("doc-new-fee").value || "0"),
    };

    try {
      const res = await fetch(`${API_BASE}/admin/doctors`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Doctor creation failed");
      }

      this.closeModal("modal-add-doctor");
      this.showToast(`Doctor ${payload.full_name} onboarded successfully!`, "success");
      await this.loadDoctors();
      this.loadAdminData();
    } catch (err) {
      this.showToast(err.message, "error");
    }
  }

  openAddDeptModal() {
    document.getElementById("modal-add-dept").classList.add("active");
  }

  async submitNewDept(event) {
    event.preventDefault();
    const payload = {
      name: document.getElementById("dept-new-name").value.trim(),
      description: document.getElementById("dept-new-desc").value.trim(),
    };

    try {
      const res = await fetch(`${API_BASE}/admin/departments`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${this.token}`,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Department creation failed");
      }

      this.closeModal("modal-add-dept");
      this.showToast(`Department "${payload.name}" created!`, "success");
      await this.loadDepartments();
      this.loadAdminData();
    } catch (err) {
      this.showToast(err.message, "error");
    }
  }

  // -------------------------------------------------------------
  // Modals & Toast Utility
  // -------------------------------------------------------------
  closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove("active");
  }

  showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast ${type}`;

    let icon = "ℹ️";
    if (type === "success") icon = "✅";
    if (type === "error") icon = "⚠️";

    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(10px)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }
}

// Instantiate global app
const app = new HAMSApp();
window.app = app;
