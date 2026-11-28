"""Shared pure-stdlib driver attribution, candidate resolution, and main-business rules."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date as dt_date, timedelta
from pathlib import Path
from typing import Any

from common import (
    extract_intrinsic_tags,
    is_intrinsic_tag,
    is_region_tag,
    is_zibei_tag,
    tag_is_active,
)

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_PATH = ROOT / "taxonomy.json"


def load_vocab(taxonomy_path: Path = TAXONOMY_PATH) -> list[str]:
    doc = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    out: list[str] = []
    seen: set[str] = set()
    for t in [*doc.get("l1_list", []), *doc.get("dynamic_groups", [])]:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


VOCAB: list[str] = load_vocab()
VOCAB_SET: set[str] = set(VOCAB)

_N_DAY_M_BOARD_RE = re.compile(r"(\d+)天(\d+)板")


def is_event_theme(tag: str | None) -> bool:
    """True for AI-surfaced event/intrinsic themes: XX字辈, province/core-city regions, 国企改革, or policy-wave 并购."""
    s = str(tag or "").strip()
    if s in ("并购", "国企改革"):
        return True
    if s.endswith("字辈") and len(s) >= 3:
        return True
    if is_region_tag(s):
        return True
    return False


def format_region(
    province: str | None,
    city: str | None = None,
    controller_province: str | None = None,
) -> str:
    """Compact human-readable region string for AI workflows (e.g. '浙江省·杭州市', '上海市')."""
    prov = str(province or "").strip()
    cty = str(city or "").strip()
    cprov = str(controller_province or "").strip()
    parts: list[str] = []
    if prov:
        parts.append(prov)
    if cty and cty != prov:
        parts.append(cty)
    base = "·".join(parts)
    if cprov and cprov != prov:
        return f"{base}({cprov}国资)" if base else f"{cprov}国资"
    return base


def is_fanbao_stock(is_fanbao: int | bool | None, boards_desc: str | None) -> bool:
    """True for any rebound/wave stock (is_fanbao=1 or N天M板), regardless of current consecutive height."""
    if bool(is_fanbao):
        return True
    if boards_desc and _N_DAY_M_BOARD_RE.search(str(boards_desc)):
        return True
    return False


def is_core_stock(height: int | None, is_fanbao: int | bool | None, boards_desc: str | None) -> bool:
    """True for consecutive boards (>=2B) and rebound/fanbao stocks (is_fanbao=1 or N天M板)."""
    return int(height or 1) >= 2 or is_fanbao_stock(is_fanbao, boards_desc)


def fanbao_board_count(boards_desc: str | None) -> int:
    """Extract M from 'N天M板' for sorting fanbao stocks."""
    if not boards_desc:
        return 1
    m = _N_DAY_M_BOARD_RE.search(str(boards_desc))
    return int(m.group(2)) if m else 1


def collect_active_event_lines(
    hot_news: list[dict[str, Any]],
    recent_event_lines: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Collect active temporary event lines (XX字辈 / XX本地) directly from AI hot_news + recent active memory.

    AI handles discovery and matching (including multi-char names, homophones, zodiacs, and
    news-backed regions); this function only passes through validated AI outputs.
    """
    out: dict[str, dict[str, Any]] = {}
    for nw in hot_news:
        th = str(nw.get("theme") or "").strip()
        if not is_event_theme(th):
            continue
        hl = str(nw.get("headline") or "").strip()
        codes = [str(c).strip() for c in (nw.get("codes") or []) if str(c).strip()]
        if th in out:
            out[th]["codes"] = sorted(set(out[th]["codes"]) | set(codes))
            if not out[th]["evidence"] and hl:
                out[th]["evidence"] = hl
        else:
            out[th] = {"codes": sorted(set(codes)), "evidence": hl, "source": "today_news"}

    for th, info in (recent_event_lines or {}).items():
        if not is_event_theme(th) or th in out:
            continue
        out[th] = {
            "codes": sorted(set(info.get("codes") or [])),
            "evidence": str(info.get("evidence") or f"延续近3日活跃暗线：{th}"),
            "source": "recent_active",
        }

    return out


def candidates(
    conn: sqlite3.Connection,
    code: str,
    trade_date: str,
    *,
    include_intrinsic: bool = True,
) -> list[str]:
    """Return ordered valid candidate tags for a stock (stock_tags + ma_events.target_l1 + permanent intrinsic 字辈/地域)."""
    rows = conn.execute(
        """
        SELECT tag, from_date, evidence FROM stock_tags
        WHERE code = ?
        ORDER BY id ASC
        """,
        (code,),
    ).fetchall()

    out: list[str] = []
    seen: set[str] = set()
    for t_raw, fdt, ev in rows:
        if not tag_is_active(fdt, ev, trade_date):
            continue
        t = str(t_raw or "").strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)

    ma_rows = conn.execute(
        """
        SELECT DISTINCT target_l1 FROM ma_events
        WHERE code = ? AND target_l1 IS NOT NULL AND target_l1 != ''
        ORDER BY from_date DESC, id ASC
        """,
        (code,),
    ).fetchall()
    for (tl1,) in ma_rows:
        t = str(tl1 or "").strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)

    if include_intrinsic:
        meta = conn.execute(
            "SELECT name, province, city, controller_province, controller_type FROM stocks WHERE code = ?",
            (code,),
        ).fetchone()
        if meta:
            for itag, _ in extract_intrinsic_tags(code, meta[0], meta[1], meta[2], meta[3], meta[4]):
                if itag not in seen:
                    seen.add(itag)
                    out.append(itag)
        else:
            prow = conn.execute(
                "SELECT name FROM daily_limit_pool WHERE code = ? ORDER BY trade_date DESC LIMIT 1",
                (code,),
            ).fetchone()
            if prow and prow[0]:
                for itag, _ in extract_intrinsic_tags(code, prow[0]):
                    if itag not in seen:
                        seen.add(itag)
                        out.append(itag)
    return out


# Ordered keyword substring rules mapping EastMoney industry ("L1-L2-L3") to 23 canonical L1 sectors
MAIN_BIZ_RULES: list[tuple[tuple[str, ...], str]] = [
    (("机器人", "机床"), "机器人"),
    (("半导体", "集成电路", "光学元件", "LED", "显示器件"), "芯片"),
    (("通信设备", "通信运营", "卫星应用", "电子元件", "其他电子器件"), "通信"),
    (("消费电子",), "通信"),
    (("电子设备制造",), "机器人"),
    (("计算机硬件", "云服务"), "算力"),
    (("计算机软件", "互联网服务", "IT服务", "教育信息化"), "AI应用"),
    (("互联网金融", "金融", "证券", "保险"), "金融"),
    (("互联网商务", "网上购物", "电子商务", "跨境电商"), "消费"),
    (
        (
            "文化传媒",
            "网络媒体",
            "影视",
            "动漫",
            "平面媒体",
            "广播电视",
            "有线电视",
            "网络电视",
            "营销服务",
            "在线教育",
            "幼儿教育",
            "成人教育",
            "游戏",
        ),
        "AI应用",
    ),
    (("轨道交通", "铁路设备", "高速公路", "工程机械"), "基建"),
    (("港口航运", "航运", "港口", "国际贸易"), "航运物流"),
    (("快递", "物流"), "航运物流"),
    (("航空", "机场", "公交"), "消费"),
    (("乘用车", "商用车", "汽车", "摩托车"), "汽车链"),
    (("其他交运设备",), "机械设备"),
    (("国防与装备", "航天装备", "航空装备", "地面装备", "船舶", "海洋工程"), "军工"),
    (("太阳能", "储能", "电池"), "锂电光伏"),
    (("电力", "输变电", "电机", "电气"), "电力"),
    (("燃气", "石油"), "油气"),
    (("煤炭", "焦炭"), "煤炭"),
    (("环保", "水务"), "环保"),
    (("楼宇设备",), "地产链"),
    (("机械设备",), "机械设备"),
    (("交通运输",), "航运物流"),
    (("基础化工",), "化工"),
    (("有色金属", "铁矿石", "钢铁", "特钢"), "有色"),
    (("医药生物",), "医药"),
    (("家具", "装修装饰", "建筑装饰设计", "陶瓷", "房地产", "玻璃"), "地产链"),
    (("食品饮料", "商贸零售", "家电", "纺织服装", "轻工制造", "休闲", "美容"), "消费"),
    (("农林牧渔",), "农业"),
    (("建筑", "建材"), "基建"),
]


def map_industry_to_l1(em_industry: str | None) -> str | None:
    if not em_industry:
        return None
    text = str(em_industry).strip()
    for kws, l1 in MAIN_BIZ_RULES:
        if any(k in text for k in kws):
            return l1
    return None


def main_business(em_industry: str | None, own_tags: list[str] | None = None) -> str:
    """Resolve a stock's main business L1, strictly respecting verified stock_tags over stale em_industry."""
    industry_tags = [t for t in (own_tags or []) if t and not is_intrinsic_tag(t)]
    mapped = map_industry_to_l1(em_industry)
    if mapped and (not industry_tags or mapped in industry_tags):
        return mapped
    if industry_tags:
        return industry_tags[0]
    if own_tags:
        return own_tags[0]
    return ""


_STOP_TOKENS = {
    "公司", "主要", "主营", "业务", "产品", "服务", "系统", "设备", "材料", "技术",
    "项目", "市场", "客户", "领域", "相关", "行业", "平台", "建设", "运营", "开发",
    "研发", "生产", "制造", "销售", "应用", "解决", "方案", "提供", "包括", "以及",
    "进行", "开展", "形成", "实现", "推进", "布局", "拓展", "用于", "属于", "方面",
    "半年", "年报", "公告", "互动", "回复", "报告", "披露", "表示", "显示", "记录",
    "全资", "子公", "控股", "参股", "股东", "投资", "设立", "合作", "协议", "战略",
    "万元", "亿元", "占比", "比例", "增长", "同比", "收入", "营收", "营业", "国内",
    "国际", "全球", "中国", "国家", "有限", "股份", "集团", "科技", "电子", "智能",
}


def _extract_domain_tokens(evidence: str) -> list[str]:
    if not evidence:
        return []
    tokens: list[str] = []
    seen: set[str] = set()
    # ASCII/alphanumeric terms (e.g. PCB, CPO, HBM, AIDC, AI, 5G, 6G, GPU, IGBT)
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9\-]{1,10}|[456]G", evidence):
        tok = m.group(0).upper()
        if tok not in seen and tok not in {"CO", "LTD", "INC"}:
            seen.add(tok)
            tokens.append(tok)
    # 2~5 char Chinese phrases between punctuation, avoiding generic boilerplate
    for seg in re.split(r"[，。；、：（）()《》“”\"'/\s]+", evidence):
        seg = seg.strip()
        if not seg:
            continue
        for m in re.finditer(r"[\u4e00-\u9fa5]{2,6}", seg):
            w = m.group(0)
            if len(w) <= 5 and w not in _STOP_TOKENS and w not in seen:
                seen.add(w)
                tokens.append(w)
            elif len(w) > 5:
                for n in (4, 3, 2):
                    for i in range(0, len(w) - n + 1):
                        sub = w[i : i + n]
                        if sub not in _STOP_TOKENS and sub not in seen:
                            seen.add(sub)
                            tokens.append(sub)
    return tokens


def rule_driver(
    cands: list[str],
    evidences_by_tag: dict[str, str],
    news_text: str,
    same_tag_counts: dict[str, int],
    prev_driver: str | None,
    height: int,
) -> str | None:
    """Deterministic fallback driver selector (zero kpl usage)."""
    if not cands:
        return None
    if height >= 2 and prev_driver and prev_driver in cands:
        return prev_driver

    # Rule fallback prefers real industry/cross-sector tags over passive permanent 字辈/地域
    pool_cands = [t for t in cands if not is_intrinsic_tag(t)] or list(cands)
    news_upper = (news_text or "").upper()
    cand_order = {t: idx for idx, t in enumerate(pool_cands)}
    if news_upper:
        best_t = None
        best_key: tuple[int, int, int] = (0, 0, 0)
        for t in pool_cands:
            ev = evidences_by_tag.get(t, "")
            toks = _extract_domain_tokens(ev)
            hits = sum(1 for tok in toks if tok in news_upper)
            if t in news_upper:
                hits += 2
            if hits > 0:
                key = (hits, same_tag_counts.get(t, 0), -cand_order[t])
                if key > best_key:
                    best_key = key
                    best_t = t
        if best_t:
            return best_t

    return max(pool_cands, key=lambda t: (same_tag_counts.get(t, 0), -cand_order[t]))
