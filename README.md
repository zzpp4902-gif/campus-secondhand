# 중고캠퍼스 校园二手物品交易平台

在韩留学生校园二手物品交易平台，全中文界面，支持商品发布、浏览搜索、意向申请、留言沟通、线下当面交易。

## 🌐 在线体验地址

- **在线访问网址**：[https://campus-secondhand-eo84.onrender.com](https://campus-secondhand-eo84.onrender.com)
- **GitHub 仓库**：[https://github.com/zzpp4902-gif/campus-secondhand](https://github.com/zzpp4902-gif/campus-secondhand)
- **演示测试账号**：
  - 卖家账号：`demo` / 密码：`demo123`（灵山大学，已有 30 件预设商品）
  - 买家账号：`buyer` / 密码：`demo123`（高丽大学）

## 技术栈

- **后端**：Python Flask + flask-login
- **数据库**：PostgreSQL（Supabase）
- **前端**：原生 HTML + CSS + JavaScript
- **图片存储**：Base64 存入数据库（零服务器文件存储）
- **部署**：Render + Gunicorn

## 功能模块

1. **用户系统**：注册、登录、退出，学校下拉选择（11所韩国高校）
2. **商品发布**：标题、分类、价格、成色、描述、单张图片（自动压缩转 Base64）
3. **浏览搜索**：商品网格列表、关键词模糊搜索、分类筛选
4. **商品详情**：大图展示、卖家信息、收藏、意向申请、公开留言板
5. **意向申请**：三态流转（申请中 → 已约定 → 已完成），商品状态同步
6. **个人中心**：我的发布（含申请管理）、我的申请、我的收藏

## 本地运行

### 1. 配置数据库

在 [Supabase](https://supabase.com) 注册免费项目，获取：
- Project URL
- anon public key
- Database connection string（URI 格式）

复制 `.env.example` 为 `.env`，填入配置：

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
DATABASE_URL=postgresql://postgres.xxx:password@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres
SECRET_KEY=campus-secondhand-secret-2026
```

### 2. 安装依赖

```bash
cd campus-secondhand
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. 初始化数据库

```bash
python init_db.py
```

### 4. 导入模拟数据（可选）

```bash
python seed_data.py
```

会创建测试账号 `demo / demo123`（灵山大学）和 30 条示例商品。

### 5. 启动服务

```bash
python app.py
```

浏览器打开 http://localhost:5000

## 部署到 Render

1. 将项目推送到 GitHub 仓库
2. 在 Render 创建 Web Service，连接 GitHub 仓库
3. 配置：
   - **Build Command**：`pip install -r requirements.txt && python init_db.py`
   - **Start Command**：`gunicorn app:app`
4. 在 Environment Variables 中填入 `DATABASE_URL`、`SECRET_KEY` 等
5. 部署完成后访问 Render 提供的 URL

项目已包含 `Procfile` 和 `render.yaml`，可自动识别配置。

## 数据库表结构

- **users**：用户表（id, username, password_hash, nickname, school, created_at）
- **items**：商品表（id, seller_id, title, category, price, condition, description, image_base64, status, created_at）
- **applications**：意向申请表（id, item_id, buyer_id, seller_id, status, message, created_at）
- **messages**：商品留言表（id, item_id, user_id, content, created_at）
- **favorites**：收藏表（id, user_id, item_id, created_at，联合唯一约束）

## 注意事项

- 本项目为课程实践项目，不做线上支付、实时私信、学生实名认证、管理员后台
- 交易均为线下当面交易，平台仅提供信息撮合
- 图片以 Base64 存入数据库，单张建议控制在 500KB 以内
- 商品状态与申请状态联动：卖家同意约定 → 商品标记为「已约定」并从首页隐藏；确认完成 → 商品标记为「已完成」
