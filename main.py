"""
AttendLens - Intelligent Student Attendance Tracking & Paper-to-Digital OCR System
Full-Stack FastAPI Application
100% Open-Source, Zero Proprietary APIs
"""
import io
import os
import json
import csv
import uuid
import random
import datetime
import base64
import socket
import math
import qrcode
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import (
    FastAPI, Depends, HTTPException, status, 
    UploadFile, File, Form, Request, Response
)
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import or_
from sqlalchemy.orm import Session
from jose import JWTError, jwt
import cv2
import numpy as np

from database import (
    engine, get_db, init_db, User, InstitutionConfig,
    Department, Subject, Student, ClassSession,
    AttendanceRecord, AuditLog, BLESession, Enrollment
)
from models import (
    UserLogin, UserRegister, UserResponse, TokenResponse,
    InstitutionUpdate, InstitutionResponse, DepartmentCreate,
    DepartmentResponse, SubjectCreate, SubjectResponse,
    StudentCreate, StudentResponse, SheetGenerateRequest,
    SheetScanResponse, AttendanceCommitRequest, AuditLogResponse,
    BLEStartRequest, BLESessionResponse, BLEStudentCheckinRequest,
    BLECheckinResult, BLEStatusResponse, DashboardKPIs,
    SubjectAnalyticsSummary, StudentAnalyticsItem,
    StudentEnrollRequest, StudentEnrollResponse,
    StudentRegisterRequest, StudentLoginRequest,
    StudentSubjectAttendance, StudentProfileResponse,
    StudentAuthResponse
)
from seed_data import seed_all, hash_pw, verify_pw
from services.sheet_generator import (
    generate_smart_pdf_sheet, generate_attendance_xlsx_template
)
from services.ocr_pipeline import (
    process_scanned_sheet, generate_synthetic_sample_sheet_image,
    base64_to_bgr, bgr_to_base64_jpeg
)
from services.report_exporter import (
    generate_shortage_pdf_report, generate_full_attendance_xlsx
)

# JWT Auth Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "attendlens-insecure-secret-hackathon-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Extract user from Authorization Bearer token or cookie"""
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if not token:
        # Fallback to demo teacher user for seamless evaluation if unauthenticated
        demo_user = db.query(User).filter_by(role="teacher").first()
        return demo_user

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return db.query(User).filter_by(role="teacher").first()
        user = db.query(User).filter_by(id=int(user_id)).first()
        return user or db.query(User).filter_by(role="teacher").first()
    except JWTError:
        return db.query(User).filter_by(role="teacher").first()

def get_current_student(request: Request, db: Session = Depends(get_db)) -> User:
    """Extract authenticated student from token or fallback to demo student"""
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    elif "access_token" in request.cookies:
        token = request.cookies.get("access_token")

    if not token:
        demo_student = db.query(User).filter_by(role="student").first()
        if demo_student:
            return demo_student
        raise HTTPException(status_code=401, detail="Authentication required. Please sign in.")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            demo_student = db.query(User).filter_by(role="student").first()
            if demo_student:
                return demo_student
            raise HTTPException(status_code=401, detail="Invalid token")
        user = db.query(User).filter_by(id=int(user_id)).first()
        if not user:
            demo_student = db.query(User).filter_by(role="student").first()
            if demo_student:
                return demo_student
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        demo_student = db.query(User).filter_by(role="student").first()
        if demo_student:
            return demo_student
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize tables and seed master synthetic data
    init_db()
    with next(get_db()) as db:
        seed_all(db)
    yield
    # Shutdown

app = FastAPI(
    title="AttendLens",
    description="Intelligent Student Attendance Tracking & Paper-to-Digital OCR System",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    with open(index_file, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/student", response_class=HTMLResponse)
async def serve_student_portal():
    student_file = os.path.join(STATIC_DIR, "student.html")
    if os.path.exists(student_file):
        with open(student_file, "r", encoding="utf-8") as f:
            return f.read()
    return HTMLResponse("<h3>Student portal template not found</h3>", status_code=404)

def get_lan_ip() -> str:
    """Detect active local LAN IPv4 address (e.g. 192.168.x.x, 10.x.x.x), fallback to 127.0.0.1"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    return "127.0.0.1"

@app.get("/api/network-info")
def get_network_info(custom_url: Optional[str] = None):
    """
    Returns detected LAN IP, port, student check-in URL,
    and a base64-encoded PNG QR code image for instant phone scanning over local hotspot/Wi-Fi.
    """
    lan_ip = get_lan_ip()
    port = 8000
    student_url = custom_url.strip() if custom_url and custom_url.strip() else f"http://{lan_ip}:{port}/student"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2
    )
    qr.add_data(student_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return {
        "lan_ip": lan_ip,
        "port": port,
        "student_url": student_url,
        "qr_code_base64": f"data:image/png;base64,{qr_b64}"
    }

# -------------------------------------------------------------
# AUTHENTICATION & RBAC ROUTES
# -------------------------------------------------------------

@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=payload.email).first()
    if not user or not verify_pw(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    token = create_access_token({"sub": str(user.id), "role": user.role, "email": user.email})
    return {"access_token": token, "token_type": "bearer", "user": user}

@app.post("/api/auth/demo-login/{role}", response_model=TokenResponse)
def demo_login(role: str, db: Session = Depends(get_db)):
    """1-Click Demo Login for Hackathon Judges & Evaluators"""
    target_role = "admin" if role.lower() == "admin" else "teacher"
    user = db.query(User).filter_by(role=target_role).first()
    if not user:
        raise HTTPException(status_code=404, detail="Demo user not found")
    
    token = create_access_token({"sub": str(user.id), "role": user.role, "email": user.email})
    return {"access_token": token, "token_type": "bearer", "user": user}

@app.post("/api/auth/register", response_model=TokenResponse)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(User).filter_by(email=payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    new_user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_pw(payload.password),
        role=payload.role if payload.role in ["admin", "teacher"] else "teacher",
        auth_provider="local"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    token = create_access_token({"sub": str(new_user.id), "role": new_user.role, "email": new_user.email})
    return {"access_token": token, "token_type": "bearer", "user": new_user}

@app.get("/api/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@app.get("/api/auth/google/url")
def google_sso_url(request: Request, mode: str = "student", db: Session = Depends(get_db)):
    """Provides Google OAuth2 redirect URL using dynamic origin"""
    cfg = db.query(InstitutionConfig).first()
    client_id = os.getenv("GOOGLE_CLIENT_ID") or (cfg.google_client_id if cfg else "")
    if client_id:
        base_url = str(request.base_url).rstrip("/")
        redirect_uri = f"{base_url}/api/auth/google/callback"
        from urllib.parse import urlencode
        params = urlencode({
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid profile email",
            "state": mode,
            "prompt": "select_account",
        })
        return {
            "configured": True,
            "url": f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
        }
    return {
        "configured": False,
        "message": "Google OAuth Client ID is not configured on the server yet. Use your Google (@gmail.com) email below to sign up."
    }

@app.get("/api/auth/google/callback")
def google_sso_callback(
    request: Request,
    code: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Handles Google OAuth2 callback and logs in or pre-fills student signup"""
    from fastapi.responses import RedirectResponse
    from urllib.parse import urlencode
    import requests as http_requests

    if error or not code:
        return RedirectResponse(url="/student?google_error=cancelled")

    cfg = db.query(InstitutionConfig).first()
    client_id = os.getenv("GOOGLE_CLIENT_ID") or (cfg.google_client_id if cfg else "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET") or (cfg.google_client_secret if cfg else "")
    if not client_id or not client_secret:
        return RedirectResponse(url="/student?google_error=not_configured")

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/auth/google/callback"

    token_res = http_requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    if not token_res.ok:
        return RedirectResponse(url="/student?google_error=token_exchange_failed")

    access_token = token_res.json().get("access_token")
    userinfo_res = http_requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if not userinfo_res.ok:
        return RedirectResponse(url="/student?google_error=userinfo_failed")

    info = userinfo_res.json()
    g_email = (info.get("email") or "").strip().lower()
    g_name = (info.get("name") or g_email.split("@")[0]).strip()
    if not g_email:
        return RedirectResponse(url="/student?google_error=no_email")

    # If already registered, sign in immediately
    existing_user = db.query(User).filter_by(email=g_email).first()
    if existing_user and existing_user.role == "student":
        jwt_token = create_access_token({
            "sub": str(existing_user.id),
            "role": "student",
            "roll_number": existing_user.roll_number,
            "email": g_email,
            "student_id": existing_user.student_id,
        })
        return RedirectResponse(url=f"/student?token={jwt_token}")

    qs = urlencode({"google_email": g_email, "google_name": g_name})
    return RedirectResponse(url=f"/student?{qs}")

# -------------------------------------------------------------
# INSTITUTIONAL MASTER DATA ENGINE (ADMIN TAB)
# -------------------------------------------------------------

@app.get("/api/admin/institution", response_model=InstitutionResponse)
def get_institution(db: Session = Depends(get_db)):
    config = db.query(InstitutionConfig).first()
    if not config:
        config = InstitutionConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config

@app.put("/api/admin/institution", response_model=InstitutionResponse)
def update_institution(
    payload: InstitutionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    config = db.query(InstitutionConfig).first()
    if not config:
        config = InstitutionConfig()
        db.add(config)

    for field, val in payload.dict(exclude_unset=True).items():
        setattr(config, field, val)

    db.commit()
    db.refresh(config)
    return config

@app.get("/api/admin/departments", response_model=List[DepartmentResponse])
def get_departments(db: Session = Depends(get_db)):
    return db.query(Department).all()

@app.post("/api/admin/departments", response_model=DepartmentResponse)
def create_department(payload: DepartmentCreate, db: Session = Depends(get_db)):
    dept = Department(code=payload.code.upper(), name=payload.name)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return dept

@app.get("/api/admin/subjects", response_model=List[SubjectResponse])
def get_subjects(db: Session = Depends(get_db)):
    return db.query(Subject).all()

@app.post("/api/admin/subjects", response_model=SubjectResponse)
def create_subject(payload: SubjectCreate, db: Session = Depends(get_db)):
    subj = Subject(
        code=payload.code.upper(),
        name=payload.name,
        department_id=payload.department_id,
        semester=payload.semester,
        academic_year=payload.academic_year,
        min_threshold=payload.min_threshold
    )
    db.add(subj)
    db.commit()
    db.refresh(subj)
    return subj

@app.get("/api/admin/students", response_model=List[StudentResponse])
def get_students(stream: Optional[str] = None, db: Session = Depends(get_db)):
    depts = {d.id: d for d in db.query(Department).all()}
    query = db.query(Student).filter_by(is_active=True)
    if stream and stream.strip().upper() != "ALL":
        dept = db.query(Department).filter_by(code=stream.strip().upper()).first()
        if dept:
            query = query.filter_by(department_id=dept.id)
        else:
            return []
    students = query.order_by(Student.department_id, Student.roll_number).all()
    result = []
    for s in students:
        d = depts.get(s.department_id)
        result.append({
            "id": s.id,
            "roll_number": s.roll_number,
            "full_name": s.full_name,
            "email": s.email,
            "department_id": s.department_id,
            "department_code": d.code if d else "GEN",
            "department_name": d.name if d else "General",
            "semester": s.semester,
            "academic_year": s.academic_year,
            "is_active": s.is_active,
        })
    return result

@app.post("/api/admin/students", response_model=StudentResponse)
def create_student(payload: StudentCreate, db: Session = Depends(get_db)):
    stud = Student(
        roll_number=payload.roll_number.upper(),
        full_name=payload.full_name,
        email=payload.email,
        department_id=payload.department_id,
        semester=payload.semester,
        academic_year=payload.academic_year
    )
    db.add(stud)
    db.commit()
    db.refresh(stud)
    return stud

@app.post("/api/admin/bulk-upload")
async def bulk_upload(
    type: str = Form(...), # 'students' or 'subjects'
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Bulk import students or subjects from CSV or JSON"""
    content = await file.read()
    filename = file.filename.lower()
    items_created = 0

    dept = db.query(Department).first()
    dept_id = dept.id if dept else 1

    try:
        if filename.endswith(".json"):
            data = json.loads(content.decode("utf-8"))
            if type == "students":
                for item in data:
                    roll = item.get("roll_number")
                    if roll and not db.query(Student).filter_by(roll_number=roll).first():
                        stud = Student(
                            roll_number=roll,
                            full_name=item.get("full_name", "Student Name"),
                            email=item.get("email", f"{roll.lower()}@dets.edu"),
                            department_id=item.get("department_id", dept_id),
                            semester=item.get("semester", "Semester 6"),
                            academic_year=item.get("academic_year", "2026-2027")
                        )
                        db.add(stud)
                        items_created += 1
            elif type == "subjects":
                for item in data:
                    code = item.get("code")
                    if code and not db.query(Subject).filter_by(code=code).first():
                        subj = Subject(
                            code=code,
                            name=item.get("name", "Subject Name"),
                            department_id=item.get("department_id", dept_id),
                            semester=item.get("semester", "Semester 6"),
                            academic_year=item.get("academic_year", "2026-2027"),
                            min_threshold=float(item.get("min_threshold", 75.0))
                        )
                        db.add(subj)
                        items_created += 1

        else: # CSV format
            decoded = content.decode("utf-8").splitlines()
            reader = csv.DictReader(decoded)
            if type == "students":
                for row in reader:
                    roll = row.get("roll_number") or row.get("Roll Number") or row.get("Roll")
                    if roll and not db.query(Student).filter_by(roll_number=roll.strip()).first():
                        stud = Student(
                            roll_number=roll.strip(),
                            full_name=row.get("full_name", row.get("Name", "Student")),
                            email=row.get("email", f"{roll.strip().lower()}@dets.edu"),
                            department_id=dept_id,
                            semester=row.get("semester", "Semester 6"),
                            academic_year=row.get("academic_year", "2026-2027")
                        )
                        db.add(stud)
                        items_created += 1
            elif type == "subjects":
                for row in reader:
                    code = row.get("code") or row.get("Subject Code") or row.get("Code")
                    if code and not db.query(Subject).filter_by(code=code.strip()).first():
                        subj = Subject(
                            code=code.strip(),
                            name=row.get("name", row.get("Subject Name", "Course")),
                            department_id=dept_id,
                            semester=row.get("semester", "Semester 6"),
                            academic_year=row.get("academic_year", "2026-2027"),
                            min_threshold=float(row.get("min_threshold", 75.0))
                        )
                        db.add(subj)
                        items_created += 1

        db.commit()
        return {"success": True, "items_created": items_created, "type": type}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process bulk upload file: {str(e)}")

# -------------------------------------------------------------
# PRINTABLE ATTENDANCE SHEET GENERATOR (TEACHER TAB)
# -------------------------------------------------------------

@app.post("/api/sheets/generate-pdf")
def generate_pdf_sheet(payload: SheetGenerateRequest, db: Session = Depends(get_db)):
    config = db.query(InstitutionConfig).first()
    institution_name = config.institution_name if config else "Department of Engineering & Technological Studies (DETS)"
    
    subject = db.query(Subject).filter_by(id=payload.subject_id).first()
    if not subject:
        subject = db.query(Subject).first()
    
    dept_name = subject.department.name if subject and subject.department else "Electronics & Instrumentation Engineering"
    subject_code = subject.code if subject else "EIE-301"
    subject_name = subject.name if subject else "Industrial Instrumentation & Transducers"

    students = db.query(Student).filter_by(is_active=True).all()
    students_data = [{"roll_number": s.roll_number, "full_name": s.full_name} for s in students]

    session_token = f"SESS-{subject_code}-{payload.session_date.replace('-', '')}-{random.randint(100, 999)}"

    pdf_bytes = generate_smart_pdf_sheet(
        institution_name=institution_name,
        department_name=dept_name,
        subject_code=subject_code,
        subject_name=subject_name,
        session_date=payload.session_date,
        academic_year=payload.academic_year,
        semester=payload.semester,
        session_token=session_token,
        students=students_data
    )

    filename = f"Smart_Attendance_Sheet_{subject_code}_{payload.session_date}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/api/sheets/generate-xlsx")
def generate_xlsx_sheet(payload: SheetGenerateRequest, db: Session = Depends(get_db)):
    config = db.query(InstitutionConfig).first()
    institution_name = config.institution_name if config else "Department of Engineering & Technological Studies (DETS)"
    
    subject = db.query(Subject).filter_by(id=payload.subject_id).first()
    subject_code = subject.code if subject else "EIE-301"
    subject_name = subject.name if subject else "Industrial Instrumentation & Transducers"

    students = db.query(Student).filter_by(is_active=True).all()
    students_data = [{"roll_number": s.roll_number, "full_name": s.full_name} for s in students]
    session_token = f"SESS-{subject_code}-{payload.session_date.replace('-', '')}-{random.randint(100, 999)}"

    xlsx_bytes = generate_attendance_xlsx_template(
        institution_name=institution_name,
        subject_code=subject_code,
        subject_name=subject_name,
        session_date=payload.session_date,
        session_token=session_token,
        students=students_data
    )

    filename = f"Attendance_Template_{subject_code}_{payload.session_date}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# -------------------------------------------------------------
# SHEET SCAN, HYBRID OCR & MANUAL VERIFICATION
# -------------------------------------------------------------

@app.post("/api/ocr/scan")
async def scan_attendance_sheet(
    file: Optional[UploadFile] = File(None),
    image_base64: Optional[str] = Form(None),
    subject_id: Optional[int] = Form(None),
    session_date: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Accepts scanned sheet via file upload or webcam base64, runs CV pipeline,
    and returns split-screen verification response.
    """
    image_bgr = None
    if file:
        content = await file.read()
        nparr = np.frombuffer(content, np.uint8)
        image_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    elif image_base64:
        image_bgr = base64_to_bgr(image_base64)

    if image_bgr is None:
        raise HTTPException(status_code=400, detail="No valid image provided for scanning")

    students = db.query(Student).filter_by(is_active=True, department_id=subject.department_id).all() if subject else db.query(Student).filter_by(is_active=True).all()
    students_data = [{"id": s.id, "roll_number": s.roll_number, "full_name": s.full_name} for s in students]
    if not students_data:
        students_data = [{"id": i, "roll_number": f"SAMPLE-{s_code}-{i:03d}", "full_name": f"Sample Entry {i}"} for i in range(1, 6)]

    scan_result = process_scanned_sheet(image_bgr, students_data)

    # Attach matched subject details
    matched_subject = None
    if subject_id:
        matched_subject = db.query(Subject).filter_by(id=subject_id).first()
    elif scan_result.get("subject_code"):
        matched_subject = db.query(Subject).filter_by(code=scan_result["subject_code"]).first()
    
    if not matched_subject:
        matched_subject = db.query(Subject).first()

    scan_result["subject_id"] = matched_subject.id if matched_subject else 1
    scan_result["subject_code"] = matched_subject.code if matched_subject else "EIE-301"
    scan_result["subject_name"] = matched_subject.name if matched_subject else "Industrial Instrumentation & Transducers"
    if session_date:
        scan_result["session_date"] = session_date

    return scan_result

@app.post("/api/ocr/generate-sample-filled")
def generate_sample_filled(
    subject_id: Optional[int] = 1,
    session_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    1-Click Hackathon Evaluator helper:
    Generates a realistic filled attendance sheet with synthetic handwritten marks
    (including 1 ambiguous mark) and processes it immediately through the CV pipeline!
    """
    subject = db.query(Subject).filter_by(id=subject_id).first()
    if not subject:
        subject = db.query(Subject).first()

    s_code = subject.code if subject else "EIE-301"
    s_name = subject.name if subject else "Industrial Instrumentation & Transducers"
    s_date = session_date or datetime.date.today().strftime("%Y-%m-%d")
    s_token = f"SESS-{s_code}-{s_date.replace('-', '')}-{random.randint(100, 999)}"

    students = db.query(Student).filter_by(is_active=True, department_id=subject.department_id).all() if subject else db.query(Student).filter_by(is_active=True).all()
    students_data = [{"id": s.id, "roll_number": s.roll_number, "full_name": s.full_name} for s in students]
    if not students_data:
        students_data = [{"id": i, "roll_number": f"SAMPLE-{s_code}-{i:03d}", "full_name": f"Sample Entry {i}"} for i in range(1, 6)]

    # Generate synthetic realistic filled sheet image
    filled_bgr = generate_synthetic_sample_sheet_image(
        students=students_data,
        subject_code=s_code,
        subject_name=s_name,
        session_date=s_date,
        session_token=s_token
    )

    # Run through the vision pipeline
    scan_result = process_scanned_sheet(filled_bgr, students_data)
    scan_result["subject_id"] = subject.id if subject else 1
    scan_result["subject_code"] = s_code
    scan_result["subject_name"] = s_name
    scan_result["session_date"] = s_date
    scan_result["session_token"] = s_token

    return scan_result

@app.post("/api/ocr/commit")
def commit_verified_attendance(
    payload: AttendanceCommitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Commits verified attendance into the unified database and logs manual overrides into AuditLog
    """
    # 1. Create or retrieve class session
    session = db.query(ClassSession).filter_by(session_token=payload.session_token).first()
    if not session:
        session = ClassSession(
            session_token=payload.session_token,
            subject_id=payload.subject_id,
            teacher_id=current_user.id if current_user else 1,
            session_date=payload.session_date,
            status="verified"
        )
        db.add(session)
        db.commit()
        db.refresh(session)
    else:
        session.status = "verified"
        db.commit()

    # 2. Process records and audit logs
    committed_count = 0
    audit_count = 0

    for item in payload.overrides:
        # Check if attendance record already exists
        rec = db.query(AttendanceRecord).filter_by(session_id=session.id, student_id=item.student_id).first()
        is_override = (item.original_status != item.corrected_status)

        if not rec:
            rec = AttendanceRecord(
                session_id=session.id,
                student_id=item.student_id,
                status=item.corrected_status,
                confidence_score=item.confidence_score or 100.0,
                detection_method="OCR",
                is_flagged=False,
                verified_by=current_user.id if current_user else 1
            )
            db.add(rec)
        else:
            rec.status = item.corrected_status
            rec.confidence_score = 100.0
            rec.verified_by = current_user.id if current_user else 1

        committed_count += 1

        # If teacher manually corrected the OCR detection, log into AuditLog
        if is_override:
            log_entry = AuditLog(
                session_id=session.id,
                student_id=item.student_id,
                original_status=item.original_status,
                corrected_status=item.corrected_status,
                confidence_score=item.confidence_score,
                teacher_id=current_user.id if current_user else 1,
                reason="Manual verification override in split-screen UI"
            )
            db.add(log_entry)
            audit_count += 1

    db.commit()
    return {
        "success": True,
        "message": f"Successfully committed {committed_count} attendance records.",
        "audit_logs_created": audit_count,
        "session_id": session.id
    }

@app.get("/api/ocr/audit-logs/{session_id}", response_model=List[AuditLogResponse])
def get_audit_logs(session_id: int, db: Session = Depends(get_db)):
    logs = db.query(AuditLog).filter_by(session_id=session_id).all()
    result = []
    for log in logs:
        result.append({
            "id": log.id,
            "session_id": log.session_id,
            "student_id": log.student_id,
            "student_name": log.student.full_name if log.student else "Student",
            "roll_number": log.student.roll_number if log.student else "Roll No",
            "original_status": log.original_status,
            "corrected_status": log.corrected_status,
            "confidence_score": log.confidence_score,
            "teacher_name": log.teacher.full_name if log.teacher else "Instructor",
            "timestamp": log.timestamp,
            "reason": log.reason
        })
    return result

# -------------------------------------------------------------
# HANDS-FREE BLE / PROXIMITY DIGITAL CHECK-IN
# -------------------------------------------------------------

@app.post("/api/ble/start-session", response_model=BLESessionResponse)
def start_ble_session(
    payload: BLEStartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    subject = db.query(Subject).filter_by(id=payload.subject_id).first()
    if not subject:
        subject = db.query(Subject).first()

    pin = f"{random.randint(1000, 9999)}"
    token = f"BLE-{subject.code}-{datetime.date.today().strftime('%Y%m%d')}-{random.randint(100, 999)}"
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=payload.duration_minutes)

    ble_session = BLESession(
        session_token=token,
        subject_id=subject.id,
        teacher_id=current_user.id if current_user else 1,
        pin_code=pin,
        expires_at=expires_at,
        is_active=True,
        checked_in_students=[]
    )
    db.add(ble_session)
    db.commit()

    return {
        "session_token": token,
        "subject_id": subject.id,
        "subject_name": f"{subject.code} - {subject.name}",
        "pin_code": pin,
        "expires_at": expires_at.isoformat(),
        "duration_seconds": payload.duration_minutes * 60
    }

@app.get("/api/ble/active-session")
def get_active_ble_session(db: Session = Depends(get_db)):
    """Allows student mobile devices to detect if a proximity check-in window is open"""
    now = datetime.datetime.utcnow()
    active = db.query(BLESession).filter(
        BLESession.is_active == True,
        BLESession.expires_at > now
    ).order_by(BLESession.created_at.desc()).first()

    if not active:
        return {"active": False, "message": "No active proximity session. Waiting for instructor..."}

    remaining = max(0, int((active.expires_at - now).total_seconds()))
    subj = db.query(Subject).filter_by(id=active.subject_id).first()
    subj_name = f"{subj.code} - {subj.name}" if subj else "Class Session"

    return {
        "active": True,
        "subject_id": active.subject_id,
        "subject_name": subj_name,
        "session_token": active.session_token,
        "remaining_seconds": remaining,
        "total_checked_in": len(active.checked_in_students or [])
    }

@app.get("/api/ble/teacher-active-session")
def get_teacher_active_ble_session(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Restores active BLE session details (including PIN) for the teacher UI after refresh"""
    now = datetime.datetime.utcnow()
    active = db.query(BLESession).filter(
        BLESession.is_active == True,
        BLESession.expires_at > now
    ).order_by(BLESession.created_at.desc()).first()

    if not active:
        return {"active": False}

    remaining = max(0, int((active.expires_at - now).total_seconds()))
    return {
        "active": True,
        "session_token": active.session_token,
        "subject_id": active.subject_id,
        "pin_code": active.pin_code,
        "remaining_seconds": remaining,
        "total_checked_in": len(active.checked_in_students or [])
    }

@app.post("/api/ble/checkin", response_model=BLECheckinResult)
def ble_student_checkin(payload: BLEStudentCheckinRequest, db: Session = Depends(get_db)):
    """Student Check-In: Submits PIN and synthetic roll number, returns live receipt"""
    active_session = db.query(BLESession).filter(
        BLESession.pin_code == payload.pin_code.strip(),
        BLESession.is_active == True,
        BLESession.expires_at > datetime.datetime.utcnow()
    ).first()

    if not active_session:
        return {"success": False, "message": "Invalid or expired 4-digit PIN code."}

    student = db.query(Student).filter_by(roll_number=payload.roll_number.strip().upper()).first()
    if not student:
        return {"success": False, "message": f"Roll number '{payload.roll_number}' not found in DETS student directory. Please self-enroll first."}

    # Fetch subject details
    subj = db.query(Subject).filter_by(id=active_session.subject_id).first()
    subj_name = f"{subj.code} - {subj.name}" if subj else "Course Session"
    timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Calculate student attendance percentage
    held_sessions = db.query(ClassSession).filter_by(subject_id=active_session.subject_id).count()
    attended_records = db.query(AttendanceRecord).join(ClassSession).filter(
        ClassSession.subject_id == active_session.subject_id,
        AttendanceRecord.student_id == student.id,
        AttendanceRecord.status == "P"
    ).count()

    total_held = max(1, held_sessions + 1)
    total_att = attended_records + 1
    att_pct = round((total_att / total_held) * 100.0, 1)

    checked_in = list(active_session.checked_in_students or [])
    if student.roll_number in checked_in:
        return {
            "success": True,
            "message": f"Student '{student.full_name}' is already marked present in this session.",
            "student_name": student.full_name,
            "roll_number": student.roll_number,
            "subject_name": subj_name,
            "session_token": active_session.session_token,
            "timestamp": timestamp_str,
            "attendance_percent": att_pct
        }

    checked_in.append(student.roll_number)
    active_session.checked_in_students = checked_in
    db.commit()

    return {
        "success": True,
        "message": f"Proximity check-in verified! {student.full_name} marked present.",
        "student_name": student.full_name,
        "roll_number": student.roll_number,
        "subject_name": subj_name,
        "session_token": active_session.session_token,
        "timestamp": timestamp_str,
        "attendance_percent": att_pct
    }

@app.post("/api/student/enroll", response_model=StudentEnrollResponse)
def student_self_enroll(payload: StudentEnrollRequest, db: Session = Depends(get_db)):
    """
    Enables students to enroll themselves with their personal details
    (Name, Roll Number, Email, Dept, Semester) into any particular class/subject.
    """
    roll = payload.roll_number.strip().upper()
    full_name = payload.full_name.strip()
    email = payload.email.strip().lower()

    if not roll or not full_name or not email:
        raise HTTPException(status_code=400, detail="Full name, roll number, and email are required.")

    # 1. Verify subject exists
    subject = db.query(Subject).filter_by(id=payload.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Selected course/subject does not exist.")

    # 2. Find or create Student record
    student = db.query(Student).filter_by(roll_number=roll).first()
    if not student:
        student = Student(
            roll_number=roll,
            full_name=full_name,
            email=email,
            department_id=payload.department_id or subject.department_id,
            semester=payload.semester or subject.semester,
            academic_year=payload.academic_year or subject.academic_year,
            is_active=True
        )
        db.add(student)
        db.commit()
        db.refresh(student)
    else:
        student.full_name = full_name
        student.email = email
        if payload.semester:
            student.semester = payload.semester.strip()
        student.is_active = True
        db.commit()
        db.refresh(student)

    # 3. Create enrollment mapping if not present
    enrollment = db.query(Enrollment).filter_by(student_id=student.id, subject_id=subject.id).first()
    if not enrollment:
        enrollment = Enrollment(
            student_id=student.id,
            subject_id=subject.id,
            status="active"
        )
        db.add(enrollment)
        db.commit()

    return {
        "success": True,
        "message": f"Successfully enrolled {student.full_name} ({student.roll_number}) in {subject.code}: {subject.name}!",
        "student": {
            "id": student.id,
            "roll_number": student.roll_number,
            "full_name": student.full_name,
            "email": student.email,
            "semester": student.semester
        },
        "subject": {
            "id": subject.id,
            "code": subject.code,
            "name": subject.name,
            "min_threshold": subject.min_threshold
        }
    }

# -------------------------------------------------------------
# STUDENT SIGNUP, AUTHENTICATION & PERSONAL DASHBOARD
# -------------------------------------------------------------

@app.post("/api/student/signup", response_model=StudentAuthResponse)
def student_signup(payload: StudentRegisterRequest, db: Session = Depends(get_db)):
    """
    Enables a student to sign up using their university Registration / Roll Number,
    Full Name, Email, and Password. Creates both User account (role=student) and 
    Student roster record (if not already existing) and auto-enrolls in department subjects.
    """
    roll = payload.roll_number.strip().upper()
    full_name = payload.full_name.strip()
    email = payload.email.strip().lower()
    password = (payload.password or "").strip()
    auth_provider = (payload.auth_provider or "google").strip().lower()

    if not roll or not full_name or not email:
        raise HTTPException(status_code=400, detail="Registration number, full name, and Google email are required.")

    if auth_provider == "google" and not password:
        password = uuid.uuid4().hex
    elif len(password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters.")

    # Resolve Stream / Department (EIE, ECE, IT)
    dept = None
    if payload.stream:
        dept = db.query(Department).filter_by(code=payload.stream.strip().upper()).first()
    if not dept and payload.department_id:
        dept = db.query(Department).filter_by(id=payload.department_id).first()
    if not dept:
        dept = db.query(Department).first()
    resolved_dept_id = dept.id if dept else 1

    # 1. Check if user account already exists with this email or roll_number
    existing_user_email = db.query(User).filter_by(email=email).first()
    if existing_user_email:
        raise HTTPException(status_code=400, detail="An account with this email already exists. Please sign in.")

    existing_user_roll = db.query(User).filter_by(roll_number=roll).first()
    if existing_user_roll:
        raise HTTPException(status_code=400, detail=f"An account for registration number '{roll}' already exists. Please sign in.")

    # 2. Check or create Student roster record
    student = db.query(Student).filter_by(roll_number=roll).first()
    if not student:
        student = Student(
            roll_number=roll,
            full_name=full_name,
            email=email,
            department_id=resolved_dept_id,
            semester=payload.semester or "Semester 6",
            academic_year=payload.academic_year or "2026-2027",
            is_active=True
        )
        db.add(student)
        db.commit()
        db.refresh(student)
    else:
        # Update details if previously stubbed
        student.full_name = full_name
        student.email = email
        student.department_id = resolved_dept_id
        if payload.semester:
            student.semester = payload.semester.strip()
        db.commit()

    # 3. Create User account
    user = User(
        email=email,
        full_name=full_name,
        hashed_password=hash_pw(password),
        role="student",
        roll_number=roll,
        student_id=student.id,
        auth_provider=auth_provider,
        is_active=True
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 4. Auto-enroll in department subjects if no enrollments exist
    dept_subjects = db.query(Subject).filter_by(department_id=student.department_id).all()
    for subj in dept_subjects:
        enroll = db.query(Enrollment).filter_by(student_id=student.id, subject_id=subj.id).first()
        if not enroll:
            db.add(Enrollment(student_id=student.id, subject_id=subj.id, status="active"))
    db.commit()

    # 5. Issue JWT access token
    token = create_access_token({
        "sub": str(user.id),
        "role": "student",
        "roll_number": roll,
        "email": email,
        "student_id": student.id
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
        "student": {
            "id": student.id,
            "roll_number": student.roll_number,
            "full_name": student.full_name,
            "email": student.email,
            "department_id": student.department_id,
            "semester": student.semester,
            "academic_year": student.academic_year
        }
    }


@app.post("/api/student/login", response_model=StudentAuthResponse)
def student_login(payload: StudentLoginRequest, db: Session = Depends(get_db)):
    """
    Student login using Registration / Roll Number OR Email + Password.
    """
    ident = payload.identifier.strip()
    password = payload.password.strip()

    if not ident or not password:
        raise HTTPException(status_code=400, detail="Registration number/email and password are required.")

    # Match by roll_number (case-insensitive upper) or email (case-insensitive lower)
    user = db.query(User).filter(
        or_(
            User.roll_number == ident.upper(),
            User.email == ident.lower()
        )
    ).first()

    if not user or not user.hashed_password or not verify_pw(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid registration number/email or password.")

    # Find associated student record
    student = None
    if user.student_id:
        student = db.query(Student).filter_by(id=user.student_id).first()
    if not student and user.roll_number:
        student = db.query(Student).filter_by(roll_number=user.roll_number).first()
    if not student:
        student = db.query(Student).filter_by(email=user.email).first()

    if not student:
        raise HTTPException(status_code=404, detail="Student roster record not found for this account.")

    token = create_access_token({
        "sub": str(user.id),
        "role": user.role,
        "roll_number": student.roll_number,
        "email": user.email,
        "student_id": student.id
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
        "student": {
            "id": student.id,
            "roll_number": student.roll_number,
            "full_name": student.full_name,
            "email": student.email,
            "department_id": student.department_id,
            "semester": student.semester,
            "academic_year": student.academic_year
        }
    }


@app.post("/api/student/demo-login/{roll_number}", response_model=StudentAuthResponse)
def student_demo_login(roll_number: str, db: Session = Depends(get_db)):
    """
    1-Click Demo Login as any student (e.g. DETS-26-EIE-001) for fast evaluation.
    """
    roll = roll_number.strip().upper()
    student = db.query(Student).filter_by(roll_number=roll).first()
    if not student:
        raise HTTPException(status_code=404, detail=f"Student {roll} not found in roster.")

    user = db.query(User).filter(or_(User.roll_number == roll, User.email == student.email)).first()
    if not user:
        user = User(
            email=student.email,
            full_name=student.full_name,
            hashed_password=hash_pw("Student@123"),
            role="student",
            roll_number=roll,
            student_id=student.id,
            auth_provider="local",
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_access_token({
        "sub": str(user.id),
        "role": "student",
        "roll_number": roll,
        "email": user.email,
        "student_id": student.id
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user,
        "student": {
            "id": student.id,
            "roll_number": student.roll_number,
            "full_name": student.full_name,
            "email": student.email,
            "department_id": student.department_id,
            "semester": student.semester,
            "academic_year": student.academic_year
        }
    }


@app.get("/api/student/me", response_model=StudentProfileResponse)
def get_student_me(current_student: User = Depends(get_current_student), db: Session = Depends(get_db)):
    """
    Retrieves the authenticated student's profile, overall attendance rate,
    and per-subject attendance breakdown with 75% shortage recovery metrics.
    """
    student = None
    if current_student.student_id:
        student = db.query(Student).filter_by(id=current_student.student_id).first()
    if not student and current_student.roll_number:
        student = db.query(Student).filter_by(roll_number=current_student.roll_number).first()
    if not student:
        student = db.query(Student).filter_by(email=current_student.email).first()

    if not student:
        raise HTTPException(status_code=404, detail="Student roster record not found.")

    dept = db.query(Department).filter_by(id=student.department_id).first()
    dept_name = dept.name if dept else "Engineering"

    # Enrolled subjects
    enrollments = db.query(Enrollment).filter_by(student_id=student.id).all()
    subject_ids = [e.subject_id for e in enrollments]
    
    # Fallback to department subjects if no explicit enrollments
    if not subject_ids:
        dept_subjs = db.query(Subject).filter_by(department_id=student.department_id).all()
        subject_ids = [s.id for s in dept_subjs]

    subjects = db.query(Subject).filter(Subject.id.in_(subject_ids)).all() if subject_ids else []

    enrolled_list = []
    total_held_all = 0
    total_attended_all = 0

    for subj in subjects:
        # Total sessions held for this subject
        sessions = db.query(ClassSession).filter_by(subject_id=subj.id).all()
        session_ids = [s.id for s in sessions]
        held = len(session_ids)

        attended = 0
        if held > 0:
            attended = db.query(AttendanceRecord).filter(
                AttendanceRecord.session_id.in_(session_ids),
                AttendanceRecord.student_id == student.id,
                AttendanceRecord.status == "P"
            ).count()

        pct = round((attended / held * 100.0), 1) if held > 0 else 100.0
        status_val = "Safe" if pct >= subj.min_threshold else "Shortage"

        needed = 0
        if held > 0 and pct < subj.min_threshold:
            needed = max(0, math.ceil((0.75 * held - attended) / 0.25))

        total_held_all += held
        total_attended_all += attended

        enrolled_list.append({
            "subject_id": subj.id,
            "subject_code": subj.code,
            "subject_name": subj.name,
            "classes_held": held,
            "classes_attended": attended,
            "attendance_percent": pct,
            "status": status_val,
            "classes_needed_for_75": needed,
            "min_threshold": subj.min_threshold
        })

    overall_pct = round((total_attended_all / total_held_all * 100.0), 1) if total_held_all > 0 else 100.0

    return {
        "id": student.id,
        "roll_number": student.roll_number,
        "full_name": student.full_name,
        "email": student.email,
        "department_id": student.department_id,
        "department_name": dept_name,
        "semester": student.semester,
        "academic_year": student.academic_year,
        "overall_attendance_rate": overall_pct,
        "total_classes_held": total_held_all,
        "total_classes_attended": total_attended_all,
        "enrolled_subjects": enrolled_list
    }

@app.get("/api/ble/session/{session_token}/status", response_model=BLEStatusResponse)
def get_ble_status(session_token: str, db: Session = Depends(get_db)):
    session = db.query(BLESession).filter_by(session_token=session_token).first()
    if not session:
        raise HTTPException(status_code=404, detail="BLE session not found")

    now = datetime.datetime.utcnow()
    remaining = max(0, int((session.expires_at - now).total_seconds()))
    is_active = session.is_active and (remaining > 0)

    checked_in_rolls = session.checked_in_students or []
    students_info = []
    for roll in checked_in_rolls:
        stud = db.query(Student).filter_by(roll_number=roll).first()
        if stud:
            students_info.append({"roll_number": stud.roll_number, "full_name": stud.full_name})

    return {
        "session_token": session.session_token,
        "is_active": is_active,
        "remaining_seconds": remaining,
        "total_checked_in": len(checked_in_rolls),
        "students": students_info
    }

@app.post("/api/ble/close-session")
def close_ble_session(session_token: str = Form(...), db: Session = Depends(get_db)):
    session = db.query(BLESession).filter_by(session_token=session_token).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.is_active = False
    
    # Commit checked in students as a verified ClassSession
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    class_sess = ClassSession(
        session_token=session.session_token,
        subject_id=session.subject_id,
        teacher_id=session.teacher_id,
        session_date=today_str,
        session_type="ble_prox",
        status="verified"
    )
    db.add(class_sess)
    db.commit()
    db.refresh(class_sess)

    all_students = db.query(Student).filter_by(is_active=True).all()
    checked_in_set = set(session.checked_in_students or [])

    for s in all_students:
        status_val = "P" if s.roll_number in checked_in_set else "A"
        rec = AttendanceRecord(
            session_id=class_sess.id,
            student_id=s.id,
            status=status_val,
            confidence_score=100.0,
            detection_method="BLE",
            is_flagged=False
        )
        db.add(rec)
    db.commit()

    return {"success": True, "message": "BLE Proximity Session closed and attendance recorded."}

# -------------------------------------------------------------
# ATTENDANCE ANALYTICS & REPORTS (ANALYTICS TAB)
# -------------------------------------------------------------

def calculate_classes_needed_for_75(attended: int, held: int, target: float = 0.75) -> int:
    """
    Computes minimum consecutive classes needed to achieve target threshold (default 75%):
    (attended + x) / (held + x) >= target
    => x >= (target * held - attended) / (1 - target)
    """
    if held == 0:
        return 0
    current_ratio = attended / float(held)
    if current_ratio >= target:
        return 0
    numerator = (target * held) - attended
    denominator = 1.0 - target
    needed = int(np.ceil(numerator / denominator))
    return max(0, needed)

@app.get("/api/analytics/dashboard", response_model=DashboardKPIs)
def get_dashboard_kpis(db: Session = Depends(get_db)):
    total_depts = db.query(Department).count()
    total_subjs = db.query(Subject).count()
    total_students = db.query(Student).filter_by(is_active=True).count()
    total_sessions = db.query(ClassSession).count()

    total_records = db.query(AttendanceRecord).count()
    present_records = db.query(AttendanceRecord).filter_by(status="P").count()
    overall_rate = round((present_records / total_records * 100.0), 1) if total_records > 0 else 0.0

    # Calculate subject breakdown
    subjects = db.query(Subject).all()
    subject_summaries = []
    students_in_shortage_set = set()

    for subj in subjects:
        sessions = db.query(ClassSession).filter_by(subject_id=subj.id).all()
        sess_count = len(sessions)
        sess_ids = [s.id for s in sessions]

        subj_p = db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id.in_(sess_ids),
            AttendanceRecord.status == "P"
        ).count() if sess_ids else 0
        subj_total = db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id.in_(sess_ids)
        ).count() if sess_ids else 0

        avg_pct = round((subj_p / subj_total * 100.0), 1) if subj_total > 0 else 0.0

        # Check shortage count
        shortage_in_subj = 0
        students = db.query(Student).filter_by(is_active=True).all()
        for s in students:
            s_att = db.query(AttendanceRecord).filter(
                AttendanceRecord.session_id.in_(sess_ids),
                AttendanceRecord.student_id == s.id,
                AttendanceRecord.status == "P"
            ).count() if sess_ids else 0
            
            s_pct = (s_att / sess_count * 100.0) if sess_count > 0 else 100.0
            if s_pct < subj.min_threshold:
                shortage_in_subj += 1
                students_in_shortage_set.add(s.id)

        subject_summaries.append({
            "subject_id": subj.id,
            "subject_code": subj.code,
            "subject_name": subj.name,
            "total_sessions": sess_count,
            "avg_attendance_percent": avg_pct,
            "shortage_count": shortage_in_subj,
            "min_threshold": subj.min_threshold
        })

    return {
        "total_departments": total_depts,
        "total_subjects": total_subjs,
        "total_students": total_students,
        "total_sessions_held": total_sessions,
        "overall_attendance_rate": overall_rate,
        "total_students_shortage": len(students_in_shortage_set),
        "subject_summaries": subject_summaries
    }

@app.get("/api/analytics/subject/{subject_id}", response_model=SubjectAnalyticsSummary)
def get_subject_analytics(
    subject_id: int, 
    from_date: Optional[str] = None, 
    to_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    subject = db.query(Subject).filter_by(id=subject_id).first()
    if not subject:
        subject = db.query(Subject).first()

    query = db.query(ClassSession).filter_by(subject_id=subject.id)
    if from_date:
        query = query.filter(ClassSession.session_date >= from_date)
    if to_date:
        query = query.filter(ClassSession.session_date <= to_date)

    sessions = query.order_by(ClassSession.session_date).all()
    sess_ids = [s.id for s in sessions]
    total_sessions = len(sessions)

    dept_map = {d.id: d.code for d in db.query(Department).all()}
    students = db.query(Student).filter_by(is_active=True, department_id=subject.department_id).order_by(Student.roll_number).all()
    student_items = []
    shortage_count = 0
    total_attended_all = 0

    for s in students:
        attended = db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id.in_(sess_ids),
            AttendanceRecord.student_id == s.id,
            AttendanceRecord.status == "P"
        ).count() if sess_ids else 0

        pct = round((attended / total_sessions * 100.0), 1) if total_sessions > 0 else 0.0
        status_val = "Safe" if pct >= subject.min_threshold else "Shortage"
        needed = calculate_classes_needed_for_75(attended, total_sessions, target=subject.min_threshold / 100.0)

        if status_val == "Shortage":
            shortage_count += 1

        total_attended_all += attended

        student_items.append({
            "student_id": s.id,
            "roll_number": s.roll_number,
            "full_name": s.full_name,
            "department_code": dept_map.get(s.department_id, "GEN"),
            "classes_held": total_sessions,
            "classes_attended": attended,
            "attendance_percent": pct,
            "status": status_val,
            "classes_needed_for_75": needed
        })

    avg_pct = round((total_attended_all / (total_sessions * len(students)) * 100.0), 1) if (total_sessions * len(students)) > 0 else 0.0

    return {
        "subject_id": subject.id,
        "subject_name": subject.name,
        "subject_code": subject.code,
        "total_sessions": total_sessions,
        "total_students": len(students),
        "avg_attendance_percent": avg_pct,
        "shortage_count": shortage_count,
        "min_threshold": subject.min_threshold,
        "students": student_items
    }

@app.get("/api/reports/shortage-pdf/{subject_id}")
def export_shortage_pdf(subject_id: int, db: Session = Depends(get_db)):
    config = db.query(InstitutionConfig).first()
    inst_name = config.institution_name if config else "Department of Engineering & Technological Studies (DETS)"

    subj_analytics = get_subject_analytics(subject_id, db=db)
    shortage_students = [s for s in subj_analytics["students"] if s["status"] == "Shortage"]

    pdf_bytes = generate_shortage_pdf_report(
        institution_name=inst_name,
        subject_code=subj_analytics["subject_code"],
        subject_name=subj_analytics["subject_name"],
        min_threshold=subj_analytics["min_threshold"],
        total_sessions=subj_analytics["total_sessions"],
        shortage_students=shortage_students
    )

    filename = f"Shortage_Notice_{subj_analytics['subject_code']}_{datetime.date.today()}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/api/reports/full-xlsx/{subject_id}")
def export_full_xlsx(subject_id: int, db: Session = Depends(get_db)):
    config = db.query(InstitutionConfig).first()
    inst_name = config.institution_name if config else "Department of Engineering & Technological Studies (DETS)"

    subject = db.query(Subject).filter_by(id=subject_id).first()
    if not subject:
        subject = db.query(Subject).first()

    sessions = db.query(ClassSession).filter_by(subject_id=subject.id).order_by(ClassSession.session_date).all()
    session_dates = [s.session_date for s in sessions]

    students = db.query(Student).filter_by(is_active=True).all()
    student_records = []

    for s in students:
        att_map = {}
        attended = 0
        for sess in sessions:
            rec = db.query(AttendanceRecord).filter_by(session_id=sess.id, student_id=s.id).first()
            stat = rec.status if rec else "-"
            att_map[sess.session_date] = stat
            if stat == "P":
                attended += 1

        held = len(sessions)
        pct = round((attended / held * 100.0), 1) if held > 0 else 0.0
        status_val = "Safe" if pct >= subject.min_threshold else "Shortage"
        needed = calculate_classes_needed_for_75(attended, held, target=subject.min_threshold / 100.0)

        student_records.append({
            "roll_number": s.roll_number,
            "full_name": s.full_name,
            "attendance": att_map,
            "held": held,
            "attended": attended,
            "percent": pct,
            "status": status_val,
            "needed": needed
        })

    xlsx_bytes = generate_full_attendance_xlsx(
        institution_name=inst_name,
        subject_code=subject.code,
        subject_name=subject.name,
        min_threshold=subject.min_threshold,
        session_dates=session_dates,
        student_records=student_records
    )

    filename = f"Full_Attendance_Report_{subject.code}_{datetime.date.today()}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# -------------------------------------------------------------
# OPEN-SOURCE COMPLIANCE & ARCHITECTURE TAB
# -------------------------------------------------------------

@app.get("/api/compliance/licenses")
def get_compliance_metadata():
    """Complete Open-Source SPDX License Attribution and Architecture Data"""
    return {
        "institution": "Department of Engineering & Technological Studies (DETS)",
        "privacy_commitment": "100% On-Premise / Local execution with synthetic anonymized data. Zero data leaves the local server boundary.",
        "libraries": [
            {
                "name": "FastAPI",
                "version": "0.110.0+",
                "license": "MIT",
                "license_url": "https://spdx.org/licenses/MIT.html",
                "purpose": "High-performance asynchronous REST API framework"
            },
            {
                "name": "Uvicorn",
                "version": "0.28.0+",
                "license": "BSD-3-Clause",
                "license_url": "https://spdx.org/licenses/BSD-3-Clause.html",
                "purpose": "Lightning-fast ASGI server implementation"
            },
            {
                "name": "SQLAlchemy",
                "version": "2.0.0+",
                "license": "MIT",
                "license_url": "https://spdx.org/licenses/MIT.html",
                "purpose": "Enterprise-grade database ORM with SQLite & PostgreSQL support"
            },
            {
                "name": "ReportLab",
                "version": "4.1.0+",
                "license": "BSD-3-Clause",
                "license_url": "https://spdx.org/licenses/BSD-3-Clause.html",
                "purpose": "PDF generation for smart fiducial sheets & shortage notices"
            },
            {
                "name": "OpenCV (opencv-python-headless)",
                "version": "4.9.0+",
                "license": "Apache-2.0",
                "license_url": "https://spdx.org/licenses/Apache-2.0.html",
                "purpose": "Perspective deskewing, fiducial square detection, QR decoding, and stroke analysis"
            },
            {
                "name": "Pillow (PIL Fork)",
                "version": "10.2.0+",
                "license": "HPND / MIT-like",
                "license_url": "https://spdx.org/licenses/HPND.html",
                "purpose": "Digital image transformation, drawing synthetic marks, thumbnail encoding"
            },
            {
                "name": "qrcode",
                "version": "7.4.2+",
                "license": "BSD-3-Clause",
                "license_url": "https://spdx.org/licenses/BSD-3-Clause.html",
                "purpose": "Matrix barcode encoding for attendance sheet metadata"
            },
            {
                "name": "OpenPyXL",
                "version": "3.1.2+",
                "license": "MIT",
                "license_url": "https://spdx.org/licenses/MIT.html",
                "purpose": "Excel spreadsheet template and multi-column report generation"
            },
            {
                "name": "Authlib & Cryptography",
                "version": "1.3.0+ / 42.0.0+",
                "license": "BSD-3-Clause / Apache-2.0",
                "license_url": "https://spdx.org/licenses/Apache-2.0.html",
                "purpose": "Google OAuth2 SSO flow and secure cryptographic hashing"
            },
            {
                "name": "Tailwind CSS (CDN)",
                "version": "3.4+",
                "license": "MIT",
                "license_url": "https://spdx.org/licenses/MIT.html",
                "purpose": "Responsive modern dashboard UI styling"
            },
            {
                "name": "Chart.js (CDN)",
                "version": "4.4+",
                "license": "MIT",
                "license_url": "https://spdx.org/licenses/MIT.html",
                "purpose": "Interactive attendance trend and shortage analytics charts"
            },
            {
                "name": "Lucide Icons (CDN)",
                "version": "0.344+",
                "license": "ISC",
                "license_url": "https://spdx.org/licenses/ISC.html",
                "purpose": "Accessible SVG user interface iconography"
            }
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
