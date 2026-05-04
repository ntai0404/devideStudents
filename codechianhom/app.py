from flask import Flask, request, session, redirect, url_for, render_template, send_file
import requests
import csv
import os
import urllib3
from chia_nhom import divide_groups
from flask import send_file
import io

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.secret_key = "super_secret_key"

# Configuration for target subject
TARGET_SUBJECT_CODE = "CSE393"
TARGET_SUBJECT_NAME = "Nhập môn điện toán đám mây"

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

def extract_practise_subj(response_json):
    cas = []
    for course in response_json:
        subj = course.get("courseSubject", {})
        if not subj:
            continue
            
        sem_subj = subj.get("semesterSubject", {}).get("subject", {})
        subject_code = sem_subj.get("subjectCode")
        
        # Simplified identification based on constants
        code_full = subj.get("code", "") or ""
        display_name = subj.get("displayName", "") or ""
        is_target = (TARGET_SUBJECT_CODE in code_full) or (TARGET_SUBJECT_NAME[:15] in display_name)
        
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

    return list(set(cas))

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
        
        try:
            resp = requests.post(url_token, data=data, verify=False, timeout=30)
            if resp.status_code == 200:
                token_info = resp.json()
                session["access_token"] = token_info["access_token"]
                session["username"] = username
                return redirect(url_for("form"))
            elif resp.status_code == 401:
                print(f"[LOGIN] 401 - Invalid credentials: {username}")
                return render_template("login.html", error="Sai MSSV hoặc mật khẩu")
            else:
                error_msg = resp.text[:200]
                print(f"[LOGIN] {resp.status_code} - {error_msg}")
                return render_template("login.html", error=f"Lỗi server ({resp.status_code}). Vui lòng thử lại sau.")
        except requests.exceptions.Timeout:
            print(f"[LOGIN] Timeout - API quá chậm")
            return render_template("login.html", error="API trường không phản hồi. Vui lòng thử lại.")
        except Exception as e:
            print(f"[LOGIN] Exception: {e}")
            return render_template("login.html", error=f"Lỗi kết nối: {str(e)[:100]}")

    return render_template("login.html", error=None)

@app.route("/form", methods=["GET", "POST"])
def form():
    if "access_token" not in session:
        return redirect(url_for("login"))
        
    if request.method == "GET":
        headers = {
            "Authorization": f"Bearer {session['access_token']}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        url_summary = "https://sinhvien1.tlu.edu.vn/education/api/studentsummarymark/getbystudent"
        url_marks = "https://sinhvien1.tlu.edu.vn/education/api/studentsubjectmark/getListStudentMarkBySemesterByLoginUser/0"
        url_courses = "https://sinhvien1.tlu.edu.vn/education/api/StudentCourseSubject/studentLoginUser/14"
        
        from concurrent.futures import ThreadPoolExecutor
        def fetch(url):
            try:
                resp = requests.get(url, headers=headers, verify=False, timeout=120)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                print(f"[FORM] Error fetching {url}: {e}")
                return {}

        try:
            with ThreadPoolExecutor() as executor:
                future_summary = executor.submit(fetch, url_summary)
                future_marks = executor.submit(fetch, url_marks)
                future_courses = executor.submit(fetch, url_courses)

                summary = future_summary.result(timeout=130)
                marks_data = future_marks.result(timeout=130)
                courses_data = future_courses.result(timeout=130)
        except Exception as e:
            print(f"[FORM] ThreadPool error: {e}")
            return render_template("form.html", error="Khong the lay du lieu tu server truong. Vui long thu lai sau.")

        student = summary.get("student", {})
        session["student_name"] = student.get("displayName")
        session["class_name"] = student.get("enrollmentClass", {}).get("className")
        session["gpa"] = summary.get("mark4")

        cse393 = None
        for item in marks_data:
            if isinstance(item, dict) and item.get("subject", {}).get("subjectCode") == "CSE393":
                cse393 = item.get("mark")
                break
        session["cse393_mark"] = cse393
        session["practise_subj"] = extract_practise_subj(courses_data)

    # Retrieve from session for both GET and POST
    name = session.get("student_name")
    mssv = session.get("username")
    class_name = session.get("class_name")
    gpa = session.get("gpa")
    cse393 = session.get("cse393_mark")
    practise_subj = session.get("practise_subj", [])

    if request.method == "POST":
        registered_class = request.form["registered_class"]
        goal = request.form["goal"]
        strengths = request.form.getlist("strength")
        strength = "; ".join(strengths)
        role = request.form["role"]

        classes = ["65HTTT"]
        header = ["MSSV", "Họ tên", "Lớp hiện tại", "GPA", "Điểm ĐTĐM", "Ca học",
                  "Mục tiêu", "Điểm mạnh", "Vai trò mong muốn"]

        for cls in classes:
            if cls == registered_class:
                continue
            file_path = f"{cls}.csv"
            if os.path.exists(file_path):
                rows = []
                with open(file_path, "r", newline="", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row["MSSV"] != mssv:
                            rows.append(row)
                with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=reader.fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)

        class_file = f"{registered_class}.csv"
        if not os.path.exists(class_file) or os.path.getsize(class_file) == 0:
            with open(class_file, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=header)
                writer.writeheader()

        rows = []
        updated = False
        if os.path.exists(class_file):
            with open(class_file, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["MSSV"] == mssv:
                        row = {
                            "MSSV": mssv,
                            "Họ tên": name,
                            "Lớp hiện tại": class_name,
                            "GPA": gpa,
                            "Điểm ĐTĐM": cse393,
                            "Ca học": ", ".join(practise_subj),
                            "Mục tiêu": goal,
                            "Điểm mạnh": strength,
                            "Vai trò mong muốn": role
                        }
                        updated = True
                    rows.append(row)

        if not updated:
            rows.append({
                "MSSV": mssv,
                "Họ tên": name,
                "Lớp hiện tại": class_name,
                "GPA": gpa,
                "Điểm ĐTĐM": cse393,
                "Ca học": ", ".join(practise_subj),
                "Mục tiêu": goal,
                "Điểm mạnh": strength,
                "Vai trò mong muốn": role
            })

        with open(class_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)

        return render_template("submitted.html", name=name, registered_class=registered_class)


    return render_template("form.html", name=name, mssv=mssv,
                       class_name=class_name, gpa=gpa, cse393=cse393,
                       practise_subj=practise_subj,
                       target_subject_name=TARGET_SUBJECT_NAME,
                       target_subject_code=TARGET_SUBJECT_CODE)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

import pandas as pd

ADMIN_USER = "admin"
ADMIN_PASS = "123456"

@app.route("/admin", methods=["GET"])
def admin():
    if "is_admin" not in session:
        return redirect(url_for("login"))

    classes = ["65HTTT"]
    selected_class = request.args.get("class")
    action = request.args.get("action")

    df = None
    html_summaries = None

    if selected_class:
        class_file = f"{selected_class}.csv"
        if os.path.exists(class_file) and os.path.getsize(class_file) > 0:
            df = pd.read_csv(class_file)
            df.insert(0, "STT", range(1, len(df)+1))
        else:
            df = pd.DataFrame()
            html_summaries = None

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
                "STT", "GroupID", "MSSV", "Họ tên", "Lớp hiện tại",
                "GPA", "Điểm ĐTĐM", "Điểm tổng",
                "Mục tiêu", "Điểm mạnh", "Vai trò mong muốn"
            ]
            export_df = export_df[[c for c in desired_order if c in export_df.columns]]

            output_file = f"{selected_class}_grouped.csv"
            buf = io.StringIO()
            export_df.to_csv(buf, index=False, encoding="utf-8-sig")
            buf.seek(0)

            return send_file(
                io.BytesIO(buf.getvalue().encode("utf-8-sig")),
                as_attachment=True,
                download_name=output_file,
                mimetype="text/csv"
            )

    return render_template("admin.html",
                           classes=classes,
                           selected_class=selected_class,
                           df=df,
                           html_summaries=html_summaries)

from waitress import serve

if __name__ == "__main__":
    cores = 5
    threads = cores * 6
    serve(app, host="0.0.0.0", port=5000, threads=threads)
