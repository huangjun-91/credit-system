"""
鏁欏笀鑾峰璇佷功绠＄悊绯荤粺 - 鍚庣 (Flask)
鍔熻兘锛氭暀甯堟敞鍐?鐧诲綍銆佷笂浼犳寚瀵煎鐢熻幏濂栬瘉涔︺€佺鐞嗗憳瀹℃牳銆佸鍒嗙粺璁?"""

import os
import sqlite3
import uuid
import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production')

# ========== 閰嶇疆 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', BASE_DIR)
DB_PATH = os.path.join(DATA_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ========== 鑾峰灞傛涓庣瓑绾ч€夐」 ==========
AWARD_LEVELS = ['鍥藉绾?, '鐪侀儴绾?, '甯傚巺绾?, '鏍＄骇', '闄㈢骇']
AWARD_GRADES = ['涓€绛夊', '浜岀瓑濂?, '涓夌瓑濂?, '鐗圭瓑濂?, '浼樼濂?, '鍏ュ洿濂?, '鍏朵粬']

# ========== 鏁版嵁搴撳垵濮嬪寲 ==========
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            real_name TEXT NOT NULL DEFAULT '',
            teacher_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            department TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'teacher',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS credits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '鍏朵粬',
            award_level TEXT NOT NULL DEFAULT '鏍＄骇',
            award_grade TEXT NOT NULL DEFAULT '涓€绛夊',
            credits REAL NOT NULL DEFAULT 1,
            description TEXT DEFAULT '',
            image_path TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT '寰呭鏍?,
            submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            review_time TIMESTAMP,
            reviewer_id INTEGER,
            review_comment TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        -- 鎻掑叆榛樿绠＄悊鍛?        INSERT OR IGNORE INTO users (username, password, real_name, role)
            VALUES ('admin', 'admin123', '绠＄悊鍛?, 'admin');
    """)
    conn.commit()
    conn.close()

init_db()

# ========== 宸ュ叿鍑芥暟 ==========
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('璇峰厛鐧诲綍', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('闇€瑕佺鐞嗗憳鏉冮檺', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def get_teacher_stats(conn, user_id):
    """鑾峰彇鏁欏笀瀛﹀垎缁熻"""
    stats = conn.execute("""
        SELECT 
            award_level,
            SUM(credits) as total,
            COUNT(*) as count
        FROM credits 
        WHERE user_id = ? AND status = '宸查€氳繃'
        GROUP BY award_level
    """, (user_id,)).fetchall()
    return {row['award_level']: {'total': row['total'], 'count': row['count']} for row in stats}

# ========== 璺敱 ==========

@app.route('/')
def index():
    if 'user_id' in session:
        user_id = session['user_id']
        role = session['role']
        if role == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('teacher_dashboard'))
    return render_template('index.html')

# ----- 璁よ瘉 -----
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if user and user['password'] == password:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['real_name'] = user['real_name']
            session['role'] = user['role']
            flash(f'娆㈣繋鍥炴潵锛寋user["real_name"] or user["username"]}锛?, 'success')
            return redirect(url_for('index'))
        flash('鐢ㄦ埛鍚嶆垨瀵嗙爜閿欒', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        real_name = request.form.get('real_name', '').strip()
        teacher_id = request.form.get('teacher_id', '').strip()
        title = request.form.get('title', '').strip()
        department = request.form.get('department', '').strip()

        if not username or not password:
            flash('鐢ㄦ埛鍚嶅拰瀵嗙爜涓嶈兘涓虹┖', 'danger')
            return render_template('register.html')

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (username, password, real_name, teacher_id, title, department, role) VALUES (?, ?, ?, ?, ?, ?, 'teacher')",
                (username, password, real_name, teacher_id, title, department)
            )
            conn.commit()
            flash('娉ㄥ唽鎴愬姛锛佽鐧诲綍', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('鐢ㄦ埛鍚嶅凡瀛樺湪', 'danger')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('宸查€€鍑虹櫥褰?, 'info')
    return redirect(url_for('login'))

# ----- 鏁欏笀绔?-----
@app.route('/teacher')
@login_required
def teacher_dashboard():
    if session.get('role') != 'teacher':
        return redirect(url_for('index'))
    conn = get_db()
    user_id = session['user_id']
    records = conn.execute(
        "SELECT * FROM credits WHERE user_id = ? ORDER BY submit_time DESC",
        (user_id,)
    ).fetchall()
    stats = get_teacher_stats(conn, user_id)
    total_credits = sum(s['total'] for s in stats.values())
    conn.close()
    return render_template('teacher.html', records=records, stats=stats, total_credits=total_credits,
                           award_levels=AWARD_LEVELS, award_grades=AWARD_GRADES)

@app.route('/teacher/submit', methods=['POST'])
@login_required
def submit_credit():
    if session.get('role') != 'teacher':
        flash('浠呴檺鏁欏笀鎿嶄綔', 'danger')
        return redirect(url_for('index'))

    title = request.form.get('title', '').strip()
    award_level = request.form.get('award_level', '').strip()
    award_grade = request.form.get('award_grade', '').strip()
    credits = request.form.get('credits', 1)
    description = request.form.get('description', '').strip()

    if not title or not award_level or not award_grade:
        flash('璇峰～鍐欒幏濂栧悕绉般€佸眰娆″拰绛夌骇', 'danger')
        return redirect(url_for('teacher_dashboard'))

    try:
        credits = float(credits)
        if credits <= 0:
            raise ValueError
    except ValueError:
        flash('鎶樼畻瀛﹀垎鏁板繀椤诲ぇ浜?', 'danger')
        return redirect(url_for('teacher_dashboard'))

    image_path = ''
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_path = filename

    conn = get_db()
    conn.execute(
        """INSERT INTO credits (user_id, title, category, award_level, award_grade, credits, description, image_path, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, '寰呭鏍?)""",
        (session['user_id'], title, award_level, award_level, award_grade, credits, description, image_path)
    )
    conn.commit()
    conn.close()

    flash('鑾峰璇佷功鐢宠宸叉彁浜わ紝绛夊緟绠＄悊鍛樺鏍?, 'success')
    return redirect(url_for('teacher_dashboard'))

# ----- 绠＄悊鍛樼 -----
@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    pending = conn.execute("""
        SELECT c.*, u.real_name, u.teacher_id, u.department
        FROM credits c JOIN users u ON c.user_id = u.id
        WHERE c.status = '寰呭鏍?
        ORDER BY c.submit_time DESC
    """).fetchall()
    
    all_records = conn.execute("""
        SELECT c.*, u.real_name, u.teacher_id, u.department
        FROM credits c JOIN users u ON c.user_id = u.id
        ORDER BY c.submit_time DESC
        LIMIT 200
    """).fetchall()

    teachers = conn.execute(
        "SELECT id, real_name, teacher_id, department FROM users WHERE role = 'teacher'"
    ).fetchall()
    conn.close()
    return render_template('admin.html', pending=pending, all_records=all_records, teachers=teachers)

@app.route('/admin/review/<int:credit_id>', methods=['POST'])
@admin_required
def review_credit(credit_id):
    action = request.form.get('action', '')
    comment = request.form.get('comment', '').strip()

    conn = get_db()
    if action == 'approve':
        conn.execute(
            "UPDATE credits SET status = '宸查€氳繃', review_time = CURRENT_TIMESTAMP, reviewer_id = ?, review_comment = ? WHERE id = ?",
            (session['user_id'], comment, credit_id)
        )
        flash('宸插鏍搁€氳繃', 'success')
    elif action == 'reject':
        conn.execute(
            "UPDATE credits SET status = '宸叉嫆缁?, review_time = CURRENT_TIMESTAMP, reviewer_id = ?, review_comment = ? WHERE id = ?",
            (session['user_id'], comment or '鏈€氳繃瀹℃牳', credit_id)
        )
        flash('宸叉嫆缁濇鐢宠', 'warning')
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/teacher/<int:teacher_id>')
@admin_required
def admin_teacher_detail(teacher_id):
    conn = get_db()
    teacher = conn.execute("SELECT * FROM users WHERE id = ?", (teacher_id,)).fetchone()
    if not teacher:
        flash('鏁欏笀涓嶅瓨鍦?, 'danger')
        return redirect(url_for('admin_dashboard'))
    records = conn.execute(
        "SELECT * FROM credits WHERE user_id = ? ORDER BY submit_time DESC",
        (teacher_id,)
    ).fetchall()
    stats = get_teacher_stats(conn, teacher_id)
    total_credits = sum(s['total'] for s in stats.values())
    conn.close()
    return render_template('admin_teacher.html', teacher=teacher, records=records, stats=stats, total_credits=total_credits)

@app.route('/admin/export')
@admin_required
def export_data():
    import csv
    import io
    conn = get_db()
    records = conn.execute("""
        SELECT c.id, u.real_name, u.teacher_id, u.department, c.title, c.award_level,
               c.award_grade, c.credits, c.status, c.submit_time, c.review_time
        FROM credits c JOIN users u ON c.user_id = u.id
        ORDER BY u.real_name, c.submit_time
    """).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['缂栧彿', '濮撳悕', '宸ュ彿', '鎵€灞炲闄?, '鑾峰鍚嶇О', '鑾峰灞傛', '鑾峰绛夌骇', '鎶樼畻瀛﹀垎', '鐘舵€?, '鎻愪氦鏃堕棿', '瀹℃牳鏃堕棿'])
    for r in records:
        writer.writerow([r['id'], r['real_name'], r['teacher_id'], r['department'],
                        r['title'], r['award_level'], r['award_grade'],
                        r['credits'], r['status'],
                        r['submit_time'], r['review_time']])
    return output.getvalue(), 200, {
        'Content-Type': 'text/csv; charset=utf-8-sig',
        'Content-Disposition': f'attachment; filename=鏁欏笀鑾峰瀛﹀垎_{datetime.date.today()}.csv'
    }

# ----- 鍥剧墖璁块棶 -----
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ========== 鍚姩 ==========
if __name__ == '__main__':
    print("=" * 50)
    print("   鏁欏笀鑾峰璇佷功绠＄悊绯荤粺 v1.0")
    print("=" * 50)
    print(f"   鍚姩鍦板潃: http://127.0.0.1:5000")
    print(f"   绠＄悊鍛樿处鍙? admin / admin123")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
