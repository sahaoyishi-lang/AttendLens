"""
AttendLens - Pydantic Request & Response Data Schemas
Validated against Python 3.10+ and Pydantic v2
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

# ----------------- AUTH SCHEMAS -----------------

class UserLogin(BaseModel):
    email: str
    password: str

class UserRegister(BaseModel):
    email: str
    full_name: str
    password: str
    role: str = "teacher"

class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    auth_provider: str
    is_active: bool

    class Config:
        from_attributes = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# ----------------- INSTITUTION & MASTER DATA -----------------

class InstitutionUpdate(BaseModel):
    institution_name: Optional[str] = None
    institution_code: Optional[str] = None
    min_attendance_threshold: Optional[float] = None
    current_academic_year: Optional[str] = None
    current_semester: Optional[str] = None
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    cloud_storage_path: Optional[str] = None
    webhook_url: Optional[str] = None

class InstitutionResponse(BaseModel):
    id: int
    institution_name: str
    institution_code: str
    min_attendance_threshold: float
    current_academic_year: str
    current_semester: str
    google_client_id: Optional[str]
    cloud_storage_path: Optional[str]
    webhook_url: Optional[str]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

class DepartmentCreate(BaseModel):
    code: str
    name: str

class DepartmentResponse(BaseModel):
    id: int
    code: str
    name: str

    class Config:
        from_attributes = True

class SubjectCreate(BaseModel):
    code: str
    name: str
    department_id: int
    semester: str = "Semester 6"
    academic_year: str = "2026-2027"
    min_threshold: float = 75.0

class SubjectResponse(BaseModel):
    id: int
    code: str
    name: str
    department_id: int
    semester: str
    academic_year: str
    min_threshold: float

    class Config:
        from_attributes = True

class StudentCreate(BaseModel):
    roll_number: str
    full_name: str
    email: str
    department_id: int
    semester: str = "Semester 6"
    academic_year: str = "2026-2027"

class StudentResponse(BaseModel):
    id: int
    roll_number: str
    full_name: str
    email: str
    department_id: int
    semester: str
    academic_year: str
    is_active: bool

    class Config:
        from_attributes = True

# ----------------- SHEET GENERATION -----------------

class SheetGenerateRequest(BaseModel):
    subject_id: int
    session_date: str # YYYY-MM-DD
    academic_year: str = "2026-2027"
    semester: str = "Semester 6"
    format: str = "pdf" # 'pdf' or 'xlsx'

# ----------------- OCR & VERIFICATION -----------------

class CellCropInfo(BaseModel):
    roll_number: str
    student_name: str
    student_id: int
    detected_status: str # 'P', 'A', 'UNCERTAIN'
    confidence_score: float # 0 to 100
    is_flagged: bool
    flag_reason: Optional[str] = None
    crop_base64: str # Base64 encoded JPEG thumbnail of the cell
    bbox: List[int] # [x, y, w, h] on canonical sheet

class SheetScanResponse(BaseModel):
    session_token: str
    subject_id: Optional[int]
    subject_code: Optional[str]
    subject_name: Optional[str]
    session_date: str
    total_students: int
    present_count: int
    absent_count: int
    uncertain_count: int
    annotated_sheet_base64: str # Full sheet with color-coded bounding boxes
    cells: List[CellCropInfo]

class ManualOverrideItem(BaseModel):
    student_id: int
    original_status: str
    corrected_status: str
    confidence_score: Optional[float] = 100.0

class AttendanceCommitRequest(BaseModel):
    session_token: str
    subject_id: int
    session_date: str
    overrides: List[ManualOverrideItem] = []

class AuditLogResponse(BaseModel):
    id: int
    session_id: int
    student_id: int
    student_name: Optional[str]
    roll_number: Optional[str]
    original_status: str
    corrected_status: str
    confidence_score: Optional[float]
    teacher_name: Optional[str]
    timestamp: datetime
    reason: str

    class Config:
        from_attributes = True

# ----------------- BLE CHECK-IN -----------------

class BLEStartRequest(BaseModel):
    subject_id: int
    duration_minutes: int = 2

class BLESessionResponse(BaseModel):
    session_token: str
    subject_id: int
    subject_name: str
    pin_code: str
    expires_at: str
    duration_seconds: int

class BLEStudentCheckinRequest(BaseModel):
    pin_code: str
    roll_number: str

class BLECheckinResult(BaseModel):
    success: bool
    message: str
    student_name: Optional[str] = None
    roll_number: Optional[str] = None
    subject_name: Optional[str] = None
    session_token: Optional[str] = None
    timestamp: Optional[str] = None
    attendance_percent: Optional[float] = None

class BLEStatusResponse(BaseModel):
    session_token: str
    is_active: bool
    remaining_seconds: int
    total_checked_in: int
    students: List[Dict[str, Any]]

# ----------------- ANALYTICS & REPORTS -----------------

class StudentAnalyticsItem(BaseModel):
    student_id: int
    roll_number: str
    full_name: str
    classes_held: int
    classes_attended: int
    attendance_percent: float
    status: str # 'Safe' vs 'Shortage'
    classes_needed_for_75: int # 0 if already >= 75%

class SubjectAnalyticsSummary(BaseModel):
    subject_id: int
    subject_name: str
    subject_code: str
    total_sessions: int
    total_students: int
    avg_attendance_percent: float
    shortage_count: int
    min_threshold: float
    students: List[StudentAnalyticsItem]

class DashboardKPIs(BaseModel):
    total_departments: int
    total_subjects: int
    total_students: int
    total_sessions_held: int
    overall_attendance_rate: float
    total_students_shortage: int
    subject_summaries: List[Dict[str, Any]]

# ----------------- STUDENT SELF-ENROLLMENT -----------------

class StudentEnrollRequest(BaseModel):
    full_name: str
    roll_number: str
    email: str
    department_id: Optional[int] = 1
    subject_id: int
    semester: Optional[str] = "Semester 6"
    academic_year: Optional[str] = "2026-2027"

class StudentEnrollResponse(BaseModel):
    success: bool
    message: str
    student: Dict[str, Any]
    subject: Dict[str, Any]
