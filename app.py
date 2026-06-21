"""
云阳县民德小学教师获奖证书管理系统 - 后端 (Flask)
功能：教师注册/登录、上传指导学生获奖证书、管理员审核、学分统计
"""

import os
import sqlite3
import uuid
import datetime
import smtplib
import json
from functools import wraps
from email.mime.text import MIMEText
from email.header import Header

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production')

# ========== 注册 Word 排版工具 ==========
try:
    from format_tool import format_bp
    app.register_blueprint(format_bp)
    print("   ✅ Word排版工具已加载 -> /format/")
except ImportError as e:
    print(f"   ⚠️  Word排版工具未加载: {e}")

# ========== 配置 ==========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', BASE_DIR)
DB_PATH = os.path.join(DATA_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')

# ========== 邮件配置 ==========
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.qq.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', '1573903046@qq.com')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
ALERT_EMAIL = os.environ.get('ALERT_EMAIL', '1573903046@qq.com')

def send_email(subject, body):
    """发送邮件通知"""
    if not SMTP_PASSWORD:
        return False
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = SMTP_USER
        msg['To'] = ALERT_EMAIL
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [ALERT_EMAIL], msg.as_string())
        return True
    except Exception as e:
        print(f"[邮件发送失败] {e}")
        return False

# ========== 健康检查 ==========
@app.route('/health')
def health_check():
    """健康检查接口 - 供外部监控使用"""
    db_ok = os.path.exists(DB_PATH)
    upload_ok = os.path.exists(UPLOAD_FOLDER)
    status = {
        'status': 'ok' if db_ok else 'degraded',
        'timestamp': datetime.datetime.now().isoformat(),
        'db_exists': db_ok,
        'volume_configured': bool(os.environ.get('RAILWAY_VOLUME_MOUNT_PATH')),
        'user_count': None,
        'record_count': None,
    }
    if db_ok:
        try:
            conn = sqlite3.connect(DB_PATH)
            status['user_count'] = conn.execute("SELECT COUNT(*) FROM users WHERE role='teacher'").fetchone()[0]
            status['record_count'] = conn.execute("SELECT COUNT(*) FROM credits").fetchone()[0]
            conn.close()
        except:
            pass
    return jsonify(status)

# ----- 测试邮件接口 -----
@app.route('/admin/test-email')
def test_email():
    """触发发送测试邮件"""
    from flask import request as flask_req
    # 简单鉴权，防止被滥用
    allowed_keys = [os.environ.get('SECRET_KEY', '')[:8], 'test', 'admin']
    key = flask_req.args.get('key', '')
    if key not in allowed_keys:
        return jsonify({'error': 'unauthorized', 'hint': '需要有效的 key 参数'}), 403
    sent = send_email(
        '✅ 信用系统测试通知',
        f'系统健康检查通过！\n\n'
        f'时间：{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n'
        f'Volume：已持久化\n'
        f'状态：正常运行\n\n'
        f'-- 云阳县民德小学教师获奖证书管理系统'
    )
    if sent:
        return jsonify({'ok': True, 'message': '测试邮件已发送到 1573903046@qq.com'})
    return jsonify({'ok': False, 'message': '邮件发送失败，请检查 SMTP 配置'}), 500
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}
MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ========== 获奖层次与等级选项 ==========
AWARD_LEVELS = ['国家级', '市级', '区县级']
AWARD_GRADES = ['一等奖（第1-2名）', '二等奖（第3-5名）', '三等奖（第6-8名）']

# ========== 数据库初始化 ==========
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def migrate_db():
    """Add new columns to existing tables without dropping data."""
    conn = get_db()
    try:
        conn.execute("ALTER TABLE credits ADD COLUMN is_team INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE credits ADD COLUMN team_size INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE credits ADD COLUMN semester TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE credits ADD COLUMN teacher_type TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE credits ADD COLUMN guide_count INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE credits ADD COLUMN class_students INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    conn.close()

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
            award_level TEXT NOT NULL DEFAULT '国家级',
            award_grade TEXT NOT NULL DEFAULT '一等奖（第1-2名）',
            credits REAL NOT NULL DEFAULT 1,
            description TEXT DEFAULT '',
            image_path TEXT DEFAULT '',
            is_team INTEGER DEFAULT 0,
            team_size INTEGER DEFAULT 1,
            semester TEXT DEFAULT '',
            teacher_type TEXT DEFAULT '',
            guide_count INTEGER DEFAULT 1,
            class_students INTEGER DEFAULT 0,
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
migrate_db()

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
        real_name = username  # Use username as real_name
        teacher_id = ''
        title = ''
        department = ''

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
        """INSERT INTO credits (user_id, title, category, award_level, award_grade, credits, description, image_path, is_team, team_size, semester, teacher_type, guide_count, class_students, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '待审核')""",
        (session['user_id'], title, award_level, award_level, award_grade, credits, description, image_path,
         int(request.form.get('is_team', 0)),
         int(request.form.get('team_size', 1)),
         request.form.get('semester', '').strip(),
         request.form.get('teacher_type', '').strip(),
         int(request.form.get('guide_count', 1)),
         int(request.form.get('class_students', 0)))
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
    return render_template('admin.html', pending=pending, all_records=all_records, teachers=teachers, volume_status=get_volume_status())

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
    conn = get_db()
    records = conn.execute("""
        SELECT c.id, u.real_name, u.teacher_id, u.department, c.title, c.award_level,
               c.award_grade, c.credits, c.is_team, c.team_size, c.semester, c.teacher_type, c.guide_count, c.class_students, c.status, c.submit_time, c.review_time
        FROM credits c JOIN users u ON c.user_id = u.id
        ORDER BY u.real_name, c.submit_time
    """).fetchall()
    conn.close()

    # Generate CSV as bytes with BOM for Excel compatibility
    header = ['编号', '姓名', '工号', '所属学院', '学期', '获奖名称', '获奖层次', '获奖等级', '折算学分', '是否团队赛', '参赛人数', '教师类型', '指导教师人数', '本班学生数', '状态', '提交时间', '审核时间']
    rows = ['\t'.join(header)]
    for r in records:
        teamDetail = ''
        if r['is_team']:
            if r['teacher_type'] == 'guide':
                teamDetail = f'指导教师x{r["guide_count"] or 1}'
            elif r['teacher_type'] == 'assistant':
                teamDetail = f'班辅(本班{r["class_students"] or 0}人)'
        rows.append('\t'.join([
            str(r['id']),
            r['real_name'] or '',
            r['teacher_id'] or '',
            r['department'] or '',
            r['semester'] or '',
            r['title'] or '',
            r['award_level'] or '',
            r['award_grade'] or '',
            f'{r["credits"]:.4f}',
            '是' if r['is_team'] else '否',
            str(r['team_size'] or 1),
            r['teacher_type'] or '',
            str(r['guide_count'] or 1),
            str(r['class_students'] or 0),
            r['status'] or '',
            r['submit_time'] or '',
            r['review_time'] or ''
        ]))
    csv_content = '\r\n'.join(rows)
    filename = f'teacher_credits_{datetime.date.today()}.csv'
    csv_bytes = csv_content.encode('utf-8-sig')
    from flask import make_response
    resp = make_response(csv_bytes)
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp

# ----- 管理后台：数据清零（保留管理员账号） -----
@app.route('/admin/clear-data', methods=['POST'])
@admin_required
def clear_all_data():
    """保留管理员账号，删除所有教师用户、学分记录、上传文件"""
    conn = get_db()
    try:
        # 1. 删除所有上传文件
        if os.path.exists(UPLOAD_FOLDER):
            for f in os.listdir(UPLOAD_FOLDER):
                fp = os.path.join(UPLOAD_FOLDER, f)
                if os.path.isfile(fp):
                    os.remove(fp)

        # 2. 删除所有学分记录（关联外键，先删 credits）
        conn.execute("DELETE FROM credits")

        # 3. 删除所有非管理员用户
        conn.execute("DELETE FROM users WHERE role != 'admin'")

        conn.commit()
        flash(f'✅ 数据已清零（{datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}）', 'success')
        flash('保留管理员账号 (admin)。所有教师账号、学分记录、上传文件已删除。', 'info')
    except Exception as e:
        conn.rollback()
        flash(f'❌ 清零失败：{str(e)}', 'danger')
    finally:
        conn.close()
    return redirect(url_for('admin_dashboard'))

# ----- Volume 状态检测（注入到模板） -----
def get_volume_status():
    """检测数据是否存储在 Railway Volume 中"""
    volume_path = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '')
    if volume_path:
        return {
            'configured': True,
            'path': volume_path,
            'db_exists': os.path.exists(DB_PATH),
            'upload_count': len(os.listdir(UPLOAD_FOLDER)) if os.path.exists(UPLOAD_FOLDER) else 0,
        }
    return {
        'configured': False,
        'path': '未配置（数据存储在临时文件系统中）',
        'hint': '建议在 Railway 后台添加 Volume 并设置环境变量 RAILWAY_VOLUME_MOUNT_PATH=/data',
    }

# ----- 图片访问 -----
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ========== 启动 ==========
if __name__ == '__main__':
    print("=" * 50)
    print("   云阳县民德小学教师获奖证书管理系统 v1.0")
    print("=" * 50)
    print(f"   启动地址: http://127.0.0.1:5000")
    print(f"   管理员账号: admin / admin123")
    vol = get_volume_status()
    if vol['configured']:
        print(f"   ✅ Volume: {vol['path']}")
    else:
        print(f"   ⚠️  Volume: 未配置 - 数据将在重启后丢失")
    if SMTP_PASSWORD:
        print(f"   ✅ 邮件通知: 已配置 -> {ALERT_EMAIL}")
    else:
        print(f"   ⚠️  邮件通知: 未配置 (设置 SMTP_PASSWORD)")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
