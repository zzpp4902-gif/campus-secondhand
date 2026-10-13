import os
import psycopg2
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

DATABASE_URL = os.environ.get('DATABASE_URL', '')

PLACEHOLDER_IMAGE = ('data:image/jpeg;base64,'
    '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0a'
    'HBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIy'
    'MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QA'
    'FAABAAAAAAAAAAAAAAAAAAAACf/EABQBAQAAAAAAAAAAAAAAAAAAAAD/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEQMRAD8A/9k=')

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
        if cur.fetchone():
            print('demo 用户已存在，跳过创建')
            cur.execute('SELECT id FROM users WHERE username = %s', (DEMO_USER[0],))
            seller_id = cur.fetchone()[0]
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
            print(f'已存在 {count} 条商品数据，跳过插入')
        else:
            for title, category, price, condition, description in SAMPLE_ITEMS:
                cur.execute(
                    'INSERT INTO items (seller_id, title, category, price, condition, description, image_base64) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                    (seller_id, title, category, price, condition, description, PLACEHOLDER_IMAGE))
            print(f'已插入 {len(SAMPLE_ITEMS)} 条示例商品')

        cur.close()
        conn.close()
        print('模拟数据导入完成')
    except Exception as e:
        print(f'数据导入失败：{e}')


if __name__ == '__main__':
    main()
