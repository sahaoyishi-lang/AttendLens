"""
AttendLens - Institutional Master Data Seeder
Seeds institutional config, staff accounts, and the 3 engineering streams
(EIE, ECE, IT) with their subjects. Zero imaginary/fake students are seeded;
only real students who sign up appear in the system.
"""
import hashlib
from sqlalchemy.orm import Session
from database import User, InstitutionConfig, Department, Subject


def hash_pw(password: str) -> str:
    """Standard SHA-256 password hash (zero C-extension dependencies)"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_pw(plain_password: str, hashed_password: str) -> bool:
    return hash_pw(plain_password) == hashed_password


STREAMS = [
    ("EIE", "Electronics & Instrumentation Engineering"),
    ("ECE", "Electronics & Communication Engineering"),
    ("IT", "Information Technology"),
]

STREAM_SUBJECTS = {
    "EIE": [
        ("EIE-301", "Industrial Instrumentation & Transducers", 75.0),
        ("EIE-302", "Microcontrollers & Embedded Systems", 75.0),
        ("EIE-303", "Process Control & Automation", 80.0),
    ],
    "ECE": [
        ("ECE-301", "Analog & Digital Communication", 75.0),
        ("ECE-302", "VLSI & Signal Processing", 75.0),
        ("ECE-303", "Microwave & Antenna Engineering", 75.0),
    ],
    "IT": [
        ("IT-301", "Data Structures & Algorithms", 75.0),
        ("IT-302", "Database Management Systems", 75.0),
        ("IT-303", "Computer Networks & Cloud Computing", 75.0),
    ],
}


def seed_all(db: Session):
    """Seed institutional config, staff accounts, 3 streams (EIE, ECE, IT), and subjects"""
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

    # 2. Staff Users (Admin and Teacher accounts)
    admin_user = db.query(User).filter_by(email="admin@dets.edu").first()
    if not admin_user:
        db.add(User(
            email="admin@dets.edu",
            full_name="Prof. D. K. Banerjee (Dean & Admin)",
            hashed_password=hash_pw("Admin@123"),
            role="admin",
            auth_provider="local"
        ))

    teacher_user = db.query(User).filter_by(email="prof.sharma@dets.edu").first()
    if not teacher_user:
        db.add(User(
            email="prof.sharma@dets.edu",
            full_name="Dr. Alok Sharma (Associate Professor)",
            hashed_password=hash_pw("Teacher@123"),
            role="teacher",
            auth_provider="local"
        ))
    db.commit()

    # 3. Three Streams (Departments): EIE, ECE, IT
    dept_map = {}
    for code, name in STREAMS:
        dept = db.query(Department).filter_by(code=code).first()
        if not dept:
            dept = Department(code=code, name=name)
            db.add(dept)
            db.commit()
            db.refresh(dept)
        dept_map[code] = dept

    # 4. Stream-specific Subjects
    for stream_code, subjects in STREAM_SUBJECTS.items():
        dept = dept_map[stream_code]
        for code, name, threshold in subjects:
            subj = db.query(Subject).filter_by(code=code).first()
            if not subj:
                db.add(Subject(
                    code=code,
                    name=name,
                    department_id=dept.id,
                    semester="Semester 6",
                    academic_year="2026-2027",
                    min_threshold=threshold
                ))
                db.commit()

    print("[AttendLens DB] Master data seeded (3 streams: EIE, ECE, IT; 0 imaginary students).")
