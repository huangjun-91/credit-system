"""
教师获奖证书管理系统 - 后端 (Flask)
功能：教师注册/登录、上传指导学生获奖证书、管理员审核、学分统计
"""

import os
import sqlite3
import uuid
import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production')

# ========== 配置 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', BASE_DIR)
DB_PATH = os.path.join(DATA_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ========== 获奖层次与等级选项 ==========
AWARD_LEVELS = ['国家级', '省部级', '市厅级', '校级', '院级']
AWARD_GRADES = ['一等奖', '二等奖', '三等奖', '特等奖', '优秀奖', '入围奖', '其他']

# ========== 数据库初始化 ==========
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
            category TEXT NOT NULL DEFAULT '其他',
            award_level TEXT NOT NULL DEFAULT '校级',
            award_grade TEXT NOT NULL DEFAULT '一等奖',
            credits REAL NOT NULL DEFAULT 1,
            description TEXT DEFAULT '',
            image_path TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT '待审核',
            submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            review_time TIMESTAMP,
            reviewer_id INTEGER,
            review_comment TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        -- 插入默认管理员
        INSERT OR IGNORE INTO users (username, password, real_name, role)
            VALUES ('admin', 'admin123', '管理员', 'admin');
    """)
    conn.commit()
    conn.close()

init_db()

# ========== 工具函数 ==========
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('需要管理员权限', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def get_teacher_stats(conn, user_id):
    """获取教师学分统计"""
    stats = conn.execute("""
        SELECT 
            award_level,
            SUM(credits) as total,
            COUNT(*) as count
        FROM credits 
        WHERE user_id = ? AND status = '已通过'
        GROUP BY award_level
    """, (user_id,)).fetchall()
    return {row['award_level']: {'total': row['total'], 'count': row['count']} for row in stats}

# ========== 路由 ==========

@app.route('/')
def index():
    if 'user_id' in session:
        user_id = session['user_id']
        role = session['role']
        if role == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('teacher_dashboard'))
    return render_template('index.html')

# ----- 认证 -----
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
            flash(f'欢迎回来，{user["real_name"] or user["username"]}！', 'success')
            return redirect(url_for('index'))
        flash('用户名或密码错误', 'danger')
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
            flash('用户名和密码不能为空', 'danger')
            return render_template('register.html')

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (username, password, real_name, teacher_id, title, department, role) VALUES (?, ?, ?, ?, ?, ?, 'teacher')",
                (username, password, real_name, teacher_id, title, department)
            )
            conn.commit()
            flash('注册成功！请登录', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('用户名已存在', 'danger')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('已退出登录', 'info')
    return redirect(url_for('login'))

# ----- 教师端 -----
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
        flash('仅限教师操作', 'danger')
        return redirect(url_for('index'))

    title = request.form.get('title', '').strip()
    award_level = request.form.get('award_level', '').strip()
    award_grade = request.form.get('award_grade', '').strip()
    credits = request.form.get('credits', 1)
    description = request.form.get('description', '').strip()

    if not title or not award_level or not award_grade:
        flash('请填写获奖名称、层次和等级', 'danger')
        return redirect(url_for('teacher_dashboard'))

    try:
        credits = float(credits)
        if credits <= 0:
            raise ValueError
    except ValueError:
        flash('折算学分数必须大于0', 'danger')
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
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, '待审核')""",
        (session['user_id'], title, award_level, award_level, award_grade, credits, description, image_path)
    )
    conn.commit()
    conn.close()

    flash('获奖证书申请已提交，等待管理员审核', 'success')
    return redirect(url_for('teacher_dashboard'))

# ----- 管理员端 -----
@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    pending = conn.execute("""
        SELECT c.*, u.real_name, u.teacher_id, u.department
        FROM credits c JOIN users u ON c.user_id = u.id
        WHERE c.status = '待审核'
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
            "UPDATE credits SET status = '已通过', review_time = CURRENT_TIMESTAMP, reviewer_id = ?, review_comment = ? WHERE id = ?",
            (session['user_id'], comment, credit_id)
        )
        flash('已审核通过', 'success')
    elif action == 'reject':
        conn.execute(
            "UPDATE credits SET status = '已拒绝', review_time = CURRENT_TIMESTAMP, reviewer_id = ?, review_comment = ? WHERE id = ?",
            (session['user_id'], comment or '未通过审核', credit_id)
        )
        flash('已拒绝此申请', 'warning')
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/teacher/<int:teacher_id>')
@admin_required
def admin_teacher_detail(teacher_id):
    conn = get_db()
    teacher = conn.execute("SELECT * FROM users WHERE id = ?", (teacher_id,)).fetchone()
    if not teacher:
        flash('教师不存在', 'danger')
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

    # Generate CSV as bytes with BOM for Excel compatibility
    header = ['编号', '姓名', '工号', '所属学院', '获奖名称', '获奖层次', '获奖等级', '折算学分', '状态', '提交时间', '审核时间']
    rows = []
    rows.append(','.join([f'"{h}"' for h in header]))
    for r in records:
        row = ','.join([
            str(r['id']),
            f'"{r["real_name"] or ""}"',
            f'"{r["teacher_id"] or ""}"',
            f'"{r["department"] or ""}"',
            f'"{r["title"] or ""}"',
            f'"{r["award_level"] or ""}"',
            f'"{r["award_grade"] or ""}"',
            str(r['credits']),
            f'"{r["status"] or ""}"',
            f'"{r["submit_time"] or ""}"',
            f'"{r["review_time"] or ""}"'
        ])
        rows.append(row)
    csv_content = '\n'.join(rows)
    filename = f'teacher_credits_{datetime.date.today()}.csv'
    # Use UTF-8 BOM for Excel compatibility
    csv_bytes = csv_content.encode('utf-8-sig')
    return csv_bytes, 200, {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': f"attachment; filename=\"{filename}\""
    }

# ----- 图片访问 -----
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ========== 启动 ==========
if __name__ == '__main__':
    print("=" * 50)
    print("   教师获奖证书管理系统 v1.0")
    print("=" * 50)
    print(f"   启动地址: http://127.0.0.1:5000")
    print(f"   管理员账号: admin / admin123")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
