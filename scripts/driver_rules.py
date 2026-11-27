"""Shared pure-stdlib driver attribution, candidate resolution, and main-business rules."""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date as dt_date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_PATH = ROOT / "taxonomy.json"


def load_vocab(taxonomy_path: Path = TAXONOMY_PATH) -> list[str]:
    doc = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    out: list[str] = []
    seen: set[str] = set()
    for t in [*doc.get("l1_list", []), *doc.get("dynamic_groups", []), "并购"]:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


VOCAB: list[str] = load_vocab()
VOCAB_SET: set[str] = set(VOCAB)

_N_DAY_M_BOARD_RE = re.compile(r"(\d+)天(\d+)板")
_NAME_LINE_RE = re.compile(r'[“"「]([\u4e00-\u9fa5]{1,2})[”"」]字|([\u4e00-\u9fa5])字辈')


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


def detect_dynamic_name_lines(
    core_stocks: list[dict[str, Any]],
    hot_news: list[dict[str, Any]],
) -> dict[str, tuple[set[str], str]]:
    """Detect active XX字辈 dynamic groupings strictly from today's hot news (no blind char-matching).

    Returns {zb_tag: (matched_core_codes, evidence_text)}.
    """
    out: dict[str, tuple[set[str], str]] = {}

    def _clean_nm(s: str) -> str:
        s = str(s or "").strip()
        for pref in ("*ST", "ST", "XD", "XR", "DR"):
            if s.startswith(pref) and len(s) > len(pref):
                s = s[len(pref) :]
        return s

    # Strictly hot-news-backed XX字辈 (e.g. 金字辈, 华字辈, 牛字辈, 羊字辈)
    for nw in hot_news:
        th = str(nw.get("theme") or "").strip()
        hl = str(nw.get("headline") or "").strip()
        dt = str(nw.get("detail") or "").strip()
        zb_tag = ""
        if th.endswith("字辈") and len(th) >= 3:
            zb_tag = th
        else:
            m = _NAME_LINE_RE.search(f"{hl} {dt}")
            if m:
                ch = m.group(1) or m.group(2)
                if ch and len(ch) == 1:
                    zb_tag = f"{ch}字辈"
        if not zb_tag:
            continue

        prefix = zb_tag[:-2]
        trigger_chars = ("羊", "洋", "阳", "杨", "扬") if zb_tag == "羊字辈" else (prefix,)
        nw_codes = {str(c) for c in (nw.get("codes") or [])}
        matched: set[str] = set()
        for st in core_stocks:
            nm = _clean_nm(st.get("name", ""))
            if any(ch in nm for ch in trigger_chars) or st["code"] in nw_codes:
                matched.add(st["code"])
        if matched:
            prev_codes, prev_ev = out.get(zb_tag, (set(), hl))
            out[zb_tag] = (prev_codes | matched, prev_ev or hl)

    return out


def candidates(conn: sqlite3.Connection, code: str, trade_date: str) -> list[str]:
    """Return ordered valid candidate tags for a stock on trade_date (365-day window + M&A)."""
    cutoff = ""
    if trade_date and len(trade_date) >= 10:
        cutoff = (dt_date.fromisoformat(trade_date[:10]) - timedelta(days=365)).isoformat()

    if cutoff:
        rows = conn.execute(
            """
            SELECT tag FROM stock_tags
            WHERE code = ? AND from_date >= ?
            ORDER BY id ASC
            """,
            (code, cutoff),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT tag FROM stock_tags
            WHERE code = ?
            ORDER BY id ASC
            """,
            (code,),
        ).fetchall()

    out: list[str] = []
    seen: set[str] = set()
    for r in rows:
        t = str(r[0] or "").strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)

    has_ma = conn.execute(
        "SELECT 1 FROM ma_events WHERE code = ? LIMIT 1", (code,)
    ).fetchone()
    if has_ma and "并购" not in seen:
        out.append("并购")
    return out


# Ordered keyword substring rules mapping EastMoney industry ("L1-L2-L3") to 25 canonical L1 sectors
MAIN_BIZ_RULES: list[tuple[tuple[str, ...], str]] = [
    (("机器人",), "机器人"),
    (("半导体", "集成电路"), "芯片"),
    (("光学元件", "LED", "消费电子", "显示器件", "电子设备制造", "其他电子器件"), "消费电子"),
    (("通信设备", "通信运营", "卫星应用", "电子元件"), "通信"),
    (("计算机硬件", "云服务"), "算力"),
    (("计算机软件", "互联网服务", "IT服务", "教育信息化"), "AI应用"),
    (("互联网金融", "金融", "证券", "保险"), "金融"),
    (("互联网商务", "网上购物", "电子商务"), "消费"),
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
        "传媒",
    ),
    (("轨道交通", "铁路设备"), "交运"),
    (("汽车", "摩托车"), "汽车"),
    (("其他交运设备",), "消费"),
    (("国防与装备", "航天装备", "航空装备", "地面装备", "船舶", "海洋工程"), "军工"),
    (("太阳能",), "光伏"),
    (("储能", "电池"), "锂电"),
    (("电力", "输变电", "电机", "电气"), "电力"),
    (("燃气", "石油"), "石油"),
    (("煤炭", "焦炭"), "煤炭"),
    (("环保", "水务"), "环保"),
    (("机械设备",), "工业设备"),
    (("交通运输",), "交运"),
    (("基础化工",), "化工"),
    (("有色金属", "铁矿石"), "有色"),
    (("医药生物",), "医药"),
    (("食品饮料", "商贸零售", "家电", "纺织服装", "轻工制造", "休闲", "美容"), "消费"),
    (("农林牧渔",), "农业"),
    (("房地产",), "地产"),
    (("建筑", "建材", "钢铁"), "基建"),
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
    """Resolve a stock's main business L1 from em_industry, falling back to own_tags[0]."""
    mapped = map_industry_to_l1(em_industry)
    if mapped:
        return mapped
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

    news_upper = (news_text or "").upper()
    cand_order = {t: idx for idx, t in enumerate(cands)}
    if news_upper:
        best_t = None
        best_key: tuple[int, int, int] = (0, 0, 0)
        for t in cands:
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

    return max(cands, key=lambda t: (same_tag_counts.get(t, 0), -cand_order[t]))
