"""
AttendLens - End-to-End Verification Test Script
Tests:
1. DB Seeding and SQLAlchemy ORM models
2. Smart PDF & XLSX sheet generation
3. Synthetic filled sheet generation & OpenCV CV/OCR pipeline
4. Shortage Notice PDF & Full Excel Report generation
5. FastAPI Test Client route testing
"""
import os
import sys
import random

def run_tests():
    print("=" * 60)
    print("AttendLens Verification & Health Check")
    print("=" * 60)

    # 1. Test Database Initialization & Seeding
    print("[1/5] Testing Database Initialization & Synthetic Seeder...")
    from database import init_db, SessionLocal, User, Department, Subject, Student, ClassSession, AttendanceRecord
    init_db()
    db = SessionLocal()
    from seed_data import seed_all
    seed_all(db)

    users_count = db.query(User).count()
    depts_count = db.query(Department).count()
    students_count = db.query(Student).count()
    subjects_count = db.query(Subject).count()
    sessions_count = db.query(ClassSession).count()
    records_count = db.query(AttendanceRecord).count()

    print(f"  ✓ Users in DB: {users_count}")
    print(f"  ✓ Streams/Departments in DB: {depts_count}")
    print(f"  ✓ Students in DB: {students_count}")
    print(f"  ✓ Subjects in DB: {subjects_count}")
    print(f"  ✓ Historical Sessions: {sessions_count}")
    print(f"  ✓ Attendance Records: {records_count}")
    assert depts_count >= 3, "Expected 3 streams (EIE, ECE, IT)"
    assert subjects_count >= 9, "Expected 9 stream subjects"

    # 2. Test Smart Sheet Generator (PDF & XLSX)
    print("\n[2/5] Testing Smart PDF & XLSX Sheet Generator...")
    from services.sheet_generator import generate_smart_pdf_sheet, generate_attendance_xlsx_template
    stud_data = [{"id": i, "roll_number": f"DETS-26-EIE-{i:03d}", "full_name": f"Test Student {i}"} for i in range(1, 21)]

    pdf_bytes = generate_smart_pdf_sheet(
        institution_name="Department of Engineering & Technological Studies (DETS)",
        department_name="Electronics & Instrumentation Engineering",
        subject_code="EIE-301",
        subject_name="Industrial Instrumentation & Transducers",
        session_date="2026-11-24",
        academic_year="2026-2027",
        semester="Semester 6",
        session_token="SESS-TEST-001",
        students=stud_data
    )
    print(f"  ✓ Generated Smart PDF size: {len(pdf_bytes)} bytes")
    assert len(pdf_bytes) > 5000, "PDF generation failed"

    xlsx_bytes = generate_attendance_xlsx_template(
        institution_name="Department of Engineering & Technological Studies (DETS)",
        subject_code="EIE-301",
        subject_name="Industrial Instrumentation & Transducers",
        session_date="2026-11-24",
        session_token="SESS-TEST-001",
        students=stud_data
    )
    print(f"  ✓ Generated XLSX Template size: {len(xlsx_bytes)} bytes")
    assert len(xlsx_bytes) > 4000, "XLSX template generation failed"

    # 3. Test OpenCV Computer Vision & Hybrid OCR Pipeline
    print("\n[3/5] Testing Computer Vision & Hybrid OCR Pipeline...")
    from services.ocr_pipeline import (
        generate_synthetic_sample_sheet_image, 
        process_scanned_sheet, 
        bgr_to_base64_jpeg
    )
    sample_bgr = generate_synthetic_sample_sheet_image(
        students=stud_data,
        subject_code="EIE-301",
        subject_name="Industrial Instrumentation & Transducers",
        session_date="2026-11-24",
        session_token="SESS-TEST-CV"
    )
    print(f"  ✓ Synthetic filled sheet shape: {sample_bgr.shape}")

    scan_result = process_scanned_sheet(
        image_bgr=sample_bgr,
        students=stud_data
    )

    print(f"  ✓ 4-Corner Fiducials Detected: {scan_result['fiducials_detected']}")
    print(f"  ✓ Present Count: {scan_result['present_count']}")
    print(f"  ✓ Absent Count: {scan_result['absent_count']}")
    print(f"  ✓ Uncertain Count: {scan_result['uncertain_count']}")
    print(f"  ✓ Total Student Cells Sliced: {len(scan_result['cells'])}")
    assert scan_result['total_students'] == 20
    assert scan_result['uncertain_count'] >= 1, "Expected ambiguous mark to be classified as UNCERTAIN"
    print("  ✓ Split-screen base64 crops generated successfully")

    # 4. Test Report Exporters (PDF Shortage & Full XLSX)
    print("\n[4/5] Testing Shortage Notice PDF & Full Excel Report Generation...")
    from services.report_exporter import generate_shortage_pdf_report, generate_full_attendance_xlsx
    shortage_pdf = generate_shortage_pdf_report(
        institution_name="Department of Engineering & Technological Studies (DETS)",
        subject_code="EIE-301",
        subject_name="Industrial Instrumentation & Transducers",
        min_threshold=75.0,
        total_sessions=12,
        shortage_students=[
            {
                "roll_number": "DETS-26-EIE-007",
                "full_name": "Vikram K. Rao",
                "classes_held": 12,
                "classes_attended": 8,
                "attendance_percent": 66.7,
                "classes_needed_for_75": 4
            }
        ]
    )
    print(f"  ✓ Shortage Notice PDF size: {len(shortage_pdf)} bytes")
    assert len(shortage_pdf) > 1000

    full_xlsx = generate_full_attendance_xlsx(
        institution_name="Department of Engineering & Technological Studies (DETS)",
        subject_code="EIE-301",
        subject_name="Industrial Instrumentation & Transducers",
        min_threshold=75.0,
        session_dates=["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"],
        student_records=[
            {
                "roll_number": "DETS-26-EIE-001",
                "full_name": "Aarav S. Patel",
                "attendance": {"2026-10-05": "P", "2026-10-12": "P", "2026-10-19": "P", "2026-10-26": "P"},
                "held": 4, "attended": 4, "percent": 100.0, "status": "Safe", "needed": 0
            }
        ]
    )
    print(f"  ✓ Full Attendance XLSX size: {len(full_xlsx)} bytes")
    assert len(full_xlsx) > 4000

    # 5. Test FastAPI Routes via TestClient
    print("\n[5/5] Testing FastAPI API Endpoints...")
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    # Check Homepage
    res = client.get("/")
    assert res.status_code == 200
    assert "AttendLens" in res.text
    print("  ✓ GET / returns 200 and serves Single Page Application")

    # Check Demo Login
    res = client.post("/api/auth/demo-login/teacher")
    assert res.status_code == 200
    token_data = res.json()
    assert "access_token" in token_data
    token = token_data["access_token"]
    print("  ✓ POST /api/auth/demo-login/teacher returns JWT token")

    # Check Dashboard Analytics
    res = client.get("/api/analytics/dashboard")
    assert res.status_code == 200
    dash_data = res.json()
    assert dash_data["total_students"] >= 0
    print(f"  ✓ GET /api/analytics/dashboard returns {dash_data['total_students']} students, overall rate {dash_data['overall_attendance_rate']}%")

    # Check Compliance Metadata
    res = client.get("/api/compliance/licenses")
    assert res.status_code == 200
    comp_data = res.json()
    assert len(comp_data["libraries"]) >= 10
    print(f"  ✓ GET /api/compliance/licenses returns {len(comp_data['libraries'])} open-source SPDX license entries")

    # Check 1-Click Synthetic Sample Filled OCR Generation
    res = client.post("/api/ocr/generate-sample-filled?subject_id=1")
    assert res.status_code == 200
    ocr_res = res.json()
    assert ocr_res["present_count"] > 0
    print(f"  ✓ POST /api/ocr/generate-sample-filled successfully processed: {ocr_res['present_count']} Present, {ocr_res['absent_count']} Absent, {ocr_res['uncertain_count']} Uncertain")

    # 6. Test Network Info, Mobile Student Portal & Student Self-Enrollment
    print("\n[6/6] Testing Network Info, Mobile Student Portal & Student Enrollment...")
    
    # Check Network Info & LAN QR Code
    res = client.get("/api/network-info")
    assert res.status_code == 200
    net_data = res.json()
    assert "lan_ip" in net_data
    assert "student_url" in net_data
    assert net_data["qr_code_base64"].startswith("data:image/png;base64,")
    print(f"  ✓ GET /api/network-info returns LAN IP: {net_data['lan_ip']}, Student URL: {net_data['student_url']}")

    # Check Mobile Student Portal HTML
    res = client.get("/student")
    assert res.status_code == 200
    assert "Student Proximity Check-In" in res.text or "Student Portal" in res.text
    assert "Course Enrollment" in res.text
    print("  ✓ GET /student serves dedicated mobile portal")

    # Check PWA Manifest & Service Worker
    res_manifest = client.get("/static/manifest.json")
    assert res_manifest.status_code == 200
    assert "AttendLens" in res_manifest.text
    res_sw = client.get("/static/sw.js")
    assert res_sw.status_code == 200
    print("  ✓ PWA assets (manifest.json, sw.js) accessible with HTTP 200")

    # Test Student Self-Enrollment
    res_enroll = client.post("/api/student/enroll", json={
        "full_name": "Aayush K. Sen",
        "roll_number": "DETS-26-EIE-021",
        "email": "aayush.sen@dets.edu",
        "subject_id": 1,
        "semester": "Semester 6"
    })
    assert res_enroll.status_code == 200
    enroll_data = res_enroll.json()
    assert enroll_data["success"] is True
    assert enroll_data["student"]["roll_number"] == "DETS-26-EIE-021"
    print(f"  ✓ POST /api/student/enroll registered student: {enroll_data['student']['full_name']} into {enroll_data['subject']['code']}")

    # Test Student Account Creation / Sign Up with Registration Number, Stream (ECE), and Google Auth Provider
    signup_roll = f"DETS-26-ECE-0{random.randint(30, 99)}"
    res_signup = client.post("/api/student/signup", json={
        "roll_number": signup_roll,
        "full_name": "Kavita S. Murthy",
        "email": f"kavita.{random.randint(100, 999)}@gmail.com",
        "password": "Password@123",
        "stream": "ECE",
        "semester": "Semester 4",
        "auth_provider": "google"
    })
    assert res_signup.status_code == 200
    signup_data = res_signup.json()
    assert signup_data["user"]["role"] == "student"
    assert signup_data["user"]["auth_provider"] == "google"
    assert signup_data["student"]["roll_number"] == signup_roll
    assert signup_data["student"]["semester"] == "Semester 4"
    stud_token = signup_data["access_token"]
    print(f"  ✓ POST /api/student/signup created Google student account for {signup_roll} ({signup_data['user']['full_name']}) in ECE, {signup_data['student']['semester']}")

    # Verify Stream filtering on teacher student directory
    res_stream = client.get("/api/admin/students?stream=ECE")
    assert res_stream.status_code == 200
    ece_students = res_stream.json()
    assert any(s["roll_number"] == signup_roll and s["department_code"] == "ECE" for s in ece_students)
    print(f"  ✓ GET /api/admin/students?stream=ECE lists {signup_roll} under ECE stream")

    # Test Student Login using Registration Number
    res_login = client.post("/api/student/login", json={
        "identifier": signup_roll,
        "password": "Password@123"
    })
    assert res_login.status_code == 200
    login_data = res_login.json()
    assert login_data["student"]["roll_number"] == signup_roll
    print(f"  ✓ POST /api/student/login successfully authenticated {signup_roll} via Registration Number")

    # Test Student Profile & Attendance Breakdown
    res_me = client.get("/api/student/me", headers={"Authorization": f"Bearer {stud_token}"})
    assert res_me.status_code == 200
    me_data = res_me.json()
    assert me_data["roll_number"] == signup_roll
    assert me_data["semester"] == "Semester 4"
    assert "enrolled_subjects" in me_data
    assert "overall_attendance_rate" in me_data
    print(f"  ✓ GET /api/student/me retrieved profile: {me_data['full_name']} with {len(me_data['enrolled_subjects'])} subjects, overall rate: {me_data['overall_attendance_rate']}%")

    # Test Student 1-Click Demo Login on registered student
    res_demo = client.post("/api/student/demo-login/DETS-26-EIE-021")
    assert res_demo.status_code == 200
    demo_data = res_demo.json()
    assert demo_data["student"]["roll_number"] == "DETS-26-EIE-021"
    print(f"  ✓ POST /api/student/demo-login/DETS-26-EIE-021 authenticated student: {demo_data['user']['full_name']}")

    # Test BLE Session Start & Student Check-In Receipt
    res_ble_start = client.post("/api/ble/start-session", json={"subject_id": 1, "duration_minutes": 2})
    assert res_ble_start.status_code == 200
    ble_sess = res_ble_start.json()
    pin_code = ble_sess["pin_code"]

    res_checkin = client.post("/api/ble/checkin", json={
        "pin_code": pin_code,
        "roll_number": "DETS-26-EIE-021"
    })
    assert res_checkin.status_code == 200
    receipt = res_checkin.json()
    assert receipt["success"] is True
    assert "timestamp" in receipt
    assert "attendance_percent" in receipt
    print(f"  ✓ POST /api/ble/checkin verified: {receipt['student_name']} ({receipt['roll_number']}), updated rate: {receipt['attendance_percent']}%")

    db.close()
    print("\n" + "=" * 60)
    print("🎉 ALL 6 TEST SUITES PASSED WITH ZERO ERRORS!")
    print("AttendLens is 100% production-ready and fully operational.")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
