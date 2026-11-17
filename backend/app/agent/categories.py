"""消费类别体系与关键词归一化。

类别体系由本模块统一维护：Agent 的 Prompt、规则兜底与统计口径都以 CATEGORIES 为准。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

CATEGORIES: tuple[str, ...] = (
    "餐饮",
    "交通",
    "购物",
    "居住",
    "娱乐",
    "医疗",
    "教育",
    "人情",
    "其他",
)

# 顺序即匹配优先级：先命中先返回，避免「打车去超市」被归到购物
CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("餐饮", ("早餐", "早饭", "午饭", "午餐", "晚饭", "晚餐", "夜宵", "外卖", "奶茶", "咖啡", "火锅", "烧烤", "食堂", "小吃", "餐厅", "吃饭", "聚餐", "喝了")),
    ("交通", ("打车", "滴滴", "网约车", "地铁", "公交", "高铁", "火车", "机票", "加油", "油费", "停车", "高速", "共享单车")),
    ("居住", ("房租", "水费", "电费", "燃气", "物业", "宽带", "房贷", "租房")),
    ("医疗", ("医院", "挂号", "买药", "药费", "体检", "看病", "牙医")),
    ("教育", ("学费", "教材", "书费", "课程", "培训", "考试报名", "网课")),
    ("娱乐", ("电影", "游戏", "KTV", "旅游", "演出", "健身", "会员", "剧本杀", "演唱会")),
    ("人情", ("红包", "份子", "礼物", "请客", "随礼")),
    ("购物", ("淘宝", "京东", "拼多多", "网购", "衣服", "鞋子", "数码", "超市", "便利店", "买了", "购物")),
)

DATE_PATTERN = r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?"


def get_tz(timezone: str) -> ZoneInfo:
    return ZoneInfo(timezone)


def today_in(timezone: str) -> date:
    return datetime.now(get_tz(timezone)).date()


def detect_category(text: str) -> str | None:
    """按关键词识别类别；无法判断时返回 None（交给模型或追问）。"""
    for category in CATEGORIES:
        if category in text:
            return category
    for category, keywords in CATEGORY_KEYWORDS:
        for keyword in keywords:
            if keyword in text:
                return category
    return None


def normalize_category(value: str | None) -> str | None:
    """把模型给出的类别收敛到 CATEGORIES 内。"""
    if not value:
        return None
    value = value.strip()
    if value in CATEGORIES:
        return value
    for category, keywords in CATEGORY_KEYWORDS:
        if category in value or any(keyword in value for keyword in keywords):
            return category
    return "其他" if value else None


def parse_amount(text: str) -> float | None:
    """从自然语言里提取金额。

    优先取带货币单位的数字（25 元 / 32 块 / ￥18.5），
    否则取最后一个不属于日期的小数/整数。
    """
    import re

    matches = list(re.finditer(r"(\d+(?:\.\d{1,2})?)\s*(?:元|块钱|块|rmb|RMB|￥|¥)", text))
    if matches:
        return float(matches[-1].group(1))

    cleaned = re.sub(DATE_PATTERN, " ", text)
    cleaned = re.sub(r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]", " ", cleaned)
    cleaned = re.sub(r"\d{1,2}\s*[日号]", " ", cleaned)
    numbers = re.findall(r"(?<![\d.])(\d+(?:\.\d{1,2})?)(?![\d.])", cleaned)
    if len(numbers) == 1:
        return float(numbers[0])
    return None


def parse_occurred_at(text: str, today: date) -> date | None:
    """解析相对/绝对日期，支持今天、昨天、前天、上周X、N 月 N 日。"""
    import re

    absolutes = re.findall(DATE_PATTERN, text)
    if absolutes:
        year, month, day = absolutes[-1]
        try:
            return date(int(year), int(month), int(day))
        except ValueError:
            return None

    month_day = re.search(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]", text)
    if month_day:
        month, day = int(month_day.group(1)), int(month_day.group(2))
        try:
            return date(today.year, month, day)
        except ValueError:
            return None

    offsets = {"今天": 0, "今日": 0, "今早": 0, "今晚": 0, "昨天": 1, "昨日": 1, "昨晚": 1, "前天": 2, "大前天": 3}
    for word, offset in offsets.items():
        if word in text:
            return today - timedelta(days=offset)

    weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
    weekday_match = re.search(r"(上周|本周|这周)([一二三四五六日天])", text)
    if weekday_match:
        scope, weekday = weekday_match.groups()
        monday = today - timedelta(days=today.weekday())
        target = monday + timedelta(days=weekday_map[weekday])
        if scope == "上周":
            target -= timedelta(days=7)
        return target

    if "上周" in text:
        return today - timedelta(days=7)
    return None


def parse_period(text: str, today: date) -> tuple[date, date] | None:
    """解析查询用的时间区间（闭区间）。"""
    import re

    if "上周" in text:
        monday = today - timedelta(days=today.weekday())
        return monday - timedelta(days=7), monday - timedelta(days=1)
    if "本周" in text or "这周" in text:
        monday = today - timedelta(days=today.weekday())
        return monday, today
    if "上个月" in text or "上月" in text:
        first = today.replace(day=1)
        last_month_end = first - timedelta(days=1)
        return last_month_end.replace(day=1), last_month_end
    if "本月" in text or "这个月" in text or "这月" in text:
        return today.replace(day=1), today
    if "今年" in text:
        return date(today.year, 1, 1), today
    if "昨天" in text:
        day = today - timedelta(days=1)
        return day, day
    if "今天" in text:
        return today, today

    recent_days = re.search(r"(?:最近|近)\s*(\d{1,2})\s*天", text)
    if recent_days:
        days = max(1, int(recent_days.group(1)))
        return today - timedelta(days=days - 1), today
    recent_months = re.search(r"(?:最近|近)\s*(\d{1,2})\s*个?月", text)
    if recent_months:
        months = max(1, int(recent_months.group(1)))
        return today - timedelta(days=30 * months), today

    month_day = re.search(r"(\d{1,2})\s*月", text)
    if month_day:
        month = int(month_day.group(1))
        if 1 <= month <= 12:
            start = date(today.year, month, 1)
            end = (start.replace(year=today.year + 1, month=1, day=1) if month == 12 else start.replace(month=month + 1, day=1)) - timedelta(days=1)
            return start, min(end, today)
    return None


def normalize_month(text: str, today: date) -> str:
    """把「上个月/本月」等归一化为 YYYY-MM 字符串，供预算工具使用。"""
    if "上个月" in text or "上月" in text:
        first = today.replace(day=1)
        return (first - timedelta(days=1)).strftime("%Y-%m")
    return today.strftime("%Y-%m")
