import os
import psycopg2
import urllib.request
import io
import base64
from PIL import Image
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

DATABASE_URL = os.environ.get('DATABASE_URL', '')

PLACEHOLDER_IMAGE = ('data:image/jpeg;base64,'
    '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a'
    'HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy'
    'MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QA'
    'FAABAAAAAAAAAAAAAAAAAAAACf/EABQBAQAAAAAAAAAAAAAAAAAAAAD/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8A/9k=')

SAMPLE_PHOTO_IDS = [
    'photo-1544716278-ca5e3f4abd8c', # 1. 高等数学教材
    'photo-1515879218367-8466d910aaa4', # 2. Python编程
    'photo-1456513080510-7bf3a84b82f8', # 3. 线性代数
    'photo-1457369804613-52c61a468e7d', # 4. 大学英语四级
    'photo-1526374965328-7f61d4dc18c5', # 5. 数据结构与算法
    'photo-1585771724684-38269d6639fd', # 6. 小米空气净化器
    'photo-1615663245857-ac93bb7c39e7', # 7. 罗技无线鼠标
    'photo-1527443224154-c4a3942d3acf', # 8. 三星27寸显示器
    'photo-1575311373937-040b8e1fd5b6', # 9. 小米手环7
    'photo-1506880018603-83d5b814b5a6', # 10. Kindle Paperwhite
    'photo-1544233726-9f1d2b27be8b', # 11. 电饭煲（3L）
    'photo-1594212699903-ec8a3eca50f5', # 12. 电热水壶
    'photo-1507473885765-e6ed057f782c', # 13. 台灯（护眼LED）
    'photo-1522337360788-8b13dee7a37e', # 14. 吹风机
    'photo-1576678927484-cc907957088c', # 15. 体重秤
    'photo-1590736969955-71cc94801759', # 16. 收纳箱（大号3个）
    'photo-1584132967334-10e028bd69f7', # 17. 单人床垫
    'photo-1518455027359-f3f8164ba6bd', # 18. 书桌（简易组装）
    'photo-1592078615290-033ee584e267', # 19. 椅子（人体工学）
    'photo-1594980596870-8aa52a78d8cd', # 20. 书架（五层）
    'photo-1571175443880-49e1d25b2bc5', # 21. 小冰箱（50L）
    'photo-1542291026-7eec264c27ff', # 22. Nike运动鞋（260mm）
    'photo-1548883354-7622d03aca27', # 23. 羽绒服（男L）
    'photo-1553062407-98eeb64c6a62', # 24. 背包（电脑包）
    'photo-1608256246200-53e635b5b65f', # 25. 围巾（羊毛）
    'photo-1588850561407-ed78c282e89b', # 26. 棒球帽
    'photo-1601925260368-ae2f83cf8b7f', # 27. 瑜伽垫
    'photo-1626224583764-f87db24ac4ea', # 28. 羽毛球拍（两支）
    'photo-1510915361894-db8b60106cb1', # 29. 吉他（民谣）
    'photo-1485965120184-e220f721d03e', # 30. 自行车（通勤）
]

SAMPLE_IMAGES_DIR = os.path.join(os.path.dirname(__file__), 'sample_images')

def load_product_image_base64(item_index):
    """优先从本地 sample_images 目录加载真实商品实拍照片"""
    local_path = os.path.join(SAMPLE_IMAGES_DIR, f'item_{item_index}.jpg')
    if os.path.exists(local_path):
        try:
            with open(local_path, 'rb') as f:
                raw = f.read()
            return 'data:image/jpeg;base64,' + base64.b64encode(raw).decode('ascii')
        except Exception as e:
            print(f'本地图片读取失败 ({local_path}): {e}')
    
    # 备用回退逻辑
    pid = SAMPLE_PHOTO_IDS[(item_index - 1) % len(SAMPLE_PHOTO_IDS)]
    return fetch_image_base64(pid)

def fetch_image_base64(photo_id):
    url = f'https://images.unsplash.com/{photo_id}?w=400&h=300&fit=crop&q=75'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read()
            im = Image.open(io.BytesIO(raw))
            buf = io.BytesIO()
            im.convert('RGB').save(buf, format='JPEG', quality=75)
            return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
    except Exception as e:
        print(f'图片获取失败 ({photo_id}): {e}')
        return PLACEHOLDER_IMAGE

DEMO_USER = ('demo', generate_password_hash('demo123'), '演示账号', '灵山大学')
BUYER_USER = ('buyer', generate_password_hash('demo123'), '张同学', '高丽大学')

SAMPLE_ITEMS = [
    ('高等数学教材（同济第七版）', '教材书籍', 5000, '八成新', '大一用过一学期，有少量笔记，不影响阅读'),
    ('Python编程从入门到实践', '教材书籍', 8000, '九成新', '几乎全新，只翻了前几章'),
    ('线性代数习题集', '教材书籍', 3000, '七成新及以下', '有较多笔记和折痕，但题目都在'),
    ('大学英语四级真题', '教材书籍', 4000, '八成新', '2023-2024年真题，做了两套'),
    ('数据结构与算法', '教材书籍', 12000, '九成新', '计算机专业必修课教材，保存完好'),
    ('小米空气净化器', '电子家电', 80000, '八成新', '用了一年，滤芯刚换过，功能正常'),
    ('罗技无线鼠标', '电子家电', 15000, '九成新', 'M720，用了半年，无磕碰'),
    ('三星27寸显示器', '电子家电', 120000, '八成新', '27寸1080p，IPS面板，无坏点'),
    ('小米手环7', '电子家电', 25000, '九成新', '黑色，表带正常，功能完好'),
    ('Kindle Paperwhite', '电子家电', 90000, '八成新', '第十代，有保护套，屏幕无划痕'),
    ('电饭煲（3L）', '生活用品', 35000, '八成新', 'CUCKOO品牌，3人份，功能正常'),
    ('电热水壶', '生活用品', 12000, '九成新', '1.7L，不锈钢内胆，用了半年'),
    ('台灯（护眼LED）', '生活用品', 18000, '九成新', '三档调光，USB供电，学习必备'),
    ('吹风机', '生活用品', 15000, '八成新', '飞利浦，冷热风，功能正常'),
    ('体重秤', '生活用品', 8000, '九成新', '电子秤，精准到0.1kg'),
    ('收纳箱（大号3个）', '生活用品', 10000, '九成新', '60L收纳箱，搬家出，干净无异味'),
    ('单人床垫', '家具家居', 50000, '八成新', '1.8m×2m，记忆棉，用了一年'),
    ('书桌（简易组装）', '家具家居', 30000, '八成新', '120×60cm，白色，需自提'),
    ('椅子（人体工学）', '家具家居', 45000, '八成新', '网布透气，升降扶手，坐了一年'),
    ('书架（五层）', '家具家居', 25000, '八成新', '白色木质，承重好，需自提'),
    ('小冰箱（50L）', '家具家居', 70000, '八成新', '单门迷你冰箱，冷藏冷冻都有，宿舍用'),
    ('Nike运动鞋（260mm）', '服饰鞋包', 40000, '八成新', 'Air Max系列，穿了几次，鞋底干净'),
    ('羽绒服（男L）', '服饰鞋包', 35000, '九成新', '黑色，充绒量足，只穿过一个冬天'),
    ('背包（电脑包）', '服饰鞋包', 20000, '九成新', 'Samsonite，15.6寸电脑仓，防水'),
    ('围巾（羊毛）', '服饰鞋包', 10000, '九成新', '灰色，纯羊毛，柔软保暖'),
    ('棒球帽', '服饰鞋包', 5000, '九成新', '黑色，MLB，几乎没戴过'),
    ('瑜伽垫', '其他', 8000, '九成新', 'TPE材质，6mm厚，防滑，用了几次'),
    ('羽毛球拍（两支）', '其他', 25000, '八成新', 'YONEX，两支拍+球筒，线刚拉过'),
    ('吉他（民谣）', '其他', 60000, '八成新', '41寸，云杉木，音色好，送琴包和拨片'),
    ('自行车（通勤）', '其他', 80000, '八成新', '26寸，6速变速，刹车灵敏，需自提'),
]

def main():
    if not DATABASE_URL:
        print('错误：未配置 DATABASE_URL，请在 .env 文件中填写数据库连接串')
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute('SELECT id FROM users WHERE username = %s', (DEMO_USER[0],))
        row = cur.fetchone()
        if row:
            print('demo 用户已存在，跳过创建')
            seller_id = row[0]
        else:
            cur.execute('INSERT INTO users (username, password_hash, nickname, school) VALUES (%s, %s, %s, %s) RETURNING id',
                        DEMO_USER)
            seller_id = cur.fetchone()[0]
            print(f'已创建测试用户：demo / demo123（灵山大学）')

        cur.execute('SELECT id FROM users WHERE username = %s', (BUYER_USER[0],))
        if not cur.fetchone():
            cur.execute('INSERT INTO users (username, password_hash, nickname, school) VALUES (%s, %s, %s, %s)', BUYER_USER)
            print(f'已创建测试买家用户：buyer / demo123（高丽大学）')

        cur.execute('SELECT COUNT(*) FROM items WHERE seller_id = %s', (seller_id,))
        count = cur.fetchone()[0]
        if count > 0:
            print(f'已存在 {count} 条商品数据，正在检查并补充高清真实实拍图片...')
            cur.execute('SELECT id, title, length(image_base64) FROM items WHERE seller_id = %s ORDER BY id', (seller_id,))
            rows = cur.fetchall()
            for idx, (i_id, i_title, img_len) in enumerate(rows):
                b64 = load_product_image_base64(idx + 1)
                cur.execute('UPDATE items SET image_base64 = %s WHERE id = %s', (b64, i_id))
                print(f'已为商品 [{i_title}] 更新真实实拍图 (ID: {i_id})')
            print('商品真实实拍图同步更新完成')
        else:
            for idx, (title, category, price, condition, description) in enumerate(SAMPLE_ITEMS):
                img_b64 = load_product_image_base64(idx + 1)
                cur.execute(
                    'INSERT INTO items (seller_id, title, category, price, condition, description, image_base64) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                    (seller_id, title, category, price, condition, description, img_b64))
            print(f'已插入 {len(SAMPLE_ITEMS)} 条示例商品（附带真实实拍图）')

        cur.close()
        conn.close()
        print('模拟数据导入完成')
    except Exception as e:
        print(f'数据导入失败：{e}')

if __name__ == '__main__':
    main()
