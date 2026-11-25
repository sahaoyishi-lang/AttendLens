/**
 * AttendLens - Intelligent Student Attendance Tracking & Paper-to-Digital OCR System
 * Client-side Single Page Application Controller
 * 100% Open-Source (Vanilla ES6+, Chart.js, Lucide Icons)
 */

let currentUser = null;
let currentScanData = null;
let activeBleToken = null;
let bleTimerInterval = null;
let subjectBarChartInstance = null;
let shortageDoughnutChartInstance = null;
let deferredPrompt = null;
let customTunnelDebounce = null;

// PWA Service Worker Registration
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/static/sw.js').catch(err => {
      console.warn('Service worker registration failed:', err);
    });
  });
}

// PWA Install prompt listener
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  const installBtn = document.getElementById('pwa-install-btn');
  if (installBtn) {
    installBtn.classList.remove('hidden');
    installBtn.onclick = async () => {
      installBtn.classList.add('hidden');
      deferredPrompt.prompt();
      await deferredPrompt.userChoice;
      deferredPrompt = null;
    };
  }
});

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", async () => {
  if (window.lucide) {
    lucide.createIcons();
  }

  // Set default date picker to today
  const today = new Date().toISOString().split("T")[0];
  const dateInput = document.getElementById("sheet-date-input");
  if (dateInput) dateInput.value = today;

  // Initial user check
  await fetchCurrentUser();

  // Load Initial Data
  await loadSubjectsDropdowns();
  await loadDashboardKPIs();
  await loadInstitutionConfig();
  await loadLicensesTable();
  await populateBLEStudentSelect();
  await fetchNetworkInfo();
});

// -------------------------------------------------------------
// NAVIGATION & ROLE SWITCHING
// -------------------------------------------------------------

function switchTab(tabId) {
  // Update nav buttons
  document.querySelectorAll(".tab-btn").forEach(btn => {
    if (btn.getAttribute("data-tab") === tabId) {
      btn.classList.add("tab-active");
      btn.classList.remove("text-slate-600");
    } else {
      btn.classList.remove("tab-active");
      btn.classList.add("text-slate-600");
    }
  });

  // Toggle content panels
  document.querySelectorAll(".tab-content").forEach(content => {
    content.classList.add("hidden");
  });

  const activeContent = document.getElementById(`view-${tabId}`);
  if (activeContent) {
    activeContent.classList.remove("hidden");
  }

  // Refresh icons
  if (window.lucide) {
    lucide.createIcons();
  }

  // Trigger tab-specific refresh
  if (tabId === "analytics") {
    loadDashboardKPIs();
  } else if (tabId === "master-data") {
    loadInstitutionConfig();
  } else if (tabId === "ble") {
    fetchNetworkInfo();
    restoreActiveBLESession();
  }
}

async function fetchCurrentUser() {
  try {
    const res = await fetch("/api/auth/me");
    if (res.ok) {
      currentUser = await res.json();
      updateUserUI();
    }
  } catch (e) {
    console.error("Auth check failed:", e);
  }
}

function updateUserUI() {
  if (!currentUser) return;
  const nameEl = document.getElementById("user-name");
  const roleEl = document.getElementById("user-role-badge");
  if (nameEl) nameEl.textContent = currentUser.full_name;
  if (roleEl) {
    roleEl.textContent = currentUser.role;
    roleEl.className = currentUser.role === "admin" 
      ? "block text-[10px] font-bold text-amber-400 uppercase tracking-wider"
      : "block text-[10px] font-bold text-teal-400 uppercase tracking-wider";
  }
}

async function handleDemoSwitch(role) {
  if (role === "student") {
    window.location.href = "/student";
    return;
  }
  try {
    const res = await fetch(`/api/auth/demo-login/${role}`, { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      currentUser = data.user;
      updateUserUI();
      showToast(`Switched role to ${currentUser.full_name} (${currentUser.role})`, "success");
      // Reset select dropdown
      document.getElementById("demo-role-select").value = "";
    }
  } catch (e) {
    showToast("Role switch failed: " + e.message, "error");
  }
}

// -------------------------------------------------------------
// TAB 1: DASHBOARD & ATTENDANCE ANALYTICS
// -------------------------------------------------------------

async function loadSubjectsDropdowns() {
  try {
    const res = await fetch("/api/admin/subjects");
    if (!res.ok) return;
    const subjects = await res.json();

    const selects = ["analytics-subject-select", "sheet-subject-select", "ble-subject-select"];
    selects.forEach(selId => {
      const sel = document.getElementById(selId);
      if (sel) {
        sel.innerHTML = "";
        subjects.forEach(s => {
          const opt = document.createElement("option");
          opt.value = s.id;
          opt.textContent = `${s.code} - ${s.name}`;
          sel.appendChild(opt);
        });
      }
    });

    if (subjects.length > 0) {
      await loadSubjectAnalytics();
    }
  } catch (e) {
    console.error("Failed to load subjects:", e);
  }
}

async function loadDashboardKPIs() {
  try {
    const res = await fetch("/api/analytics/dashboard");
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById("kpi-total-sessions").textContent = data.total_sessions_held;
    document.getElementById("kpi-total-students").textContent = data.total_students;
    document.getElementById("kpi-avg-attendance").textContent = `${data.overall_attendance_rate}%`;
    document.getElementById("kpi-shortage-count").textContent = data.total_students_shortage;

    renderAnalyticsCharts(data);
  } catch (e) {
    console.error("Failed to load dashboard KPIs:", e);
  }
}

function renderAnalyticsCharts(data) {
  // 1. Subject Bar Chart
  const labels = data.subject_summaries.map(s => s.subject_code);
  const values = data.subject_summaries.map(s => s.avg_attendance_percent);

  const ctxBar = document.getElementById("subjectBarChart");
  if (ctxBar) {
    if (subjectBarChartInstance) subjectBarChartInstance.destroy();
    
    subjectBarChartInstance = new Chart(ctxBar, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [{
          label: "Average Attendance %",
          data: values,
          backgroundColor: values.map(v => v >= 75 ? "rgba(13, 148, 136, 0.85)" : "rgba(225, 29, 72, 0.85)"),
          borderColor: values.map(v => v >= 75 ? "#0f766e" : "#be123c"),
          borderWidth: 1.5,
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false }
        },
        scales: {
          y: {
            beginAtZero: true,
            max: 100,
            ticks: { callback: v => v + "%" },
            grid: { color: "#f1f5f9" }
          },
          x: { grid: { display: false } }
        }
      }
    });
  }

  // 2. Safe vs Shortage Doughnut Chart
  const totalStudents = data.total_students || 20;
  const shortageCount = data.total_students_shortage || 0;
  const safeCount = Math.max(0, totalStudents - shortageCount);

  const safePct = Math.round((safeCount / totalStudents) * 100);
  const shortagePct = 100 - safePct;

  document.getElementById("stat-safe-pct").textContent = `${safePct}%`;
  document.getElementById("stat-shortage-pct").textContent = `${shortagePct}%`;

  const ctxDoughnut = document.getElementById("shortageDoughnutChart");
  if (ctxDoughnut) {
    if (shortageDoughnutChartInstance) shortageDoughnutChartInstance.destroy();

    shortageDoughnutChartInstance = new Chart(ctxDoughnut, {
      type: "doughnut",
      data: {
        labels: ["Safe (>=75%)", "Shortage (<75%)"],
        datasets: [{
          data: [safeCount, shortageCount],
          backgroundColor: ["#10b981", "#f43f5e"],
          hoverBackgroundColor: ["#059669", "#e11d48"],
          borderWidth: 2,
          borderColor: "#ffffff"
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "72%",
        plugins: {
          legend: { display: false }
        }
      }
    });
  }
}

async function loadSubjectAnalytics() {
  const sel = document.getElementById("analytics-subject-select");
  if (!sel || !sel.value) return;

  try {
    const res = await fetch(`/api/analytics/subject/${sel.value}`);
    if (!res.ok) return;
    const data = await res.json();

    const tbody = document.getElementById("student-table-body");
    tbody.innerHTML = "";

    data.students.forEach((s, idx) => {
      const isShortage = (s.status === "Shortage" || s.attendance_percent < data.min_threshold);
      const tr = document.createElement("tr");
      tr.className = isShortage ? "bg-rose-50/40 hover:bg-rose-50/80 transition" : "hover:bg-slate-50 transition";

      tr.innerHTML = `
        <td class="py-2.5 px-4 text-slate-400 font-medium">${idx + 1}</td>
        <td class="py-2.5 px-4 font-bold text-slate-800">${s.roll_number}</td>
        <td class="py-2.5 px-4 font-medium text-slate-700">${s.full_name}</td>
        <td class="py-2.5 px-4 text-center text-slate-600">${s.classes_held}</td>
        <td class="py-2.5 px-4 text-center font-semibold text-slate-800">${s.classes_attended}</td>
        <td class="py-2.5 px-4 text-center font-bold ${isShortage ? 'text-rose-600' : 'text-emerald-600'}">
          ${s.attendance_percent}%
        </td>
        <td class="py-2.5 px-4 text-center">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
            isShortage 
              ? 'bg-rose-100 text-rose-800 border border-rose-200' 
              : 'bg-emerald-100 text-emerald-800 border border-emerald-200'
          }">
            ${isShortage ? 'Shortage Alert' : 'Safe'}
          </span>
        </td>
        <td class="py-2.5 px-4 text-center">
          ${s.classes_needed_for_75 > 0 
            ? `<span class="font-bold text-rose-700 bg-rose-100/80 px-2 py-0.5 rounded text-[11px]">${s.classes_needed_for_75} consecutive classes</span>` 
            : `<span class="text-slate-400 font-medium">—</span>`
          }
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Failed to load subject analytics:", e);
  }
}

function filterStudentTable() {
  const query = document.getElementById("student-search-input").value.toLowerCase();
  const rows = document.querySelectorAll("#student-table-body tr");
  rows.forEach(row => {
    const text = row.innerText.toLowerCase();
    row.style.display = text.includes(query) ? "" : "none";
  });
}

function exportShortagePDF() {
  const sel = document.getElementById("analytics-subject-select");
  if (!sel || !sel.value) return;
  window.open(`/api/reports/shortage-pdf/${sel.value}`, "_blank");
}

function exportFullXLSX() {
  const sel = document.getElementById("analytics-subject-select");
  if (!sel || !sel.value) return;
  window.open(`/api/reports/full-xlsx/${sel.value}`, "_blank");
}

// -------------------------------------------------------------
// TAB 2: PRINTABLE ATTENDANCE SHEET GENERATOR
// -------------------------------------------------------------

async function downloadSheet(format) {
  const subjectId = document.getElementById("sheet-subject-select").value;
  const sessionDate = document.getElementById("sheet-date-input").value || new Date().toISOString().split("T")[0];
  const academicYear = document.getElementById("sheet-year-input").value || "2026-2027";
  const semester = document.getElementById("sheet-semester-input").value || "Semester 6";

  const endpoint = format === "pdf" ? "/api/sheets/generate-pdf" : "/api/sheets/generate-xlsx";
  showToast(`Generating ${format.toUpperCase()} attendance sheet...`, "info");

  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        subject_id: parseInt(subjectId),
        session_date: sessionDate,
        academic_year: academicYear,
        semester: semester,
        format: format
      })
    });

    if (!res.ok) throw new Error("Generation failed");

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = format === "pdf" 
      ? `Smart_Attendance_Sheet_${sessionDate}.pdf`
      : `Attendance_Template_${sessionDate}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    showToast(`Smart ${format.toUpperCase()} sheet downloaded successfully!`, "success");
  } catch (e) {
    showToast("Error downloading sheet: " + e.message, "error");
  }
}

// -------------------------------------------------------------
// TAB 3: SCAN & SPLIT-SCREEN OCR VERIFICATION
// -------------------------------------------------------------

async function triggerSampleSheetDemo() {
  showToast("⚡ Generating synthetic filled sheet & running computer vision pipeline...", "info");
  
  const subjectId = document.getElementById("analytics-subject-select")?.value || 1;
  const sessionDate = new Date().toISOString().split("T")[0];

  try {
    const res = await fetch(`/api/ocr/generate-sample-filled?subject_id=${subjectId}&session_date=${sessionDate}`, {
      method: "POST"
    });

    if (!res.ok) throw new Error("Pipeline execution failed");
    const data = await res.json();
    currentScanData = data;
    renderSplitScreenVerification(data);
    showToast("Sheet processed! 4 fiducials aligned & marks segmented.", "success");
  } catch (e) {
    showToast("OCR processing error: " + e.message, "error");
  }
}

async function handleFileUpload(file) {
  if (!file) return;
  showToast(`Uploading and scanning ${file.name}...`, "info");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/ocr/scan", {
      method: "POST",
      body: formData
    });

    if (!res.ok) throw new Error("Image scanning failed");
    const data = await res.json();
    currentScanData = data;
    renderSplitScreenVerification(data);
    showToast("Sheet scanned successfully!", "success");
  } catch (e) {
    showToast("Scan failed: " + e.message, "error");
  }
}

function renderSplitScreenVerification(data) {
  // Hide empty state, unhide workspace
  document.getElementById("ocr-empty-state").classList.add("hidden");
  document.getElementById("ocr-status-bar").classList.remove("hidden");
  document.getElementById("ocr-workspace").classList.remove("hidden");

  // Populate Header Stats
  document.getElementById("scan-subject-tag").textContent = `${data.subject_code} - ${data.subject_name || ''}`;
  document.getElementById("scan-date-tag").textContent = data.session_date;
  document.getElementById("scan-token-tag").textContent = data.session_token;

  document.getElementById("scan-present-badge").textContent = `${data.present_count} Present`;
  document.getElementById("scan-absent-badge").textContent = `${data.absent_count} Absent`;
  document.getElementById("scan-uncertain-badge").textContent = `${data.uncertain_count} Uncertain`;

  // Left Sheet Preview
  const imgEl = document.getElementById("annotated-sheet-img");
  imgEl.src = `data:image/jpeg;base64,${data.annotated_sheet_base64}`;

  // Right Table Rows with Cell Crops and P/A Toggles
  const tbody = document.getElementById("ocr-verification-tbody");
  tbody.innerHTML = "";

  data.cells.forEach((cell, idx) => {
    const tr = document.createElement("tr");
    tr.id = `cell-row-${cell.student_id}`;
    tr.className = cell.is_flagged ? "bg-amber-50/50 hover:bg-amber-50 transition" : "hover:bg-slate-50 transition";

    const badgeColor = cell.detected_status === "P" 
      ? "bg-emerald-100 text-emerald-800 border-emerald-300" 
      : cell.detected_status === "A"
      ? "bg-rose-100 text-rose-800 border-rose-300"
      : "bg-amber-100 text-amber-800 border-amber-300";

    tr.innerHTML = `
      <td class="py-2 px-3 text-slate-400 font-medium">${idx + 1}</td>
      <td class="py-2 px-3">
        <span class="font-bold text-slate-900 block">${cell.roll_number}</span>
        <span class="text-[11px] text-slate-500 block">${cell.student_name}</span>
        ${cell.is_flagged ? `<span class="text-[10px] text-amber-700 font-semibold block mt-0.5">⚠️ ${cell.flag_reason || 'Flagged for review'}</span>` : ''}
      </td>
      <td class="py-2 px-3 text-center">
        <div class="inline-block p-1 bg-white border border-slate-200 rounded shadow-xs">
          <img src="data:image/jpeg;base64,${cell.crop_base64}" alt="Cell crop" class="h-8 w-16 object-cover rounded">
        </div>
      </td>
      <td class="py-2 px-3 text-center">
        <span id="detected-badge-${cell.student_id}" class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border ${badgeColor}">
          ${cell.detected_status} (${Math.round(cell.confidence_score)}%)
        </span>
      </td>
      <td class="py-2 px-3 text-center">
        <div class="inline-flex rounded-lg border border-slate-300 bg-white p-0.5 shadow-2xs">
          <button type="button" onclick="setOverride(${cell.student_id}, 'P')" id="btn-p-${cell.student_id}" class="px-2.5 py-1 text-xs font-bold rounded ${cell.detected_status === 'P' ? 'bg-emerald-600 text-white' : 'text-slate-600 hover:bg-slate-100'}">
            P
          </button>
          <button type="button" onclick="setOverride(${cell.student_id}, 'A')" id="btn-a-${cell.student_id}" class="px-2.5 py-1 text-xs font-bold rounded ${cell.detected_status === 'A' ? 'bg-rose-600 text-white' : 'text-slate-600 hover:bg-slate-100'}">
            A
          </button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });

  if (window.lucide) {
    lucide.createIcons();
  }
}

function setOverride(studentId, newStatus) {
  if (!currentScanData) return;
  const cell = currentScanData.cells.find(c => c.student_id === studentId);
  if (!cell) return;

  cell.override_status = newStatus;

  // Update button highlights
  const btnP = document.getElementById(`btn-p-${studentId}`);
  const btnA = document.getElementById(`btn-a-${studentId}`);
  if (newStatus === "P") {
    btnP.className = "px-2.5 py-1 text-xs font-bold rounded bg-emerald-600 text-white";
    btnA.className = "px-2.5 py-1 text-xs font-bold rounded text-slate-600 hover:bg-slate-100";
  } else {
    btnP.className = "px-2.5 py-1 text-xs font-bold rounded text-slate-600 hover:bg-slate-100";
    btnA.className = "px-2.5 py-1 text-xs font-bold rounded bg-rose-600 text-white";
  }

  // Update badge
  const badge = document.getElementById(`detected-badge-${studentId}`);
  if (badge) {
    badge.textContent = `${newStatus} (Override)`;
    badge.className = newStatus === "P"
      ? "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border bg-emerald-100 text-emerald-800 border-emerald-300"
      : "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border bg-rose-100 text-rose-800 border-rose-300";
  }
}

async function commitVerification() {
  if (!currentScanData) return;

  const overridesList = currentScanData.cells.map(c => ({
    student_id: c.student_id,
    original_status: c.detected_status,
    corrected_status: c.override_status || (c.detected_status === "UNCERTAIN" ? "P" : c.detected_status),
    confidence_score: c.override_status ? 100.0 : c.confidence_score
  }));

  try {
    const res = await fetch("/api/ocr/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_token: currentScanData.session_token,
        subject_id: currentScanData.subject_id,
        session_date: currentScanData.session_date,
        overrides: overridesList
      })
    });

    if (!res.ok) throw new Error("Commit failed");
    const result = await res.json();
    showToast(result.message, "success");
    // Refresh analytics
    await loadDashboardKPIs();
    await loadSubjectAnalytics();
  } catch (e) {
    showToast("Failed to commit attendance: " + e.message, "error");
  }
}

// -------------------------------------------------------------
// WEBCAM LIVE CAPTURE MODAL
// -------------------------------------------------------------

let webcamStream = null;

async function openWebcamModal() {
  const modal = document.getElementById("webcam-modal");
  modal.classList.remove("hidden");
  
  try {
    webcamStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }
    });
    const video = document.getElementById("webcam-video");
    video.srcObject = webcamStream;
  } catch (e) {
    showToast("Could not access camera: " + e.message, "error");
    closeWebcamModal();
  }
}

function closeWebcamModal() {
  if (webcamStream) {
    webcamStream.getTracks().forEach(track => track.stop());
    webcamStream = null;
  }
  document.getElementById("webcam-modal").classList.add("hidden");
}

function captureWebcamFrame() {
  const video = document.getElementById("webcam-video");
  if (!video || !webcamStream) return;

  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth || 1280;
  canvas.height = video.videoHeight || 720;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

  const base64Data = canvas.toDataURL("image/jpeg", 0.9);
  closeWebcamModal();

  // Send to scan endpoint
  showToast("Processing captured camera frame...", "info");
  const formData = new FormData();
  formData.append("image_base64", base64Data);

  fetch("/api/ocr/scan", { method: "POST", body: formData })
    .then(r => r.json())
    .then(data => {
      currentScanData = data;
      renderSplitScreenVerification(data);
      showToast("Webcam frame processed successfully!", "success");
    })
    .catch(err => {
      showToast("Camera frame processing failed: " + err.message, "error");
    });
}

// -------------------------------------------------------------
// TAB 4: HANDS-FREE BLE / PROXIMITY DIGITAL CHECK-IN
// -------------------------------------------------------------

async function fetchNetworkInfo(customUrl = null) {
  try {
    const url = customUrl ? `/api/network-info?custom_url=${encodeURIComponent(customUrl)}` : '/api/network-info';
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();
    
    const qrImg = document.getElementById("ble-qr-img");
    const lanUrl = document.getElementById("ble-lan-url");
    if (qrImg && data.qr_code_base64) {
      qrImg.src = data.qr_code_base64;
    }
    if (lanUrl) {
      lanUrl.href = data.student_url;
      lanUrl.textContent = data.student_url;
    }
  } catch (e) {
    console.error("Network info fetch error:", e);
  }
}

function handleCustomTunnelChange(val) {
  if (customTunnelDebounce) clearTimeout(customTunnelDebounce);
  customTunnelDebounce = setTimeout(() => {
    fetchNetworkInfo(val);
  }, 400);
}

async function populateBLEStudentSelect() {
  try {
    const res = await fetch("/api/admin/students");
    if (!res.ok) return;
    const students = await res.json();
    const sel = document.getElementById("ble-student-select");
    if (!sel) return;

    sel.innerHTML = "";
    students.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s.roll_number;
      opt.textContent = `${s.roll_number} — ${s.full_name}`;
      sel.appendChild(opt);
    });
  } catch (e) {
    console.error("BLE student select population failed:", e);
  }
}

async function restoreActiveBLESession() {
  if (activeBleToken) {
    await pollBLEStatus();
    return;
  }
  try {
    const res = await fetch("/api/ble/teacher-active-session");
    if (!res.ok) return;
    const data = await res.json();
    if (!data.active) return;

    activeBleToken = data.session_token;
    document.getElementById("ble-pin-display").textContent = data.pin_code;
    document.getElementById("ble-pin-input").value = data.pin_code;
    document.getElementById("ble-active-panel").classList.remove("hidden");
    document.getElementById("ble-start-btn").classList.add("hidden");
    document.getElementById("ble-close-btn").classList.remove("hidden");

    startBLETimer(data.remaining_seconds);
    await pollBLEStatus();
  } catch (e) {
    console.error("Failed to restore active BLE session:", e);
  }
}

async function startBLESession() {
  const subjectId = document.getElementById("ble-subject-select").value || 1;

  try {
    const res = await fetch("/api/ble/start-session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subject_id: parseInt(subjectId), duration_minutes: 2 })
    });

    if (!res.ok) throw new Error("Failed to start BLE session");
    const data = await res.json();

    activeBleToken = data.session_token;
    document.getElementById("ble-pin-display").textContent = data.pin_code;
    document.getElementById("ble-pin-input").value = data.pin_code; // autofill for instant demo convenience
    document.getElementById("ble-active-panel").classList.remove("hidden");
    document.getElementById("ble-start-btn").classList.add("hidden");
    document.getElementById("ble-close-btn").classList.remove("hidden");

    // Make sure QR code matches current network URL
    await fetchNetworkInfo();

    startBLETimer(data.duration_seconds);
    showToast(`2-minute proximity session started! PIN: ${data.pin_code}`, "success");
  } catch (e) {
    showToast("Error starting BLE session: " + e.message, "error");
  }
}

function startBLETimer(seconds) {
  let remaining = seconds;
  if (bleTimerInterval) clearInterval(bleTimerInterval);

  bleTimerInterval = setInterval(async () => {
    remaining--;
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    document.getElementById("ble-timer-display").textContent = 
      `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;

    if (remaining % 3 === 0 && activeBleToken) {
      await pollBLEStatus();
    }

    if (remaining <= 0) {
      clearInterval(bleTimerInterval);
      showToast("Proximity window expired. Finalizing session...", "info");
      await closeBLESession();
    }
  }, 1000);
}

async function pollBLEStatus() {
  if (!activeBleToken) return;
  try {
    const res = await fetch(`/api/ble/session/${activeBleToken}/status`);
    if (!res.ok) return;
    const status = await res.json();
    document.getElementById("ble-checkedin-count").textContent = status.total_checked_in;

    const feed = document.getElementById("ble-live-feed");
    if (feed) {
      if (status.students && status.students.length > 0) {
        feed.innerHTML = "";
        status.students.forEach((s, idx) => {
          const item = document.createElement("div");
          item.className = "flex items-center justify-between p-2 bg-white border border-emerald-200/80 rounded-xl shadow-2xs text-xs";
          item.innerHTML = `
            <div class="flex items-center space-x-2.5">
              <span class="w-6 h-6 rounded-full bg-emerald-100 text-emerald-800 font-bold flex items-center justify-center text-[10px] shrink-0">${idx + 1}</span>
              <div>
                <span class="font-bold text-slate-900 block">${s.roll_number}</span>
                <span class="text-[11px] text-slate-500 block">${s.full_name}</span>
              </div>
            </div>
            <span class="px-2 py-0.5 text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300 rounded-full flex items-center space-x-1">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <span>Verified Live</span>
            </span>
          `;
          feed.appendChild(item);
        });
      } else {
        feed.innerHTML = `<p class="text-slate-400 italic text-center py-6">Waiting for students to scan QR or enter PIN...</p>`;
      }
    }
  } catch (e) {
    console.error("BLE poll failed:", e);
  }
}

async function submitStudentBLECheckin() {
  const pin = document.getElementById("ble-pin-input").value.trim();
  const roll = document.getElementById("ble-student-select").value;
  const alertEl = document.getElementById("ble-checkin-alert");

  if (!pin) {
    showToast("Please enter the 4-digit PIN", "error");
    return;
  }

  try {
    const res = await fetch("/api/ble/checkin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin_code: pin, roll_number: roll })
    });

    const result = await res.json();
    alertEl.classList.remove("hidden");
    if (result.success) {
      alertEl.className = "p-3 rounded-lg text-xs font-semibold bg-emerald-100 text-emerald-800 border border-emerald-300";
      alertEl.textContent = `✓ ${result.message}`;
      await pollBLEStatus();
    } else {
      alertEl.className = "p-3 rounded-lg text-xs font-semibold bg-rose-100 text-rose-800 border border-rose-300";
      alertEl.textContent = `✕ ${result.message}`;
    }
  } catch (e) {
    showToast("Check-in failed: " + e.message, "error");
  }
}

async function closeBLESession() {
  if (!activeBleToken) return;
  if (bleTimerInterval) clearInterval(bleTimerInterval);

  const formData = new FormData();
  formData.append("session_token", activeBleToken);

  try {
    const res = await fetch("/api/ble/close-session", { method: "POST", body: formData });
    if (!res.ok) throw new Error("Close session failed");

    document.getElementById("ble-active-panel").classList.add("hidden");
    document.getElementById("ble-start-btn").classList.remove("hidden");
    document.getElementById("ble-close-btn").classList.add("hidden");
    activeBleToken = null;

    showToast("BLE Session committed to database!", "success");
    await loadDashboardKPIs();
  } catch (e) {
    showToast("Error closing BLE session: " + e.message, "error");
  }
}

// -------------------------------------------------------------
// TAB 5: MASTER DATA ENGINE (ADMIN TAB)
// -------------------------------------------------------------

async function loadInstitutionConfig() {
  try {
    const res = await fetch("/api/admin/institution");
    if (!res.ok) return;
    const cfg = await res.json();

    document.getElementById("cfg-inst-name").value = cfg.institution_name;
    document.getElementById("cfg-inst-code").value = cfg.institution_code;
    document.getElementById("cfg-threshold-range").value = cfg.min_attendance_threshold;
    document.getElementById("cfg-threshold-val").textContent = `${cfg.min_attendance_threshold}%`;

    document.getElementById("cfg-google-id").value = cfg.google_client_id || "";
    document.getElementById("cfg-storage-path").value = cfg.cloud_storage_path || "";
    document.getElementById("cfg-webhook-url").value = cfg.webhook_url || "";
  } catch (e) {
    console.error("Config fetch error:", e);
  }
}

function updateThresholdLabel(val) {
  document.getElementById("cfg-threshold-val").textContent = `${val}%`;
}

async function saveInstitutionConfig() {
  const payload = {
    institution_name: document.getElementById("cfg-inst-name").value,
    institution_code: document.getElementById("cfg-inst-code").value,
    min_attendance_threshold: parseFloat(document.getElementById("cfg-threshold-range").value),
    google_client_id: document.getElementById("cfg-google-id").value,
    cloud_storage_path: document.getElementById("cfg-storage-path").value,
    webhook_url: document.getElementById("cfg-webhook-url").value
  };

  try {
    const res = await fetch("/api/admin/institution", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) throw new Error("Failed to save settings");
    showToast("Institutional master configuration saved successfully!", "success");
    await loadDashboardKPIs();
  } catch (e) {
    showToast("Error saving configuration: " + e.message, "error");
  }
}

async function submitBulkUpload() {
  const fileInput = document.getElementById("bulk-file-input");
  const typeSelect = document.getElementById("bulk-type-select");
  if (!fileInput.files[0]) {
    showToast("Please choose a CSV or JSON file to upload", "error");
    return;
  }

  const formData = new FormData();
  formData.append("type", typeSelect.value);
  formData.append("file", fileInput.files[0]);

  try {
    const res = await fetch("/api/admin/bulk-upload", { method: "POST", body: formData });
    if (!res.ok) throw new Error("Upload processing error");
    const result = await res.json();
    showToast(`Bulk upload completed! Created ${result.items_created} new ${result.type}.`, "success");
    fileInput.value = "";
    await loadSubjectsDropdowns();
    await populateBLEStudentSelect();
    await loadDashboardKPIs();
  } catch (e) {
    showToast("Bulk upload failed: " + e.message, "error");
  }
}

async function submitCreateSubject() {
  const code = document.getElementById("add-subj-code").value.trim();
  const name = document.getElementById("add-subj-name").value.trim();
  const threshold = parseFloat(document.getElementById("add-subj-threshold").value) || 75.0;

  if (!code || !name) {
    showToast("Please provide both subject code and name", "error");
    return;
  }

  try {
    const res = await fetch("/api/admin/subjects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code: code,
        name: name,
        department_id: 1,
        min_threshold: threshold
      })
    });

    if (!res.ok) throw new Error("Subject creation failed");
    showToast(`Subject ${code} created successfully!`, "success");
    document.getElementById("add-subj-code").value = "";
    document.getElementById("add-subj-name").value = "";
    await loadSubjectsDropdowns();
  } catch (e) {
    showToast("Error creating subject: " + e.message, "error");
  }
}

// -------------------------------------------------------------
// TAB 6: OPEN-SOURCE COMPLIANCE
// -------------------------------------------------------------

async function loadLicensesTable() {
  try {
    const res = await fetch("/api/compliance/licenses");
    if (!res.ok) return;
    const data = await res.json();

    const tbody = document.getElementById("licenses-table-body");
    tbody.innerHTML = "";

    data.libraries.forEach(lib => {
      const tr = document.createElement("tr");
      tr.className = "hover:bg-slate-50 transition";
      tr.innerHTML = `
        <td class="py-2.5 px-4 font-bold text-slate-900">${lib.name}</td>
        <td class="py-2.5 px-4 font-mono text-slate-500">${lib.version}</td>
        <td class="py-2.5 px-4">
          <a href="${lib.license_url}" target="_blank" class="inline-flex items-center space-x-1 font-semibold text-teal-700 bg-teal-50 hover:bg-teal-100 px-2 py-0.5 rounded border border-teal-200">
            <span>${lib.license}</span>
            <span class="text-[10px]">&#8599;</span>
          </a>
        </td>
        <td class="py-2.5 px-4 text-slate-600">${lib.purpose}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Compliance fetch error:", e);
  }
}

// -------------------------------------------------------------
// TOAST NOTIFICATIONS HELPER
// -------------------------------------------------------------

function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `pointer-events-auto px-4 py-3 rounded-xl shadow-lg border text-xs font-semibold flex items-center space-x-2 transition-all duration-300 transform translate-y-2 opacity-0 ${
    type === "success" 
      ? "bg-slate-900 text-emerald-400 border-emerald-500/30" 
      : type === "error" 
      ? "bg-slate-900 text-rose-400 border-rose-500/30" 
      : "bg-slate-900 text-teal-300 border-teal-500/30"
  }`;

  const iconName = type === "success" ? "check-circle" : type === "error" ? "alert-circle" : "info";
  toast.innerHTML = `<i data-lucide="${iconName}" class="w-4 h-4 shrink-0"></i><span>${message}</span>`;
  container.appendChild(toast);

  if (window.lucide) {
    lucide.createIcons();
  }

  // Animate in
  setTimeout(() => {
    toast.classList.remove("translate-y-2", "opacity-0");
  }, 10);

  // Auto remove after 3.5s
  setTimeout(() => {
    toast.classList.add("translate-y-2", "opacity-0");
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
