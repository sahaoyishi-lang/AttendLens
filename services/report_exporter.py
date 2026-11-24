"""
AttendLens - Attendance & Shortage Report Exporter Service
Generates:
1. Shortage Notice PDF Report: Official university shortage letter with recovery calculator
2. Full Attendance XLSX Report: Multi-session tabular ledger with color-coded safe/shortage status
100% Open-Source (ReportLab & OpenPyXL)
"""
import io
import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

PAGE_WIDTH, PAGE_HEIGHT = A4 # 595.27 x 841.89 points

def generate_shortage_pdf_report(
    institution_name: str,
    subject_code: str,
    subject_name: str,
    min_threshold: float,
    total_sessions: int,
    shortage_students: list # list of dicts: roll_number, full_name, held, attended, percent, needed
) -> bytes:
    """
    Generates official institutional PDF attendance shortage notice & condonation report.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    margin = 40

    # 1. Official Header
    c.setFillColor(colors.HexColor("#0F172A")) # Slate-900
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 45, institution_name.upper())

    c.setFillColor(colors.HexColor("#DC2626")) # Red-600
    c.setFont("Helvetica-Bold", 10.5)
    c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 62, "OFFICIAL ATTENDANCE SHORTAGE & CONDONATION NOTICE")

    c.setStrokeColor(colors.HexColor("#E2E8F0"))
    c.setLineWidth(1)
    c.line(margin, PAGE_HEIGHT - 72, PAGE_WIDTH - margin, PAGE_HEIGHT - 72)

    # 2. Metadata Box
    c.setFillColor(colors.HexColor("#F8FAFC"))
    c.rect(margin, PAGE_HEIGHT - 130, PAGE_WIDTH - 2 * margin, 50, fill=1, stroke=1)
    
    c.setFillColor(colors.HexColor("#334155"))
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(margin + 12, PAGE_HEIGHT - 92, f"Subject: {subject_code} - {subject_name}")
    c.drawString(margin + 12, PAGE_HEIGHT - 106, f"Minimum Required Attendance: {min_threshold:.1f}%")
    c.drawString(margin + 12, PAGE_HEIGHT - 120, f"Total Classes Conducted: {total_sessions}")

    gen_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.setFont("Helvetica", 8)
    c.drawRightString(PAGE_WIDTH - margin - 12, PAGE_HEIGHT - 92, f"Generated: {gen_time}")
    c.drawRightString(PAGE_WIDTH - margin - 12, PAGE_HEIGHT - 106, f"Students Below Threshold: {len(shortage_students)}")
    c.drawRightString(PAGE_WIDTH - margin - 12, PAGE_HEIGHT - 120, "Status: STRICT AUDIT NOTICE")

    # 3. Table Headers
    table_top = PAGE_HEIGHT - 145
    col_w_sno = 24
    col_w_roll = 100
    col_w_name = 145
    col_w_held = 46
    col_w_att = 46
    col_w_pct = 58
    col_w_need = 96
    total_w = col_w_sno + col_w_roll + col_w_name + col_w_held + col_w_att + col_w_pct + col_w_need # 515 pt

    c.setFillColor(colors.HexColor("#1E293B"))
    c.rect(margin, table_top - 18, total_w, 18, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(margin + col_w_sno / 2, table_top - 13, "#")
    c.drawString(margin + col_w_sno + 6, table_top - 13, "Roll Number")
    c.drawString(margin + col_w_sno + col_w_roll + 6, table_top - 13, "Student Name")
    c.drawCentredString(margin + col_w_sno + col_w_roll + col_w_name + col_w_held / 2, table_top - 13, "Held")
    c.drawCentredString(margin + col_w_sno + col_w_roll + col_w_name + col_w_held + col_w_att / 2, table_top - 13, "Attended")
    c.drawCentredString(margin + col_w_sno + col_w_roll + col_w_name + col_w_held + col_w_att + col_w_pct / 2, table_top - 13, "Attendance %")
    c.drawCentredString(margin + total_w - col_w_need / 2, table_top - 13, "Classes Needed (75%)")

    # 4. Table Rows
    curr_y = table_top - 18
    row_h = 22

    if not shortage_students:
        curr_y -= row_h * 2
        c.setFillColor(colors.HexColor("#0D9488"))
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(PAGE_WIDTH / 2, curr_y + 10, "All enrolled students meet the minimum attendance threshold (75%). No shortages recorded.")
    else:
        for idx, s in enumerate(shortage_students):
            curr_y -= row_h
            bg = colors.HexColor("#FEF2F2") if idx % 2 == 0 else colors.white
            c.setFillColor(bg)
            c.rect(margin, curr_y, total_w, row_h, fill=1, stroke=0)

            c.setStrokeColor(colors.HexColor("#FECACA"))
            c.setLineWidth(0.5)
            c.rect(margin, curr_y, total_w, row_h, fill=0, stroke=1)

            c.setFillColor(colors.HexColor("#475569"))
            c.setFont("Helvetica", 7.5)
            c.drawCentredString(margin + col_w_sno / 2, curr_y + 7, str(idx + 1))

            c.setFillColor(colors.HexColor("#0F172A"))
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString(margin + col_w_sno + 6, curr_y + 7, s.get("roll_number", ""))

            c.setFont("Helvetica", 7.5)
            c.drawString(margin + col_w_sno + col_w_roll + 6, curr_y + 7, s.get("full_name", ""))

            c.drawCentredString(margin + col_w_sno + col_w_roll + col_w_name + col_w_held / 2, curr_y + 7, str(s.get("classes_held", total_sessions)))
            c.drawCentredString(margin + col_w_sno + col_w_roll + col_w_name + col_w_held + col_w_att / 2, curr_y + 7, str(s.get("classes_attended", 0)))

            # Red percentage
            c.setFillColor(colors.HexColor("#DC2626"))
            c.setFont("Helvetica-Bold", 7.5)
            pct_val = s.get("attendance_percent", 0.0)
            c.drawCentredString(margin + col_w_sno + col_w_roll + col_w_name + col_w_held + col_w_att + col_w_pct / 2, curr_y + 7, f"{pct_val:.1f}%")

            # Classes needed
            needed = s.get("classes_needed_for_75", 0)
            c.setFillColor(colors.HexColor("#7C3AED")) # Violet-600
            c.drawCentredString(margin + total_w - col_w_need / 2, curr_y + 7, f"{needed} consecutive classes")

    # 5. Regulatory Notice
    notice_y = curr_y - 35
    c.setFillColor(colors.HexColor("#64748B"))
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(margin, notice_y, "ACADEMIC BYLAWS RULE: Students failing to secure 75% aggregate attendance are subject to condonation hearings or exam debarment.")
    c.drawString(margin, notice_y - 10, "Students with shortages must report to the Departmental Academic Committee within 7 days of notice publication.")

    # 6. Official Signatures
    sig_y = notice_y - 45
    c.setStrokeColor(colors.HexColor("#94A3B8"))
    c.setLineWidth(0.8)
    
    # 3 Signature lines
    sig_w = 120
    x_course = margin + 10
    x_hod = PAGE_WIDTH / 2 - sig_w / 2
    x_dean = PAGE_WIDTH - margin - sig_w - 10

    c.line(x_course, sig_y, x_course + sig_w, sig_y)
    c.line(x_hod, sig_y, x_hod + sig_w, sig_y)
    c.line(x_dean, sig_y, x_dean + sig_w, sig_y)

    c.setFillColor(colors.HexColor("#1E293B"))
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(x_course + sig_w / 2, sig_y - 12, "Course Coordinator")
    c.drawCentredString(x_hod + sig_w / 2, sig_y - 12, "Head of Department (EIE)")
    c.drawCentredString(x_dean + sig_w / 2, sig_y - 12, "Dean (Academic Affairs)")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

def generate_full_attendance_xlsx(
    institution_name: str,
    subject_code: str,
    subject_name: str,
    min_threshold: float,
    session_dates: list, # sorted list of session dates ['2026-10-05', '2026-10-12', ...]
    student_records: list # list of dicts: {'roll_number', 'full_name', 'attendance': {date: 'P'/'A'}, 'held', 'attended', 'percent', 'status', 'needed'}
) -> bytes:
    """
    Generates a full Excel attendance ledger with session dates as columns,
    aggregate metrics, and conditional formatting.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Full_Attendance_Report"

    # Styling definitions
    title_font = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
    sub_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    bold_hdr = Font(name="Calibri", size=9, bold=True, color="FFFFFF")
    bold_dark = Font(name="Calibri", size=9, bold=True, color="0F172A")
    regular_font = Font(name="Calibri", size=9)

    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    sub_fill = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid")
    table_hdr_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    safe_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid") # soft green
    shortage_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid") # soft red

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1")
    )

    # 1. Title Rows
    total_cols = 3 + len(session_dates) + 5 # S.No, Roll, Name, (Dates...), Held, Attended, %, Status, Needed
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    ws.cell(row=1, column=1, value=institution_name).font = title_font
    ws.cell(row=1, column=1).fill = header_fill
    ws.cell(row=1, column=1).alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 26

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=total_cols)
    ws.cell(row=2, column=1, value=f"COMPREHENSIVE ATTENDANCE AUDIT & ELIGIBILITY LEDGER — {subject_code}: {subject_name} (Threshold: {min_threshold}%)").font = sub_font
    ws.cell(row=2, column=1).fill = sub_fill
    ws.cell(row=2, column=1).alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    # 2. Table Column Headers
    ws.row_dimensions[4].height = 24
    base_headers = ["#", "Roll Number", "Student Name"]
    for c_idx, h in enumerate(base_headers, start=1):
        cell = ws.cell(row=4, column=c_idx, value=h)
        cell.font = bold_hdr
        cell.fill = table_hdr_fill
        cell.alignment = Alignment(horizontal="center" if c_idx == 1 else "left", vertical="center")
        cell.border = thin_border

    # Dynamic Session Date Columns
    col_tracker = 4
    for s_date in session_dates:
        cell = ws.cell(row=4, column=col_tracker, value=s_date)
        cell.font = bold_hdr
        cell.fill = table_hdr_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border
        col_tracker += 1

    summary_headers = ["Total Held", "Attended", "Attendance %", "Eligibility Status", "Classes Needed (75%)"]
    for sh in summary_headers:
        cell = ws.cell(row=4, column=col_tracker, value=sh)
        cell.font = bold_hdr
        cell.fill = table_hdr_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border
        col_tracker += 1

    # 3. Populate Student Rows
    for idx, s in enumerate(student_records, start=1):
        row_num = 4 + idx
        ws.row_dimensions[row_num].height = 19
        
        # Base info
        c1 = ws.cell(row=row_num, column=1, value=idx)
        c2 = ws.cell(row=row_num, column=2, value=s.get("roll_number"))
        c3 = ws.cell(row=row_num, column=3, value=s.get("full_name"))
        c1.alignment = Alignment(horizontal="center", vertical="center")
        c2.alignment = Alignment(horizontal="left", vertical="center")
        c3.alignment = Alignment(horizontal="left", vertical="center")

        curr_col = 4
        # Per-session marks
        att_map = s.get("attendance", {})
        for s_date in session_dates:
            mark = att_map.get(s_date, "-")
            c = ws.cell(row=row_num, column=curr_col, value=mark)
            c.alignment = Alignment(horizontal="center", vertical="center")
            if mark == "P":
                c.font = Font(name="Calibri", size=9, bold=True, color="166534") # dark green
            elif mark == "A":
                c.font = Font(name="Calibri", size=9, bold=True, color="991B1B") # dark red
            else:
                c.font = regular_font
            curr_col += 1

        # Summary Metrics
        held = s.get("held", len(session_dates))
        attended = s.get("attended", 0)
        pct = s.get("percent", 0.0)
        status = s.get("status", "Safe")
        needed = s.get("needed", 0)

        c_held = ws.cell(row=row_num, column=curr_col, value=held)
        c_att = ws.cell(row=row_num, column=curr_col + 1, value=attended)
        c_pct = ws.cell(row=row_num, column=curr_col + 2, value=f"{pct:.1f}%")
        c_stat = ws.cell(row=row_num, column=curr_col + 3, value=status)
        c_need = ws.cell(row=row_num, column=curr_col + 4, value=f"{needed} classes" if needed > 0 else "None")

        for c in [c_held, c_att, c_pct, c_stat, c_need]:
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.font = bold_dark

        # Color fill status column
        if status == "Shortage" or pct < min_threshold:
            c_stat.fill = shortage_fill
            c_stat.font = Font(name="Calibri", size=9, bold=True, color="991B1B")
            c_pct.font = Font(name="Calibri", size=9, bold=True, color="991B1B")
        else:
            c_stat.fill = safe_fill
            c_stat.font = Font(name="Calibri", size=9, bold=True, color="166534")

        # Borders
        for c_i in range(1, total_cols + 1):
            ws.cell(row=row_num, column=c_i).border = thin_border
            if idx % 2 == 0 and c_i <= 3:
                ws.cell(row=row_num, column=c_i).fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    # Column auto-width adjustment
    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 19
    ws.column_dimensions["C"].width = 24
    for c_i in range(4, 4 + len(session_dates)):
        ws.column_dimensions[get_column_letter(c_i)].width = 13
    ws.column_dimensions[get_column_letter(4 + len(session_dates))].width = 12
    ws.column_dimensions[get_column_letter(5 + len(session_dates))].width = 12
    ws.column_dimensions[get_column_letter(6 + len(session_dates))].width = 14
    ws.column_dimensions[get_column_letter(7 + len(session_dates))].width = 18
    ws.column_dimensions[get_column_letter(8 + len(session_dates))].width = 20

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue()
