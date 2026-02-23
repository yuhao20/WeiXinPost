import config
import time
import os
import base64
from time import localtime
from requests import get, post
from datetime import datetime, date
from PIL import Image, ImageDraw, ImageFont


# ==================== 微信接口 ====================

def get_access_token():
    app_id = config.app_id
    app_secret = config.app_secret
    post_url = ("https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={}&secret={}"
                .format(app_id, app_secret))
    #print(get(post_url).json())
    access_token = get(post_url).json()['access_token']
    return access_token


# ==================== 天气 ====================

def get_weather(city):
    # 第一步：城市名转经纬度
    geo_url = "https://geocoding-api.open-meteo.com/v1/search?name={}&count=1&language=zh".format(city)
    geo_data = get(geo_url).json()
    lat = geo_data["results"][0]["latitude"]
    lon = geo_data["results"][0]["longitude"]
    
    # 第二步：根据坐标查天气
    weather_url = ("https://api.open-meteo.com/v1/forecast?"
                   "latitude={}&longitude={}&current_weather=true"
                   "&daily=temperature_2m_max,temperature_2m_min"
                   "&timezone=auto").format(lat, lon)
    data = get(weather_url).json()
    
    code = data["current_weather"]["weathercode"]
    # 天气码转中文
    weather_map = {
        0:"晴天", 1:"基本晴朗", 2:"局部多云", 3:"阴天",
        51:"小毛毛雨", 61:"小雨", 63:"中雨", 65:"大雨",
        71:"小雪", 73:"中雪", 75:"大雪", 80:"阵雨",
        95:"雷阵雨"
    }
    weather = weather_map.get(code, "未知")
    temp = str(data["daily"]["temperature_2m_max"][0]) + "℃"
    tempn = str(data["daily"]["temperature_2m_min"][0]) + "℃"
    
    return weather, temp, tempn

def is_rainy_weather(city):
    """检查今日天气是否包含降雨，返回 (bool, weather_str)"""
    RAIN_CODES = {51, 53, 55, 61, 63, 65, 71, 73, 75, 80, 81, 82, 95, 96, 99}
    
    geo_url = "https://geocoding-api.open-meteo.com/v1/search?name={}&count=1&language=zh".format(city)
    geo_data = get(geo_url).json()
    lat = geo_data["results"][0]["latitude"]
    lon = geo_data["results"][0]["longitude"]

    weather_url = (
        "https://api.open-meteo.com/v1/forecast?"
        "latitude={}&longitude={}&current_weather=true"
        "&daily=precipitation_sum"
        "&timezone=auto"
    ).format(lat, lon)
    data = get(weather_url).json()

    code = data["current_weather"]["weathercode"]
    cur_tmeperature = data["current_weather"]["temperature"]
    precip = data["daily"]["precipitation_sum"][0]   # 今日总降水量(mm)

    weather_map = {
        0:"晴天", 1:"基本晴朗", 2:"局部多云", 3:"阴天",
        51:"小毛毛雨", 53:"毛毛雨", 55:"大毛毛雨",
        61:"小雨", 63:"中雨", 65:"大雨",
        71:"小雪", 73:"中雪", 75:"大雪",
        80:"阵雨", 81:"中阵雨", 82:"强阵雨",
        95:"雷阵雨", 96:"雷阵雨夹冰雹", 99:"强雷阵雨"
    }
    weather_desc = weather_map.get(code, "未知")
    is_rain = code in RAIN_CODES or precip > 0
    return is_rain, weather_desc, int(precip), str(round(float(cur_tmeperature),1))

def send_Rain_Reminder(to_user, access_token, class_index, weather_desc, precip, cur_tmeperature):
    """课后雨天提醒（template_id3）"""
    url = "https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={}".format(access_token)
    #theuser = to_user[0]
    print(config.template_id3)
    for theuser in to_user:
        data = {
            "touser": theuser,
            "template_id": config.template_id3,
            "url": "http://weixin.qq.com/download",
            "topcolor": "#FF0000",
            "data": {
                "weather_desc": {
                    "value": weather_desc,
                    "color": "#1E90FF",
                },
                "precip":{
                    "value": precip,
                    "color": "#1E90FF",
                },
                "cur_tmeperature":{
                    "value": cur_tmeperature,
                    "color": "#1E90FF",
                }
            }
        }
        #f"☔ 第{class_index}节课已结束，注意天气变化！",
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36'
        }
        response = post(url, headers=headers, json=data)
        print(f"雨天提醒发送结果:", response.text)#print(f"雨天提醒发送结果 (第{class_index}节后):", response.text)
# ==================== 课程相关 ====================

def get_Today_Week():
    y = config.year
    m = config.month
    d = config.day
    startWeek = datetime(y, m, d)
    today = datetime.today()
    d_days = today - startWeek
    trueWeek = (d_days.days // 7) + 1
    return str(trueWeek)


def get_Week_Classes(w):
    if w is not None:
        week_Class = config.classes.get(w)
    else:
        week = get_Today_Week()
        week_Class = config.classes.get(week)
    return week_Class


def get_Today_Class():
    year = localtime().tm_year
    month = localtime().tm_mon
    day = localtime().tm_mday
    today = datetime.date(datetime(year=year, month=month, day=day))
    todayClasses = get_Week_Classes(None)[today.weekday()]
    return todayClasses


def get_Class(day):
    theClasses = get_Week_Classes(None)[day]
    return theClasses


# ==================== 图片生成 ====================
import re

def generate_daily_card(city_name, weather, max_temperature, min_temperature,
                        love_days, birth_day, today_class, weeks, today, week):
    width, height = 660, 1200
    img = Image.new('RGB', (width, height), color='#FFFAF0')
    draw = ImageDraw.Draw(img)

    # ── 字体加载 ──────────────────────────────────────────────────────
    font_paths = [
        "./font.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    font_path = None
    for fp in font_paths:
        if os.path.exists(fp):
            font_path = fp
            break

    emoji_font_path = "./NotoColorEmoji.ttf"  # emoji 字体路径

    try:
        font_large  = ImageFont.truetype(font_path, 30)
        font_normal = ImageFont.truetype(font_path, 24)
        font_small  = ImageFont.truetype(font_path, 20)
        # Noto Color Emoji 必须用 109 的倍数才能正常缩放
        emoji_large  = ImageFont.truetype(emoji_font_path, 109)
        emoji_normal = ImageFont.truetype(emoji_font_path, 109)
        emoji_small  = ImageFont.truetype(emoji_font_path, 109)
    except Exception as e:
        print("字体加载失败，使用默认字体:", e)
        font_large = font_normal = font_small = ImageFont.load_default()
        emoji_large = emoji_normal = emoji_small = font_large

    MARGIN  = 20
    PADDING = 24
    GAP     = 16

    # ── emoji 判断 ────────────────────────────────────────────────────
    EMOJI_RE = re.compile(
        r'[\U0001F300-\U0001FAFF'   # 杂项符号/表情
        r'\U00002600-\U000027BF'    # 杂项符号
        r'\U0000FE00-\U0000FE0F'    # 变体选择符
        r'\U0001F1E0-\U0001F1FF]'   # 国旗
    )

    def is_emoji(ch):
        return bool(EMOJI_RE.match(ch))

    # ── 混合绘制函数 ───────────────────────────────────────────────────
    # emoji_scale：因为 Noto emoji 字体固定 109px，需要缩放到目标尺寸
    def draw_mixed_text(xy, text, font_cn, font_em, fill, target_size):
        x, y = xy
        scale = target_size / 109          # 缩放比例
        for ch in text:
            if is_emoji(ch):
                # 用 emoji 字体渲染到临时小图，再缩放贴回
                ch_w, ch_h = 109, 109
                em_img = Image.new('RGBA', (ch_w, ch_h), (0, 0, 0, 0))
                em_draw = ImageDraw.Draw(em_img)
                em_draw.text((0, 0), ch, font=font_em, embedded_color=True)
                new_size = (int(ch_w * scale), int(ch_h * scale))
                em_img = em_img.resize(new_size, Image.LANCZOS)
                img.paste(em_img, (int(x), int(y)), em_img)
                x += new_size[0]
            else:
                draw.text((x, y), ch, font=font_cn, fill=fill)
                bbox = font_cn.getbbox(ch)
                x += bbox[2] - bbox[0]

    # ── 天气卡片 ──────────────────────────────────────────────────────
    W1, W2 = 20, 295
    draw.rounded_rectangle([MARGIN, W1, width - MARGIN, W2], radius=18,
                            fill='#E8F4FD', outline='#87CEEB', width=2)
    draw_mixed_text((40, W1 + PADDING),       "🌤  天气",                                                   font_large,  emoji_large,  '#1E90FF', 30)
    draw_mixed_text((40, W1 + PADDING + 55),  f"📅 {today}  {week}  第 {weeks} 周",                         font_normal, emoji_normal, '#555555', 24)
    draw_mixed_text((40, W1 + PADDING + 105), f"📍 {city_name}    {weather}",                               font_normal, emoji_normal, '#333333', 24)
    draw_mixed_text((40, W1 + PADDING + 160), f"🔥 最高 {max_temperature}      ❄️ 最低 {min_temperature}",
                                                                                                              font_normal, emoji_normal, '#555555', 24)

    # ── 纪念日卡片 ────────────────────────────────────────────────────
    L1, L2 = W2 + GAP, W2 + GAP + 179
    draw.rounded_rectangle([MARGIN, L1, width - MARGIN, L2], radius=18,
                            fill='#FFF0F5', outline='#FFB6C1', width=2)
    draw_mixed_text((40, L1 + PADDING),      "💕  纪念日",                                                   font_large,  emoji_large,  '#FF69B4', 30)
    draw_mixed_text((40, L1 + PADDING + 58), f"在一起第  {love_days}  天    🎂 距生日还有  {birth_day}  天",  font_normal, emoji_normal, '#888888', 24)

    # ── 课程卡片 ──────────────────────────────────────────────────────
    C1, C2 = L2 + GAP, height - MARGIN
    draw.rounded_rectangle([MARGIN, C1, width - MARGIN, C2], radius=18,
                            fill='#F0FFF0', outline='#98FB98', width=2)
    draw_mixed_text((40, C1 + PADDING), "📚  今日课程", font_large, emoji_large, '#2E8B57', 30)

    class_labels = ["第一节", "第二节", "第三节", "第四节", "第五节", "第六节"]
    tag_colors   = ['#FF6347', '#FF8C00', '#4169E1', '#8A2BE2', '#20B2AA', '#DC143C']
    HEADER_H = 70
    ROW_H    = (C2 - C1 - HEADER_H) // len(class_labels)
    for i, (label, cls) in enumerate(zip(class_labels, today_class)):
        y_pos = C1 + HEADER_H + i * ROW_H
        if i > 0:
            draw.line([(40, y_pos), (width - 40, y_pos)], fill='#C8E6C9', width=1)
        tag_y = y_pos + (ROW_H - 36) // 2
        draw.rounded_rectangle([40, tag_y, 118, tag_y + 36], radius=8, fill=tag_colors[i])
        draw.text((49, tag_y + 8), label, font=font_small, fill='#FFFFFF')   # 节次标签纯中文，直接用 draw.text
        text = cls if cls else "暂无课程"
        draw.text((132, tag_y + 8), text, font=font_normal, fill='#333333')  # 课程名一般无 emoji，同上

    path = '/tmp/daily_card.png'
    img.save(path)
    print("图片生成成功:", path)
    return path

# ==================== 图床上传 ====================

# 免费注册并获取 API Key：https://api.imgbb.com
# 然后在 config.py 中添加一行：imgbb_key = "你的key"
# def upload_to_imgbb(image_path):
#     with open(image_path, 'rb') as f:
#         image_data = base64.b64encode(f.read()).decode('utf-8')
#     response = post("https://api.imgbb.com/1/upload", data={
#         "key": "4e29ec5c380534560d414fc4f067c745", #config.imgbb_key,
#         "image": image_data,
#     })
#     result = response.json()
#     print("imgbb 上传结果:", result)
#     if result.get("success"):
#         return result["data"]["url"]
#     print("imgbb 上传失败:", result)
#     return None

def upload_to_gitee(image_path):
    with open(image_path, 'rb') as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')
    
    filename = datetime.now().strftime('%Y%m%d%H%M%S') + '.png'
    url = "https://gitee.com/api/v5/repos/{}/{}/contents/{}".format(
        config.gitee_owner, config.gitee_repo, filename
    )
    response = post(url, json={
        "access_token": config.gitee_token,
        "message": "upload image",
        "content": image_data,
    })
    result = response.json()
    print("gitee 上传结果:", result.get("content", {}).get("name", result))
    if response.status_code == 201:
        raw_url = "https://gitee.com/{}/{}/raw/master/{}".format(
            config.gitee_owner, config.gitee_repo, filename
        )
        print("jyh图片直链:", raw_url)
        return raw_url
    print("gitee 上传失败:", result)
    return None


# ==================== 微信发送相关 ====================

# 发送每日信息
# 模板消息正常显示所有内容（周次/日期/天气/纪念日/课程）
# url 字段替换为图片直链，点击消息标题跳转彩色图片卡片
def send_message(to_user, access_token, city_name, weather, max_temperature, min_temperature):
    week_list = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    year  = localtime().tm_year
    month = localtime().tm_mon
    day   = localtime().tm_mday
    today = datetime.date(datetime(year=year, month=month, day=day))
    week  = week_list[today.weekday()]
    weeks = get_Today_Week()

    # 在一起天数
    love_year  = int(config.love_date.split("-")[0])
    love_month = int(config.love_date.split("-")[1])
    love_day   = int(config.love_date.split("-")[2])
    love_date  = date(love_year, love_month, love_day)
    love_days  = str(today.__sub__(love_date)).split(" ")[0]

    # 生日倒计时
    birthday_month = int(config.birthday.split("-")[1])
    birthday_day   = int(config.birthday.split("-")[2])
    year_date = date(year, birthday_month, birthday_day)
    if today > year_date:
        birth_date = date((year + 1), birthday_month, birthday_day)
        birth_day  = str(birth_date.__sub__(today)).split(" ")[0]
    elif today == year_date:
        birth_day = 0
    else:
        birth_day = str(year_date.__sub__(today)).split(" ")[0]

    theClass = get_Today_Class()

    # 生成图片 → 上传图床 → 拿到直链作为跳转 url
    card_url = "http://weixin.qq.com/download"   # 上传失败时的兜底链接
    try:
        image_path = generate_daily_card(
            city_name, weather, max_temperature, min_temperature,
            love_days, birth_day, theClass, weeks, today, week
        )
        img_url = upload_to_gitee(image_path) #img_url = upload_to_imgbb(image_path)
        
        if img_url:
            card_url = img_url
            print("图片直链:", card_url)
        os.remove(image_path)
    except Exception as e:
        print("图片生成/上传失败，使用默认链接:", e)

    # 发送模板消息，内容完整，点击标题跳转图片卡片
    url = "https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={}".format(access_token)
    #theuser = to_user[0]
    for theuser in to_user:
        data = {
            "touser": theuser,
            "template_id": config.template_id1,
            "url": card_url,          # ← 点击消息跳转彩色图片卡片
            "topcolor": "#FF0000",
            "data": {
                "weeks": {
                    "value": weeks,
                    "color": "#00FFFF"
                },
                "date": {
                    "value": "{} {}".format(today, week),
                    "color": "#00FFFF"
                },
                "city": {
                    "value": city_name,
                    "color": "#808A87"
                },
                "weather": {
                    "value": weather,
                    "color": "#ED9121"
                },
                "min_temperature": {
                    "value": min_temperature,
                    "color": "#00FF00"
                },
                "max_temperature": {
                    "value": max_temperature,
                    "color": "#FF6100"
                },
                "love_day": {
                    "value": love_days,
                    "color": "#87CEEB"
                },
                "birthday": {
                    "value": birth_day,
                    "color": "#FF8000"
                },
                "firstClass": {
                    "value": theClass[0],
                    "color": "#FF8000"
                },
                "secondClass": {
                    "value": theClass[1],
                    "color": "#FF8000"
                },
                "thirdClass": {
                    "value": theClass[2],
                    "color": "#FF8000"
                },
                "fourthClass": {
                    "value": theClass[3],
                    "color": "#FF8000"
                },
                "fifthClass": {
                    "value": theClass[4],
                    "color": "#FF8000"
                },
                "sixthClass": {
                    "value": theClass[5],
                    "color": "#FF8000"
                }
            }
        }
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36'
        }
        response = post(url, headers=headers, json=data)
        print("模板消息发送结果:", response.text)


# 发送课程提醒消息
def send_Class_Message(to_user, access_token, classInfo):
    url = "https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={}".format(access_token)
    #theuser = to_user[0]
    class_name = classInfo['class_name']
    class_time = classInfo['class_time']
    for theuser in to_user:
        data = {
            "touser": theuser,
            "template_id": config.template_id2,
            "url": "http://weixin.qq.com/download",
            "topcolor": "#FF0000",
            "data": {
                "className": {
                    "value": class_name,
                    "color": "#FF8000"
                },
                "classTime": {
                    "value": class_time,
                    "color": "#FF8000"
                }
            }
        }
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36'
        }
        response = post(url, headers=headers, json=data)
        print(response.text)





# ==================== 工具函数 ====================

def calculate_Time_Difference(t1, t2):
    h1 = int(t1[0:2]);  h2 = int(t2[0:2])
    m1 = int(t1[3:5]);  m2 = int(t2[3:5])
    s1 = int(t1[6:8]);  s2 = int(t2[6:8])
    d1 = datetime(2022, 1, 1, h1, m1, s1)
    d2 = datetime(2022, 1, 1, h2, m2, s2)
    return (d1 - d2).seconds


# ==================== 主函数 ====================
def main():
    accessToken = get_access_token()
    print('token:', accessToken)

    user = config.user
    print('user:', user)

    city = config.city
    weather, max_temperature, min_temperature = get_weather(city)

    # 每日推送：模板消息显示完整内容，点击标题跳转彩色图片卡片
    if datetime.now().strftime('%H:%M:%S') < config.post_Time:
        send_message(user, accessToken, city, weather, max_temperature, min_temperature)



    # 课程提醒推送
    # todayClasses = get_Today_Class()
    # time_table = config.time_table
    # for i in range(len(time_table)):
    #     reminderTime = time_table[i]
    #     nowTime = datetime.now().strftime('%H:%M:%S')
    #     if reminderTime > nowTime and calculate_Time_Difference(reminderTime, nowTime) > config.remain_time:  # 当前没有合适的课程提醒时段
    #         break
    #     if reminderTime < nowTime and calculate_Time_Difference(nowTime, reminderTime) > 30:  # 跳过之前的时段
    #         continue
    #     while True:
    #         nowTime = datetime.now().strftime('%H:%M:%S')
    #         if reminderTime == nowTime:
    #             if len(todayClasses[i]) != 0:
    #                 classInfo = dict()
    #                 classInfo['class_name'] = "课程信息: " + todayClasses[i]
    #                 classInfo['class_time'] = "上课时间: " + config.course_Time[i]
    #                 send_Class_Message(user, accessToken, classInfo)
    #                 print("课程信息推送成功！")
    #             break
    #         elif reminderTime < nowTime:
    #             break
    #         defference = calculate_Time_Difference(reminderTime, nowTime) - 3
    #         if defference > 0:
    #             print(f'休眠{defference}秒')
    #             time.sleep(defference)
    #     break

    # 天气提醒推送
    class_end_time = config.class_end_time
    for i in range(len(class_end_time)):
        endTime = class_end_time[i]
        nowTime = datetime.now().strftime('%H:%M:%S')
        if endTime > nowTime and calculate_Time_Difference(endTime, nowTime) > config.remain_time:  # 当前没有合适的天气提醒时段
            break
        if endTime < nowTime and calculate_Time_Difference(nowTime, endTime) > 30:  # 跳过之前的时段
            continue
        while True:
            nowTime = datetime.now().strftime('%H:%M:%S')

            if nowTime >= endTime:
                try:
                    is_rain, weather_desc, precip, cur_temperature = is_rainy_weather(city)
                    if is_rain:
                        send_Rain_Reminder(user, accessToken, i + 1, weather_desc, precip, cur_temperature)
                        print("雨天提醒已发送")
                    else:
                        print("天气良好，无需提醒")
                except Exception as e:
                    print("天气查询失败:", e)
                break

            diff = calculate_Time_Difference(endTime, nowTime) - 3
            if diff > 0:
                print(f'休眠{diff}秒')
                time.sleep(diff)

        break

# ==================== 主程序 ====================
if __name__ == '__main__':
    main()
