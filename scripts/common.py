"""Pure-stdlib shared taxonomy, normalization, and strict record validator for Super-Board."""
from __future__ import annotations

import json
import re
from datetime import date as dt_date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_PATH = ROOT / "taxonomy.json"
DB_PATH = ROOT / "data/super_board.sqlite"
ULTRA_BOARD_RAW = Path(r"C:\Ai\Ultra-Board\data\kaipanla\raw")

STATE_CENTRAL_KEYWORDS = (
    "国务院国有资产监督管理委员会",
    "国务院国资委",
    "财政部",
    "中央汇金",
    "中国中信",
    "中国航天",
    "中国航空工业",
    "中国兵器",
    "中国船舶",
    "中国电子科技",
    "中国电子信息",
    "中国石油",
    "中国石化",
    "国家电网",
    "中国华能",
    "中国大唐",
    "中国华电",
    "国家能源",
    "国家电力投资",
    "中国中车",
    "中国建材",
    "中国宝武",
    "招商局集团",
    "华润",
    "保利",
    "中国电信",
    "中国移动",
    "中国联通",
    "中粮集团",
    "中国五矿",
    "中国铝业",
    "中国稀土",
    "中国科学院",
)

STATE_LOCAL_KEYWORDS = (
    "国有资产监督管理",
    "国资委",
    "国资局",
    "国有资产",
    "财政厅",
    "财政局",
    "人民政府",
    "市国资",
    "省国资",
    "开发区管委会",
    "管理委员会",
    "国有资本运营",
    "国有控股",
)

CITY_TO_PROVINCE_ALIASES: dict[str, str] = {
    "深圳": "广东省",
    "广州": "广东省",
    "珠海": "广东省",
    "佛山": "广东省",
    "东莞": "广东省",
    "厦门": "福建省",
    "福州": "福建省",
    "宁波": "浙江省",
    "杭州": "浙江省",
    "温州": "浙江省",
    "青岛": "山东省",
    "济南": "山东省",
    "大连": "辽宁省",
    "沈阳": "辽宁省",
    "苏州": "江苏省",
    "南京": "江苏省",
    "无锡": "江苏省",
    "武汉": "湖北省",
    "成都": "四川省",
    "西安": "陕西省",
    "郑州": "河南省",
    "长沙": "湖南省",
    "合肥": "安徽省",
    "长春": "吉林省",
    "哈尔滨": "黑龙江省",
    "昆明": "云南省",
    "贵阳": "贵州省",
    "南宁": "广西壮族自治区",
    "海口": "海南省",
    "三亚": "海南省",
    "乌鲁木齐": "新疆维吾尔自治区",
    "呼和浩特": "内蒙古自治区",
    "拉萨": "西藏自治区",
    "银川": "宁夏回族自治区",
    "西宁": "青海省",
    "兰州": "甘肃省",
    "太原": "山西省",
    "石家庄": "河北省",
    "南昌": "江西省",
    "绵阳": "四川省",
    "宜宾": "四川省",
    "德阳": "四川省",
    "泸州": "四川省",
    "烟台": "山东省",
    "潍坊": "山东省",
    "淄博": "山东省",
    "济宁": "山东省",
    "临沂": "山东省",
    "威海": "山东省",
    "东营": "山东省",
    "泉州": "福建省",
    "漳州": "福建省",
    "龙岩": "福建省",
    "莆田": "福建省",
    "宁德": "福建省",
    "常州": "江苏省",
    "南通": "江苏省",
    "徐州": "江苏省",
    "扬州": "江苏省",
    "盐城": "江苏省",
    "镇江": "江苏省",
    "绍兴": "浙江省",
    "嘉兴": "浙江省",
    "金华": "浙江省",
    "台州": "浙江省",
    "湖州": "浙江省",
    "芜湖": "安徽省",
    "马鞍山": "安徽省",
    "蚌埠": "安徽省",
    "惠州": "广东省",
    "中山": "广东省",
    "江门": "广东省",
    "汕头": "广东省",
    "湛江": "广东省",
    "宜昌": "湖北省",
    "襄阳": "湖北省",
    "株洲": "湖南省",
    "湘潭": "湖南省",
    "衡阳": "湖南省",
    "洛阳": "河南省",
    "唐山": "河北省",
    "保定": "河北省",
    "包头": "内蒙古自治区",
    "柳州": "广西壮族自治区",
    "桂林": "广西壮族自治区",
    "宝鸡": "陕西省",
    "咸阳": "陕西省",
    "遵义": "贵州省",
    "九江": "江西省",
    "赣州": "江西省",
}

OVERSEAS_KEYWORDS = ("境外", "国外", "外销", "海外", "出口", "国际", "港澳台及海外")
DOMESTIC_KEYWORDS = ("境内", "国内", "内销", "大陆", "中国地区")
NON_OVERSEAS_EXCLUDE = ("其他(补充)", "补充", "抵销", "未分配")

MA_FORBIDDEN_IN_DYNAMIC = (
    "并购重组",
    "并购",
    "重组",
    "控股权转让",
    "控制权变更",
    "股权转让",
    "借壳",
    "资产注入",
    "资产重组",
)

FORBIDDEN_SINGLE_L1_NICHES = {
    "固态电池",
    "锂电",
    "光伏",
    "储能",
    "汽车",
    "无人驾驶",
    "新能源汽车",
    "光刻胶",
    "半导体洁净室",
    "洁净室",
    "先进封装",
    "GPU",
    "HBM",
    "人形机器人",
    "电子皮肤",
    "丝杠",
    "减速器",
    "工业设备",
    "工业母机",
    "交运",
    "轨道交通",
    "算力租赁",
    "AIDC",
    "液冷",
    "算力电源",
    "冰雪产业",
    "免税",
    "零售",
    "水产品",
    "水产养殖",
    "猪肉",
    "黄金",
    "稀土",
    "稀土永磁",
    "锂矿",
    "光模块",
    "PCB",
    "覆铜板",
    "创新药",
    "中药",
    "AI医疗",
    "传媒",
    "游戏",
    "影视",
    "风电",
    "核电",
    "可控核聚变",
    "特高压",
    "智能电网",
    "国产替代/信创",
    "国产替代",
    "信创",
    "自主可控",
    "数据要素",
    "数字货币",
    "大飞机",
    "3D打印",
    "中日韩贸易",
    "字节链",
    "阿里链",
    "地产",
    "石油",
    "消费电子",
}


CONTROLLER_MAPPING_KEYWORDS = (
    "实控人变更",
    "控股权变更",
    "控制权变更",
    "控股股东变更",
    "新实控人",
    "新控股股东",
    "实控人映射",
    "实控人产业背景",
    "入主",
)
TAG_TTL_DAYS = 365
CONTROLLER_MAPPING_TTL_DAYS = 730

CLASSIC_ZIBEI_ORDER: tuple[str, ...] = (
    "中字头",
    "数字辈",
    "动物",
    "华字辈",
    "东方字辈",
    "龙字辈",
    "金字辈",
    "羊字辈",
)
CLASSIC_ZIBEI_SET: set[str] = set(CLASSIC_ZIBEI_ORDER)

YANG_ZIBEI_CHARS: tuple[str, ...] = ("羊", "阳", "洋", "扬", "杨")
YANG_ZIBEI_EXTRA_CODES: set[str] = {"002292"}  # 奥飞娱乐（喜羊羊核心IP）
NUMBER_ZIBEI_CHARS: tuple[str, ...] = tuple("零一二三四五六七八九十百千万")
ANIMAL_MYSTIC_CHARS: tuple[str, ...] = tuple("鼠牛虎兔龙蛇马羊猴鸡狗猪狼狮鹿熊豹猫犬狐驼鹰鹤燕鸥鹅凤凰鱼鲸鲨鸭鸟雀鸽蜂蝶麒麟")

PROVINCE_SHORT_MAP: dict[str, str] = {
    "北京市": "北京",
    "天津市": "天津",
    "上海市": "上海",
    "重庆市": "重庆",
    "内蒙古自治区": "内蒙古",
    "广西壮族自治区": "广西",
    "西藏自治区": "西藏",
    "宁夏回族自治区": "宁夏",
    "新疆维吾尔自治区": "新疆",
}

CORE_CITY_REGION_MAP: dict[str, str] = {
    "深圳市": "深圳",
    "杭州市": "杭州",
    "苏州市": "苏州",
    "合肥市": "合肥",
    "成都市": "成都",
    "武汉市": "武汉",
}

WESTERN_DEV_PROVINCES: set[str] = {
    "四川", "重庆", "贵州", "云南", "西藏", "陕西",
    "甘肃", "青海", "宁夏", "新疆", "广西", "内蒙古",
}

NORTHEAST_PROVINCES: set[str] = {
    "辽宁", "吉林", "黑龙江",
}

ALL_REGION_TAG_SET: set[str] = {
    "北京", "天津", "上海", "重庆", "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南",
    "广东", "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海",
    "内蒙古", "广西", "西藏", "宁夏", "新疆",
    "深圳", "杭州", "苏州", "合肥", "成都", "武汉",
    "西部大开发", "东北", "雄安",
}


def short_province(prov: str | None) -> str:
    s = str(prov or "").strip()
    if not s:
        return ""
    if s in PROVINCE_SHORT_MAP:
        return PROVINCE_SHORT_MAP[s]
    return s.replace("省", "").replace("市", "")


def normalize_region_tag(tag: str | None) -> str:
    s = str(tag or "").strip()
    if s.endswith("本地") and len(s) >= 4 and s[:-2] in ALL_REGION_TAG_SET:
        return s[:-2]
    return s


def is_zibei_tag(tag: str | None) -> bool:
    s = str(tag or "").strip()
    return s.endswith("字辈") and len(s) >= 3


def is_region_tag(tag: str | None) -> bool:
    s = str(tag or "").strip()
    if s in ALL_REGION_TAG_SET:
        return True
    return s.endswith("本地") and len(s) >= 4 and s[:-2] in ALL_REGION_TAG_SET


SOE_REFORM_TAG = "国企改革"


def is_intrinsic_tag(tag: str | None) -> bool:
    """True for permanent intrinsic tags (classic XX字辈, permanent province/core-city regions, and 国企改革)."""
    s = str(tag or "").strip()
    return s in CLASSIC_ZIBEI_SET or is_region_tag(s) or s == SOE_REFORM_TAG


def extract_intrinsic_tags(
    code: str | None,
    name: str | None,
    province: str | None = None,
    city: str | None = None,
    controller_province: str | None = None,
    controller_type: str | None = None,
) -> list[tuple[str, str]]:
    """Derive permanent non-expiring intrinsic tags (classic 字辈 + 地域 + 国企改革) from stock metadata."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(tag: str, ev: str) -> None:
        if tag and tag not in seen:
            seen.add(tag)
            out.append((tag, ev))

    cname = clean_stock_name(name)
    code_s = str(code or "").strip()
    if "华" in cname:
        _add("华字辈", "常驻经典字辈：股票简称含“华”")
    if "东方" in cname:
        _add("东方字辈", "常驻经典字辈：股票简称含“东方”")
    if "龙" in cname:
        _add("龙字辈", "常驻经典字辈：股票简称含“龙”")
    if "金" in cname:
        _add("金字辈", "常驻经典字辈：股票简称含“金”")
    if any(ch in cname for ch in YANG_ZIBEI_CHARS) or code_s in YANG_ZIBEI_EXTRA_CODES:
        ev = (
            "常驻经典字辈：核心IP含“喜羊羊”（羊年玄学辨识度标的）"
            if code_s in YANG_ZIBEI_EXTRA_CODES and not any(ch in cname for ch in YANG_ZIBEI_CHARS)
            else "常驻经典字辈：股票简称含“羊/阳/洋/扬/杨”"
        )
        _add("羊字辈", ev)

    if any(ch in cname for ch in NUMBER_ZIBEI_CHARS):
        _add("数字辈", "常驻玄学字辈：股票简称含数字（一至十/百/千/万/零）")
    if any(ch in cname for ch in ANIMAL_MYSTIC_CHARS) or ("象" in cname and "印象" not in cname):
        _add("动物", "常驻玄学属性：股票简称含生肖或动物字眼（动物园玄学）")

    ct_s = str(controller_type or "").strip()
    if cname.startswith("中国") or (cname.startswith("中") and ct_s == "央企"):
        _add("中字头", "常驻字头属性：股票简称“中国”开头或央企“中”字头标的")
    if ct_s in ("央企", "地方国企"):
        _add(SOE_REFORM_TAG, f"常驻股东属性：{ct_s}背景（央国企改革/市值管理/国资整合映射）")

    city_s = str(city or "").strip()
    prov_s = str(province or "").strip()
    if city_s in CORE_CITY_REGION_MAP:
        _add(CORE_CITY_REGION_MAP[city_s], f"常驻地域属性：注册位于{city_s}")
    if prov_s:
        ps = short_province(prov_s)
        if ps:
            _add(ps, f"常驻地域属性：注册位于{prov_s}")
            if ps in WESTERN_DEV_PROVINCES:
                _add("西部大开发", f"常驻地域属性：注册位于{prov_s}（西部大开发区域）")
            if ps in NORTHEAST_PROVINCES:
                _add("东北", f"常驻地域属性：注册位于{prov_s}（东北振兴区域）")
            if ps == "河北":
                _add("雄安", f"常驻地域属性：注册位于{prov_s}（雄安新区核心区域）")

    return out


def is_controller_mapping_evidence(evidence: str | None) -> bool:
    text = str(evidence or "")
    return any(kw in text for kw in CONTROLLER_MAPPING_KEYWORDS)


def tag_is_active(from_date: str | None, evidence: str | None, ref_date: str | None) -> bool:
    """All verified tags remain active indefinitely until explicitly denied, terminated, or divested."""
    fdt = str(from_date or "").strip()
    return len(fdt) >= 10


def load_taxonomy(path: Path = TAXONOMY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_stock_name(name: str | None) -> str:
    s = str(name or "").strip()
    while s.startswith(("XD", "XR", "DR")) and len(s) > 2:
        s = s[2:]
    return s.strip()


def normalize_province(raw_province: str | None, reg_address: str | None, taxonomy: dict[str, Any]) -> str | None:
    aliases = taxonomy["province_aliases"]
    valid = set(taxonomy["provinces"])
    for text in (raw_province, reg_address):
        if not text:
            continue
        cleaned = str(text).strip()
        if cleaned in valid:
            return cleaned
        if cleaned in aliases:
            return aliases[cleaned]
        for alias, std in sorted(aliases.items(), key=lambda kv: -len(kv[0])):
            if cleaned.startswith(alias) or alias in cleaned[:8]:
                return std
    return None


def extract_city(reg_address: str | None, province: str | None) -> str | None:
    if not reg_address:
        return None
    addr = str(reg_address).strip()
    if province in ("北京市", "天津市", "上海市", "重庆市"):
        return province
    if "深圳" in addr[:16]:
        return "深圳市"
    m = re.search(r"([\u4e00-\u9fa5]{2,8}?(?:市|自治州|地区|盟))", addr)
    if m:
        candidate = m.group(1)
        if province and candidate != province:
            return candidate
    return None


def infer_controller_type(controller_name: str | None, concepts: list[str] | None = None) -> str:
    name = (controller_name or "").strip()
    if any(kw in name for kw in STATE_CENTRAL_KEYWORDS):
        return "央企"
    if any(kw in name for kw in STATE_LOCAL_KEYWORDS):
        return "地方国企"
    cset = set(concepts or [])
    if "央企" in cset or "中字头" in cset:
        return "央企"
    if "地方国企" in cset or "国有企业" in cset or any(c.endswith("国资") for c in cset):
        return "地方国企"
    return "民营及其他"


def extract_controller_province(
    controller_name: str | None,
    controller_type: str | None,
    taxonomy: dict[str, Any],
) -> str | None:
    if controller_type != "地方国企" or not controller_name:
        return None
    name = str(controller_name).strip()
    if not name:
        return None
    mapping: dict[str, str] = {}
    for p in taxonomy.get("provinces", []):
        mapping[p] = p
    mapping.update(taxonomy.get("province_aliases", {}))
    mapping.update(CITY_TO_PROVINCE_ALIASES)
    for key, std in sorted(mapping.items(), key=lambda kv: -len(kv[0])):
        if key in name:
            return std
    return None


def extract_overseas_pct(region_rows: list[dict[str, Any]] | None) -> float | None:
    if not region_rows:
        return None
    overseas = 0.0
    matched_overseas = False
    has_split = False
    for row in region_rows:
        name = str(row.get("name") or "").strip()
        ratio = row.get("ratio_pct")
        if ratio is None or any(bad in name for bad in NON_OVERSEAS_EXCLUDE):
            continue
        val = float(ratio)
        if any(kw in name for kw in OVERSEAS_KEYWORDS) or any(
            reg in name for reg in ("北美", "欧洲", "亚洲", "日本", "美国", "东南亚", "韩国", "非洲", "南美", "大洋洲", "中东")
        ):
            overseas += val
            matched_overseas = True
            has_split = True
        elif any(kw in name for kw in DOMESTIC_KEYWORDS):
            has_split = True
    if matched_overseas:
        return round(min(100.0, max(0.0, overseas)), 2)
    if has_split:
        return 0.0
    return None


def validate_record(
    rec: dict[str, Any],
    ev: dict[str, Any] | None,
    taxonomy: dict[str, Any],
    min_tag_date: str | None = None,
    *,
    min_dynamic_date: str | None = None,
) -> list[str]:
    errors: list[str] = []
    cutoff = min_tag_date or min_dynamic_date or (datetime.now().date() - timedelta(days=366)).isoformat()
    valid_l1 = set(taxonomy["l1_list"])
    valid_prov = set(taxonomy["provinces"])
    valid_ctrl = set(taxonomy["controller_types"])
    valid_dyn = set(taxonomy["dynamic_groups"])
    valid_tags = valid_l1 | valid_dyn
    valid_ma_types = set(taxonomy["ma_event_types"])

    code = str(rec.get("code") or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        errors.append(f"invalid code: {code!r}")
    if ev and code != ev.get("code"):
        errors.append(f"code mismatch: {code} != {ev.get('code')}")
    if not clean_stock_name(rec.get("name")):
        errors.append(f"{code}: missing name")
    if rec.get("province") not in valid_prov:
        errors.append(f"{code}: invalid province {rec.get('province')!r}")
    if rec.get("controller_type") not in valid_ctrl:
        errors.append(f"{code}: invalid controller_type {rec.get('controller_type')!r}")

    tags = rec.get("tags")
    if not isinstance(tags, list) or not tags:
        errors.append(f"{code}: tags must be non-empty list (unified dynamic tags)")
        tags = []

    seen_tags: set[str] = set()
    for idx, item in enumerate(tags):
        if not isinstance(item, dict):
            errors.append(f"{code}: tags[{idx}] not dict")
            continue
        tname = str(item.get("tag") or "").strip()
        if not tname:
            errors.append(f"{code}: tags[{idx}] missing tag")
        elif len(tname) > 20:
            errors.append(f"{code}: tags[{idx}] tag too long: {tname[:20]}...")
        elif tname in seen_tags:
            errors.append(f"{code}: duplicate tag {tname!r}")
        elif tname in FORBIDDEN_SINGLE_L1_NICHES:
            errors.append(f"{code}: tag {tname!r} is a forbidden niche -> map to {len(valid_l1)} L1 or {len(valid_dyn)} canonical groups")
        elif any(m in tname for m in MA_FORBIDDEN_IN_DYNAMIC):
            errors.append(f"{code}: tag {tname!r} is M&A -> move into ma_events with target_name")
        elif tname not in valid_tags:
            errors.append(
                f"{code}: tag {tname!r} not in {len(valid_tags)} canonical tags ({len(valid_l1)} L1 + {len(valid_dyn)} groups)"
            )
        else:
            seen_tags.add(tname)

        fdt = str(item.get("from_date") or "").strip()
        ev_str = str(item.get("evidence") or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fdt):
            errors.append(f"{code}: tags[{idx}] ({tname}) invalid from_date {fdt!r} (expect YYYY-MM-DD)")
        if not ev_str:
            errors.append(f"{code}: tags[{idx}] ({tname}) missing evidence")

    mas = rec.get("ma_events")
    if not isinstance(mas, list):
        errors.append(f"{code}: ma_events must be list")
        mas = []
    for idx, item in enumerate(mas):
        if not isinstance(item, dict):
            errors.append(f"{code}: ma_events[{idx}] not dict")
            continue
        if item.get("event_type") not in valid_ma_types:
            errors.append(f"{code}: ma_events[{idx}] invalid event_type {item.get('event_type')!r}")
        if item.get("status") in ("已完成", "已终止"):
            errors.append(
                f"{code}: ma_events[{idx}] status {item.get('status')!r} forbidden (已完成->tags, 已终止->omit)"
            )
        tname = str(item.get("target_name") or "").strip()
        if not tname:
            errors.append(f"{code}: ma_events[{idx}] missing target_name (must state restructuring target!)")
        elif len(tname) > 45:
            errors.append(f"{code}: ma_events[{idx}] target_name too long: {tname[:25]}...")
        tl1 = item.get("target_l1")
        if tl1 is not None and tl1 != "" and tl1 not in valid_l1:
            errors.append(f"{code}: ma_events[{idx}] invalid target_l1 {tl1!r}")
        if not str(item.get("from_date") or "").strip():
            errors.append(f"{code}: ma_events[{idx}] missing from_date")
        if not str(item.get("evidence") or "").strip():
            errors.append(f"{code}: ma_events[{idx}] missing evidence")

    return errors
