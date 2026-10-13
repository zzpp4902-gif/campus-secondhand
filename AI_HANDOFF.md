# AI 交接文档：校园二手物品交易平台（高质感 UI 与私聊增强版）

> 本文档写给接手此项目的 AI。读完即可理解项目架构、运行网站、继续进行后续开发与 UI 调整。

---

## 一、项目概况

在韩留学生校园二手物品交易 Web 平台，全中文界面。支持注册登录、商品发布（图片 Base64 存库）、浏览搜索、意向申请三态流转、商品留言、收藏、**一对一私聊在线沟通**。无线上支付，纯线下当面交易。

---

## 二、技术栈（严格遵守，不要替换）

| 层级 | 技术 | 说明 |
|---|---|---|
| **后端** | Python Flask 3.1 | 原生路由与轻量控制器 |
| **认证** | flask-login 0.6.3 | Session-based 用户认证体系 |
| **数据库** | PostgreSQL 17 | 原生 psycopg2 执行原生 SQL，**严禁引入 ORM** |
| **前端** | 原生 HTML5 + Jinja2 模板 + 现代原生 CSS + 原生 JS | **严禁引入 React / Vue / Bootstrap / Tailwind CDN** |
| **图片** | Base64 存数据库 TEXT 字段（前端 Canvas 自动压缩至 800px） | 不要本地文件系统 / S3 |
| **部署** | Gunicorn + Render | 本地开发直接运行 `python app.py` |

---

## 三、项目结构

```text
campus-secondhand/
├── app.py                  # Flask 主程序，全部路由（含私聊、三态流转、鉴权）
├── init_db.py              # 数据库建表脚本（6张表，含 direct_messages，支持幂等创建）
├── seed_data.py            # 演示数据脚本（demo 卖家 + buyer 买家 + 30条示例商品）
├── requirements.txt        # Python 依赖包清单
├── .env.example            # 环境变量模版
├── .env                    # 本地环境变量配置（含 DATABASE_URL, SECRET_KEY, PORT）
├── Procfile                # 云端生产部署入口
├── render.yaml             # Render 蓝图
├── README.md               # 项目基础说明
├── AI_HANDOFF.md           # 本交接文档
├── static/
│   ├── css/style.css       # 现代高质感设计系统（含毛玻璃导航、Bento卡片、私聊样式等）
│   └── js/main.js          # 图片 Canvas 压缩预览、表单校验、下拉交互
└── templates/
    ├── base.html           # 基础模板：毛玻璃导航栏 +「全部功能」大型悬浮菜单（含私聊入口）+ 页脚
    ├── index.html          # 首页：Hero 搜索栏 + 快捷分类药丸 + Bento 商品卡片网格
    ├── detail.html         # 商品详情页：大图展台 + 卖家卡片 + 意向申请弹窗 + 公开留言板
    ├── publish.html        # 发布商品页：拖拽/点击图片上传 Dropzone
    ├── edit_item.html      # 编辑商品页
    ├── profile.html        # 个人中心：用户 Banner + 胶囊 Tabs（我的发布/我的申请/我的收藏）
    ├── login.html          # 登录页（含 demo 测试账号便捷填充）
    └── register.html       # 注册页（用户名、密码、昵称）
```

---

## 四、数据库设计（5张表）

### 1. `users`
- `id` (SERIAL PRIMARY KEY)
- `username` (VARCHAR(50) UNIQUE NOT NULL)
- `password_hash` (VARCHAR(255) NOT NULL)
- `nickname` (VARCHAR(50) NOT NULL)
- `school` (VARCHAR(100) NOT NULL, 注册默认 '其他')
- `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)

### 2. `items`
- `id` (SERIAL PRIMARY KEY)
- `seller_id` (INTEGER REFERENCES users(id) ON DELETE CASCADE)
- `title` (VARCHAR(100) NOT NULL)
- `category` (VARCHAR(20) NOT NULL)
- `price` (INTEGER NOT NULL)
- `condition` (VARCHAR(20) NOT NULL)
- `description` (TEXT)
- `image_base64` (TEXT)
- `status` (VARCHAR(10) NOT NULL DEFAULT '在售') — 取值：`在售` / `已约定` / `已完成`
- `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)

### 3. `applications`
- `id` (SERIAL PRIMARY KEY)
- `item_id` (INTEGER REFERENCES items(id) ON DELETE CASCADE)
- `buyer_id` (INTEGER REFERENCES users(id) ON DELETE CASCADE)
- `seller_id` (INTEGER REFERENCES users(id) ON DELETE CASCADE)
- `status` (VARCHAR(10) NOT NULL DEFAULT '申请中') — 取值：`申请中` / `已约定` / `已完成`
- `message` (VARCHAR(500))
- `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
- `UNIQUE(item_id, buyer_id)`

### 4. `messages`（商品公开留言）
- `id` (SERIAL PRIMARY KEY)
- `item_id` (INTEGER REFERENCES items(id) ON DELETE CASCADE)
- `user_id` (INTEGER REFERENCES users(id) ON DELETE CASCADE)
- `content` (VARCHAR(500) NOT NULL)
- `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)

### 5. `favorites`（商品收藏）
- `id` (SERIAL PRIMARY KEY)
- `user_id` (INTEGER REFERENCES users(id) ON DELETE CASCADE)
- `item_id` (INTEGER REFERENCES items(id) ON DELETE CASCADE)
- `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
- `UNIQUE(user_id, item_id)`

---

## 五、核心业务逻辑

### 1. 三态流转（严禁修改）
```text
申请中 ──(卖家同意约定)──> 已约定 ──(双方确认完成)──> 已完成
  ↑
买家发起意向
```
- 卖家同意约定时：`application.status = '已约定'`，同时 `item.status = '已约定'`。
- 确认完成时：`application.status = '已完成'`，同时 `item.status = '已完成'`。

### 2. 留言与交流模式
- 本项目采用**公开商品留言板**，买家在商品详情页留言，所有留言公开可见，**不做实时私信**。

### 3. 图片规范
- 前端 Canvas 自动压缩至最长边 800px，JPEG 质量 0.7，输出 `data:image/jpeg;base64,...` 存入数据库。

---

## 六、本地运行指南

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 检查配置 .env
# DATABASE_URL=postgresql://postgres:password@localhost:5432/campus_secondhand
# PORT=5000（或 5001）
# SECRET_KEY=campus-secondhand-secret-2026

# 3. 运行建表与导入模拟数据
python init_db.py
python seed_data.py

# 4. 启动服务
python app.py
```

### 测试账号信息
| 账号 | 密码 | 角色 | 学校 |
|---|---|---|---|
| `demo` | `demo123` | 演示账号（商品卖家） | 灵山大学 |
| `buyer` | `demo123` | 测试买家（可用于测试私聊和申请） | 高丽大学 |

---

## 七、路由清单

| 请求方法 | 路由路径 | 功能说明 |
|---|---|---|
| `GET` | `/` | 首页（支持 `?keyword=` 与 `?category=`） |
| `GET/POST` | `/register` | 用户注册 |
| `GET/POST` | `/login` | 用户登录 |
| `GET` | `/logout` | 退出登录 |
| `GET` | `/item/<id>` | 商品详情页 |
| `GET/POST` | `/publish` | 发布二手商品 |
| `GET/POST` | `/item/<id>/edit` | 编辑商品信息 |
| `POST` | `/item/<id>/delete` | 删除商品 |
| `POST` | `/item/<id>/apply` | 提交意向申请 |
| `POST` | `/application/<id>/accept` | 卖家同意约定 |
| `POST` | `/application/<id>/complete` | 确认完成交易 |
| `POST` | `/item/<id>/favorite` | 收藏 / 取消收藏 |
| `POST` | `/item/<id>/message` | 发表公开留言 |
| `GET` | `/profile` | 个人中心（`?tab=published/applied/favorites`） |

---

## 八、接手 AI 须知与禁忌（CRITICAL）

1. ❌ **严禁引入前端重型框架**：不要引入 React、Vue、Angular、Bootstrap 或外部庞大 Tailwind CDN，保持原生高效。
2. ❌ **严禁修改三态流转逻辑**：必须保持 申请中 → 已约定 → 已完成。
3. ❌ **严禁增加线上支付**：平台定位纯同校线下当面交易。
4. ❌ **严禁修改既有文案**：除非用户明确要求修改文字，否则保持所有中文界面用语严谨一致。
5. ❌ **严禁改用 ORM**：使用原生 SQL 与 `psycopg2`，遵循极简透明原则。
