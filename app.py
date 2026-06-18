"""
鏁欏笀鑾峰璇佷功绠＄悊绯荤粺 - 鍚庣徿 (Flask)
功能：教师注册／登录、上传指导学生获奖证书、管理员审核、学分统计
*/

import os
import sqlite3
import uuid
import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-in-production')

# ========= 配置 =========
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', BASE_DIR)
DB_PATH = os.path.join(DATA_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ========= 获喞层次与等级选项 =========
AWARD_LEVELS = ['国家级', '省部级', '市厸级', '校级', '院级']
AWARD_GRADES = ['一等喞', '二等喞', '三等喞', '特等喞', '优秀喞', '嘅奖喞', '其他']

# ========= 揰接库初始化 =========
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
            award_grade TEXT NOT NULL DEFAULT '一等喞',
            credits REAL NOT NULL DEFAULT 1,
           description TEXT DEFAULT '',
            image_path TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT '待审批',
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

# ========= 工具函数 =========
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

# ========= 路由 =========

@app.route('')
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
            flash(f'欢迎回i�R��W6W%�'&V����R%��"W6W%�'W6W&��R%����r�w7V66W72r��&WGW&�&VF�&V7B�W&��f�"�v��FW�r���f�6��~yJ�h�~Y�h�nZ�nz�I�r�vF�vW"r��&WGW&�&V�FW%�FV��FR�v��v���F��r����&�WFR�r�&Vv�7FW"r��WF��G3ղttUBr�u�5BuҐ�FVb&Vv�7FW"�����b&WVW7B��WF��B��u�5Bs��W6W&��R�&WVW7B�f�&��vWB�wW6W&��Rr�rr��7G&����77v�&B�&WVW7B�f�&��vWB�w77v�&Br�rr��7G&����&V����R�&WVW7B�f�&��vWB�w&V����Rr�rr��7G&����FV6�W%��B�&WVW7B�f�&��vWB�wFV6�W%��Br�rr��7G&����F�F�R�&WVW7B�f�&��vWB�wF�F�Rr�rr��7G&����FW'F�V�B�&WVW7B�f�&��vWB�vFW'F�V�Br�rr��7G&������b��BW6W&��R�"��B77v�&C��f�6��~yJ�h�~Y�Y(�Z�nzK�ވ;�K��z��r�vF�vW"r��&WGW&�&V�FW%�FV��FR�w&Vv�7FW"�F��r���6����vWE�F"���G'���6����W�V7WFR��$��4U%B��D�W6W'2�W6W&��R�77v�&B�&V����R�FV6�W%��B�F�F�R�FW'F�V�B�&��R�d�TU2�������������wFV6�W"r�"���W6W&��R�77v�&B�&V����R�FV6�W%��B�F�F�R�FW'F�V�B����6����6��֗B���f�6��~k:�Xh�h�X������~y��[�Rr�w7V66W72r��&WGW&�&VF�&V7B�W&��f�"�v��v��r���W�6WB7ƗFS2��FVw&�G�W'&�#��f�6��~yJ�h�~Y�[{.ZَYʂr�vF�vW"r��f���Ǔ��6����6��6R���&WGW&�&V�FW%�FV��FR�w&Vv�7FW"�F��r����&�WFR�r���v�WBr��FVb��v�WB����6W76����6�V"���f�6��~[{.�X{�y��[�Rr�v��f�r��&WGW&�&VF�&V7B�W&��f�"�v��v��r����2�����iY�[��z������Ф�&�WFR�r�FV6�W"r����v���&WV�&V@�FVbFV6�W%�F6�&�&B�����b6W76����vWB�w&��Rr��wFV6�W"s��&WGW&�&VF�&V7B�W&��f�"�v��FW�r���6����vWE�F"���W6W%��B�6W76���wW6W%��BuТ&V6�&G2�6����W�V7WFR��%4T�T5B�e$��7&VF�G2t�U$RW6W%��B���$DU"%�7V&֗E�F��RDU42"���W6W%��B���fWF6����7FG2�vWE�FV6�W%�7FG2�6����W6W%��B��F�F��7&VF�G2�7V҇5�wF�F�u�f�"2��7FG2�f�VW2����6����6��6R���&WGW&�&V�FW%�FV��FR�wFV6�W"�F��r�&V6�&G3�&V6�&G2�7FG3�7FG2�F�F��7&VF�G3�F�F��7&VF�G2��v&E��WfV�3�t$E��UdT�2�v&E�w&FW3�t$E�u$DU2����&�WFR�r�FV6�W"�7V&֗Br��WF��G3ղu�5BuҐ���v���&WV�&V@�FVb7V&֗E�7&VF�B�����b6W76����vWB�w&��Rr��wFV6�W"s��f�6��~K�^��iY�[��i8�K��r�vF�vW"r��&WGW&�&VF�&V7B�W&��f�"�v��FW�r����F�F�R�&WVW7B�f�&��vWB�wF�F�Rr�rr��7G&����v&E��WfV��&WVW7B�f�&��vWB�vv&E��WfV�r�rr��7G&����v&E�w&FR�&WVW7B�f�&��vWB�vv&E�w&FRr�rr��7G&����7&VF�G2�&WVW7B�f�&��vWB�v7&VF�G2r���FW67&�F����&WVW7B�f�&��vWB�vFW67&�F���r�rr��7G&������b��BF�F�R�"��Bv&E��WfV��"��Bv&E�w&FS��f�6��~��~Z�Xi���~Yi�Y�z{8[.j�Y(�z؞{�rr�vF�vW"r��&WGW&�&VF�&V7B�W&��f�"�wFV6�W%�F6�&�&Br����G'���7&VF�G2�f��B�7&VF�G2���b7&VF�G2����&�6Rf�VTW'&� �W�6WBf�VTW'&�#��f�6��~h��z�~Z�nX�ni[[�^��ZJ~K��r�vF�vW"r��&WGW&�&VF�&V7B�W&��f�"�wFV6�W%�F6�&�&Br������vU�F��rp��bv��vRr��&WVW7B�f��W3��f��R�&WVW7B�f��W5�v��vRuТ�bf��R�Bf��R�f��V��R�B���vVE�f��R�f��R�f��V��R���W�B�f��R�f��V��R�'7ƗB�r�r�������vW"���f��V��R�b'�WV�B�WV�CB���W���W�G� �f��R�6fR��2�F������6��f�u�uU��E�d��DU"u��f��V��R�����vU�F��f��V��P��6����vWE�F"���6����W�V7WFR��""$��4U%B��D�7&VF�G2�W6W%��B�F�F�R�6FVv�'��v&E��WfV��v&E�w&FR�7&VF�G2�FW67&�F������vU�F��7FGW2��d�TU2�����������������~[�^Z�h��r�""���6W76���wW6W%��Bu��F�F�R�v&E��WfV��v&E��WfV��v&E�w&FR�7&VF�G2�FW67&�F������vU�F�����6����6��֗B���6����6��6R����f�6��~��~Yi��K�nyK>��~[{.h�K�N���z؞[�^z�ynY�Z�j�r�w7V66W72r��&WGW&�&VF�&V7B�W&��f�"�wFV6�W%�F6�&�&Br����2�����z�ynY�z������Ф�&�WFR�r�F֖�r��F֖��&WV�&V@�FVbF֖��F6�&�&B����6����vWE�F"���V�F��r�6����W�V7WFR�"" �4T�T5B2��R�&V����R�R�FV6�W%��B�R�FW'F�V�@�e$��7&VF�G22����W6W'2R��2�W6W%��B�R�@�t�U$R2�7FGW2�~[�^Z�h��p��$DU"%�2�7V&֗E�F��RDU40�"""��fWF6���
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
        flash('已审批通过', 'success')
    elif action == 'reject':
        conn.execute(
            "UPDATE credits SET status = '已拒绝', review_time = CURRENT_TIMESTAMP, reviewer_id = ?, review_comment = ? WHERE id = ?",
            (session['user_id'], comment or '未通过审批', credit_id)
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

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['编号', '姓名', '工号', '所属学院', '获喞名称', '获喞层次',
                   '获喞等级', '折算学分', '状态', '提交时间', '审核时间'])
    for r in records:
        writer.writerow([r['id'], r['real_name'], r['teacher_id'], r['department'],
                        r['title'], r['award_level'], r['award_grade'],
                        r['credits'], r['status'],
                        r['submit_time'], r['review_time']])
    return output.getvalue(), 200, {
        'Content-Type': 'text/csv; charset=utf-8-sig',
        'Content-Disposition': f'attachment; filename=教师获喞学分_{datetime.date.today()}.csv'
    }

# ----- 图片访问 -----
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ========== 启动 ==========
if __name__ == '__main__':
    print("=" * 50)
    print("   教师获喞证书管理系统 v1.0")
    print("=" * 50)
    print(f"   启动地址: http://127.0.0.1:5000")
    print(f"   管理员账号: admin / admin123")
    print("=" * 50)
    app.run(host='0.0.0.0', port=5000, debug=True)
