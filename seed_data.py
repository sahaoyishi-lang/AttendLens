"""
AttendLens - Institutional Synthetic Master Data Seeder
Generates 100% synthetic, anonymized university records for
the Department of Engineering & Technological Studies (DETS).
Never uses real personal data.
"""
import hashlib
import datetime
from sqlalchemy.orm import Session
from database import (
    User, InstitutionConfig, Department, Subject, 
    Student, ClassSession, AttendanceRecord
)

def hash_pw(password: str) -> str:
    """Standard SHA-256 password hash (zero C-extension dependencies)"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def verify_pw(plain_password: str, hashed_password: str) -> bool:
    return hash_pw(plain_password) == hashed_password

SYNTHETIC_STUDENTS = [
    ("DETS-26-EIE-001", "Aarav S. Patel", "aarav.patel@dets.edu"),
    ("DETS-26-EIE-002", "Ananya R. Sharma", "ananya.sharma@dets.edu"),
    ("DETS-26-EIE-003", "Rohan M. Gupta", "rohan.gupta@dets.edu"),
    ("DETS-26-EIE-004", "Priya K. Nair", "priya.nair@dets.edu"),
    ("DETS-26-EIE-005", "Aditya V. Verma", "aditya.verma@dets.edu"),
    ("DETS-26-EIE-006", "Sneha D. Joshi", "sneha.joshi@dets.edu"),
    ("DETS-26-EIE-007", "Vikram K. Rao", "vikram.rao@dets.edu"),
    ("DETS-26-EIE-008", "Neha T. Kulkarni", "neha.kulkarni@dets.edu"),
    ("DETS-26-EIE-009", "Karan P. Sen", "karan.sen@dets.edu"),
    ("DETS-26-EIE-010", "Riya B. Mukherjee", "riya.mukherjee@dets.edu"),
    ("DETS-26-EIE-011", "Manish C. Das", "manish.das@dets.edu"),
    ("DETS-26-EIE-012", "Pooja L. Menon", "pooja.menon@dets.edu"),
    ("DETS-26-EIE-013", "Siddharth R. Bhat", "siddharth.bhat@dets.edu"),
    ("DETS-26-EIE-014", "Kavya S. Iyer", "kavya.iyer@dets.edu"),
    ("DETS-26-EIE-015", "Arjun V. Reddy", "arjun.reddy@dets.edu"),
    ("DETS-26-EIE-016", "Meera A. Pillai", "meera.pillai@dets.edu"),
    ("DETS-26-EIE-017", "Devendra N. Roy", "devendra.roy@dets.edu"),
    ("DETS-26-EIE-018", "Tanvi H. Deshmukh", "tanvi.deshmukh@dets.edu"),
    ("DETS-26-EIE-019", "Nikhil G. Chopra", "nikhil.chopra@dets.edu"),
    ("DETS-26-EIE-020", "Ishita S. Bose", "ishita.bose@dets.edu"),
]

SYNTHETIC_SUBJECTS = [
    ("EIE-301", "Industrial Instrumentation & Transducers", 75.0),
    ("EIE-302", "Microcontrollers & Embedded Systems", 75.0),
    ("EIE-303", "Process Control & Automation", 80.0),
]

def seed_all(db: Session):
    """Seed comprehensive initial master data if database is empty"""
    # 1. Institutional Configuration
    config = db.query(InstitutionConfig).first()
    if not config:
        config = InstitutionConfig(
            institution_name="Department of Engineering & Technological Studies (DETS)",
            institution_code="DETS",
            min_attendance_threshold=75.0,
            current_academic_year="2026-2027",
            current_semester="Semester 6",
            google_client_id="",
            google_client_secret="",
            cloud_storage_path="s3://dets-attendance-archive/2026/",
            webhook_url="https://erp.dets.edu/api/v1/attendance-webhook"
        )
        db.add(config)
        db.commit()

    # 2. Users (Admin and Teacher accounts for 1-click evaluation)
    admin_user = db.query(User).filter_by(email="admin@dets.edu").first()
    if not admin_user:
        admin_user = User(
            email="admin@dets.edu",
            full_name="Prof. D. K. Banerjee (Dean & Admin)",
            hashed_password=hash_pw("Admin@123"),
            role="admin",
            auth_provider="local"
        )
        db.add(admin_user)

    teacher_user = db.query(User).filter_by(email="prof.sharma@dets.edu").first()
    if not teacher_user:
        teacher_user = User(
            email="prof.sharma@dets.edu",
            full_name="Dr. Alok Sharma (Associate Professor)",
            hashed_password=hash_pw("Teacher@123"),
            role="teacher",
            auth_provider="local"
        )
        db.add(teacher_user)
    db.commit()

    # 3. Department
    dept = db.query(Department).filter_by(code="EIE").first()
    if not dept:
        dept = Department(
            code="EIE",
            name="Electronics & Instrumentation Engineering"
        )
        db.add(dept)
        db.commit()

    # 4. Subjects
    subjects_map = {}
    for code, name, threshold in SYNTHETIC_SUBJECTS:
        subj = db.query(Subject).filter_by(code=code).first()
        if not subj:
            subj = Subject(
                code=code,
                name=name,
                department_id=dept.id,
                semester="Semester 6",
                academic_year="2026-2027",
                min_threshold=threshold
            )
            db.add(subj)
            db.commit()
        subjects_map[code] = subj

    # 5. Students
    students_list = []
    for roll, name, email in SYNTHETIC_STUDENTS:
        stud = db.query(Student).filter_by(roll_number=roll).first()
        if not stud:
            stud = Student(
                roll_number=roll,
                full_name=name,
                email=email,
                department_id=dept.id,
                semester="Semester 6",
                academic_year="2026-2027"
            )
            db.add(stud)
            db.commit()
        students_list.append(stud)

    # 6. Historical Class Sessions & Attendance (12 sessions across subjects)
    existing_sessions = db.query(ClassSession).count()
    if existing_sessions == 0:
        session_dates = [
            ("2026-10-05", "EIE-301"),
            ("2026-10-08", "EIE-302"),
            ("2026-10-12", "EIE-301"),
            ("2026-10-15", "EIE-303"),
            ("2026-10-19", "EIE-301"),
            ("2026-10-22", "EIE-302"),
            ("2026-10-26", "EIE-301"),
            ("2026-10-29", "EIE-303"),
            ("2026-11-02", "EIE-301"),
            ("2026-11-05", "EIE-302"),
            ("2026-11-09", "EIE-301"),
            ("2026-11-12", "EIE-303"),
        ]

        # Deterministic attendance patterns to create realistic analytics:
        # High attenders: 100% or 90%+
        # Moderate attenders: 75% to 85%
        # Defaulters/Shortage:
        #   Student 7 (Vikram K. Rao): attends 4 of 6 sessions (~66%)
        #   Student 12 (Pooja L. Menon): attends 3 of 6 sessions (~50%)
        #   Student 19 (Nikhil G. Chopra): attends 3 of 6 sessions (~50%)
        
        for idx, (sdate, scode) in enumerate(session_dates):
            subject_obj = subjects_map[scode]
            session = ClassSession(
                session_token=f"SESS-2026-{scode}-{idx+1:03d}",
                subject_id=subject_obj.id,
                teacher_id=teacher_user.id,
                session_date=sdate,
                academic_year="2026-2027",
                semester="Semester 6",
                session_type="regular" if idx % 3 != 0 else "lab",
                status="verified"
            )
            db.add(session)
            db.commit()

            # Create attendance record for each student
            for s_idx, student in enumerate(students_list):
                # Custom attendance distribution
                if s_idx in [6]: # Vikram K. Rao (~66%)
                    status = "P" if idx % 3 != 0 else "A"
                elif s_idx in [11, 18]: # Pooja & Nikhil (~50%)
                    status = "P" if idx % 2 == 0 else "A"
                elif s_idx in [4, 9, 14]: # Sneha, Riya, Arjun (~83%)
                    status = "P" if idx % 6 != 2 else "A"
                else: # High attenders (~92%-100%)
                    status = "P" if idx % 10 != 1 else "A"

                rec = AttendanceRecord(
                    session_id=session.id,
                    student_id=student.id,
                    status=status,
                    confidence_score=97.5 if status == "P" else 95.0,
                    detection_method="OCR",
                    is_flagged=False,
                    verified_by=teacher_user.id
                )
                db.add(rec)
            db.commit()

    print("[AttendLens DB] Synthetic master data successfully verified/seeded.")
