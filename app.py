"""
Lotus Academy - Student Attendance Portal
Flask Backend with SQLite Database
"""

import sqlite3
import requests
import hashlib
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.secret_key = 'lotus_academy_secret_2024_anubhav'

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')
API_URL = 'https://apilotus.qqz.io/get-all-records'

# ─── Admin credentials ───────────────────────────────────────────────────────
ADMINS = {
    'anubhav': 'anulotus.ea',
    'gaurav':  'lotusgurav.ea',
}

# ─── DB helpers ──────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    with get_db() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS students (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL,
                password      TEXT    NOT NULL,
                student_name  TEXT    NOT NULL,
                class         TEXT    NOT NULL,
                board         TEXT    NOT NULL,
                stream        TEXT    NOT NULL DEFAULT 'nan'
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                date       TEXT    NOT NULL,
                time       TEXT    NOT NULL,
                status     TEXT    NOT NULL,
                board      TEXT    NOT NULL,
                class      TEXT    NOT NULL,
                stream     TEXT    NOT NULL,
                UNIQUE(student_id, date, time),
                FOREIGN KEY (student_id) REFERENCES students(id)
            );
        ''')


def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


# ─── API sync logic ───────────────────────────────────────────────────────────

def normalize_class(raw: str) -> str:
    """Strip 'Class ' prefix if present, e.g. 'Class 9' → '9'."""
    return str(raw).replace('Class ', '').strip()


def sync_attendance():
    """Fetch API records and match against registered students."""
    print(f"[{datetime.now()}] Syncing attendance from API…")
    try:
        try:
            resp = requests.get(API_URL, timeout=15)
        except requests.exceptions.SSLError:
            # Fallback: skip SSL verification (self-signed / clock skew environments)
            resp = requests.get(API_URL, timeout=15, verify=False)
        resp.raise_for_status()
        records = resp.json()
        if isinstance(records, dict):
            records = [records]
    except Exception as e:
        print(f"  API error: {e}")
        return {'status': 'error', 'message': str(e)}

    with get_db() as conn:
        students = conn.execute('SELECT * FROM students').fetchall()
        inserted = 0
        for rec in records:
            api_name   = (rec.get('name')   or '').strip()
            api_class  = normalize_class(rec.get('class') or '')
            api_board  = (rec.get('board')  or '').strip().upper()
            api_stream = (rec.get('stream') or 'nan').strip()
            api_status = (rec.get('status') or '').strip()
            api_time   = (rec.get('time')   or '').strip()
            api_date   = (rec.get('date')   or datetime.now().strftime('%Y-%m-%d')).strip()

            for stu in students:
                stu_name   = stu['student_name'].strip()
                stu_class  = normalize_class(stu['class'])
                stu_board  = stu['board'].strip().upper()
                stu_stream = (stu['stream'] or 'nan').strip()

                name_match   = stu_name.lower()   == api_name.lower()
                class_match  = stu_class           == api_class
                board_match  = stu_board           == api_board
                stream_match = stu_stream.lower() == api_stream.lower()

                if name_match and class_match and board_match and stream_match:
                    try:
                        conn.execute(
                            '''INSERT OR IGNORE INTO attendance
                               (student_id, date, time, status, board, class, stream)
                               VALUES (?, ?, ?, ?, ?, ?, ?)''',
                            (stu['id'], api_date, api_time, api_status,
                             api_board, stu_class, stu_stream)
                        )
                        inserted += conn.execute('SELECT changes()').fetchone()[0]
                    except Exception as ie:
                        print(f"  Insert error: {ie}")

    print(f"  Done. {inserted} new records inserted.")
    return {'status': 'ok', 'inserted': inserted}


# ─── Scheduler ───────────────────────────────────────────────────────────────

scheduler = BackgroundScheduler()
scheduler.add_job(sync_attendance, 'interval', hours=6, id='attendance_sync')
scheduler.start()


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('admin_login'))


# ── Admin login ───────────────────────────────────────────────────────────────
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        uname = request.form.get('username', '').strip()
        pwd   = request.form.get('password', '').strip()
        if ADMINS.get(uname) == pwd:
            session['admin'] = uname
            return redirect(url_for('registration'))
        error = 'Invalid admin credentials. Please try again.'
    return render_template('login.html', mode='admin', error=error)


# ── Student login ─────────────────────────────────────────────────────────────
@app.route('/student-login', methods=['GET', 'POST'])
def student_login():
    error = None
    if request.method == 'POST':
        uname = request.form.get('username', '').strip()
        pwd   = request.form.get('password', '').strip()
        with get_db() as conn:
            stu = conn.execute(
                'SELECT * FROM students WHERE username = ?', (uname,)
            ).fetchone()
        if stu and stu['password'] == hash_password(pwd):
            session['student_id']   = stu['id']
            session['student_name'] = stu['student_name']
            return redirect(url_for('dashboard'))
        error = 'Invalid username or password.'
    return render_template('login.html', mode='student', error=error)


# ── Registration ──────────────────────────────────────────────────────────────
@app.route('/register-student', methods=['GET', 'POST'])
def registration():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    message = None
    error   = None
    students = []

    with get_db() as conn:
        students = conn.execute(
            'SELECT id, username, student_name, class, board, stream FROM students ORDER BY id DESC'
        ).fetchall()

    if request.method == 'POST':
        uname  = request.form.get('username', '').strip()
        pwd    = request.form.get('password', '').strip()
        name   = request.form.get('student_name', '').strip()
        cls    = request.form.get('class', '').strip()
        board  = request.form.get('board', '').strip()
        stream = request.form.get('stream', 'nan').strip() or 'nan'

        if int(cls) < 11:
            stream = 'nan'

        if not all([uname, pwd, name, cls, board]):
            error = 'All fields are required.'
        else:
            try:
                with get_db() as conn:
                    conn.execute(
                        '''INSERT INTO students (username, password, student_name, class, board, stream)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (uname, hash_password(pwd), name, cls, board, stream)
                    )
                message = f'Student "{name}" registered successfully!'
                with get_db() as conn:
                    students = conn.execute(
                        'SELECT id, username, student_name, class, board, stream FROM students ORDER BY id DESC'
                    ).fetchall()
            except sqlite3.IntegrityError:
                error = f'Username "{uname}" already exists.'

    return render_template('registration.html',
                           admin=session['admin'],
                           students=students,
                           message=message,
                           error=error)


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route('/dashboard')
def dashboard():
    if 'student_id' not in session:
        return redirect(url_for('student_login'))

    sid = session['student_id']
    with get_db() as conn:
        stu = conn.execute('SELECT * FROM students WHERE id = ?', (sid,)).fetchone()
        records = conn.execute(
            'SELECT * FROM attendance WHERE student_id = ? ORDER BY date DESC, time DESC', (sid,)
        ).fetchall()

    total    = len(records)
    present  = sum(1 for r in records if r['status'].upper() == 'PRESENT')
    absent   = total - present
    pct      = round((present / total * 100), 1) if total else 0
    latest   = records[0]['status'] if records else 'N/A'

    return render_template('dashboard.html',
                           student=stu,
                           records=records,
                           total=total,
                           present=present,
                           absent=absent,
                           pct=pct,
                           latest=latest)


# ── Refresh records (manual trigger) ─────────────────────────────────────────
@app.route('/refresh-records', methods=['POST'])
def refresh_records():
    if 'admin' not in session:
        return jsonify({'status': 'unauthorized'}), 403
    result = sync_attendance()
    return jsonify(result)


# ── API sync endpoint (external trigger) ──────────────────────────────────────
@app.route('/api/sync', methods=['POST'])
def api_sync():
    result = sync_attendance()
    return jsonify(result)


# ── Logout ────────────────────────────────────────────────────────────────────
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('admin_login'))


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(debug=True, use_reloader=False)
