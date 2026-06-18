# 学分管理系统 📚

一个美观、轻量的学分自助登记系统，支持图片上传、管理员审核、学分分类统计。

## 功能

### 学生端
- 📝 **自主登记学分**：选择类型（德智体美劳+创新创业），填写说明
- 🖼️ **上传证明材料**：支持 JPG/PNG/PDF，最大 16MB
- 📊 **分类统计**：自动汇总各类别已通过学分
- 👀 **实时进度**：查看每项申请的审核状态

### 管理员端
- ✅ **一键审核**：通过/拒绝，可填写审核意见
- 👥 **学生管理**：查看每个学生的学分详情
- 📥 **数据导出**：一键导出 CSV 统计文件

## 快速启动

### 方法 1：直接运行（需要 Python）

```bash
# 1. 安装 Python（如果没有的话）
# 下载：https://www.python.org/downloads/
# 安装时勾选 "Add Python to PATH"

# 2. 安装依赖
pip install flask

# 3. 启动
python app.py
```

浏览器访问：http://127.0.0.1:5000

### 方法 2：Docker 部署

```bash
docker build -t credit-system .
docker run -d -p 5000:5000 -v credit-data:/app/uploads credit-system
```

## 默认账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 管理员 | admin | admin123 |
| 学生 | 注册获取 | 自行设置 |

## 部署到服务器（免费方案）

### 方案 A：Railway（推荐，免费）
1. 注册 https://railway.app （GitHub 登录）
2. New Project → Deploy from GitHub repo
3. 自动检测 Python，直接部署
4. 免费额度足够个人/班级使用

### 方案 B：Vercel + Python
需要加 vercel.json 配置，可免费托管

### 方案 C：自己的服务器
直接 Python 运行，Nginx 反代即可

## 项目结构

```
credit-system/
├── app.py              # 主程序
├── requirements.txt    # 依赖
├── templates/          # 前端模板
│   ├── index.html      # 首页
│   ├── login.html      # 登录
│   ├── register.html   # 注册
│   ├── student.html    # 学生面板
│   ├── admin.html      # 管理面板
│   └── admin_student.html  # 学生详情
├── uploads/            # 上传文件目录
└── database.db         # SQLite 数据库（自动创建）
```

## 技术栈

- **后端**：Python Flask
- **前端**：Bootstrap 5 + Bootstrap Icons
- **数据库**：SQLite（零配置）
- **图片存储**：本地文件系统
