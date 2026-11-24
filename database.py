"""
AttendLens - Database Configuration & SQLAlchemy ORM Models
100% Open-Source Full-Stack Architecture
Supports SQLite (default) and PostgreSQL via DATABASE_URL
"""
import os
import datetime
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, 
    DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./attendlens.db")

# For SQLite, check_same_thread needs to be False for multithreaded FastAPI requests
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------- MODELS -----------------

class User(Base):
    """User account model for Teachers, Admins, and Staff"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=True)
    role = Column(String(50), default="teacher", nullable=False) # 'admin', 'teacher'
    is_active = Column(Boolean, default=True)
    auth_provider = Column(String(50), default="local") # 'local', 'google'
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    sessions = relationship("ClassSession", back_populates="teacher")
    audit_logs = relationship("AuditLog", back_populates="teacher")


class InstitutionConfig(Base):
    """Institutional Master Data & Global Configuration Settings"""
    __tablename__ = "institution_configs"

    id = Column(Integer, primary_key=True, index=True)
    institution_name = Column(String(255), default="Department of Engineering & Technological Studies (DETS)")
    institution_code = Column(String(50), default="DETS")
    min_attendance_threshold = Column(Float, default=75.0)
    current_academic_year = Column(String(20), default="2026-2027")
    current_semester = Column(String(20), default="Semester 6")
    
    # External integrations settings (modular, configurable)
    google_client_id = Column(String(255), nullable=True)
    google_client_secret = Column(String(255), nullable=True)
    cloud_storage_path = Column(String(255), default="s3://dets-attendance-archive/2026/")
    webhook_url = Column(String(255), default="https://erp.dets.edu/api/v1/attendance-webhook")
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class Department(Base):
    """University Departments / Schools"""
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False) # e.g., 'EIE'
    name = Column(String(255), nullable=False) # e.g., 'Electronics and Instrumentation Engineering'
    
    subjects = relationship("Subject", back_populates="department")
    students = relationship("Student", back_populates="department")


class Subject(Base):
    """Academic Subject / Course Unit"""
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False) # e.g., 'EIE-301'
    name = Column(String(255), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    semester = Column(String(50), default="Semester 6")
    academic_year = Column(String(50), default="2026-2027")
    min_threshold = Column(Float, default=75.0) # Subject-specific minimum attendance %

    department = relationship("Department", back_populates="subjects")
    sessions = relationship("ClassSession", back_populates="subject")


class Student(Base):
    """Student master record (anonymized synthetic data)"""
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    roll_number = Column(String(50), unique=True, index=True, nullable=False) # e.g., 'DETS-26-EIE-001'
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    semester = Column(String(50), default="Semester 6")
    academic_year = Column(String(50), default="2026-2027")
    is_active = Column(Boolean, default=True)

    department = relationship("Department", back_populates="students")
    attendance_records = relationship("AttendanceRecord", back_populates="student")


class ClassSession(Base):
    """A single held lecture or lab class session"""
    __tablename__ = "class_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String(64), unique=True, index=True, nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_date = Column(String(20), nullable=False) # YYYY-MM-DD
    academic_year = Column(String(20), default="2026-2027")
    semester = Column(String(20), default="Semester 6")
    session_type = Column(String(50), default="regular") # 'regular', 'lab', 'ble_prox'
    status = Column(String(50), default="verified") # 'created', 'scanned', 'verified'
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    subject = relationship("Subject", back_populates="sessions")
    teacher = relationship("User", back_populates="sessions")
    attendance_records = relationship("AttendanceRecord", back_populates="session", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="session", cascade="all, delete-orphan")


class AttendanceRecord(Base):
    """Individual student attendance mark in a specific class session"""
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    status = Column(String(20), nullable=False) # 'P' (Present), 'A' (Absent), 'UNCERTAIN'
    confidence_score = Column(Float, default=100.0) # 0.0 to 100.0
    detection_method = Column(String(50), default="OCR") # 'OCR', 'BLE', 'MANUAL'
    is_flagged = Column(Boolean, default=False)
    notes = Column(String(255), nullable=True)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    session = relationship("ClassSession", back_populates="attendance_records")
    student = relationship("Student", back_populates="attendance_records")


class AuditLog(Base):
    """Audit trail for manual verification and status corrections"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("class_sessions.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    original_status = Column(String(20), nullable=False)
    corrected_status = Column(String(20), nullable=False)
    confidence_score = Column(Float, nullable=True)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    reason = Column(String(255), default="Manual teacher review & verification")

    session = relationship("ClassSession", back_populates="audit_logs")
    student = relationship("Student")
    teacher = relationship("User", back_populates="audit_logs")


class BLESession(Base):
    """Proximity/BLE digital classroom check-in session"""
    __tablename__ = "ble_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_token = Column(String(64), unique=True, index=True, nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    pin_code = Column(String(10), nullable=False) # 4-digit numeric PIN
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    checked_in_students = Column(JSON, default=list) # List of student roll numbers
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    subject = relationship("Subject")
    teacher = relationship("User")


def init_db():
    Base.metadata.create_all(bind=engine)
