import os
import uuid
import re
from datetime import datetime
from functools import wraps

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from flask import (Flask, flash, redirect, render_template, request,
                   session, url_for)
from flask_login import (LoginManager, UserMixin, current_user,
                         login_required, login_user, logout_user)
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录'

DATABASE_URL = os.environ.get('DATABASE_URL', '')


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    return conn


def query_db(query, args=(), one=False):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(query, args)
    rv = cur.fetchall()
    cur.close()
    conn.close()
    return (rv[0] if rv else None) if one else rv


def execute_db(query, args=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, args)
    conn.commit()
    cur.close()
    conn.close()


def execute_transaction(operations):
    """Executes multiple queries in a single atomic ACID transaction with rollback on failure."""
    conn = get_db()
    cur = conn.cursor()
    try:
        for query, args in operations:
            cur.execute(query, args)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


class User(UserMixin):
    def __init__(self, user_dict):
        self.id = str(user_dict['id'])
        self.username = user_dict['username']
        self.nickname = user_dict['nickname']
        self.school = user_dict['school']
        self.session_token = user_dict.get('session_token')



@app.before_request
def check_single_session():
    # 静态资源、健康检查接口跳过校验
    if request.endpoint in ('static', 'healthz') or request.path.startswith('/static'):
        return None

    if current_user.is_authenticated:
        client_token = session.get('session_token')
        user_db = query_db('SELECT session_token FROM users WHERE id = %s', (current_user.id,), one=True)
        if not user_db or not user_db.get('session_token') or user_db['session_token'] != client_token:
            # 顶号踢出逻辑
            logout_user()
            session.clear()
            if request.endpoint not in ('login', 'register'):
                flash('该账号已在其他设备或窗口登录，当前会话已下线。', 'warning')
                return redirect(url_for('login'))


@login_manager.user_loader
def load_user(user_id):
    user = query_db('SELECT * FROM users WHERE id = %s', (user_id,), one=True)
    return User(user) if user else None


def time_ago(dt):
    if not dt:
        return ''
    now = datetime.now()
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace('Z', '+00:00')).replace(tzinfo=None)
    diff = now - dt
    if diff.days > 30:
        return f'{diff.days // 30} 个月前'
    if diff.days > 0:
        return f'{diff.days} 天前'
    if diff.seconds > 3600:
        return f'{diff.seconds // 3600} 小时前'
    if diff.seconds > 60:
        return f'{diff.seconds // 60} 分钟前'
    return '刚刚'


app.jinja_env.filters['time_ago'] = time_ago


@app.route('/')
def index():
    keyword = request.args.get('keyword', '').strip()
    category = request.args.get('category', '').strip()
    query = "SELECT i.*, u.nickname as seller_nickname, u.school as seller_school FROM items i JOIN users u ON i.seller_id = u.id WHERE i.status = '在售'"
    args = []
    if keyword:
        query += " AND i.title ILIKE %s"
        args.append(f'%{keyword}%')
    if category:
        query += " AND i.category = %s"
        args.append(category)
    query += " ORDER BY i.created_at DESC"
    items = query_db(query, tuple(args))
    categories = ['教材书籍', '电子家电', '生活用品', '家具家居', '服饰鞋包', '其他']
    return render_template('index.html', items=items, categories=categories,
                           keyword=keyword, category=category)


@app.route('/healthz')
def healthz():
    """健康检查端点：供 Render / 监控探针使用，顺带验证数据库连通性。"""
    try:
        query_db('SELECT 1', one=True)
        db_ok = True
    except Exception:
        db_ok = False
    return {'status': 'ok' if db_ok else 'degraded', 'database': db_ok}, (200 if db_ok else 503)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        nickname = request.form.get('nickname', '').strip()
        if not all([username, password, nickname]):
            flash('请填写所有必填项', 'error')
            return redirect(url_for('register'))
        if len(username) < 3 or len(username) > 20:
            flash('用户名需 3-20 个字符', 'error')
            return redirect(url_for('register'))
        if len(password) < 6:
            flash('密码至少 6 位', 'error')
            return redirect(url_for('register'))
        existing = query_db('SELECT id FROM users WHERE username = %s', (username,), one=True)
        if existing:
            flash('用户名已被注册', 'error')
            return redirect(url_for('register'))
        pw_hash = generate_password_hash(password)
        execute_db('INSERT INTO users (username, password_hash, nickname, school) VALUES (%s, %s, %s, %s)',
                   (username, pw_hash, nickname, '其他'))
        flash('注册成功，请登录', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = query_db('SELECT * FROM users WHERE username = %s', (username,), one=True)
        if user and check_password_hash(user['password_hash'], password):
            # 单设备登录（顶号机制）：每次登录生成新的 session_token 写入数据库
            token = str(uuid.uuid4())
            execute_db('UPDATE users SET session_token = %s WHERE id = %s', (token, user['id']))
            user['session_token'] = token
            session['session_token'] = token
            login_user(User(user))
            next_page = request.args.get('next')
            flash('登录成功', 'success')
            return redirect(next_page or url_for('index'))
        flash('用户名或密码错误', 'error')
        return redirect(url_for('login'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    if current_user.is_authenticated:
        try:
            execute_db('UPDATE users SET session_token = NULL WHERE id = %s', (current_user.id,))
        except Exception:
            pass
        logout_user()
    session.clear()
    flash('已退出登录', 'success')
    return redirect(url_for('index'))


@app.route('/publish', methods=['GET', 'POST'])
@login_required
def publish():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category', '').strip()
        price = request.form.get('price', '').strip()
        condition = request.form.get('condition', '').strip()
        description = request.form.get('description', '').strip()
        image_base64 = request.form.get('image_base64', '').strip()
        if not all([title, category, price, condition, image_base64]):
            flash('请填写标题、分类、价格、成色并上传图片', 'error')
            return redirect(url_for('publish'))
        try:
            price_int = int(price)
            if price_int < 0:
                raise ValueError
        except ValueError:
            flash('价格必须为非负整数', 'error')
            return redirect(url_for('publish'))
        execute_db(
            'INSERT INTO items (seller_id, title, category, price, condition, description, image_base64) VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (current_user.id, title, category, price_int, condition, description, image_base64))
        flash('发布成功', 'success')
        return redirect(url_for('index'))
    categories = ['教材书籍', '电子家电', '生活用品', '家具家居', '服饰鞋包', '其他']
    conditions = ['全新', '九成新', '八成新', '七成新及以下']
    return render_template('publish.html', categories=categories, conditions=conditions)


@app.route('/item/<int:item_id>')
def detail(item_id):
    item = query_db(
        'SELECT i.*, u.nickname as seller_nickname, u.school as seller_school FROM items i JOIN users u ON i.seller_id = u.id WHERE i.id = %s',
        (item_id,), one=True)
    if not item:
        flash('商品不存在', 'error')
        return redirect(url_for('index'))
    messages = query_db(
        'SELECT m.*, u.nickname, u.school FROM messages m JOIN users u ON m.user_id = u.id WHERE m.item_id = %s ORDER BY m.created_at ASC',
        (item_id,))
    is_favorited = False
    if current_user.is_authenticated:
        fav = query_db('SELECT id FROM favorites WHERE user_id = %s AND item_id = %s',
                       (current_user.id, item_id), one=True)
        is_favorited = fav is not None
    return render_template('detail.html', item=item, messages=messages, is_favorited=is_favorited)


@app.route('/item/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_item(item_id):
    item = query_db('SELECT * FROM items WHERE id = %s', (item_id,), one=True)
    if not item:
        flash('商品不存在', 'error')
        return redirect(url_for('index'))
    if str(item['seller_id']) != str(current_user.id):
        flash('无权编辑他人商品', 'error')
        return redirect(url_for('detail', item_id=item_id))
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category', '').strip()
        price = request.form.get('price', '').strip()
        condition = request.form.get('condition', '').strip()
        description = request.form.get('description', '').strip()
        image_base64 = request.form.get('image_base64', '').strip()
        if not all([title, category, price, condition]):
            flash('请填写标题、分类、价格、成色', 'error')
            return redirect(url_for('edit_item', item_id=item_id))
        try:
            price_int = int(price)
        except ValueError:
            flash('价格必须为整数', 'error')
            return redirect(url_for('edit_item', item_id=item_id))
        if image_base64:
            execute_db(
                'UPDATE items SET title=%s, category=%s, price=%s, condition=%s, description=%s, image_base64=%s WHERE id=%s',
                (title, category, price_int, condition, description, image_base64, item_id))
        else:
            execute_db(
                'UPDATE items SET title=%s, category=%s, price=%s, condition=%s, description=%s WHERE id=%s',
                (title, category, price_int, condition, description, item_id))
        flash('修改成功', 'success')
        return redirect(url_for('detail', item_id=item_id))
    categories = ['教材书籍', '电子家电', '生活用品', '家具家居', '服饰鞋包', '其他']
    conditions = ['全新', '九成新', '八成新', '七成新及以下']
    return render_template('edit_item.html', item=item, categories=categories, conditions=conditions)


@app.route('/item/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_item(item_id):
    item = query_db('SELECT * FROM items WHERE id = %s', (item_id,), one=True)
    if not item or str(item['seller_id']) != str(current_user.id):
        flash('无权删除', 'error')
        return redirect(url_for('index'))
    execute_db('DELETE FROM favorites WHERE item_id = %s', (item_id,))
    execute_db('DELETE FROM messages WHERE item_id = %s', (item_id,))
    execute_db('DELETE FROM applications WHERE item_id = %s', (item_id,))
    execute_db('DELETE FROM items WHERE id = %s', (item_id,))
    flash('商品已删除', 'success')
    return redirect(url_for('profile'))


@app.route('/item/<int:item_id>/apply', methods=['POST'])
@login_required
def apply_item(item_id):
    item = query_db('SELECT * FROM items WHERE id = %s', (item_id,), one=True)
    if not item:
        flash('商品不存在', 'error')
        return redirect(url_for('index'))
    if str(item['seller_id']) == str(current_user.id):
        flash('不能对自己的商品申请', 'error')
        return redirect(url_for('detail', item_id=item_id))
    if item['status'] != '在售':
        flash('该商品已不可申请', 'error')
        return redirect(url_for('detail', item_id=item_id))
    message = request.form.get('message', '').strip()
    existing = query_db(
        'SELECT id FROM applications WHERE item_id=%s AND buyer_id=%s AND status=%s',
        (item_id, current_user.id, '申请中'), one=True)
    if existing:
        flash('您已提交过申请，请等待卖家确认', 'error')
        return redirect(url_for('detail', item_id=item_id))
    execute_db(
        'INSERT INTO applications (item_id, buyer_id, seller_id, status, message) VALUES (%s, %s, %s, %s, %s)',
        (item_id, current_user.id, item['seller_id'], '申请中', message))
    flash('申请已提交，等待卖家确认', 'success')
    return redirect(url_for('profile', tab='applied'))


@app.route('/item/<int:item_id>/favorite', methods=['POST'])
@login_required
def favorite_item(item_id):
    item = query_db('SELECT id FROM items WHERE id = %s', (item_id,), one=True)
    if not item:
        flash('商品不存在', 'error')
        return redirect(url_for('index'))
    existing = query_db('SELECT id FROM favorites WHERE user_id=%s AND item_id=%s',
                         (current_user.id, item_id), one=True)
    if existing:
        execute_db('DELETE FROM favorites WHERE user_id=%s AND item_id=%s',
                   (current_user.id, item_id))
        flash('已取消收藏', 'success')
    else:
        execute_db('INSERT INTO favorites (user_id, item_id) VALUES (%s, %s)',
                   (current_user.id, item_id))
        flash('已收藏', 'success')
    return redirect(url_for('detail', item_id=item_id))


@app.route('/item/<int:item_id>/message', methods=['POST'])
@login_required
def add_message(item_id):
    item = query_db('SELECT id FROM items WHERE id = %s', (item_id,), one=True)
    if not item:
        flash('商品不存在', 'error')
        return redirect(url_for('index'))
    content = request.form.get('content', '').strip()
    if not content:
        flash('留言内容不能为空', 'error')
        return redirect(url_for('detail', item_id=item_id))
    execute_db('INSERT INTO messages (item_id, user_id, content) VALUES (%s, %s, %s)',
               (item_id, current_user.id, content))
    return redirect(url_for('detail', item_id=item_id))


@app.route('/application/<int:app_id>/accept', methods=['POST'])
@login_required
def accept_application(app_id):
    application = query_db('SELECT * FROM applications WHERE id = %s', (app_id,), one=True)
    if not application or str(application['seller_id']) != str(current_user.id):
        flash('无权操作', 'error')
        return redirect(url_for('profile'))
    if application['status'] != '申请中':
        flash('该申请状态不可操作', 'error')
        return redirect(url_for('profile'))
    # Atomic transaction for application status and item visibility
    execute_transaction([
        ('UPDATE applications SET status=%s WHERE id=%s', ('已约定', app_id)),
        ('UPDATE items SET status=%s WHERE id=%s', ('已约定', application['item_id']))
    ])
    flash('已同意约定', 'success')
    return redirect(url_for('profile'))


@app.route('/application/<int:app_id>/complete', methods=['POST'])
@login_required
def complete_application(app_id):
    application = query_db('SELECT * FROM applications WHERE id = %s', (app_id,), one=True)
    if not application:
        flash('申请不存在', 'error')
        return redirect(url_for('profile'))
    if str(application['buyer_id']) != str(current_user.id) and str(application['seller_id']) != str(current_user.id):
        flash('无权操作', 'error')
        return redirect(url_for('profile'))
    if application['status'] != '已约定':
        flash('该申请状态不可操作', 'error')
        return redirect(url_for('profile'))
    # Atomic transaction for transaction completion
    execute_transaction([
        ('UPDATE applications SET status=%s WHERE id=%s', ('已完成', app_id)),
        ('UPDATE items SET status=%s WHERE id=%s', ('已完成', application['item_id']))
    ])
    flash('交易已完成', 'success')
    return redirect(url_for('profile'))


@app.route('/profile')
@login_required
def profile():
    tab = request.args.get('tab', 'published')
    if tab == 'published':
        items = query_db(
            'SELECT i.*, (SELECT COUNT(*) FROM applications a WHERE a.item_id=i.id AND a.status=%s) as pending_count FROM items i WHERE i.seller_id=%s ORDER BY i.created_at DESC',
            ('申请中', current_user.id))
        applications_by_item = {}
        for item in items:
            apps = query_db(
                'SELECT a.*, u.nickname as buyer_nickname, u.school as buyer_school FROM applications a JOIN users u ON a.buyer_id=u.id WHERE a.item_id=%s ORDER BY a.created_at DESC',
                (item['id'],))
            applications_by_item[item['id']] = apps
        return render_template('profile.html', tab=tab, items=items,
                               applications_by_item=applications_by_item)
    elif tab == 'applied':
        applications = query_db(
            'SELECT a.*, i.title as item_title, i.price as item_price, i.image_base64 as item_image, u.nickname as seller_nickname FROM applications a JOIN items i ON a.item_id=i.id JOIN users u ON a.seller_id=u.id WHERE a.buyer_id=%s ORDER BY a.created_at DESC',
            (current_user.id,))
        return render_template('profile.html', tab=tab, applications=applications)
    elif tab == 'favorites':
        favorites = query_db(
            'SELECT f.*, i.title, i.price, i.image_base64, i.status, u.nickname as seller_nickname FROM favorites f JOIN items i ON f.item_id=i.id JOIN users u ON i.seller_id=u.id WHERE f.user_id=%s ORDER BY f.created_at DESC',
            (current_user.id,))
        return render_template('profile.html', tab=tab, favorites=favorites)
    return redirect(url_for('profile'))




@app.context_processor
def inject_unread_chat_count():
    if current_user.is_authenticated:
        try:
            res = query_db('SELECT COUNT(*) as cnt FROM chat_messages WHERE receiver_id = %s AND is_read = FALSE', (current_user.id,), one=True)
            return {'unread_chat_count': res['cnt'] if res else 0}
        except Exception:
            return {'unread_chat_count': 0}
    return {'unread_chat_count': 0}


@app.route('/chat')
@login_required
def chat_view():
    target_user_id = request.args.get('user_id')
    item_id = request.args.get('item_id')

    conv_sql = """
        WITH latest_msgs AS (
            SELECT 
                CASE WHEN sender_id = %s THEN receiver_id ELSE sender_id END AS other_user_id,
                content,
                created_at,
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY CASE WHEN sender_id = %s THEN receiver_id ELSE sender_id END 
                    ORDER BY created_at DESC, id DESC
                ) as rn
            FROM chat_messages
            WHERE sender_id = %s OR receiver_id = %s
        ),
        unread_counts AS (
            SELECT sender_id AS other_user_id, COUNT(*) AS unread_cnt
            FROM chat_messages
            WHERE receiver_id = %s AND is_read = FALSE
            GROUP BY sender_id
        )
        SELECT 
            u.id AS user_id,
            u.nickname,
            u.school,
            lm.content AS last_message,
            lm.created_at AS last_time,
            COALESCE(uc.unread_cnt, 0) AS unread_count
        FROM latest_msgs lm
        JOIN users u ON lm.other_user_id = u.id
        LEFT JOIN unread_counts uc ON u.id = uc.other_user_id
        WHERE lm.rn = 1
        ORDER BY lm.created_at DESC;
    """
    conversations = query_db(conv_sql, (current_user.id, current_user.id, current_user.id, current_user.id, current_user.id)) or []

    selected_user = None
    if target_user_id:
        if str(target_user_id) == str(current_user.id):
            flash('不能与自己发起私聊', 'warning')
            return redirect(url_for('chat_view'))
        selected_user = query_db('SELECT id, nickname, school FROM users WHERE id = %s', (target_user_id,), one=True)
        if selected_user and not any(str(c['user_id']) == str(target_user_id) for c in conversations):
            conversations.insert(0, {
                'user_id': selected_user['id'],
                'nickname': selected_user['nickname'],
                'school': selected_user['school'],
                'last_message': '开启新的私聊...',
                'last_time': None,
                'unread_count': 0
            })
    elif conversations:
        selected_user = query_db('SELECT id, nickname, school FROM users WHERE id = %s', (conversations[0]['user_id'],), one=True)

    current_item = None
    if item_id:
        current_item = query_db('SELECT id, title, price, status, image_base64 FROM items WHERE id = %s', (item_id,), one=True)

    chat_history = []
    if selected_user:
        execute_db('UPDATE chat_messages SET is_read = TRUE WHERE sender_id = %s AND receiver_id = %s AND is_read = FALSE', (selected_user['id'], current_user.id))
        history_sql = """
            SELECT cm.*, u.nickname as sender_nickname
            FROM chat_messages cm
            JOIN users u ON cm.sender_id = u.id
            WHERE (cm.sender_id = %s AND cm.receiver_id = %s)
               OR (cm.sender_id = %s AND cm.receiver_id = %s)
            ORDER BY cm.created_at ASC, cm.id ASC
        """
        chat_history = query_db(history_sql, (current_user.id, selected_user['id'], selected_user['id'], current_user.id)) or []
        
        if not current_item and chat_history:
            for msg in reversed(chat_history):
                if msg.get('item_id'):
                    current_item = query_db('SELECT id, title, price, status, image_base64 FROM items WHERE id = %s', (msg['item_id'],), one=True)
                    if current_item:
                        break

    return render_template('chat.html',
                           conversations=conversations,
                           selected_user=selected_user,
                           chat_history=chat_history,
                           current_item=current_item)


@app.route('/api/chat/send', methods=['POST'])
@login_required
def api_send_chat():
    receiver_id = request.form.get('receiver_id')
    item_id = request.form.get('item_id') or None
    content = request.form.get('content', '').strip()

    if not receiver_id or not content:
        return {'status': 'error', 'message': '接收者或消息内容不能为空'}, 400
    if str(receiver_id) == str(current_user.id):
        return {'status': 'error', 'message': '不能给自己发消息'}, 400
    if len(content) > 1000:
        return {'status': 'error', 'message': '消息长度不能超过1000字'}, 400

    execute_db(
        'INSERT INTO chat_messages (sender_id, receiver_id, item_id, content) VALUES (%s, %s, %s, %s)',
        (current_user.id, receiver_id, item_id, content)
    )
    msg = query_db(
        'SELECT id, sender_id, receiver_id, content, created_at FROM chat_messages WHERE sender_id = %s ORDER BY id DESC LIMIT 1',
        (current_user.id,), one=True
    )
    return {
        'status': 'success',
        'message': {
            'id': msg['id'],
            'sender_id': msg['sender_id'],
            'content': msg['content'],
            'time': msg['created_at'].strftime('%H:%M') if msg['created_at'] else ''
        }
    }


@app.route('/api/chat/messages')
@login_required
def api_get_messages():
    other_id = request.args.get('other_id')
    after_id = int(request.args.get('after_id', 0))
    if not other_id:
        return {'status': 'error', 'messages': []}, 400

    sql = """
        SELECT cm.id, cm.sender_id, cm.receiver_id, cm.content, cm.created_at, u.nickname as sender_nickname
        FROM chat_messages cm
        JOIN users u ON cm.sender_id = u.id
        WHERE ((cm.sender_id = %s AND cm.receiver_id = %s)
            OR (cm.sender_id = %s AND cm.receiver_id = %s))
          AND cm.id > %s
        ORDER BY cm.created_at ASC, cm.id ASC
    """
    new_msgs = query_db(sql, (current_user.id, other_id, other_id, current_user.id, after_id)) or []
    if new_msgs:
        execute_db('UPDATE chat_messages SET is_read = TRUE WHERE sender_id = %s AND receiver_id = %s AND is_read = FALSE', (other_id, current_user.id))

    res = []
    for m in new_msgs:
        res.append({
            'id': m['id'],
            'sender_id': m['sender_id'],
            'is_me': str(m['sender_id']) == str(current_user.id),
            'content': m['content'],
            'nickname': m['sender_nickname'],
            'time': m['created_at'].strftime('%H:%M') if m['created_at'] else ''
        })
    return {'status': 'success', 'messages': res}


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)


