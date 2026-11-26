"""Pure-stdlib shared taxonomy, normalization, and strict record validator for Super-Board."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
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
    "储能",
    "智能驾驶",
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
    "游戏",
    "影视",
    "风电",
    "核电",
    "特高压",
    "智能电网",
    "国产替代/信创",
    "国产替代",
    "信创",
    "自主可控",
    "端侧AI",
    "数据要素",
    "数字货币",
    "大飞机",
    "3D打印",
    "中日韩贸易",
    "字节链",
    "阿里链",
}


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
    min_dynamic_date: str | None = None,
) -> list[str]:
    errors: list[str] = []
    cutoff = min_dynamic_date or (datetime.now().date() - timedelta(days=366)).isoformat()
    valid_l1 = set(taxonomy["l1_list"])
    valid_prov = set(taxonomy["provinces"])
    valid_ctrl = set(taxonomy["controller_types"])
    valid_dyn = set(taxonomy["dynamic_groups"])
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

    stags = rec.get("static_tags")
    if not isinstance(stags, list) or not stags:
        errors.append(f"{code}: static_tags must be non-empty list")
        stags = []
    elif len(stags) > 4:
        errors.append(f"{code}: static_tags count={len(stags)} > 4 limit")

    seen_l1: set[str] = set()
    for idx, item in enumerate(stags):
        if not isinstance(item, dict):
            errors.append(f"{code}: static_tags[{idx}] not dict")
            continue
        l1 = item.get("l1")
        if l1 not in valid_l1:
            errors.append(f"{code}: static_tags[{idx}] invalid l1 {l1!r} (only 25 L1 allowed)")
        elif l1 in seen_l1:
            errors.append(f"{code}: duplicate static l1 {l1!r} (each L1 must appear at most once)")
        else:
            seen_l1.add(l1)
        ev_txt = str(item.get("evidence") or "").strip()
        if not ev_txt:
            errors.append(f"{code}: static_tags[{idx}] missing evidence")
        pct = item.get("revenue_pct")
        if not isinstance(pct, (int, float)) or isinstance(pct, bool) or float(pct) <= 0:
            errors.append(
                f"{code}: static_tags[{idx}] ({l1}) requires revenue_pct > 0 (if <5% hot side business, move to dynamic_tags or delete)"
            )
        elif float(pct) < 5.0 and not re.search(r"(?:[2-9](?:\.\d+)?|[1-9]\d+(?:\.\d+)?)\s*亿", ev_txt):
            errors.append(
                f"{code}: static_tags[{idx}] ({l1}) revenue_pct={pct}% < 5% without >=2亿元 evidence (move to dynamic_tags or delete)"
            )

    dtags = rec.get("dynamic_tags")
    if not isinstance(dtags, list):
        errors.append(f"{code}: dynamic_tags must be list")
        dtags = []
    active_dyn = 0
    for idx, item in enumerate(dtags):
        if not isinstance(item, dict):
            errors.append(f"{code}: dynamic_tags[{idx}] not dict")
            continue
        gname = str(item.get("group_name") or "").strip()
        if not gname:
            errors.append(f"{code}: dynamic_tags[{idx}] missing group_name")
        elif len(gname) > 20:
            errors.append(f"{code}: dynamic_tags[{idx}] group_name too long: {gname[:20]}...")
        elif gname in seen_l1:
            errors.append(f"{code}: dynamic group_name {gname!r} duplicates own static_tags L1")
        elif gname in FORBIDDEN_SINGLE_L1_NICHES:
            errors.append(f"{code}: dynamic group_name {gname!r} is a forbidden single-L1 niche -> use 25 L1 or canonical dynamic_groups")
        elif any(m in gname for m in MA_FORBIDDEN_IN_DYNAMIC):
            errors.append(f"{code}: dynamic group_name {gname!r} is M&A -> move into ma_events with target_name")
        elif gname not in valid_dyn and gname not in valid_l1 and not gname.endswith("字辈"):
            errors.append(
                f"{code}: dynamic group_name {gname!r} not in canonical dynamic_groups or 25 L1 -> standardize or delete"
            )
        fdt = str(item.get("from_date") or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fdt):
            errors.append(f"{code}: dynamic_tags[{idx}] invalid from_date {fdt!r} (expect YYYY-MM-DD)")
        elif not item.get("to_date") and fdt < cutoff:
            errors.append(
                f"{code}: dynamic_tags[{idx}] ({gname}) from_date={fdt} < 1-year cutoff {cutoff} (update recent evidence date or remove stale tag)"
            )
        if not str(item.get("evidence") or "").strip():
            errors.append(f"{code}: dynamic_tags[{idx}] missing evidence")
        if not item.get("to_date"):
            active_dyn += 1
    if active_dyn > 4:
        errors.append(f"{code}: active dynamic_tags count={active_dyn} > 4 limit")

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
                f"{code}: ma_events[{idx}] status {item.get('status')!r} forbidden (已完成->static_tags, 已终止->omit)"
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
