from flask import Flask, request, session, redirect, url_for, render_template, send_file
import requests
import csv
import os
import urllib3
import unicodedata
from chia_nhom import divide_groups
from flask import send_file
import io
import traceback

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.secret_key = "super_secret_key"

ADMIN_USER = "admin"
ADMIN_PASS = "admin"

# Configuration for target subjects
ALLOWED_SUBJECT_LIST = [
    {"code": "CSE441", "name": "Phát triển ứng dụng di động"},
    {"code": "CSE450", "name": "Hệ thống kinh doanh thông minh"},
    {"code": "CSE455", "name": "Quản trị hệ thống thông tin"},
    {"code": "CSE393", "name": "Nhập môn điện toán đám mây"}
]
TARGET_SUBJECT_CODE = "CSE393"
TARGET_SUBJECT_NAME = "Nhập môn điện toán đám mây"

def normalize_vn(text):
    if not text or not isinstance(text, str):
        return text
    return unicodedata.normalize('NFC', text)

def get_ca(start_index, end_index):
    if start_index == 1 and end_index == 3:
        return "Ca 1"
    elif start_index == 4 and end_index == 6:
        return "Ca 2"
    elif start_index == 7 and end_index == 9:
        return "Ca 3"
    elif start_index == 10 and end_index == 12:
        return "Ca 4"
    return None

def get_subjects_from_courses(response_json):
    subjects_map = {}
    
    # Identify all subjects first from any entry
    for item in response_json:
        subj = item.get("courseSubject", {})
        if not subj: continue
        
        sem_subj = subj.get("semesterSubject", {}).get("subject", {})
        full_code = (sem_subj.get("subjectCode") or subj.get("code") or "").upper()
        display_name = normalize_vn(subj.get("displayName") or sem_subj.get("subjectName") or full_code)
        
        base_code = full_code.split('_')[0] if '_' in full_code else full_code
        
        if base_code not in subjects_map:
            subjects_map[base_code] = {
                "code": base_code,
                "name": display_name,
                "practice_classes": []
            }
        
        subject_type = subj.get("courseSubjectType")
        if subject_type == 6:
            sessions = []
            for tt in subj.get("timetables", []):
                start = tt.get("startHour", {}).get("indexNumber")
                end = tt.get("endHour", {}).get("indexNumber")
                ca = get_ca(start, end)
                if ca and ca not in sessions:
                    sessions.append(ca)
            
            subjects_map[base_code]["practice_classes"].append({
                "code": subj.get("code") or full_code,
                "name": normalize_vn(subj.get("displayName") or ""),
                "sessions": sessions
            })
        elif subject_type == 1 or subject_type is None:
             # Prefer main class name if available
             subjects_map[base_code]["name"] = display_name

    # Return subjects that have practice classes
    result = []
    for bc in sorted(subjects_map.keys()):
        s = subjects_map[bc]
        if s["practice_classes"]:
            result.append(s)
    return result

def extract_practise_subj(response_json, target_code=None, target_name=None):
    """Extract practical session names (Ca) for a specific target subject."""
    cas = []
    for course in response_json:
        subj = course.get("courseSubject", {})
        if not subj:
            continue
            
        sem_subj = subj.get("semesterSubject", {}).get("subject", {})
        subject_code = sem_subj.get("subjectCode")
        
        # Identification based on provided target
        code_full = subj.get("code", "") or ""
        display_name = subj.get("displayName", "") or ""
        
        is_target = False
        if target_code and subject_code:
            is_target = (target_code in subject_code) or (target_code in code_full)
        if not is_target and target_name:
            is_target = (target_name[:15] in display_name)
        
        # In some data (like Semester 12 log), courseSubjectType is null
        subject_type = subj.get("courseSubjectType")
        is_practice = (subject_type == 6) or (subject_type is None)

        if is_target and is_practice:
            for tt in subj.get("timetables", []):
                start_index = tt.get("startHour", {}).get("indexNumber")
                end_index = tt.get("endHour", {}).get("indexNumber")
                ca = get_ca(start_index, end_index)
                if ca:
                    cas.append(ca)

    return list(dict.fromkeys(cas))

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == ADMIN_USER and password == ADMIN_PASS:
            session["is_admin"] = True
            return redirect(url_for("admin"))
        
        url_token = "https://sinhvien1.tlu.edu.vn/education/oauth/token"
        data = {
            "client_id": "education_client",
            "client_secret": "password",
            "grant_type": "password",
            "username": username,
            "password": password,
        }
        resp = requests.post(url_token, data=data, verify=False)

        if resp.status_code != 200:
            return render_template("login.html", error="Sai MSSV hoặc mật khẩu")

        token_data = resp.json()
        session["access_token"] = token_data["access_token"]
        session["username"] = username
        return redirect(url_for("form"))

    return render_template("login.html")

@app.route("/form", methods=["GET", "POST"])
def form():
    if "access_token" not in session:
        return redirect(url_for("login"))

    headers = {"Authorization": f"Bearer {session['access_token']}"}
    mssv = session.get("username")
    
    # Try to get data from cache (session) to avoid TLU API instability and speed up reloads
    cached = session.get("student_cache")
    if cached and "summary" in cached:
        summary = cached["summary"]
        marks_data = cached["marks_data"]
        semesters = cached["semesters"]
        courses_data = cached["courses_data"]
    else:
        url_summary = "https://sinhvien1.tlu.edu.vn/education/api/studentsummarymark/getbystudent"
        url_marks = "https://sinhvien1.tlu.edu.vn/education/api/studentsubjectmark/getListStudentMarkBySemesterByLoginUser/0"
        url_semesters = "https://sinhvien1.tlu.edu.vn/education/api/semester/all"
        
        from concurrent.futures import ThreadPoolExecutor

        def fetch(url):
            try:
                r = requests.get(url, headers=headers, verify=False, timeout=10)
                return r.json() if r.status_code == 200 else None
            except:
                return None

        with ThreadPoolExecutor() as executor:
            future_summary = executor.submit(fetch, url_summary)
            future_marks = executor.submit(fetch, url_marks)
            future_semesters = executor.submit(fetch, url_semesters)

            summary = future_summary.result()
            marks_data = future_marks.result()
            semesters = future_semesters.result()

        # Determine current semester ID automatically
        semester_id = "14" # default fallback
        if semesters and isinstance(semesters, list):
            current = next((s for s in semesters if s.get("isCurrent")), None)
            if current:
                semester_id = str(current.get("id"))
            else:
                semester_id = str(semesters[-1].get("id"))

        url_courses = f"https://sinhvien1.tlu.edu.vn/education/api/StudentCourseSubject/studentLoginUser/{semester_id}"
        courses_data = fetch(url_courses)
        
        # Save to cache ONLY if data is valid
        if summary and courses_data and isinstance(summary, dict) and summary.get("student"):
            session["student_cache"] = {
                "summary": summary,
                "marks_data": marks_data,
                "semesters": semesters,
                "courses_data": courses_data
            }
        else:
            # If API failed, clear any old bad cache just in case
            session.pop("student_cache", None)

    student = summary.get("student", {}) if summary else {}
    name = normalize_vn(student.get("displayName") or "Sinh viên")
    class_name = student.get("enrollmentClass", {}).get("className")
    gpa = summary.get("mark4") if summary else None

    cse393 = None
    if marks_data:
        for item in marks_data:
            if isinstance(item, dict) and item.get("subject", {}).get("subjectCode") == "CSE393":
                cse393 = item.get("mark")
                break

    subjects = get_subjects_from_courses(courses_data or [])
    
    selected_subject_code = request.values.get("subject_code")
    selected_subject = next((s for s in subjects if s["code"] == selected_subject_code), subjects[0] if subjects else None)
    
    if selected_subject:
        selected_subject_code = selected_subject["code"]
        selected_subject_name = selected_subject["name"]
        practice_classes = selected_subject["practice_classes"]
    else:
        selected_subject_code = None
        selected_subject_name = "Không có môn học hỗ trợ"
        practice_classes = []

    # Auto-fill from existing CSV if available
    existing_data = {}
    if practice_classes:
        # Check all possible practice classes for this student
        for pc in practice_classes:
            cf = f"{pc['code']}.csv"
            if os.path.exists(cf):
                with open(cf, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row["MSSV"] == mssv and row["Môn học"] == selected_subject_name:
                            existing_data = row
                            break
            if existing_data: break

    if request.method == "POST":
        registered_class = request.form["registered_class"]
        p_class = next((p for p in practice_classes if p["code"] == registered_class or p["name"] == registered_class), None)
        sessions_str = ", ".join(p_class["sessions"]) if p_class else ""

        goal = request.form.get("goal")
        strengths = request.form.getlist("strength")
        role = request.form.get("role")

        class_file = f"{registered_class}.csv"
        header = ["Môn học", "MSSV", "Họ tên", "Lớp hiện tại", "GPA", "Điểm ĐTĐM", "Ca học", "Mục tiêu", "Điểm mạnh", "Vai trò mong muốn"]
        
        rows = []
        if os.path.exists(class_file) and os.path.getsize(class_file) > 0:
            with open(class_file, "r", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))

        found = False
        for r in rows:
            if r["MSSV"] == mssv and r["Môn học"] == selected_subject_name:
                r.update({
                    "Họ tên": name,
                    "Lớp hiện tại": class_name or "",
                    "GPA": gpa or "",
                    "Điểm ĐTĐM": cse393 or "",
                    "Ca học": sessions_str,
                    "Mục tiêu": goal,
                    "Điểm mạnh": "; ".join(strengths),
                    "Vai trò mong muốn": role
                })
                found = True
                break
        
        if not found:
            rows.append({
                "Môn học": selected_subject_name,
                "MSSV": mssv,
                "Họ tên": name,
                "Lớp hiện tại": class_name or "",
                "GPA": gpa or "",
                "Điểm ĐTĐM": cse393 or "",
                "Ca học": sessions_str,
                "Mục tiêu": goal,
                "Điểm mạnh": "; ".join(strengths),
                "Vai trò mong muốn": role
            })

        with open(class_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)

        return render_template("submitted.html", name=name, registered_class=registered_class)

    return render_template("form.html", name=name, mssv=mssv,
                       class_name=class_name, gpa=gpa, cse393=cse393,
                       target_subject_name=selected_subject_name,
                       target_subject_code=selected_subject_code,
                       subjects=subjects,
                       practice_classes=practice_classes,
                       selected_subject_code=selected_subject_code,
                       existing_data=existing_data)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

import pandas as pd

@app.route("/admin", methods=["GET"])
def admin():
    if "is_admin" not in session:
        return redirect(url_for("login"))

    classes = ["65HTTT5"]
    selected_class = request.args.get("class")
    action = request.args.get("action")

    df = pd.DataFrame()
    html_summaries = None
    available_subjects = []
    selected_subject = None

    if selected_class:
        class_file = f"{selected_class}.csv"
        if os.path.exists(class_file) and os.path.getsize(class_file) > 0:
            df = pd.read_csv(class_file)
            df.insert(0, "STT", range(1, len(df)+1))
        # Get unique subjects for filtering
        available_subjects = df['Môn học'].unique().tolist() if not df.empty and 'Môn học' in df.columns else []
        selected_subject = request.args.get("subject")
        if not selected_subject and available_subjects:
             selected_subject = available_subjects[0]
        
        if selected_subject and not df.empty and 'Môn học' in df.columns:
            df = df[df['Môn học'] == selected_subject].copy()

        if action == "group" and not df.empty:
            df['Điểm tổng'] = df.apply(
                lambda row: row['GPA'] if pd.isna(row['Điểm ĐTĐM']) else 0.6*row['GPA'] + 0.16*row['Điểm ĐTĐM'],
                axis=1
            )
            html_summaries, all_results = divide_groups(df)

            session['all_results'] = [
                {
                    "records": g.to_dict('records'),
                    "Ca": g.attrs.get('Ca', 'Unknown')
                }
                for g in all_results
            ]

        elif action == "save_original" and not df.empty:
            output_file = f"{selected_class}_original.csv"
            df.to_csv(output_file, index=False, encoding="utf-8-sig")
            return send_file(output_file,
                             as_attachment=True,
                             download_name=f"{selected_class}_original.csv",
                             mimetype='text/csv')

        elif action == "export" and 'all_results' in session:
            all_results = session['all_results']
            result_rows = []

            for group_idx, g_dict in enumerate(all_results, 1):
                g_df = pd.DataFrame(g_dict["records"])
                ca = g_dict.get("Ca", "Unknown")
                group_id = f"G{group_idx}_{ca}"
                for mem in g_df.to_dict('records'):
                    mem['GroupID'] = group_id
                    result_rows.append(mem)

            export_df = pd.DataFrame(result_rows)

            if "STT" in export_df.columns:
                export_df = export_df.drop(columns=["STT"])

            export_df.insert(0, "STT", range(1, len(export_df)+1))

            desired_order = [
                "STT", "GroupID", "Môn học", "MSSV", "Họ tên", "Lớp hiện tại",
                "GPA", "Điểm ĐTĐM", "Điểm tổng",
                "Mục tiêu", "Điểm mạnh", "Vai trò mong muốn"
            ]
            export_df = export_df[[c for c in desired_order if c in export_df.columns]]

            output_file = f"{selected_class}_grouped.csv"
            buf = io.StringIO()
            export_df.to_csv(buf, index=False, encoding="utf-8-sig")
            buf.seek(0)
            return send_file(io.BytesIO(buf.read().encode("utf-8-sig")),
                             as_attachment=True,
                             download_name=output_file,
                             mimetype='text/csv')

    return render_template("admin.html",
                           classes=classes,
                           selected_class=selected_class,
                           selected_subject=selected_subject,
                           available_subjects=available_subjects,
                           df=df,
                           html_summaries=html_summaries)

from waitress import serve

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
