import os
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


class User(UserMixin):
    def __init__(self, user_dict):
        self.id = str(user_dict['id'])
        self.username = user_dict['username']
        self.nickname = user_dict['nickname']
        self.school = user_dict['school']


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
            login_user(User(user))
            next_page = request.args.get('next')
            flash('登录成功', 'success')
            return redirect(next_page or url_for('index'))
        flash('用户名或密码错误', 'error')
        return redirect(url_for('login'))
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
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
    execute_db('UPDATE applications SET status=%s WHERE id=%s', ('已约定', app_id))
    execute_db('UPDATE items SET status=%s WHERE id=%s', ('已约定', application['item_id']))
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
    execute_db('UPDATE applications SET status=%s WHERE id=%s', ('已完成', app_id))
    execute_db('UPDATE items SET status=%s WHERE id=%s', ('已完成', application['item_id']))
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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)


