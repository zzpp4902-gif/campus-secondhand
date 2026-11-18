import base64
import json
import os
import re
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

import psycopg2
import qrcode
from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from qrcode.image.svg import SvgPathFillImage


ORDER_ID = re.compile(r'[a-f0-9]{32}')
SUPPORTED_RESULTS = {'DONE', 'WAITING_FOR_DEPOSIT', 'CANCELED', 'ABORTED', 'EXPIRED'}
MINIMUM_TEST_AMOUNT = 200
QR_TTL_SECONDS = 600


class TossRequestError(Exception):
    def __init__(self, code, uncertain=False):
        self.code = code
        self.uncertain = uncertain


def configure_toss_demo(app):
    client_key = os.getenv('TOSS_CLIENT_KEY', '').strip()
    secret_key = os.getenv('TOSS_SECRET_KEY', '').strip()
    origin = (os.getenv('TOSS_DEMO_ORIGIN') or os.getenv('RENDER_EXTERNAL_URL') or '').rstrip('/')
    try:
        parsed_origin = urlsplit(origin)
        host = parsed_origin.hostname
        parsed_origin.port
    except ValueError:
        parsed_origin = urlsplit('')
        host = None
    item_id = os.getenv('TOSS_DEMO_ITEM_ID', '').strip()
    item_id_valid = not item_id or bool(re.fullmatch(r'[1-9][0-9]{0,9}', item_id))
    is_local = parsed_origin.scheme == 'http' and host in {'localhost', '127.0.0.1'}
    origin_ok = (
        host and (parsed_origin.scheme == 'https' or is_local)
        and not (parsed_origin.username or parsed_origin.path or parsed_origin.query or parsed_origin.fragment)
    )
    app.config['TOSS_DEMO_ENABLED'] = bool(
        os.getenv('TOSS_DEMO_ENABLED') == '1'
        and re.fullmatch(r'test_gck_[A-Za-z0-9_-]+', client_key)
        and re.fullmatch(r'test_gsk_[A-Za-z0-9_-]+', secret_key)
        and origin_ok and item_id_valid
    )
    app.config['TOSS_DEMO_CLIENT_KEY'] = client_key
    app.config['TOSS_DEMO_SECRET_KEY'] = secret_key
    app.config['TOSS_DEMO_ORIGIN'] = origin
    app.config['TOSS_DEMO_ITEM_ID'] = int(item_id) if item_id and item_id_valid else None


def is_demo_item(item):
    configured_item = current_app.config['TOSS_DEMO_ITEM_ID']
    return (
        current_app.config['TOSS_DEMO_ENABLED']
        and (configured_item is None or item['id'] == configured_item)
        and item['status'] == '在售' and item['price'] >= MINIMUM_TEST_AMOUNT
    )


def toss_request(path, payload=None, *, idempotency_key=None):
    secret_key = current_app.config['TOSS_DEMO_SECRET_KEY']
    if not current_app.config['TOSS_DEMO_ENABLED'] or not secret_key.startswith('test_gsk_'):
        raise TossRequestError('TEST_ENVIRONMENT_DISABLED')
    basic = base64.b64encode((secret_key + ':').encode('ascii')).decode('ascii')
    headers = {'Authorization': 'Basic ' + basic, 'Accept': 'application/json'}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if idempotency_key:
        headers['Idempotency-Key'] = idempotency_key
    api_request = Request('https://api.tosspayments.com/v1/payments' + path, data=data, headers=headers)
    try:
        with urlopen(api_request, timeout=8) as response:
            result = json.load(response)
    except HTTPError as exc:
        try:
            with exc:
                body = json.load(exc)
            code = body.get('code', 'TOSS_REQUEST_FAILED') if isinstance(body, dict) else 'TOSS_REQUEST_FAILED'
        except (ValueError, OSError):
            code = 'TOSS_REQUEST_FAILED'
        raise TossRequestError(code, uncertain=(
            exc.code >= 500 or exc.code in (408, 409, 429)
            or code in {'ALREADY_PROCESSED_PAYMENT', 'PROVIDER_ERROR', 'DUPLICATED_ORDER_ID'}
        )) from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise TossRequestError('TOSS_RESPONSE_UNAVAILABLE', uncertain=True) from exc
    if not isinstance(result, dict):
        raise TossRequestError('INVALID_TOSS_RESPONSE', uncertain=True)
    return result


def csrf_token():
    if 'toss_demo_csrf' not in session:
        session['toss_demo_csrf'] = secrets.token_urlsafe(32)
    return session['toss_demo_csrf']


def qr_serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='campus-demo-payment-qr-v1')


def register_toss_demo(app, query_db, execute_db):
    configure_toss_demo(app)
    routes = Blueprint('toss_demo', __name__)
    app.add_template_global(csrf_token, 'toss_demo_csrf')

    @routes.before_request
    def require_test_config():
        if not current_app.config['TOSS_DEMO_ENABLED']:
            abort(404)

    @routes.after_request
    def private_checkout(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    def require_csrf():
        token = request.form.get('csrf_token', '')
        if not token.isascii() or not secrets.compare_digest(token, csrf_token()):
            abort(400)

    def get_order(order_id):
        if not ORDER_ID.fullmatch(order_id or ''):
            abort(404)
        order = query_db(
            'SELECT * FROM demo_payment_orders WHERE order_id = %s AND buyer_id = %s',
            (order_id, current_user.id), one=True)
        if not order:
            abort(404)
        return order

    def result_redirect(order_id):
        return redirect(url_for('.result', order_id=order_id), code=303)

    def complete_sale(order_id, payment_key, expected_states, source):
        # Lock the order and move the item out of the marketplace in one statement.
        execute_db(
            """
            WITH eligible_order AS (
                SELECT order_id, item_id, amount FROM demo_payment_orders
                WHERE order_id = %s AND status = ANY(%s) AND payment_key IS NOT DISTINCT FROM %s
                FOR UPDATE
            ),
            sold_item AS (
                UPDATE items AS i SET status = '已售' FROM eligible_order AS o
                WHERE i.id = o.item_id AND i.status = '在售' AND i.price = o.amount
                RETURNING i.id
            ),
            closed_applications AS (
                UPDATE applications SET status = '已取消'
                WHERE item_id IN (SELECT id FROM sold_item) AND status = '申请中'
            )
            UPDATE demo_payment_orders AS o
            SET status = CASE WHEN EXISTS (SELECT 1 FROM sold_item) THEN 'DONE' ELSE 'FAILED' END,
                confirmation_source = CASE WHEN EXISTS (SELECT 1 FROM sold_item) THEN %s END,
                updated_at = CURRENT_TIMESTAMP
            FROM eligible_order
            WHERE o.order_id = eligible_order.order_id
            """,
            (order_id, expected_states, payment_key, source))

    def record_provider_result(order, data):
        if (data.get('orderId') != order['order_id'] or data.get('paymentKey') != order['payment_key']
                or data.get('totalAmount') != order['amount'] or data.get('currency') != 'KRW'):
            current_app.logger.warning('Toss demo response did not match order %s', order['order_id'])
            return
        state = data.get('status')
        if state not in SUPPORTED_RESULTS:
            return
        if state == 'DONE':
            complete_sale(order['order_id'], order['payment_key'],
                          ['CHECKING', 'WAITING_FOR_DEPOSIT'], 'TOSS_TEST')
            return
        if state in {'ABORTED', 'EXPIRED'}:
            state = 'FAILED'
        execute_db(
            """
            UPDATE demo_payment_orders SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE order_id = %s AND payment_key = %s AND status IN ('CHECKING', 'WAITING_FOR_DEPOSIT')
            """,
            (state, order['order_id'], order['payment_key']))

    @routes.post('/item/<int:item_id>/demo-payment')
    @login_required
    def create(item_id):
        require_csrf()
        item = query_db(
            'SELECT id, title, price, status FROM items WHERE id = %s',
            (item_id,), one=True)
        if not item or not is_demo_item(item):
            abort(404)
        order = execute_db(
            """
            INSERT INTO demo_payment_orders (order_id, buyer_id, item_id, order_name, amount)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (buyer_id, item_id) WHERE status = 'READY'
            DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            RETURNING order_id
            """,
            (uuid4().hex, current_user.id, item_id, item['title'], item['price']), returning=True)
        endpoint = '.qr' if request.form.get('method') == 'qr' else '.checkout'
        return redirect(url_for(endpoint, order_id=order['order_id']), code=303)

    @routes.get('/demo-payment/qr/<order_id>')
    @login_required
    def qr(order_id):
        order = get_order(order_id)
        if order['status'] != 'READY':
            return result_redirect(order_id)
        token = qr_serializer().dumps(order_id)
        scan_path = url_for('.qr_confirm', token=token)
        scan_url = current_app.config['TOSS_DEMO_ORIGIN'] + scan_path
        qr_svg = qrcode.make(scan_url, image_factory=SvgPathFillImage).to_string()
        return render_template(
            'demo_payment_qr.html', order=order, scan_path=scan_path,
            qr_image=base64.b64encode(qr_svg).decode('ascii'), ttl=QR_TTL_SECONDS)

    @routes.get('/demo-payment/qr-status/<order_id>')
    @login_required
    def qr_status(order_id):
        return {'status': get_order(order_id)['status']}

    @routes.route('/demo-payment/scan/<token>', methods=['GET', 'POST'])
    def qr_confirm(token):
        try:
            order_id = qr_serializer().loads(token, max_age=QR_TTL_SECONDS)
        except SignatureExpired:
            abort(410)
        except BadSignature:
            abort(404)
        if not isinstance(order_id, str) or not ORDER_ID.fullmatch(order_id):
            abort(404)
        if request.method == 'POST':
            require_csrf()
            complete_sale(order_id, None, ['READY'], 'DEMO_QR')
            return redirect(url_for('.qr_confirm', token=token), code=303)
        order = query_db(
            """
            SELECT order_id, item_id, order_name, amount, status, confirmation_source
            FROM demo_payment_orders WHERE order_id = %s
            """,
            (order_id,), one=True)
        if not order:
            abort(404)
        return render_template('demo_payment_qr.html', order=order, token=token)

    @routes.get('/demo-payment/checkout/<order_id>')
    @login_required
    def checkout(order_id):
        order = get_order(order_id)
        if order['status'] != 'READY':
            return result_redirect(order_id)
        if 'toss_demo_customer' not in session:
            session['toss_demo_customer'] = uuid4().hex
        origin = current_app.config['TOSS_DEMO_ORIGIN']
        config = {
            'clientKey': current_app.config['TOSS_DEMO_CLIENT_KEY'],
            'customerKey': session['toss_demo_customer'],
            'amount': order['amount'],
            'orderId': order_id,
            'orderName': '캠퍼스 중고거래 결제 실습',
            'successUrl': origin + url_for('.success'),
            'failUrl': origin + url_for('.failure') + '?' + urlencode({'ref': order_id}),
        }
        return render_template('demo_payment_checkout.html', order=order, payment_config=config)

    @routes.get('/demo-payment/success')
    @login_required
    def success():
        order = get_order(request.args.get('orderId'))
        if order['status'] not in {'READY', 'CHECKING'}:
            return result_redirect(order['order_id'])
        key = request.args.get('paymentKey', '')
        amount = request.args.get('amount', '')
        if not (key and key.isascii() and key.isprintable() and len(key) <= 200
                and amount == str(order['amount'])
                and (not order['payment_key'] or order['payment_key'] == key)):
            return render_template('demo_payment_result.html', order=order, invalid=True), 400
        return render_template('demo_payment_result.html', order=order,
                               confirm_key=key)

    @routes.post('/demo-payment/confirm/<order_id>')
    @login_required
    def confirm(order_id):
        require_csrf()
        order = get_order(order_id)
        if order['status'] not in {'READY', 'CHECKING', 'WAITING_FOR_DEPOSIT'}:
            return result_redirect(order_id)
        supplied_key = request.form.get('payment_key', '')
        key = order['payment_key'] or supplied_key
        if not key or not key.isascii() or not key.isprintable() or len(key) > 200:
            abort(400)
        if supplied_key and (supplied_key != key or request.form.get('amount') != str(order['amount'])):
            abort(400)

        lookup_only = order['status'] == 'WAITING_FOR_DEPOSIT'
        if not lookup_only:
            try:
                order = execute_db(
                    """
                    UPDATE demo_payment_orders SET status = 'CHECKING', payment_key = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE order_id = %s AND buyer_id = %s AND status IN ('READY', 'CHECKING')
                      AND (payment_key IS NULL OR payment_key = %s)
                    RETURNING *
                    """,
                    (key, order_id, current_user.id, key), returning=True)
            except psycopg2.errors.UniqueViolation:
                abort(400)
            if not order:
                return result_redirect(order_id)
        try:
            if lookup_only:
                data = toss_request('/' + quote(key, safe=''))
            else:
                data = toss_request('/confirm', {
                    'paymentKey': key, 'orderId': order_id, 'amount': order['amount'],
                }, idempotency_key=order_id)
            record_provider_result(order, data)
        except TossRequestError as exc:
            if exc.uncertain and not lookup_only:
                try:
                    record_provider_result(order, toss_request('/' + quote(key, safe='')))
                except TossRequestError:
                    pass
            elif not lookup_only:
                execute_db(
                    """
                    UPDATE demo_payment_orders SET status = 'FAILED', updated_at = CURRENT_TIMESTAMP
                    WHERE order_id = %s AND status = 'CHECKING'
                    """,
                    (order_id,))
        return result_redirect(order_id)

    @routes.get('/demo-payment/fail')
    @login_required
    def failure():
        order = get_order(request.args.get('orderId') or request.args.get('ref'))
        state = 'CANCELED' if request.args.get('code') in {'PAY_PROCESS_CANCELED', 'USER_CANCEL'} else 'FAILED'
        execute_db(
            """
            UPDATE demo_payment_orders SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE order_id = %s AND buyer_id = %s AND status = 'READY'
            """,
            (state, order['order_id'], current_user.id))
        return result_redirect(order['order_id'])

    @routes.get('/demo-payment/result/<order_id>')
    @login_required
    def result(order_id):
        return render_template('demo_payment_result.html', order=get_order(order_id))

    app.register_blueprint(routes)
