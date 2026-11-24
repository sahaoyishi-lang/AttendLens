"""
AttendLens - Smart Attendance Sheet Generator Service
Generates:
1. Smart PDF Sheet: 4 fiducial alignment corner squares, header metadata QR code,
   and structured student attendance grid for computer vision parsing.
2. Formatted XLSX Sheet: Excel attendance template with institutional styling.
100% Open-Source (ReportLab, OpenPyXL, Pillow, qrcode)
"""
import io
import os
import qrcode
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

PAGE_WIDTH, PAGE_HEIGHT = A4 # 595.27 x 841.89 points
FIDUCIAL_SIZE = 32 # points (approx 11.3 mm)
MARGIN = 28 # points

def generate_qr_image(content: str, size_px: int = 150) -> Image.Image:
    """Generate high-contrast PIL QR code image"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=1,
    )
    qr.add_data(content)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")

def generate_smart_pdf_sheet(
    institution_name: str,
    department_name: str,
    subject_code: str,
    subject_name: str,
    session_date: str,
    academic_year: str,
    semester: str,
    session_token: str,
    students: list # list of dicts: {'roll_number': str, 'full_name': str}
) -> bytes:
    """
    Generate print-ready Smart Attendance PDF Sheet with:
    - 4 solid black corner fiducial squares for cv2 alignment
    - Header metadata QR code (subject_code|session_date|session_token)
    - Standardized student grid with exact box coordinates
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    # 1. Draw 4 Solid Black Fiducial Corner Squares for CV deskewing
    c.setFillColor(colors.black)
    # Top-Left
    c.rect(MARGIN, PAGE_HEIGHT - MARGIN - FIDUCIAL_SIZE, FIDUCIAL_SIZE, FIDUCIAL_SIZE, fill=1, stroke=0)
    # Top-Right
    c.rect(PAGE_WIDTH - MARGIN - FIDUCIAL_SIZE, PAGE_HEIGHT - MARGIN - FIDUCIAL_SIZE, FIDUCIAL_SIZE, FIDUCIAL_SIZE, fill=1, stroke=0)
    # Bottom-Left
    c.rect(MARGIN, MARGIN, FIDUCIAL_SIZE, FIDUCIAL_SIZE, fill=1, stroke=0)
    # Bottom-Right
    c.rect(PAGE_WIDTH - MARGIN - FIDUCIAL_SIZE, MARGIN, FIDUCIAL_SIZE, FIDUCIAL_SIZE, fill=1, stroke=0)

    # 2. Draw Header Title and Institutional Info
    c.setFillColor(colors.HexColor("#0F172A")) # Slate-900
    c.setFont("Helvetica-Bold", 12)
    c.drawString(75, PAGE_HEIGHT - 45, institution_name.upper())

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#0D9488")) # Teal-600
    c.drawString(75, PAGE_HEIGHT - 60, f"{department_name} — OFFICIAL ATTENDANCE RECORD")

    c.setFillColor(colors.HexColor("#334155")) # Slate-700
    c.setFont("Helvetica-Bold", 9)
    c.drawString(75, PAGE_HEIGHT - 75, f"Subject: {subject_code} - {subject_name}")
    c.setFont("Helvetica", 8.5)
    c.drawString(75, PAGE_HEIGHT - 88, f"Date: {session_date}   |   Semester: {semester}   |   Session Token: {session_token}")

    # 3. Generate & Draw QR Code (Top-Right)
    qr_payload = f"{subject_code}|{session_date}|{session_token}"
    qr_img = generate_qr_image(qr_payload, size_px=140)
    qr_buffer = io.BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    
    qr_x = PAGE_WIDTH - MARGIN - FIDUCIAL_SIZE - 75
    qr_y = PAGE_HEIGHT - 98
    c.drawImage(ImageReader(qr_buffer), qr_x, qr_y, width=65, height=65)
    c.setFont("Helvetica", 6.5)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawCentredString(qr_x + 32, qr_y - 7, "ALIGN & SCAN QR")

    # 4. Header Horizontal Divider
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(1)
    c.line(MARGIN + FIDUCIAL_SIZE + 10, PAGE_HEIGHT - 108, PAGE_WIDTH - MARGIN - FIDUCIAL_SIZE - 10, PAGE_HEIGHT - 108)

    # 5. Grid Table Configuration
    # Table dimensions:
    # Page width: ~595 pt. Fiducials at x=28 to 60, and 535 to 567.
    # Usable width = 500 pt. Table X starts at 48 pt.
    table_x = 48
    col_w_sno = 26
    col_w_roll = 104
    col_w_name = 165
    col_w_mark = 85
    col_w_sign = 120
    total_w = col_w_sno + col_w_roll + col_w_name + col_w_mark + col_w_sign # 500 pt

    table_top = PAGE_HEIGHT - 120
    row_height = 28 # pt per student (20 students = 560 pt, table ends at ~160 pt, safe from bottom 60 pt)

    # Draw Table Header
    c.setFillColor(colors.HexColor("#1E293B")) # Dark Slate
    c.rect(table_x, table_top - 20, total_w, 20, fill=1, stroke=1)
    
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(table_x + col_w_sno / 2, table_top - 14, "#")
    c.drawString(table_x + col_w_sno + 6, table_top - 14, "Roll Number")
    c.drawString(table_x + col_w_sno + col_w_roll + 6, table_top - 14, "Student Name")
    c.drawCentredString(table_x + col_w_sno + col_w_roll + col_w_name + col_w_mark / 2, table_top - 14, "Mark [ P / A ]")
    c.drawCentredString(table_x + col_w_sno + col_w_roll + col_w_name + col_w_mark + col_w_sign / 2, table_top - 14, "Student Signature")

    # Draw Rows
    curr_y = table_top - 20
    c.setFont("Helvetica", 8)

    for idx, student in enumerate(students):
        curr_y -= row_height
        is_even = (idx % 2 == 0)
        
        # Row background alternating
        row_bg = colors.HexColor("#F8FAFC") if is_even else colors.white
        c.setFillColor(row_bg)
        c.rect(table_x, curr_y, total_w, row_height, fill=1, stroke=0)

        # Outer border
        c.setStrokeColor(colors.HexColor("#E2E8F0"))
        c.setLineWidth(0.7)
        c.rect(table_x, curr_y, total_w, row_height, fill=0, stroke=1)

        # Vertical Column Separators
        x1 = table_x + col_w_sno
        x2 = x1 + col_w_roll
        x3 = x2 + col_w_name
        x4 = x3 + col_w_mark
        c.line(x1, curr_y, x1, curr_y + row_height)
        c.line(x2, curr_y, x2, curr_y + row_height)
        c.line(x3, curr_y, x3, curr_y + row_height)
        c.line(x4, curr_y, x4, curr_y + row_height)

        # Text labels
        c.setFillColor(colors.HexColor("#475569"))
        c.drawCentredString(table_x + col_w_sno / 2, curr_y + 10, str(idx + 1))
        
        c.setFillColor(colors.HexColor("#0F172A"))
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x1 + 6, curr_y + 10, student.get("roll_number", f"DETS-26-EIE-{idx+1:03d}"))

        c.setFont("Helvetica", 8)
        c.drawString(x2 + 6, curr_y + 10, student.get("full_name", f"Student {idx+1}"))

        # In Mark column: draw two clear target square boxes for [ P ] and [ A ]
        mark_box_w = 20
        mark_box_h = 16
        mark_box_y = curr_y + 6
        
        # P Box
        p_box_x = x3 + 12
        c.setStrokeColor(colors.HexColor("#0D9488")) # Teal border
        c.setLineWidth(0.8)
        c.rect(p_box_x, mark_box_y, mark_box_w, mark_box_h, fill=0, stroke=1)
        c.setFillColor(colors.HexColor("#0D9488"))
        c.setFont("Helvetica-Bold", 7.5)
        c.drawCentredString(p_box_x + mark_box_w / 2, mark_box_y + 4.5, "P")

        # A Box
        a_box_x = x3 + col_w_mark - mark_box_w - 12
        c.setStrokeColor(colors.HexColor("#EF4444")) # Rose/Red border
        c.rect(a_box_x, mark_box_y, mark_box_w, mark_box_h, fill=0, stroke=1)
        c.setFillColor(colors.HexColor("#EF4444"))
        c.drawCentredString(a_box_x + mark_box_w / 2, mark_box_y + 4.5, "A")

        # Signature cell baseline
        c.setStrokeColor(colors.HexColor("#CBD5E1"))
        c.setLineWidth(0.5)
        c.setDash(2, 2)
        c.line(x4 + 10, curr_y + 7, x4 + col_w_sign - 10, curr_y + 7)
        c.setDash() # reset dash

    # Bottom Instructions & Verification Footer
    footer_y = curr_y - 20
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(colors.HexColor("#64748B"))
    c.drawString(table_x, footer_y, "INSTRUCTIONS: Mark clearly inside [ P ] for Present, [ A ] for Absent. Ensure the 4 corner alignment squares remain intact.")
    
    c.setFont("Helvetica", 7.5)
    c.drawString(table_x + total_w - 130, footer_y - 12, "Faculty Signature: __________________")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

def generate_attendance_xlsx_template(
    institution_name: str,
    subject_code: str,
    subject_name: str,
    session_date: str,
    session_token: str,
    students: list
) -> bytes:
    """Generate Excel attendance template using openpyxl"""
    wb = Workbook()
    ws = wb.active
    ws.title = f"Attendance_{session_date}"

    # Header styling
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    sub_fill = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid")
    title_font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    sub_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    bold_font = Font(name="Calibri", size=10, bold=True)
    regular_font = Font(name="Calibri", size=10)

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1")
    )

    # Title rows
    ws.merge_cells("A1:E1")
    ws["A1"] = institution_name
    ws["A1"].font = title_font
    ws["A1"].fill = header_fill
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:E2")
    ws["A2"] = f"OFFICIAL CLASS ATTENDANCE SHEET — {subject_code}: {subject_name}"
    ws["A2"].font = sub_font
    ws["A2"].fill = sub_fill
    ws["A2"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 22

    # Metadata
    ws["A3"] = "Class Date:"
    ws["B3"] = session_date
    ws["D3"] = "Session Token:"
    ws["E3"] = session_token
    ws["A3"].font = bold_font
    ws["D3"].font = bold_font

    ws.row_dimensions[4].height = 10 # empty spacer

    # Table Column Headers
    headers = ["S.No", "Roll Number", "Student Full Name", "Status (P/A)", "Signature / Remarks"]
    ws.row_dimensions[5].height = 22
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=5, column=col_idx, value=header)
        cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        cell.alignment = Alignment(horizontal="center" if col_idx in [1, 4] else "left", vertical="center")
        cell.border = thin_border

    # Student rows
    for idx, student in enumerate(students, start=1):
        row_num = 5 + idx
        ws.row_dimensions[row_num].height = 20

        c_sno = ws.cell(row=row_num, column=1, value=idx)
        c_roll = ws.cell(row=row_num, column=2, value=student.get("roll_number"))
        c_name = ws.cell(row=row_num, column=3, value=student.get("full_name"))
        c_stat = ws.cell(row=row_num, column=4, value="") # Blank for filling
        c_rem = ws.cell(row=row_num, column=5, value="")

        c_sno.alignment = Alignment(horizontal="center", vertical="center")
        c_roll.alignment = Alignment(horizontal="left", vertical="center")
        c_name.alignment = Alignment(horizontal="left", vertical="center")
        c_stat.alignment = Alignment(horizontal="center", vertical="center")
        c_rem.alignment = Alignment(horizontal="left", vertical="center")

        for c in [c_sno, c_roll, c_name, c_stat, c_rem]:
            c.font = regular_font
            c.border = thin_border
            if idx % 2 == 0:
                c.fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    # Column widths
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 28
    ws.column_dimensions["D"].width = 16
    ws.column_dimensions["E"].width = 24

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()
