"""Lightweight stdlib HTTP server & JSON serializer for Super-Board Mobile Web UI."""
from __future__ import annotations

import argparse
import gzip
import http.client
import json
import mimetypes
import re
import socket
import sqlite3
import threading
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date as dt_date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from common import (
    CLASSIC_ZIBEI_ORDER,
    extract_intrinsic_tags,
    is_intrinsic_tag,
    is_region_tag,
    is_zibei_tag,
    tag_is_active,
)
from driver_rules import TAXONOMY_PATH, VOCAB_SET, fanbao_board_count, is_core_stock, is_event_theme, is_fanbao_stock, main_business, rule_driver

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data/super_board.sqlite"
WEB_DIR = ROOT / "web"
ULTRA_BOARD_RAW = Path(r"C:\Ai\Ultra-Board\data\kaipanla\raw")
MOOD_CACHE_PATH = ROOT / "data/market_mood_cache.json"
KLINE_DIR = ROOT / "data/raw_kline"
INDEX_KLINE_PATH = ROOT / "data/index_kline.json"
INTRADAY_DIR = ROOT / "data/raw_intraday"
INTRADAY_DAYS_DIR = ROOT / "data/intraday_days"
SHARES_CACHE_PATH = ROOT / "data/shares_cache.json"
_MOOD_CACHE: dict[str, dict[str, Any]] | None = None
_DAY_DISPLAY_CACHE: dict[str, dict[str, list[str]]] = {}
_DAY_THEME_STATS_CACHE: dict[str, dict[str, tuple[int, int]]] = {}
_KLINE_CACHE: dict[str, tuple[list[str], list[float], dict[str, int]]] = {}
_INDEX_KLINE_CACHE: dict[str, dict[str, float]] | None = None
_INTRADAY_MEM_CACHE: dict[tuple[str, str], tuple[dict[str, Any], bytes, bytes]] = {}
_INTRADAY_DAY_CACHE: dict[str, tuple[float, int, dict[str, Any], bytes, bytes]] = {}
_INTRADAY_INFLIGHT: dict[tuple[str, str], threading.Event] = {}
_SHARES_CACHE: dict[str, dict[str, float]] | None = None
_INTRADAY_LOCK = threading.Lock()
_LIVE_POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="intraday-live")
_BG_WARM_POOL = ThreadPoolExecutor(max_workers=12, thread_name_prefix="intraday-warm")
_INTRADAY_TLS = threading.local()
_WARMED_INTRADAY_DATES: set[str] = set()
_DAY_CORE_CODES_CACHE: dict[str, list[str]] = {}
_CODE_RE = re.compile(r"^\d{6}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SEARCH_INDEX_CACHE: dict[str, Any] | None = None
_DATES_CACHE: list[dict[str, Any]] | None = None
_DAY_JSON_CACHE: dict[str, tuple[bytes, bytes]] = {}
_SEARCH_JSON_CACHE: tuple[bytes, bytes] | None = None
_DATES_JSON_CACHE: tuple[bytes, bytes] | None = None
_DB_CACHE_MTIME: float = -1.0
_CACHE_LOCK = threading.Lock()
_N_DAY_RE = re.compile(r"(\d+)天(\d+)板")
STOCK_SHARD_COUNT = 16
MIN_DISPLAY_DATE = "2025-10-01"


def _ensure_cache_fresh() -> None:
    global _DB_CACHE_MTIME, _DATES_CACHE, _DATES_JSON_CACHE, _SEARCH_INDEX_CACHE, _SEARCH_JSON_CACHE
    try:
        mtime = DB_PATH.stat().st_mtime
    except OSError:
        return
    if mtime == _DB_CACHE_MTIME:
        return
    with _CACHE_LOCK:
        if mtime == _DB_CACHE_MTIME:
            return
        _DB_CACHE_MTIME = mtime
        _DATES_CACHE = None
        _DATES_JSON_CACHE = None
        _SEARCH_INDEX_CACHE = None
        _SEARCH_JSON_CACHE = None
        _DAY_JSON_CACHE.clear()
        _DAY_DISPLAY_CACHE.clear()
        _DAY_THEME_STATS_CACHE.clear()


def _encode_json_pair(payload: Any) -> tuple[bytes, bytes]:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    gz = gzip.compress(raw, compresslevel=5) if len(raw) >= 512 else b""
    return raw, gz


def _get_cached_dates_pair() -> tuple[bytes, bytes]:
    global _DATES_CACHE, _DATES_JSON_CACHE
    _ensure_cache_fresh()
    if _DATES_JSON_CACHE is not None:
        return _DATES_JSON_CACHE
    dates = get_available_dates()
    pair = _encode_json_pair({"dates": dates})
    with _CACHE_LOCK:
        _DATES_CACHE = dates
        _DATES_JSON_CACHE = pair
    return pair


def _extract_day_core_codes(payload: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    codes: list[str] = []
    for tier in payload.get("ladder") or []:
        for c in tier.get("codes") or []:
            if c and c not in seen:
                seen.add(c)
                codes.append(c)
    for c in payload.get("fanbao_boards") or []:
        if c and c not in seen:
            seen.add(c)
            codes.append(c)
    for b in payload.get("broken_boards") or []:
        c = b.get("code")
        if c and c not in seen:
            seen.add(c)
            codes.append(c)
    return codes


def _get_cached_day_pair(date: str | None) -> tuple[bytes, bytes]:
    _ensure_cache_fresh()
    key = date or "__latest__"
    cached = _DAY_JSON_CACHE.get(key)
    if cached is not None:
        actual_dt = date or (_DATES_CACHE[0]["date"] if _DATES_CACHE else "")
        if actual_dt and actual_dt in _DAY_CORE_CODES_CACHE:
            _warm_day_intraday_async(actual_dt, _DAY_CORE_CODES_CACHE[actual_dt])
        return cached
    payload = get_day_payload(date)
    pair = _encode_json_pair(payload)
    actual_dt = payload.get("date")
    core_codes = _extract_day_core_codes(payload)
    with _CACHE_LOCK:
        if len(_DAY_JSON_CACHE) >= 120:
            _DAY_JSON_CACHE.pop(next(iter(_DAY_JSON_CACHE)))
        _DAY_JSON_CACHE[key] = pair
        if actual_dt:
            _DAY_CORE_CODES_CACHE[actual_dt] = core_codes
            if actual_dt != key:
                _DAY_JSON_CACHE[actual_dt] = pair
    if actual_dt and core_codes:
        _warm_day_intraday_async(actual_dt, core_codes)
    return pair


def _get_cached_search_pair() -> tuple[bytes, bytes]:
    global _SEARCH_JSON_CACHE
    _ensure_cache_fresh()
    if _SEARCH_JSON_CACHE is not None:
        return _SEARCH_JSON_CACHE
    pair = _encode_json_pair(get_search_index())
    with _CACHE_LOCK:
        _SEARCH_JSON_CACHE = pair
    return pair


def _warm_server_cache() -> None:
    """Warm latest trading days, search index, and latest day's intraday charts in background."""
    try:
        _get_cached_dates_pair()
        dates = _DATES_CACHE or []
        for idx, d in enumerate(dates[:4]):
            dt = d["date"]
            _get_cached_day_pair(dt)
            if idx < 3 and dt in _DAY_CORE_CODES_CACHE:
                _warm_day_intraday_async(dt, _DAY_CORE_CODES_CACHE[dt])
        _get_cached_search_pair()
    except Exception:
        pass

THEME_ACCENTS: dict[str, str] = {
    "商业航天": "coral",
    "AI应用": "amber",
    "机器人": "cyan",
    "算力": "blue",
    "芯片": "indigo",
    "航运物流": "blue",
    "汽车链": "sky",
    "机械设备": "ochre",
    "海洋经济": "teal",
    "消费": "rose",
    "并购": "violet",
    "通信": "violet",
    "华为链": "sky",
    "国产替代/信创": "sky",
    "军工": "emerald",
    "化工": "ochre",
    "油气": "ochre",
    "医药": "mint",
    "电力": "lime",
    "有色": "amber",
    "锂电光伏": "teal",
    "智能驾驶": "cyan",
    "低空经济": "coral",
    "氢能源": "emerald",
    "量子科技": "violet",
    "脑机接口": "cyan",
    "海峡两岸": "coral",
    "冰雪经济": "sky",
    "端侧AI": "cyan",
    "国企改革": "amber",
    "地产链": "ochre",
}

NEWS_EVENT_SHORT_TITLES: list[tuple[str, str, str]] = [
    ("“金”字", "金字辈", "amber"),
    ("金字辈", "金字辈", "amber"),
    ("字辈", "字辈暗线", "amber"),
    ("羊年", "羊年暗线", "amber"),
    ("生肖", "生肖暗线", "amber"),
    ("国企改革", "国企改革", "amber"),
    ("并购", "并购", "violet"),
    ("股权转让", "并购", "violet"),
    ("要约", "并购", "violet"),
    ("端侧", "端侧AI", "cyan"),
    ("AI眼镜", "端侧AI", "cyan"),
    ("AI手机", "端侧AI", "cyan"),
    ("AI玩具", "端侧AI", "cyan"),
    ("SpaceX", "商业航天", "coral"),
    ("卫星", "商业航天", "coral"),
    ("航天", "商业航天", "coral"),
    ("神舟", "商业航天", "coral"),
    ("舰载机", "商业航天", "coral"),
    ("航展", "军工", "emerald"),
    ("宇树", "机器人", "cyan"),
    ("具身", "机器人", "cyan"),
    ("机器人", "机器人", "cyan"),
    ("PCB", "通信", "violet"),
    ("覆铜板", "通信", "violet"),
    ("电子铜箔", "通信", "violet"),
    ("大模型", "AI应用", "amber"),
    ("云计算", "AI应用", "amber"),
    ("HBM", "芯片", "indigo"),
    ("封装", "芯片", "indigo"),
    ("存储", "芯片", "indigo"),
    ("光刻", "芯片", "indigo"),
    ("芯片", "芯片", "indigo"),
    ("算力", "算力", "blue"),
    ("华为", "华为链", "sky"),
    ("海洋", "海洋经济", "teal"),
    ("冰雪", "冰雪经济", "sky"),
    ("灵顺寺", "消费", "rose"),
    ("零售", "消费", "rose"),
    ("平准", "平准稳市", "coral"),
    ("稳市", "平准稳市", "coral"),
    ("回购", "回购催化", "amber"),
    ("关税", "贸易催化", "ochre"),
    ("301", "贸易催化", "ochre"),
    ("摘帽", "摘帽复牌", "mint"),
    ("ST", "摘帽复牌", "mint"),
]

PROVINCE_SHORT = {
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


def _short_prov(prov: str | None) -> str:
    if not prov:
        return ""
    if prov in PROVINCE_SHORT:
        return PROVINCE_SHORT[prov]
    return prov.replace("省", "").replace("市", "")


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    s = re.sub(r"\s+", " ", str(text)).strip()
    return s


def _accent_for(theme: str) -> str:
    if theme in THEME_ACCENTS:
        return THEME_ACCENTS[theme]
    if theme.endswith("字辈"):
        return "amber"
    if is_region_tag(theme):
        return "coral"
    return "slate"


def _load_kline(code: str) -> tuple[list[str], list[float], dict[str, int]] | None:
    if code in _KLINE_CACHE:
        return _KLINE_CACHE[code]
    p = KLINE_DIR / f"{code}.json"
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        days = doc.get("days") or []
        dates = [str(d[0]) for d in days]
        closes = [float(d[1]) for d in days]
        idx_map = {dt: i for i, dt in enumerate(dates)}
        val = (dates, closes, idx_map)
        _KLINE_CACHE[code] = val
        return val
    except Exception:
        return None


def _compute_fanbao_gain_pct(
    conn: sqlite3.Connection, code: str, date: str, boards_desc: str | None
) -> float | None:
    """Compute cumulative % gain from pre-first-board close to trade_date close for a fanbao stock."""
    kl = _load_kline(code)
    if not kl:
        return None
    dates, closes, idx_map = kl
    cur_idx = idx_map.get(date)
    if cur_idx is None or cur_idx <= 0:
        return None

    m = _N_DAY_RE.search(str(boards_desc or ""))
    base_idx: int | None = None
    if m:
        n_days = int(m.group(1))
        if cur_idx - n_days >= 0:
            base_idx = cur_idx - n_days
    if base_idx is None:
        # Walk backwards across recent limit-up dates (gap <= 3 trading days) to find wave's first board
        lu_dates = [
            r[0]
            for r in conn.execute(
                "SELECT trade_date FROM daily_limit_pool WHERE code = ? AND trade_date < ? ORDER BY trade_date DESC LIMIT 12",
                (code, date),
            ).fetchall()
        ]
        wave_start_idx = cur_idx
        for ld in lu_dates:
            li = idx_map.get(ld)
            if li is not None and wave_start_idx - li <= 3:
                wave_start_idx = li
            else:
                break
        if wave_start_idx - 1 >= 0:
            base_idx = wave_start_idx - 1

    if base_idx is None or closes[base_idx] <= 0:
        return None
    return round((closes[cur_idx] / closes[base_idx] - 1.0) * 100.0, 1)


def _load_mood_cache() -> dict[str, dict[str, Any]]:
    global _MOOD_CACHE
    if _MOOD_CACHE is not None:
        return _MOOD_CACHE
    if MOOD_CACHE_PATH.exists():
        try:
            _MOOD_CACHE = json.loads(MOOD_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            _MOOD_CACHE = {}
    else:
        _MOOD_CACHE = {}
    return _MOOD_CACHE


def _save_mood_cache() -> None:
    if _MOOD_CACHE is None:
        return
    try:
        MOOD_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        MOOD_CACHE_PATH.write_text(
            json.dumps(_MOOD_CACHE, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        pass


def _get_day_mood(date: str, zt_count: int, fetch_remote: bool = True) -> dict[str, Any]:
    cache = _load_mood_cache()
    entry = dict(cache.get(date) or {})
    changed = False

    # Read-only lookup of local sentiment.json (never writes to Ultra-Board)
    if "sign" not in entry:
        for base in (ROOT / "data/market_raw", ULTRA_BOARD_RAW):
            sp = base / date / "sentiment.json"
            if sp.exists():
                try:
                    info = json.loads(sp.read_text(encoding="utf-8")).get("info") or {}
                    entry["sign"] = str(info.get("sign") or "")
                    entry["dt_count"] = int(info.get("SJDT") or info.get("DT") or 0)
                    entry["up_count"] = int(info.get("SZJS") or 0)
                    entry["down_count"] = int(info.get("XDJS") or 0)
                    changed = True
                    break
                except Exception:
                    pass

    # Fetch exact zhaban count from EastMoney ZBPool once and cache locally
    if "zb_count" not in entry and fetch_remote and date and len(date) == 10:
        dt_compact = date.replace("-", "")
        url = (
            "https://push2ex.eastmoney.com/getTopicZBPool"
            "?ut=7eea3edcaed734bea9cbfc24409ed989&dpt=wz.ztzt"
            f"&Pageindex=0&pagesize=1&sort=fbt%3Aasc&date={dt_compact}"
        )
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                tc = (data.get("data") or {}).get("tc")
                if tc is not None and int(tc) > 0:
                    entry["zb_count"] = int(tc)
                    changed = True
        except Exception:
            pass

    if changed:
        cache[date] = entry
        _save_mood_cache()

    zb = entry.get("zb_count")
    zb_rate = None
    if zb is not None and int(zb) > 0 and (zt_count + zb) > 0:
        zb_rate = round(zb * 100.0 / (zt_count + zb), 1)

    return {
        "zb_count": zb,
        "zhaban_rate": zb_rate,
        "dt_count": entry.get("dt_count"),
        "up_count": entry.get("up_count"),
        "down_count": entry.get("down_count"),
        "sign": entry.get("sign") or "",
    }


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_available_dates(limit: int = 1000) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        news_counts = {
            r["trade_date"]: r["cnt"]
            for r in conn.execute(
                "SELECT trade_date, COUNT(*) AS cnt FROM daily_hot_news GROUP BY trade_date"
            ).fetchall()
        }
        top_leaders_by_date: dict[str, list[dict[str, str]]] = defaultdict(list)
        top_leader_seen: dict[str, set[str]] = defaultdict(set)
        for r in conn.execute(
            """
            WITH mx AS (
                SELECT trade_date, MAX(board_height) AS mh
                FROM daily_limit_pool
                WHERE trade_date >= ?
                GROUP BY trade_date
            )
            SELECT d.trade_date,
                   d.code,
                   COALESCE(s.name, d.name) AS stock_name,
                   drv.driver AS drv_theme,
                   (SELECT tag FROM stock_tags t WHERE t.code = d.code ORDER BY t.id ASC LIMIT 1) AS first_tag,
                   (SELECT target_l1 FROM ma_events m WHERE m.code = d.code AND m.target_l1 IS NOT NULL AND m.target_l1 != '' ORDER BY m.from_date DESC, m.id ASC LIMIT 1) AS ma_l1,
                   s.em_industry AS em_industry
            FROM daily_limit_pool d
            JOIN mx ON d.trade_date = mx.trade_date AND d.board_height = mx.mh
            LEFT JOIN stocks s ON s.code = d.code
            LEFT JOIN daily_stock_driver drv ON drv.trade_date = d.trade_date AND drv.code = d.code
            ORDER BY d.trade_date DESC, d.is_one_word DESC, d.first_limit_time ASC, d.amount_yi DESC, d.code ASC
            """,
            (MIN_DISPLAY_DATE,),
        ).fetchall():
            td_k = r["trade_date"]
            code_k = r["code"]
            sname = _clean_text(r["stock_name"])
            if not sname or code_k in top_leader_seen[td_k]:
                continue
            top_leader_seen[td_k].add(code_k)
            theme_lbl = (
                _clean_text(r["drv_theme"])
                or _clean_text(r["first_tag"])
                or _clean_text(r["ma_l1"])
                or main_business(r["em_industry"], [])
            )
            top_leaders_by_date[td_k].append(
                {
                    "code": code_k,
                    "name": sname,
                    "theme": theme_lbl,
                }
            )

        rows = conn.execute(
            """
            SELECT
                d.trade_date,
                COUNT(*) AS total,
                SUM(CASE WHEN d.board_height >= 2 THEN 1 ELSE 0 END) AS multi,
                SUM(CASE WHEN d.is_one_word = 1 THEN 1 ELSE 0 END) AS one_word,
                MAX(d.board_height) AS max_height,
                SUM(CASE WHEN EXISTS(SELECT 1 FROM stocks s WHERE s.code = d.code) THEN 1 ELSE 0 END) AS tagged
            FROM daily_limit_pool d
            WHERE d.trade_date >= ?
            GROUP BY d.trade_date
            ORDER BY d.trade_date DESC
            LIMIT ?
            """,
            (MIN_DISPLAY_DATE, limit),
        ).fetchall()
        out = []
        for r in rows:
            td = r["trade_date"]
            tot = int(r["total"] or 0)
            leaders = top_leaders_by_date.get(td, [])
            out.append(
                {
                    "date": td,
                    "total": tot,
                    "multi": int(r["multi"] or 0),
                    "one_word": int(r["one_word"] or 0),
                    "max_height": int(r["max_height"] or 1),
                    "top_leaders": leaders[:3],
                    "top_leader_count": len(leaders),
                    "tagged": int(r["tagged"] or 0),
                    "news_count": int(news_counts.get(td, 0)),
                }
            )
        return out
    finally:
        conn.close()


def _query_in_chunks(
    conn: sqlite3.Connection, sql_template: str, codes: list[str], chunk_size: int = 500
) -> list[sqlite3.Row]:
    if not codes:
        return []
    out: list[sqlite3.Row] = []
    for i in range(0, len(codes), chunk_size):
        chunk = codes[i : i + chunk_size]
        ph = ",".join("?" * len(chunk))
        out.extend(conn.execute(sql_template.format(ph=ph), chunk).fetchall())
    return out


def _get_day_theme_stats(conn: sqlite3.Connection, dt: str) -> dict[str, tuple[int, int]]:
    """Return {theme: (zt_count, max_height)} for a trading day, with in-memory cache."""
    if dt in _DAY_THEME_STATS_CACHE:
        return _DAY_THEME_STATS_CACHE[dt]

    p_rows = conn.execute(
        "SELECT code, name, board_height FROM daily_limit_pool WHERE trade_date = ?",
        (dt,),
    ).fetchall()
    if not p_rows:
        _DAY_THEME_STATS_CACHE[dt] = {}
        return {}

    p_codes = [r["code"] for r in p_rows]
    h_by_code = {r["code"]: int(r["board_height"] or 1) for r in p_rows}
    name_by_code = {r["code"]: _clean_text(r["name"]) for r in p_rows}

    s_meta = {
        r["code"]: dict(r)
        for r in _query_in_chunks(
            conn,
            "SELECT code, name, province, city, controller_province, controller_type FROM stocks WHERE code IN ({ph})",
            p_codes,
        )
    }

    theme_codes: dict[str, set[str]] = defaultdict(set)
    for r in _query_in_chunks(
        conn,
        "SELECT code, tag, from_date, evidence FROM stock_tags WHERE code IN ({ph})",
        p_codes,
    ):
        if tag_is_active(r["from_date"], r["evidence"], dt):
            tg = _clean_text(r["tag"])
            if tg:
                theme_codes[tg].add(r["code"])

    for r in _query_in_chunks(
        conn,
        "SELECT code, target_l1 FROM ma_events WHERE code IN ({ph}) AND target_l1 IS NOT NULL AND target_l1 != ''",
        p_codes,
    ):
        tl1 = _clean_text(r["target_l1"])
        if tl1:
            theme_codes[tl1].add(r["code"])

    for r in conn.execute(
        "SELECT code, driver, driver2 FROM daily_stock_driver WHERE trade_date = ?",
        (dt,),
    ).fetchall():
        c = r["code"]
        if c in h_by_code:
            for t in (r["driver"], r["driver2"]):
                ts = _clean_text(t)
                if ts:
                    theme_codes[ts].add(c)

    for c in p_codes:
        m = s_meta.get(c)
        sname = (m.get("name") if m and m.get("name") else name_by_code.get(c)) or c
        for itag, _ in extract_intrinsic_tags(
            c,
            sname,
            m.get("province") if m else None,
            m.get("city") if m else None,
            m.get("controller_province") if m else None,
            m.get("controller_type") if m else None,
        ):
            theme_codes[itag].add(c)

    stats = {
        t: (len(cs), max((h_by_code.get(c, 1) for c in cs), default=1))
        for t, cs in theme_codes.items()
    }
    _DAY_THEME_STATS_CACHE[dt] = stats
    return stats


def _get_stock_day_pct(code: str, dt: str) -> float | None:
    """Compute exact daily close-to-close % change on `dt` from local raw_kline cache."""
    if not code or not dt:
        return None
    kl = _load_kline(code)
    if not kl:
        return None
    _, closes, idx_map = kl
    idx = idx_map.get(dt)
    if idx is None or idx <= 0:
        return None
    prev_close = closes[idx - 1]
    if prev_close <= 0:
        return None
    return round((closes[idx] / prev_close - 1.0) * 100.0, 2)


def _format_tier_shape(codes: list[str], raw_stocks: dict[str, dict[str, Any]]) -> str:
    """Build compact ladder skeleton string like '5·3·2×4' from multi-board codes."""
    counts: dict[int, int] = defaultdict(int)
    for c in codes:
        st = raw_stocks.get(c)
        if not st:
            continue
        h = int(st.get("height") or 0)
        if h >= 2:
            counts[h] += 1
    if not counts:
        return ""
    parts = []
    for h in sorted(counts.keys(), reverse=True):
        cnt = counts[h]
        parts.append(f"{h}×{cnt}" if cnt > 1 else f"{h}")
    return "·".join(parts)


def _calc_streak_days(trend: list[dict[str, Any]]) -> int:
    """Count consecutive trailing trading days (ending today) with active theme presence."""
    streak = 0
    for item in reversed(trend or []):
        if (item.get("zt") or 0) >= 2 or (item.get("h") or 0) >= 2:
            streak += 1
        else:
            break
    return streak


def _get_broken_boards(
    conn: sqlite3.Connection,
    prev_date: str | None,
    today_code_set: set[str],
    prev_display_map: dict[str, list[str]],
    cur_date: str = "",
) -> list[dict[str, Any]]:
    """Return stocks that had >=3 consecutive boards on prev_date but broke streak today, with today's % change."""
    if not prev_date:
        return []
    rows = conn.execute(
        """
        SELECT d.code,
               COALESCE(s.name, d.name) AS stock_name,
               d.board_height AS prev_height,
               drv.driver AS drv_theme,
               (SELECT tag FROM stock_tags t WHERE t.code = d.code ORDER BY t.id ASC LIMIT 1) AS first_tag,
               (SELECT target_l1 FROM ma_events m WHERE m.code = d.code AND m.target_l1 IS NOT NULL AND m.target_l1 != '' ORDER BY m.from_date DESC, m.id ASC LIMIT 1) AS ma_l1,
               s.em_industry AS em_industry
        FROM daily_limit_pool d
        LEFT JOIN stocks s ON s.code = d.code
        LEFT JOIN daily_stock_driver drv ON drv.trade_date = d.trade_date AND drv.code = d.code
        WHERE d.trade_date = ? AND d.board_height >= 3
        ORDER BY d.board_height DESC, d.is_one_word DESC, d.first_limit_time ASC, d.amount_yi DESC, d.code ASC
        """,
        (prev_date,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        code = r["code"]
        if code in today_code_set:
            continue
        prev_pair = prev_display_map.get(code) or []
        theme = (
            _clean_text(r["drv_theme"])
            or (prev_pair[0] if prev_pair else "")
            or _clean_text(r["first_tag"])
            or _clean_text(r["ma_l1"])
            or main_business(r["em_industry"], [])
        )
        pct = _get_stock_day_pct(code, cur_date) if cur_date else None
        out.append(
            {
                "code": code,
                "name": _clean_text(r["stock_name"]) or code,
                "prev_height": int(r["prev_height"] or 3),
                "theme": theme,
                "pct_chg": pct,
                "is_nuclear": bool(pct is not None and pct <= -8.5),
            }
        )
    return out


def _get_recent_broken(
    conn: sqlite3.Connection,
    cur_date: str,
    prev_dates: list[str],
    exclude_codes: set[str],
) -> list[dict[str, Any]]:
    """Return >=3B stocks that broke 1~2 trading days ago and haven't limited up again since, with daily % trail."""
    if not cur_date or len(prev_dates) < 2:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set(exclude_codes)
    # days_ago=1 -> broken on prev_dates[0] (was >=3B on prev_dates[1])
    # days_ago=2 -> broken on prev_dates[1] (was >=3B on prev_dates[2])
    pool_by_dt: dict[str, set[str]] = {}
    for dt_k in prev_dates[:2]:
        pool_by_dt[dt_k] = {
            str(r[0])
            for r in conn.execute(
                "SELECT code FROM daily_limit_pool WHERE trade_date = ?", (dt_k,)
            ).fetchall()
        }

    for days_ago in (1, 2):
        if len(prev_dates) <= days_ago:
            break
        broken_dt = prev_dates[days_ago - 1]
        peak_dt = prev_dates[days_ago]
        trail_dates = [*reversed(prev_dates[:days_ago]), cur_date]
        later_pool: set[str] = set()
        for dt_k in prev_dates[:days_ago]:
            later_pool |= pool_by_dt.get(dt_k, set())

        rows = conn.execute(
            """
            SELECT d.code,
                   COALESCE(s.name, d.name) AS stock_name,
                   d.board_height AS prev_height,
                   drv.driver AS drv_theme,
                   (SELECT tag FROM stock_tags t WHERE t.code = d.code ORDER BY t.id ASC LIMIT 1) AS first_tag,
                   (SELECT target_l1 FROM ma_events m WHERE m.code = d.code AND m.target_l1 IS NOT NULL AND m.target_l1 != '' ORDER BY m.from_date DESC, m.id ASC LIMIT 1) AS ma_l1,
                   s.em_industry AS em_industry
            FROM daily_limit_pool d
            LEFT JOIN stocks s ON s.code = d.code
            LEFT JOIN daily_stock_driver drv ON drv.trade_date = d.trade_date AND drv.code = d.code
            WHERE d.trade_date = ? AND d.board_height >= 3
            ORDER BY d.board_height DESC, d.amount_yi DESC, d.code ASC
            """,
            (peak_dt,),
        ).fetchall()

        for r in rows:
            code = str(r["code"])
            if code in seen or code in later_pool:
                continue
            seen.add(code)
            theme = (
                _clean_text(r["drv_theme"])
                or _clean_text(r["first_tag"])
                or _clean_text(r["ma_l1"])
                or main_business(r["em_industry"], [])
            )
            trail = [{"d": td, "pct": _get_stock_day_pct(code, td)} for td in trail_dates]
            today_pct = trail[-1]["pct"] if trail else None
            out.append(
                {
                    "code": code,
                    "name": _clean_text(r["stock_name"]) or code,
                    "prev_height": int(r["prev_height"] or 3),
                    "broken_date": broken_dt,
                    "days_ago": days_ago,
                    "theme": theme,
                    "today_pct": today_pct,
                    "trail": trail,
                }
            )
    out.sort(key=lambda x: (x["days_ago"], -x["prev_height"], x["code"]))
    return out[:12]


def _compute_day_relay_mood(
    conn: sqlite3.Connection,
    date: str,
    prev_date: str | None,
    total_zt: int,
    today_code_set: set[str],
    broken_boards: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute relay promotion rates (1->2, 2->3, 3->4+, multi), seal/zb mood, and nuclear broken count."""
    p12_base = p12_hit = 0
    p23_base = p23_hit = 0
    p3p_base = p3p_hit = 0
    if prev_date:
        for r in conn.execute(
            "SELECT code, board_height FROM daily_limit_pool WHERE trade_date = ?",
            (prev_date,),
        ).fetchall():
            c = str(r["code"])
            h = int(r["board_height"] or 1)
            hit = 1 if c in today_code_set else 0
            if h == 1:
                p12_base += 1
                p12_hit += hit
            elif h == 2:
                p23_base += 1
                p23_hit += hit
            elif h >= 3:
                p3p_base += 1
                p3p_hit += hit

    m_base = p23_base + p3p_base
    m_hit = p23_hit + p3p_hit

    def _rate(h_v: int, b_v: int) -> float | None:
        return round(h_v * 100.0 / b_v, 1) if b_v > 0 else None

    base_mood = _get_day_mood(date, total_zt, fetch_remote=False) if date else {}
    zb_cnt = base_mood.get("zb_count")
    seal_rate = None
    if zb_cnt is not None and (total_zt + int(zb_cnt)) > 0:
        seal_rate = round(total_zt * 100.0 / (total_zt + int(zb_cnt)), 1)

    nuclear_cnt = sum(1 for b in broken_boards if b.get("is_nuclear"))
    return {
        "zb_count": zb_cnt,
        "seal_rate": seal_rate,
        "zhaban_rate": base_mood.get("zhaban_rate"),
        "p12_hit": p12_hit,
        "p12_base": p12_base,
        "p12_rate": _rate(p12_hit, p12_base),
        "p23_hit": p23_hit,
        "p23_base": p23_base,
        "p23_rate": _rate(p23_hit, p23_base),
        "p3p_hit": p3p_hit,
        "p3p_base": p3p_base,
        "p3p_rate": _rate(p3p_hit, p3p_base),
        "multi_hit": m_hit,
        "multi_base": m_base,
        "multi_rate": _rate(m_hit, m_base),
        "broken_count": len(broken_boards),
        "nuclear_count": nuclear_cnt,
    }


def get_day_payload(date: str | None = None, _depth: int = 0) -> dict[str, Any]:
    conn = _conn()
    try:
        if not date:
            row = conn.execute(
                """
                SELECT trade_date FROM daily_hot_news
                ORDER BY trade_date DESC LIMIT 1
                """
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT MAX(trade_date) AS trade_date FROM daily_limit_pool"
                ).fetchone()
            date = row["trade_date"] if row else ""

        prev_dates = [
            r["trade_date"]
            for r in conn.execute(
                "SELECT DISTINCT trade_date FROM daily_limit_pool WHERE trade_date < ? ORDER BY trade_date DESC LIMIT 5",
                (date,),
            ).fetchall()
        ]
        prev_date = prev_dates[0] if prev_dates else None

        pool_rows = conn.execute(
            """
            SELECT trade_date, code, name, board_height, boards_desc,
                   first_limit_time, amount_yi, turnover_rate, is_one_word, is_fanbao
            FROM daily_limit_pool
            WHERE trade_date = ?
            ORDER BY board_height DESC, is_one_word DESC, first_limit_time ASC, amount_yi DESC, code ASC
            """,
            (date,),
        ).fetchall()

        total_zt = len(pool_rows)
        all_pool_codes = [r["code"] for r in pool_rows]
        core_rows = [
            r
            for r in pool_rows
            if is_core_stock(r["board_height"], r["is_fanbao"], r["boards_desc"])
        ]
        codes = [r["code"] for r in core_rows]
        core_code_set = set(codes)
        if not codes:
            all_pool_set = set(all_pool_codes)
            broken_empty = _get_broken_boards(conn, prev_date, all_pool_set, {}, cur_date=date)
            recent_empty = _get_recent_broken(
                conn, date, prev_dates, all_pool_set | {b["code"] for b in broken_empty}
            )
            mood_empty = _compute_day_relay_mood(conn, date, prev_date, total_zt, all_pool_set, broken_empty)
            return {
                "date": date,
                "summary": {
                    "total": total_zt,
                    "core": 0,
                    "multi": 0,
                    "fanbao": 0,
                    "first": total_zt,
                    "one_word": 0,
                    "max_height": 1 if total_zt else 0,
                },
                "mood": mood_empty,
                "catalysts": [],
                "hot_sectors": [],
                "hot_news": [],
                "ladder": [],
                "fanbao_boards": [],
                "broken_boards": broken_empty,
                "recent_broken": recent_empty,
                "first_boards": [],
                "first_board_codes": all_pool_codes,
                "stocks": {},
                "themes": {},
            }

        stock_meta = {
            r["code"]: dict(r)
            for r in _query_in_chunks(conn, "SELECT * FROM stocks WHERE code IN ({ph})", all_pool_codes)
        }

        tags_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        tag_rows = _query_in_chunks(
            conn,
            """
            SELECT code, tag, from_date, evidence
            FROM stock_tags
            WHERE code IN ({ph})
            ORDER BY id ASC
            """,
            all_pool_codes,
        )
        for r in tag_rows:
            if tag_is_active(r["from_date"], r["evidence"], date):
                tags_by_code[r["code"]].append(dict(r))

        ma_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in _query_in_chunks(
            conn,
            """
            SELECT code, event_type, target_name, target_l1, from_date, evidence
            FROM ma_events
            WHERE code IN ({ph})
            ORDER BY from_date DESC, id ASC
            """,
            all_pool_codes,
        ):
            ma_by_code[r["code"]].append(dict(r))

        # Intraday full-market breadth per theme across ALL limit-up stocks (core + 1st board)
        zt_codes_by_theme: dict[str, list[str]] = defaultdict(list)
        zt_seen_by_theme: dict[str, set[str]] = defaultdict(set)
        first_boards_by_theme: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in pool_rows:
            p_code = r["code"]
            p_meta = stock_meta.get(p_code)
            p_name = (p_meta["name"] if p_meta and p_meta.get("name") else r["name"]) or p_code
            p_tags: list[str] = []
            seen_pt: set[str] = set()
            for tr in tags_by_code.get(p_code, []):
                tg = _clean_text(tr["tag"])
                if tg and tg not in seen_pt:
                    seen_pt.add(tg)
                    p_tags.append(tg)
            for mr in ma_by_code.get(p_code, []):
                tl1 = _clean_text(mr.get("target_l1"))
                if tl1 and tl1 not in seen_pt:
                    seen_pt.add(tl1)
                    p_tags.append(tl1)
            for itag, _ in extract_intrinsic_tags(
                p_code,
                p_name,
                p_meta.get("province") if p_meta else None,
                p_meta.get("city") if p_meta else None,
                p_meta.get("controller_province") if p_meta else None,
                p_meta.get("controller_type") if p_meta else None,
            ):
                if itag not in seen_pt:
                    seen_pt.add(itag)
                    p_tags.append(itag)
            fb_obj = (
                {
                    "code": p_code,
                    "name": p_name,
                    "first_time": (r["first_limit_time"] or "")[:5],
                    "amount_yi": round(float(r["amount_yi"] or 0), 2),
                    "turnover": round(float(r["turnover_rate"] or 0), 1),
                    "is_one_word": bool(r["is_one_word"]),
                }
                if p_code not in core_code_set
                else None
            )
            for tg in p_tags:
                if p_code not in zt_seen_by_theme[tg]:
                    zt_seen_by_theme[tg].add(p_code)
                    zt_codes_by_theme[tg].append(p_code)
                    if fb_obj is not None:
                        first_boards_by_theme[tg].append(fb_obj)

        news_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT rank, headline, detail, hit_count, theme, codes
                FROM daily_hot_news
                WHERE trade_date = ?
                ORDER BY rank ASC
                """,
                (date,),
            ).fetchall()
        ]

        driver_rows = {
            r["code"]: dict(r)
            for r in conn.execute(
                """
                SELECT code, driver, driver2, basis_type, basis, source
                FROM daily_stock_driver
                WHERE trade_date = ?
                """,
                (date,),
            ).fetchall()
        }

        prev_driver_map: dict[str, str] = {}
        for pd in reversed(prev_dates):
            for r in conn.execute(
                "SELECT code, driver FROM daily_stock_driver WHERE trade_date = ? AND driver IS NOT NULL",
                (pd,),
            ).fetchall():
                prev_driver_map[r["code"]] = r["driver"]

        # Pass 1: build unified full-dynamic pure themes per core stock (连板+反包) + driver-weighted sector stats
        raw_stocks: dict[str, dict[str, Any]] = {}
        theme_members: dict[str, list[str]] = defaultdict(list)
        theme_drivers: dict[str, list[str]] = defaultdict(list)
        theme_multi: dict[str, int] = defaultdict(int)
        theme_core_multi: dict[str, float] = defaultdict(float)
        theme_core_total: dict[str, float] = defaultdict(float)
        theme_one_word: dict[str, int] = defaultdict(int)
        theme_max_h: dict[str, int] = defaultdict(int)
        ev_text_by_code: dict[str, dict[str, str]] = defaultdict(dict)
        tag_pop: dict[str, int] = defaultdict(int)

        for r in core_rows:
            code = r["code"]
            meta = stock_meta.get(code)
            t_list = tags_by_code.get(code, [])
            ma_list = ma_by_code.get(code, [])

            themes: list[str] = []
            seen_t: set[str] = set()
            evidences: list[dict[str, Any]] = []

            for t_row in t_list:
                t = _clean_text(t_row["tag"])
                if t and t not in seen_t:
                    seen_t.add(t)
                    themes.append(t)
                    ev_txt = _clean_text(t_row["evidence"])
                    ev_text_by_code[code][t] = ev_txt
                    evidences.append(
                        {
                            "theme": t,
                            "pct": None,
                            "text": ev_txt,
                        }
                    )

            for m in ma_list:
                tl1 = _clean_text(m.get("target_l1"))
                if tl1 and tl1 not in seen_t:
                    seen_t.add(tl1)
                    themes.append(tl1)
                    ma_ev = f"{m['event_type']}：{m['target_name']}"
                    ev_text_by_code[code][tl1] = ma_ev
                    evidences.append(
                        {
                            "theme": tl1,
                            "pct": None,
                            "text": ma_ev,
                        }
                    )

            name = (meta["name"] if meta and meta.get("name") else r["name"]) or code
            for itag, iev in extract_intrinsic_tags(
                code,
                name,
                meta.get("province") if meta else None,
                meta.get("city") if meta else None,
                meta.get("controller_province") if meta else None,
                meta.get("controller_type") if meta else None,
            ):
                if itag not in seen_t:
                    seen_t.add(itag)
                    themes.append(itag)
                    ev_text_by_code[code][itag] = iev
                    evidences.append(
                        {
                            "theme": itag,
                            "pct": None,
                            "text": iev,
                        }
                    )

            h = int(r["board_height"] or 1)
            is_ow = bool(r["is_one_word"])
            for t in themes:
                theme_members[t].append(code)
                if not is_intrinsic_tag(t):
                    tag_pop[t] += 1

            prov = _short_prov(meta["province"]) if meta else ""
            ctrl_prov = (
                _short_prov(meta["controller_province"])
                if meta and meta.get("controller_province")
                else ""
            )
            ctrl_type = (meta.get("controller_type") or "") if meta else ""
            if ctrl_type == "民营及其他":
                ctrl_type = "民营"

            name = (meta["name"] if meta and meta.get("name") else r["name"]) or code
            first_time = (r["first_limit_time"] or "")[:5]
            amount_yi = round(float(r["amount_yi"]), 2) if r["amount_yi"] is not None else None
            turnover = round(float(r["turnover_rate"]), 1) if r["turnover_rate"] is not None else None

            is_fb = is_fanbao_stock(r["is_fanbao"], r["boards_desc"])
            raw_stocks[code] = {
                "code": code,
                "name": name,
                "height": h,
                "boards_desc": _clean_text(r["boards_desc"]),
                "first_time": first_time,
                "amount_yi": amount_yi,
                "turnover": turnover,
                "is_one_word": is_ow,
                "is_fanbao": is_fb,
                "fanbao_gain_pct": _compute_fanbao_gain_pct(conn, code, date, r["boards_desc"]) if is_fb else None,
                "province": prov,
                "controller_province": ctrl_prov if ctrl_prov and ctrl_prov != prov else "",
                "controller_type": ctrl_type,
                "industry": (meta.get("em_industry") or "") if meta else "",
                "themes": themes,
                "evidences": evidences,
                "ma_events": [
                    {
                        "type": m["event_type"],
                        "target": m["target_name"],
                        "target_l1": m["target_l1"] or "",
                        "from_date": m["from_date"] or "",
                    }
                    for m in ma_list
                ],
                "primary_theme": "",
                "driver": None,
                "driver2": None,
                "driver_basis": "",
                "driver_basis_type": "",
                "driver_source": "",
                "display_source": "",
            }

        news_text_all = " ".join(
            f"{_clean_text(nw['headline'])} {_clean_text(nw['detail'])}" for nw in news_rows
        )
        for r in core_rows:
            code = r["code"]
            st = raw_stocks[code]
            h = st["height"]
            is_ow = st["is_one_word"]
            d_row = driver_rows.get(code)
            if d_row:
                drv = d_row.get("driver") or None
                drv2 = d_row.get("driver2") or None
                btype = d_row.get("basis_type") or ""
                basis = _clean_text(d_row.get("basis"))
                dsrc = d_row.get("source") or "llm"
            else:
                drv = rule_driver(
                    st["themes"],
                    ev_text_by_code.get(code, {}),
                    news_text_all,
                    tag_pop,
                    prev_driver_map.get(code),
                    h,
                )
                drv2 = None
                btype = "resonance" if drv else ""
                basis = "规则兜底：同涨共振/证据匹配" if drv else ""
                dsrc = "rule"

            st["driver"] = drv
            st["driver2"] = drv2
            st["driver_basis"] = basis
            st["driver_basis_type"] = btype
            st["driver_source"] = dsrc

            for t in (drv, drv2):
                if t and t not in st["themes"]:
                    st["themes"].append(t)
                    theme_members[t].append(code)
                    tag_pop[t] += 1
                    ev_text_by_code[code][t] = basis
                    st["evidences"].append({"theme": t, "pct": None, "text": basis})
                if t and code not in zt_seen_by_theme[t]:
                    zt_seen_by_theme[t].add(code)
                    zt_codes_by_theme[t].append(code)

            weighted_pairs: list[tuple[str, float]] = []
            if drv:
                weighted_pairs.append((drv, 1.0))
            if drv2 and drv2 != drv:
                weighted_pairs.append((drv2, 0.4))
            for t, w in weighted_pairs:
                theme_drivers[t].append(code)
                theme_core_total[t] += w
                if h >= 2:
                    theme_multi[t] += 1
                    theme_core_multi[t] += w
                if is_ow:
                    theme_one_word[t] += 1
                if h > theme_max_h[t]:
                    theme_max_h[t] = h

        # Pass 2: build Top Catalyst Cards FIRST from daily_hot_news + driver-based ladders
        name_to_code = {st["name"]: code for code, st in raw_stocks.items()}
        pool_set = set(raw_stocks.keys())
        theme_news_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
        event_catalysts: list[dict[str, Any]] = []
        raw_hot_news: list[dict[str, Any]] = []

        for nw in news_rows:
            hl = _clean_text(nw["headline"])
            dt = _clean_text(nw["detail"])
            combined = f"{hl} {dt}"

            mentioned: list[str] = []
            raw_codes = nw.get("codes")
            if raw_codes:
                try:
                    parsed_codes = json.loads(raw_codes) if isinstance(raw_codes, str) else raw_codes
                    mentioned = [str(c) for c in parsed_codes if str(c) in pool_set]
                except Exception:
                    mentioned = []
            if not mentioned:
                mentioned = [
                    code
                    for sname, code in name_to_code.items()
                    if sname and sname in combined
                ]
            mentioned.sort(
                key=lambda c: (
                    -raw_stocks[c]["height"],
                    -int(raw_stocks[c]["is_one_word"]),
                    raw_stocks[c]["first_time"],
                )
            )

            mapped_theme: str | None = None
            event_label: str | None = None
            event_accent: str = "amber"
            nw_theme = _clean_text(nw.get("theme"))
            if nw_theme and (nw_theme in VOCAB_SET or is_event_theme(nw_theme)):
                if nw_theme in theme_drivers:
                    mapped_theme = nw_theme
                else:
                    event_label = nw_theme
                    event_accent = _accent_for(nw_theme)

            if not mapped_theme and not event_label:
                for kw, label, acc in NEWS_EVENT_SHORT_TITLES:
                    if kw in combined:
                        event_label = label
                        event_accent = acc
                        break

            event_cat_id: str | None = None
            if mapped_theme:
                theme_news_map[mapped_theme].append(
                    {
                        "rank": nw["rank"],
                        "headline": hl,
                        "detail": dt,
                        "hit_count": int(nw.get("hit_count") or 1),
                        "mentioned": mentioned,
                    }
                )
            else:
                max_h_m = max((raw_stocks[c]["height"] for c in mentioned), default=0)
                if len(mentioned) >= 2 or max_h_m >= 3:
                    ev_title = event_label or hl[:6]
                    ev_multi = sum(1 for c in mentioned if raw_stocks[c]["height"] >= 2)
                    ev_ow = sum(1 for c in mentioned if raw_stocks[c]["is_one_word"])
                    event_cat_id = f"event:{nw['rank']}"
                    event_catalysts.append(
                        {
                            "id": event_cat_id,
                            "kind": "event",
                            "title": ev_title,
                            "theme": None,
                            "accent": event_accent,
                            "headline": hl,
                            "news": [{"headline": hl, "detail": dt}],
                            "codes": mentioned,
                            "total": len(mentioned),
                            "multi": ev_multi,
                            "one_word": ev_ow,
                            "max_height": max_h_m,
                            "leaders": [
                                {
                                    "code": c,
                                    "name": raw_stocks[c]["name"],
                                    "height": raw_stocks[c]["height"],
                                    "is_one_word": raw_stocks[c]["is_one_word"],
                                }
                                for c in mentioned[:3]
                            ],
                            "_score": 20.0 + int(nw.get("hit_count") or 1) * 3.0 + max_h_m * 3.0 - nw["rank"] * 0.6,
                        }
                    )

            raw_hot_news.append(
                {
                    "rank": int(nw["rank"]),
                    "headline": hl,
                    "detail": dt,
                    "mapped_theme": mapped_theme,
                    "event_label": event_label or (nw_theme if nw_theme else ""),
                    "event_cat_id": event_cat_id,
                    "mentioned": mentioned,
                }
            )

        catalysts: list[dict[str, Any]] = []
        included_themes: set[str] = set()

        def _make_theme_catalyst(t: str, news_list: list[dict[str, Any]]) -> dict[str, Any]:
            codes_t = list(theme_drivers[t])
            seen_c = set(codes_t)
            for nw in news_list:
                for c in nw["mentioned"]:
                    if c not in seen_c:
                        seen_c.add(c)
                        codes_t.append(c)
            codes_t.sort(
                key=lambda c: (
                    -raw_stocks[c]["height"],
                    -int(raw_stocks[c]["is_one_word"]),
                    raw_stocks[c]["first_time"],
                    -(raw_stocks[c]["amount_yi"] or 0),
                )
            )
            multi_cnt = sum(1 for c in codes_t if raw_stocks[c]["height"] >= 2)
            ow_cnt = sum(1 for c in codes_t if raw_stocks[c]["is_one_word"])
            max_h = max((raw_stocks[c]["height"] for c in codes_t), default=1)
            heights_present = sorted({raw_stocks[c]["height"] for c in codes_t}, reverse=True)

            if news_list:
                headline = news_list[0]["headline"]
                news_payload = [
                    {"headline": n["headline"], "detail": n["detail"]}
                    for n in news_list
                ]
            else:
                lead = raw_stocks[codes_t[0]]
                h_chain = "→".join(("反包" if x == 1 else f"{x}板") for x in heights_present[:4])
                ow_note = "一字" if lead["is_one_word"] else ""
                lead_h = lead["boards_desc"] if lead["height"] == 1 and lead["boards_desc"] else f"{lead['height']}板"
                headline = f"{lead_h}{ow_note}{lead['name']}领涨，梯队覆盖 {h_chain}"
                news_payload = []

            best_rank = min((n["rank"] for n in news_list), default=14)
            news_hits = sum(int(n.get("hit_count") or 1) for n in news_list)
            score = (
                max_h * 9.0
                + (24.0 + news_hits * 2.5 if news_list else 0.0)
                + theme_core_multi[t] * 6.5
                + theme_core_total[t] * 2.0
                - best_rank * 0.45
            )
            return {
                "id": f"theme:{t}",
                "kind": "theme",
                "title": t,
                "theme": t,
                "accent": _accent_for(t),
                "headline": headline,
                "news": news_payload,
                "codes": codes_t,
                "total": len(codes_t),
                "multi": multi_cnt,
                "one_word": ow_cnt,
                "max_height": max_h,
                "leaders": [
                    {
                        "code": c,
                        "name": raw_stocks[c]["name"],
                        "height": raw_stocks[c]["height"],
                        "is_one_word": raw_stocks[c]["is_one_word"],
                    }
                    for c in codes_t[:3]
                ],
                "_score": score,
            }

        # Add news-backed pure themes that have >= 1 driving core stock
        for t, nlist in theme_news_map.items():
            if len(theme_drivers[t]) >= 1:
                included_themes.add(t)
                catalysts.append(_make_theme_catalyst(t, nlist))

        # Add strong driver-backed core ladder themes (>=2 core drivers, or >=3B / >=3-board fanbao leader)
        for t, drv_codes in theme_drivers.items():
            if t in included_themes:
                continue
            has_strong_fb = any(fanbao_board_count(raw_stocks[c]["boards_desc"]) >= 3 for c in drv_codes)
            if len(drv_codes) >= 2 or ((theme_max_h[t] >= 3 or has_strong_fb) and len(drv_codes) >= 1):
                included_themes.add(t)
                catalysts.append(_make_theme_catalyst(t, []))

        catalysts.extend(event_catalysts)
        catalysts.sort(key=lambda x: -x["_score"])
        for c_item in catalysts:
            c_item.pop("_score", None)
        catalysts = catalysts[:10]

        # Assign explicit intraday fermentation heat_rank (1 = 最强发酵 红, 2 = 第二发酵 橙, 3+ = 常规)
        theme_heat_rank: dict[str, int] = {}
        for idx, c_item in enumerate(catalysts, 1):
            c_item["heat_rank"] = idx
            if c_item["theme"]:
                theme_heat_rank[c_item["theme"]] = idx
            else:
                c_item["event_rank"] = idx

        # Pass 3: Strict User Display Rule (core stocks: 连板+反包):
        #   1. slot1 = driver if driver in top10
        #   2. else slot1 = most recent prior primary_theme in last 5 trading days (yesterday for streaks, pre-break for fanbao)
        #   3. else slot1 = main_business(em_industry, own_tags)
        top10_themes = {c_item["theme"] for c_item in catalysts if c_item.get("theme")}

        prev_display_map: dict[str, list[str]] = {}
        if prev_dates and _depth < 60:
            for pd in reversed(prev_dates):
                if pd not in _DAY_DISPLAY_CACHE:
                    get_day_payload(pd, _depth=_depth + 1)
                for c_prev, pair_prev in _DAY_DISPLAY_CACHE.get(pd, {}).items():
                    if pair_prev:
                        prev_display_map[c_prev] = pair_prev

        today_display_map: dict[str, list[str]] = {}
        for code, st in raw_stocks.items():
            drv = st["driver"]
            drv2 = st["driver2"]
            prev_pair = prev_display_map.get(code) or []
            prev_first = prev_pair[0] if prev_pair else None

            if drv and drv in top10_themes:
                slot1 = drv
                dsrc = "driver"
            elif prev_first:
                slot1 = prev_first
                dsrc = "prev"
            else:
                slot1 = main_business(st["industry"], st["themes"])
                dsrc = "main"

            pair = [slot1] if slot1 else []
            st["primary_theme"] = slot1
            st["primary_accent"] = _accent_for(slot1)
            st["display_source"] = dsrc
            st["display_themes"] = [
                {"name": t, "heat_rank": theme_heat_rank.get(t, 99)}
                for t in pair
            ]
            today_display_map[code] = pair

        if date:
            _DAY_DISPLAY_CACHE[date] = today_display_map

        # Build complete theme index (core stocks + intraday all-market limit-up breadth & 1st boards)
        themes_index: dict[str, dict[str, Any]] = {}
        all_active_themes: set[str] = set(theme_members.keys())
        for t, zt_list in zt_codes_by_theme.items():
            if len(zt_list) >= 2 or t in theme_news_map:
                all_active_themes.add(t)

        for t in all_active_themes:
            members = theme_members.get(t, [])
            drv_set = set(theme_drivers.get(t, []))
            sorted_m = sorted(
                members,
                key=lambda c: (
                    0 if c in drv_set else 1,
                    -raw_stocks[c]["height"],
                    -fanbao_board_count(raw_stocks[c]["boards_desc"]),
                    -int(raw_stocks[c]["is_one_word"]),
                    raw_stocks[c]["first_time"],
                    -(raw_stocks[c]["amount_yi"] or 0),
                ),
            )
            news_list = [
                {"headline": n["headline"], "detail": n["detail"]}
                for n in theme_news_map.get(t, [])
            ]
            fb_list = first_boards_by_theme.get(t, [])
            zt_tot = max(len(zt_codes_by_theme.get(t, [])), len(sorted_m))
            themes_index[t] = {
                "name": t,
                "accent": _accent_for(t),
                "heat_rank": theme_heat_rank.get(t, 99),
                "codes": sorted_m,
                "driver_codes": [c for c in sorted_m if c in drv_set],
                "total": len(sorted_m),
                "zt_total": zt_tot,
                "multi": sum(1 for c in sorted_m if raw_stocks[c]["height"] >= 2),
                "fanbao": sum(1 for c in sorted_m if raw_stocks[c]["height"] == 1),
                "one_word": sum(1 for c in sorted_m if raw_stocks[c]["is_one_word"]),
                "max_height": max((raw_stocks[c]["height"] for c in sorted_m), default=1 if zt_tot else 0),
                "news": news_list,
                "first_board_total": len(fb_list),
                "first_boards": fb_list,
            }

        if date:
            _DAY_THEME_STATS_CACHE[date] = {
                t: (th["zt_total"], th["max_height"])
                for t, th in themes_index.items()
            }

        # Attach 5-trading-day fermentation trajectory per active theme
        trend_dates = [*reversed(prev_dates[:4]), date] if date else []
        if trend_dates and _depth == 0:
            prev_stats_by_dt = {
                td: _get_day_theme_stats(conn, td)
                for td in trend_dates[:-1]
            }
            for t, th in themes_index.items():
                trend: list[dict[str, Any]] = []
                for td in trend_dates[:-1]:
                    zt_v, h_v = prev_stats_by_dt[td].get(t, (0, 0))
                    trend.append({"d": td, "zt": zt_v, "h": h_v})
                trend.append({"d": date, "zt": th["zt_total"], "h": th["max_height"]})
                th["trend"] = trend

        # Build intraday hot_sectors (ranked hot sectors combining top catalysts + remaining active sectors)
        cat_by_id = {c_item["id"]: c_item for c_item in catalysts}
        hot_sectors: list[dict[str, Any]] = []
        seen_hot_names: set[str] = set()
        for c_item in catalysts:
            if c_item["kind"] == "theme":
                t = c_item["theme"]
                th = themes_index.get(t)
                if not th:
                    continue
                seen_hot_names.add(t)
                has_news = bool(c_item.get("news"))
                th_trend = th.get("trend") or []
                hot_sectors.append(
                    {
                        "id": c_item["id"],
                        "kind": "theme",
                        "name": t,
                        "heat_rank": c_item["heat_rank"],
                        "zt_total": th["zt_total"],
                        "core_total": th["total"],
                        "driver_count": len(th["driver_codes"]),
                        "multi": th["multi"],
                        "fanbao": th["fanbao"],
                        "max_height": th["max_height"],
                        "tier_shape": _format_tier_shape(th["codes"], raw_stocks),
                        "trend": th_trend,
                        "streak_days": _calc_streak_days(th_trend),
                        "headline": c_item["headline"] if has_news else "",
                        "leaders": c_item["leaders"],
                        "catalyst_id": c_item["id"],
                    }
                )
            else:
                seen_hot_names.add(c_item["title"])
                hot_sectors.append(
                    {
                        "id": c_item["id"],
                        "kind": "event",
                        "name": c_item["title"],
                        "heat_rank": c_item["heat_rank"],
                        "zt_total": c_item["total"],
                        "core_total": c_item["total"],
                        "driver_count": c_item["total"],
                        "multi": c_item["multi"],
                        "fanbao": c_item["total"] - c_item["multi"],
                        "max_height": c_item["max_height"],
                        "tier_shape": _format_tier_shape(c_item.get("codes") or [], raw_stocks),
                        "trend": [],
                        "streak_days": 0,
                        "headline": c_item["headline"],
                        "leaders": c_item["leaders"],
                        "catalyst_id": c_item["id"],
                    }
                )

        extra_themes = [
            th
            for t, th in themes_index.items()
            if t not in seen_hot_names
            and (not is_intrinsic_tag(t) or len(th["driver_codes"]) >= 1)
            and (len(th["driver_codes"]) >= 1 or th["multi"] >= 2 or th["zt_total"] >= 8)
        ]
        extra_themes.sort(
            key=lambda th: (
                -len(th["driver_codes"]),
                -th["multi"],
                -th["zt_total"],
                -th["max_height"],
            )
        )
        for th in extra_themes:
            if len(hot_sectors) >= 8:
                break
            lead_codes = th["codes"][:3]
            leaders = [
                {
                    "code": c,
                    "name": raw_stocks[c]["name"],
                    "height": raw_stocks[c]["height"],
                    "is_one_word": raw_stocks[c]["is_one_word"],
                }
                for c in lead_codes
            ]
            if not leaders and th["first_boards"]:
                leaders = [
                    {
                        "code": fb["code"],
                        "name": fb["name"],
                        "height": 1,
                        "is_one_word": fb["is_one_word"],
                    }
                    for fb in th["first_boards"][:3]
                ]
            th_trend = th.get("trend") or []
            hot_sectors.append(
                {
                    "id": f"theme:{th['name']}",
                    "kind": "theme",
                    "name": th["name"],
                    "heat_rank": th["heat_rank"],
                    "zt_total": th["zt_total"],
                    "core_total": th["total"],
                    "driver_count": len(th["driver_codes"]),
                    "multi": th["multi"],
                    "fanbao": th["fanbao"],
                    "max_height": th["max_height"],
                    "tier_shape": _format_tier_shape(th["codes"], raw_stocks),
                    "trend": th_trend,
                    "streak_days": _calc_streak_days(th_trend),
                    "headline": th["news"][0]["headline"] if th["news"] else "",
                    "leaders": leaders,
                    "catalyst_id": None,
                }
            )
        hot_sectors = hot_sectors[:8]

        # Build complete curated hot_news list (preserving every daily_hot_news dispatch)
        hot_news: list[dict[str, Any]] = []
        for rn in raw_hot_news:
            mt = rn["mapped_theme"]
            ev_id = rn["event_cat_id"]
            ev_cat = cat_by_id.get(ev_id) if ev_id else None
            if mt and mt in themes_index:
                target_type = "theme"
                target_id = mt
                h_rank = theme_heat_rank.get(mt, 99)
                theme_lbl = mt
                lead_codes = rn["mentioned"][:3] or themes_index[mt]["codes"][:3]
            elif ev_cat:
                target_type = "catalyst"
                target_id = ev_cat["id"]
                h_rank = ev_cat.get("heat_rank", 99)
                theme_lbl = ev_cat["title"]
                lead_codes = ev_cat["codes"][:3]
            else:
                elbl = rn["event_label"]
                if elbl and elbl in themes_index:
                    target_type = "theme"
                    target_id = elbl
                    h_rank = theme_heat_rank.get(elbl, 99)
                    theme_lbl = elbl
                    lead_codes = rn["mentioned"][:3] or themes_index[elbl]["codes"][:3]
                else:
                    target_type = ""
                    target_id = ""
                    h_rank = 99
                    theme_lbl = elbl
                    lead_codes = rn["mentioned"][:3]

            hot_news.append(
                {
                    "rank": rn["rank"],
                    "headline": rn["headline"],
                    "detail": rn["detail"],
                    "theme": theme_lbl,
                    "target_type": target_type,
                    "target_id": target_id,
                    "heat_rank": h_rank,
                    "leaders": [
                        {
                            "code": c,
                            "name": raw_stocks[c]["name"],
                            "height": raw_stocks[c]["height"],
                            "is_one_word": raw_stocks[c]["is_one_word"],
                        }
                        for c in lead_codes
                        if c in raw_stocks
                    ],
                }
            )

        # Order each stock's themes: driver -> driver2 -> 33 industry tags -> permanent 国企改革/字辈 -> permanent 地域
        for st in raw_stocks.values():
            drv = st["driver"]
            drv2 = st["driver2"]
            st["themes"].sort(
                key=lambda t: (
                    0 if t == drv else (1 if t == drv2 else (4 if is_region_tag(t) else (3 if is_intrinsic_tag(t) else 2))),
                    theme_heat_rank.get(t, 99),
                    0 if t == st["primary_theme"] else 1,
                    -(themes_index[t]["multi"] * 4 + themes_index[t]["total"])
                    if t in themes_index
                    else 0,
                )
            )
            # If the stock participates in rank-1 or rank-2 intraday hottest theme, check if its primary_theme is that rank
            pt_rank = theme_heat_rank.get(st["primary_theme"], 99)
            if pt_rank > 2:
                best_owned = min((theme_heat_rank.get(t, 99) for t in st["themes"]), default=99)
                st["best_heat_rank"] = best_owned
            else:
                st["best_heat_rank"] = pt_rank
            st["primary_heat_rank"] = pt_rank

        # Build ladder tiers (>=2板) & fanbao_boards (反包 / N天M板); a stock can appear in BOTH!
        tiers_map: dict[int, list[str]] = defaultdict(list)
        fanbao_boards: list[str] = []
        for r in core_rows:
            code = r["code"]
            st = raw_stocks[code]
            if st["height"] >= 2:
                tiers_map[st["height"]].append(code)
            if st["is_fanbao"]:
                fanbao_boards.append(code)

        fanbao_boards.sort(
            key=lambda c: (
                -fanbao_board_count(raw_stocks[c]["boards_desc"]),
                -raw_stocks[c]["height"],
                -int(raw_stocks[c]["is_one_word"]),
                raw_stocks[c]["first_time"],
                -(raw_stocks[c]["amount_yi"] or 0),
            )
        )

        ladder = [
            {"height": h, "codes": tiers_map[h]}
            for h in sorted(tiers_map.keys(), reverse=True)
        ]

        multi_total = sum(len(x["codes"]) for x in ladder)
        ow_total = sum(1 for st in raw_stocks.values() if st["is_one_word"])
        max_height = ladder[0]["height"] if ladder else (1 if total_zt else 0)

        all_pool_set = set(all_pool_codes)
        first_board_codes = [r["code"] for r in pool_rows if r["code"] not in core_code_set]
        broken_boards = _get_broken_boards(conn, prev_date, all_pool_set, prev_display_map, cur_date=date)
        recent_broken = _get_recent_broken(
            conn, date, prev_dates, all_pool_set | {b["code"] for b in broken_boards}
        )
        relay_mood = _compute_day_relay_mood(conn, date, prev_date, total_zt, all_pool_set, broken_boards)
        deviations = compute_day_deviations(conn, date, raw_stocks, broken_boards)
        _compute_day_replenishments(conn, date, raw_stocks, stock_meta, tags_by_code, ma_by_code)

        # Curated 1->2 front-row first boards from today's Top 5 hot themes (deduplicated, sorted by early seal + volume)
        curated_first_boards: list[dict[str, Any]] = []
        seen_fb_codes: set[str] = set()
        top_hot_themes = [s for s in hot_sectors if s["kind"] == "theme"][:5]
        for s in top_hot_themes:
            th = themes_index.get(s["name"])
            if not th:
                continue
            fbs = [
                fb
                for fb in (th.get("first_boards") or [])
                if "ST" not in str(fb.get("name") or "").upper()
            ]
            fbs.sort(
                key=lambda x: (
                    -int(bool(x.get("is_one_word"))),
                    x.get("first_time") or "99:99",
                    -(x.get("amount_yi") or 0),
                )
            )
            picked = 0
            for fb in fbs:
                c = fb["code"]
                if c in seen_fb_codes:
                    continue
                seen_fb_codes.add(c)
                curated_first_boards.append(
                    {
                        "code": c,
                        "name": fb["name"],
                        "theme": s["name"],
                        "heat_rank": s["heat_rank"],
                        "first_time": fb.get("first_time") or "",
                        "amount_yi": fb.get("amount_yi") or 0,
                        "turnover": fb.get("turnover") or 0,
                        "is_one_word": bool(fb.get("is_one_word")),
                    }
                )
                picked += 1
                if picked >= 8:
                    break

        return {
            "date": date,
            "summary": {
                "total": total_zt,
                "core": len(raw_stocks),
                "multi": multi_total,
                "fanbao": len(fanbao_boards),
                "first": len(first_board_codes),
                "one_word": ow_total,
                "max_height": max_height,
            },
            "mood": relay_mood,
            "catalysts": catalysts,
            "hot_sectors": hot_sectors,
            "hot_news": hot_news,
            "ladder": ladder,
            "fanbao_boards": fanbao_boards,
            "broken_boards": broken_boards,
            "recent_broken": recent_broken,
            "deviations": deviations,
            "first_boards": curated_first_boards,
            "first_board_codes": first_board_codes,
            "stocks": raw_stocks,
            "themes": themes_index,
        }
    finally:
        conn.close()


def _stock_shard_id(code: str) -> str:
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    n = int(digits) % STOCK_SHARD_COUNT if digits else 0
    return f"{n:02d}"


_GBK_PY_BOUNDS: tuple[tuple[int, str], ...] = (
    (0xB0A1, "a"), (0xB0C5, "b"), (0xB2C1, "c"), (0xB4EE, "d"),
    (0xB6EA, "e"), (0xB7A2, "f"), (0xB8C1, "g"), (0xB9FE, "h"),
    (0xBBF7, "j"), (0xBFA6, "k"), (0xC0AC, "l"), (0xC2E8, "m"),
    (0xC4C3, "n"), (0xC5B6, "o"), (0xC5BE, "p"), (0xC6DA, "q"),
    (0xC8BB, "r"), (0xC8F6, "s"), (0xCBFA, "t"), (0xCDDA, "w"),
    (0xCEF4, "x"), (0xD1B9, "y"), (0xD4D1, "z"),
)

_EXTRA_PY_INITIALS: dict[str, str] = {
    "兖": "y", "冢": "z", "圳": "z", "奕": "y", "孚": "f", "宸": "c",
    "岱": "d", "岹": "t", "崧": "s", "崴": "w", "嵘": "r", "徕": "l",
    "怡": "y", "恺": "k", "憬": "j", "懋": "m", "昀": "y", "昇": "s",
    "昊": "h", "昕": "x", "昱": "y", "晖": "h", "晟": "s", "曦": "x",
    "柘": "z", "楠": "n", "楹": "y", "榈": "l", "榕": "r", "沐": "m",
    "泓": "h", "泸": "l", "浔": "x", "淼": "m", "渥": "w", "濠": "h",
    "濮": "p", "瀚": "h", "瀛": "y", "灏": "h", "炀": "y", "炜": "w",
    "烨": "y", "熵": "s", "獐": "z", "玑": "j", "玮": "w", "珀": "p",
    "珂": "k", "珈": "j", "琏": "l", "琚": "j", "琛": "c", "瑜": "y",
    "璞": "p", "璟": "j", "甬": "y", "癀": "h", "皓": "h", "睿": "r",
    "祺": "q", "禧": "x", "罡": "g", "胤": "y", "芸": "y", "茗": "m",
    "荃": "q", "荻": "d", "莞": "g", "萃": "c", "蒽": "e", "蜓": "t",
    "蜻": "q", "螂": "l", "螳": "t", "蟒": "m", "蟠": "p", "蠡": "l",
    "衢": "q", "迦": "j", "鑫": "x", "钛": "t", "钰": "y", "钴": "g",
    "钶": "k", "钼": "m", "钽": "t", "铖": "c", "锂": "l", "锆": "g",
    "锝": "d", "锴": "k", "锶": "s", "韬": "t", "颀": "q", "馨": "x",
    "骐": "q", "魅": "m", "鳌": "a", "鹄": "h", "鹞": "y", "鹭": "l",
    "麒": "q", "麟": "l", "麾": "h", "黛": "d",
}


def _pinyin_initials(text: str) -> str:
    """Zero-dependency Pinyin initials for A-share stock names (100% GBK L1 + L2 coverage)."""
    out: list[str] = []
    for ch in str(text or ""):
        if ch.isascii():
            if ch.isalnum():
                out.append(ch.lower())
            continue
        if ch in _EXTRA_PY_INITIALS:
            out.append(_EXTRA_PY_INITIALS[ch])
            continue
        if "\u4e00" <= ch <= "\u9fff":
            b = ch.encode("gbk", errors="ignore")
            if len(b) == 2:
                val = (b[0] << 8) + b[1]
                if 0xB0A1 <= val <= 0xD7F9:
                    letter = "a"
                    for bound, py in _GBK_PY_BOUNDS:
                        if val >= bound:
                            letter = py
                        else:
                            break
                    out.append(letter)
    return "".join(out)


def get_search_index(force_refresh: bool = False) -> dict[str, Any]:
    global _SEARCH_INDEX_CACHE
    if _SEARCH_INDEX_CACHE is not None and not force_refresh:
        return _SEARCH_INDEX_CACHE

    tax = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    l1_list: list[str] = list(tax.get("l1_list") or [])
    dynamic_list: list[str] = list(tax.get("dynamic_groups") or [])

    conn = _conn()
    try:
        latest_row = conn.execute("SELECT MAX(trade_date) FROM daily_limit_pool").fetchone()
        latest_dt = str(latest_row[0] or "2026-11-27")

        tags_by_code: dict[str, list[str]] = defaultdict(list)
        for r in conn.execute("SELECT code, tag, from_date, evidence FROM stock_tags ORDER BY id ASC"):
            if not tag_is_active(r["from_date"], r["evidence"], latest_dt):
                continue
            tg = _clean_text(r["tag"])
            if tg and tg not in tags_by_code[r["code"]]:
                tags_by_code[r["code"]].append(tg)

        ma_by_code: dict[str, list[str]] = defaultdict(list)
        for r in conn.execute("SELECT code, target_l1 FROM ma_events ORDER BY from_date DESC, id ASC"):
            tl1 = _clean_text(r["target_l1"])
            if tl1 and tl1 not in ma_by_code[r["code"]]:
                ma_by_code[r["code"]].append(tl1)

        lu_stats: dict[str, tuple[str, int, int, str]] = {}
        for r in conn.execute(
            """
            SELECT code,
                   MAX(trade_date) AS last_dt,
                   MAX(board_height) AS max_h,
                   COUNT(*) AS cnt,
                   MAX(name) AS pool_name
            FROM daily_limit_pool
            WHERE trade_date >= ?
            GROUP BY code
            """,
            (MIN_DISPLAY_DATE,),
        ):
            lu_stats[r["code"]] = (
                str(r["last_dt"] or ""),
                int(r["max_h"] or 0),
                int(r["cnt"] or 0),
                _clean_text(r["pool_name"]),
            )

        items: list[list[Any]] = []
        seen_codes: set[str] = set()
        sector_sets: dict[str, set[str]] = defaultdict(set)
        region_tags_seen: set[str] = set()

        for r in conn.execute("SELECT code, name, province, city, controller_province, controller_type FROM stocks ORDER BY code ASC"):
            code = r["code"]
            seen_codes.add(code)
            sname = _clean_text(r["name"]) or code
            tgs = list(tags_by_code.get(code, []))
            seen_tg = set(tgs)
            for itag, _ in extract_intrinsic_tags(code, sname, r["province"], r["city"], r["controller_province"], r["controller_type"]):
                if itag not in seen_tg:
                    seen_tg.add(itag)
                    tgs.append(itag)
                if is_region_tag(itag):
                    region_tags_seen.add(itag)
            mas = ma_by_code.get(code, [])
            for t in (*tgs, *mas):
                sector_sets[t].add(code)
            last_dt, max_h, cnt, _ = lu_stats.get(code, ("", 0, 0, ""))
            items.append(
                [
                    code,
                    sname,
                    _short_prov(r["province"]),
                    tgs,
                    mas,
                    last_dt,
                    max_h,
                    cnt,
                    _pinyin_initials(sname),
                ]
            )

        for code, (last_dt, max_h, cnt, pool_name) in lu_stats.items():
            if code in seen_codes:
                continue
            sname = pool_name or code
            itags = [itag for itag, _ in extract_intrinsic_tags(code, sname)]
            for t in itags:
                sector_sets[t].add(code)
            items.append([code, sname, "", itags, [], last_dt, max_h, cnt, _pinyin_initials(sname)])

        items.sort(key=lambda x: (x[5] or "", x[6], x[7], x[0]), reverse=True)
        sector_counts = {t: len(cs) for t, cs in sector_sets.items()}
        region_list = sorted(region_tags_seen, key=lambda r: -sector_counts.get(r, 0))

        ma_events_list: list[list[str]] = []
        for r in conn.execute(
            """
            SELECT m.code,
                   COALESCE(s.name, m.code) AS stock_name,
                   s.province,
                   m.event_type,
                   m.target_name,
                   m.target_l1,
                   m.from_date
            FROM ma_events m
            LEFT JOIN stocks s ON s.code = m.code
            ORDER BY m.from_date DESC, m.id DESC
            """
        ):
            ma_events_list.append(
                [
                    r["code"],
                    _clean_text(r["stock_name"]) or r["code"],
                    _short_prov(r["province"]),
                    _clean_text(r["event_type"]),
                    _clean_text(r["target_name"]),
                    _clean_text(r["target_l1"]),
                    _clean_text(r["from_date"]),
                ]
            )

        _SEARCH_INDEX_CACHE = {
            "l1": l1_list,
            "dynamic": dynamic_list,
            "intrinsic": ["国企改革"],
            "zibei": list(CLASSIC_ZIBEI_ORDER),
            "regions": region_list,
            "sector_counts": sector_counts,
            "stocks": items,
            "ma_events": ma_events_list,
        }
        return _SEARCH_INDEX_CACHE
    finally:
        conn.close()


_HIST_NOISE_TOPICS = {
    "其他",
    "次新股",
    "ST摘帽",
    "摘帽",
    "一季报增长",
    "中报增长",
    "三季报增长",
    "年报增长",
    "业绩增长",
    "业绩预增",
    "超跌",
    "超跌反弹",
    "低价",
    "低价股",
    "破净",
    "复牌",
    "公告",
}


def _clean_hist_token(tok: str) -> str:
    s = _clean_text(tok)
    if not s:
        return ""
    # Handle forms like "芯片(先进封装)" or "PCB概念(PCB)"
    m = re.match(r"^([^()（）]+)[(（]([^()（）]+)[)）]$", s)
    if m:
        outer, inner = m.group(1).strip(), m.group(2).strip()
        s = inner if len(inner) >= 2 and inner != outer else outer
    if s.endswith("概念") and len(s) >= 4:
        s = s[:-2]
    if s.endswith("本地") and len(s) >= 4:
        s = s[:-2]
    if s in _HIST_NOISE_TOPICS:
        return ""
    return s


def _format_history_reason(
    driver: str | None,
    driver2: str | None,
    kpl_topic: str | None,
    kpl_reason: str | None,
) -> str:
    d1 = _clean_hist_token(driver or "")
    d2 = _clean_hist_token(driver2 or "")
    if d1:
        return f"{d1} · {d2}" if d2 and d2 != d1 else d1

    t = _clean_hist_token(kpl_topic or "")
    if t:
        return t

    raw_r = _clean_text(kpl_reason or "")
    if raw_r:
        head = re.split(r"[；;。]", raw_r, maxsplit=1)[0].strip()
        if head and len(head) <= 28:
            parts: list[str] = []
            for p in re.split(r"[+、/]", head):
                cp = _clean_hist_token(p)
                if cp and cp not in parts:
                    parts.append(cp)
                if len(parts) >= 2:
                    break
            if parts:
                return " · ".join(parts)
    return ""


def _build_stock_profile(
    conn: sqlite3.Connection, code: str, latest_dt: str
) -> dict[str, Any] | None:
    st = conn.execute("SELECT * FROM stocks WHERE code = ?", (code,)).fetchone()
    hist_rows = conn.execute(
        """
        SELECT p.trade_date, p.name, p.board_height, p.boards_desc, p.first_limit_time,
               p.is_one_word, p.amount_yi, p.kpl_topic, p.kpl_reason,
               d.driver, d.driver2
        FROM daily_limit_pool p
        LEFT JOIN daily_stock_driver d ON d.trade_date = p.trade_date AND d.code = p.code
        WHERE p.code = ? AND p.trade_date >= ?
        ORDER BY p.trade_date DESC
        LIMIT 20
        """,
        (code, MIN_DISPLAY_DATE),
    ).fetchall()
    if not st and not hist_rows:
        return None

    name = _clean_text(st["name"]) if st and st["name"] else (_clean_text(hist_rows[0]["name"]) if hist_rows else code)
    prov = _short_prov(st["province"]) if st else ""
    ctrl_prov = _short_prov(st["controller_province"]) if st and st["controller_province"] else ""
    ctrl_type = (st["controller_type"] or "") if st else ""
    if ctrl_type == "民营及其他":
        ctrl_type = "民营"

    themes: list[str] = []
    seen_t: set[str] = set()
    evidences: list[dict[str, Any]] = []
    for r in conn.execute(
        "SELECT tag, from_date, evidence FROM stock_tags WHERE code = ? ORDER BY id ASC",
        (code,),
    ).fetchall():
        if not tag_is_active(r["from_date"], r["evidence"], latest_dt):
            continue
        t = _clean_text(r["tag"])
        if t and t not in seen_t:
            seen_t.add(t)
            themes.append(t)
            evidences.append(
                {
                    "theme": t,
                    "from_date": r["from_date"] or "",
                    "text": _clean_text(r["evidence"]),
                }
            )

    ma_events: list[dict[str, Any]] = []
    for m in conn.execute(
        "SELECT event_type, target_name, target_l1, from_date, evidence FROM ma_events WHERE code = ? ORDER BY from_date DESC, id ASC",
        (code,),
    ).fetchall():
        tl1 = _clean_text(m["target_l1"])
        if tl1 and tl1 not in seen_t:
            seen_t.add(tl1)
            themes.append(tl1)
        ma_events.append(
            {
                "type": _clean_text(m["event_type"]),
                "target": _clean_text(m["target_name"]),
                "target_l1": tl1,
                "from_date": m["from_date"] or "",
            }
        )

    for itag, iev in extract_intrinsic_tags(
        code,
        name,
        st["province"] if st else None,
        st["city"] if st else None,
        st["controller_province"] if st else None,
        st["controller_type"] if st else None,
    ):
        if itag not in seen_t:
            seen_t.add(itag)
            themes.append(itag)
            evidences.append({"theme": itag, "from_date": "", "text": iev})

    history = [
        {
            "date": r["trade_date"],
            "height": int(r["board_height"] or 1),
            "boards_desc": _clean_text(r["boards_desc"]),
            "first_time": (r["first_limit_time"] or "")[:5],
            "is_one_word": bool(r["is_one_word"]),
            "reason": _format_history_reason(r["driver"], r["driver2"], r["kpl_topic"], r["kpl_reason"]),
        }
        for r in hist_rows
    ]

    return {
        "code": code,
        "name": name,
        "province": prov,
        "controller_province": ctrl_prov if ctrl_prov and ctrl_prov != prov else "",
        "controller_type": ctrl_type,
        "industry": (st["em_industry"] or "") if st else "",
        "themes": themes,
        "evidences": evidences,
        "ma_events": ma_events,
        "history": history,
    }


def get_stock_profile(code: str) -> dict[str, Any] | None:
    conn = _conn()
    try:
        latest_row = conn.execute("SELECT MAX(trade_date) FROM daily_limit_pool").fetchone()
        latest_dt = str(latest_row[0] or "2026-11-27")
        return _build_stock_profile(conn, code, latest_dt)
    finally:
        conn.close()


def export_search_and_profiles(out_data: Path) -> None:
    """Export global search_index.json and 16 sharded stock archive JSONs for GitHub Pages."""
    idx = get_search_index(force_refresh=True)
    (out_data / "search_index.json").write_text(
        json.dumps(idx, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    out_stocks = out_data / "stocks"
    out_stocks.mkdir(parents=True, exist_ok=True)
    conn = _conn()
    try:
        latest_row = conn.execute("SELECT MAX(trade_date) FROM daily_limit_pool").fetchone()
        latest_dt = str(latest_row[0] or "2026-11-27")

        stock_meta = {
            r["code"]: dict(r)
            for r in conn.execute("SELECT * FROM stocks").fetchall()
        }
        tags_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in conn.execute("SELECT code, tag, from_date, evidence FROM stock_tags ORDER BY id ASC"):
            if tag_is_active(r["from_date"], r["evidence"], latest_dt):
                tags_by_code[r["code"]].append(dict(r))

        ma_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in conn.execute(
            "SELECT code, event_type, target_name, target_l1, from_date FROM ma_events ORDER BY from_date DESC, id ASC"
        ):
            ma_by_code[r["code"]].append(dict(r))

        hist_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        pool_name_by_code: dict[str, str] = {}
        for r in conn.execute(
            """
            SELECT p.code, p.trade_date, p.name, p.board_height, p.boards_desc,
                   p.first_limit_time, p.is_one_word, p.kpl_topic, p.kpl_reason,
                   d.driver, d.driver2
            FROM daily_limit_pool p
            LEFT JOIN daily_stock_driver d ON d.trade_date = p.trade_date AND d.code = p.code
            WHERE p.trade_date >= ?
            ORDER BY p.trade_date DESC
            """,
            (MIN_DISPLAY_DATE,),
        ):
            code = r["code"]
            if code not in pool_name_by_code and r["name"]:
                pool_name_by_code[code] = _clean_text(r["name"])
            if len(hist_by_code[code]) < 20:
                hist_by_code[code].append(
                    {
                        "date": r["trade_date"],
                        "height": int(r["board_height"] or 1),
                        "boards_desc": _clean_text(r["boards_desc"]),
                        "first_time": (r["first_limit_time"] or "")[:5],
                        "is_one_word": bool(r["is_one_word"]),
                        "reason": _format_history_reason(r["driver"], r["driver2"], r["kpl_topic"], r["kpl_reason"]),
                    }
                )

        shards: dict[str, dict[str, Any]] = {f"{i:02d}": {} for i in range(STOCK_SHARD_COUNT)}
        all_codes = sorted(set(stock_meta.keys()) | set(hist_by_code.keys()))
        for code in all_codes:
            st = stock_meta.get(code)
            prov = _short_prov(st["province"]) if st else ""
            ctrl_prov = _short_prov(st["controller_province"]) if st and st.get("controller_province") else ""
            ctrl_type = (st.get("controller_type") or "") if st else ""
            if ctrl_type == "民营及其他":
                ctrl_type = "民营"

            themes: list[str] = []
            seen_t: set[str] = set()
            evidences: list[dict[str, Any]] = []
            for tr in tags_by_code.get(code, []):
                t = _clean_text(tr["tag"])
                if t and t not in seen_t:
                    seen_t.add(t)
                    themes.append(t)
                    evidences.append(
                        {
                            "theme": t,
                            "from_date": tr["from_date"] or "",
                            "text": _clean_text(tr["evidence"]),
                        }
                    )
            ma_list: list[dict[str, Any]] = []
            for m in ma_by_code.get(code, []):
                tl1 = _clean_text(m.get("target_l1"))
                if tl1 and tl1 not in seen_t:
                    seen_t.add(tl1)
                    themes.append(tl1)
                ma_list.append(
                    {
                        "type": _clean_text(m["event_type"]),
                        "target": _clean_text(m["target_name"]),
                        "target_l1": tl1,
                        "from_date": m["from_date"] or "",
                    }
                )
            sname = _clean_text(st["name"]) if st and st.get("name") else pool_name_by_code.get(code, code)
            for itag, iev in extract_intrinsic_tags(
                code,
                sname,
                st.get("province") if st else None,
                st.get("city") if st else None,
                st.get("controller_province") if st else None,
                st.get("controller_type") if st else None,
            ):
                if itag not in seen_t:
                    seen_t.add(itag)
                    themes.append(itag)
                    evidences.append({"theme": itag, "from_date": "", "text": iev})
            shards[_stock_shard_id(code)][code] = {
                "code": code,
                "name": sname,
                "province": prov,
                "controller_province": ctrl_prov if ctrl_prov and ctrl_prov != prov else "",
                "controller_type": ctrl_type,
                "industry": (st.get("em_industry") or "") if st else "",
                "themes": themes,
                "evidences": evidences,
                "ma_events": ma_list,
                "history": hist_by_code.get(code, []),
            }

        for sid, data in shards.items():
            (out_stocks / f"{sid}.json").write_text(
                json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        print(f"Exported search index ({len(idx['stocks'])} stocks) and {STOCK_SHARD_COUNT} profile shards")
    finally:
        conn.close()


def _load_shares_cache() -> dict[str, dict[str, float]]:
    global _SHARES_CACHE
    if _SHARES_CACHE is not None:
        return _SHARES_CACHE
    with _INTRADAY_LOCK:
        if _SHARES_CACHE is not None:
            return _SHARES_CACHE
        if SHARES_CACHE_PATH.exists():
            try:
                raw = json.loads(SHARES_CACHE_PATH.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    _SHARES_CACHE = raw
                    return _SHARES_CACHE
            except Exception:
                pass
        _SHARES_CACHE = {}
        return _SHARES_CACHE


def _qt_symbol(code: str) -> str:
    prefix = "sh" if code.startswith(("6", "90")) else "bj" if code.startswith(("8", "4", "92")) else "sz"
    return f"{prefix}{code}"


def _batch_fetch_shares(codes: list[str]) -> None:
    """Batch-fetch total & float shares (亿股) for up to 60 stocks per single Tencent HTTP call."""
    cache = _load_shares_cache()
    missing = [c for c in dict.fromkeys(codes) if _CODE_RE.match(c) and c not in cache]
    if not missing:
        return
    updated = False
    for i in range(0, len(missing), 60):
        chunk = missing[i : i + 60]
        syms = ",".join(_qt_symbol(c) for c in chunk)
        url = f"https://qt.gtimg.cn/q={syms}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4.5) as resp:
                text = resp.read().decode("gbk", errors="ignore")
        except Exception:
            continue
        for line in text.splitlines():
            if '="' not in line:
                continue
            head, rest = line.split('="', 1)
            body = rest.split('"', 1)[0]
            m = re.search(r"(\d{6})$", head.strip())
            if not m:
                continue
            code = m.group(1)
            parts = body.split("~")
            if len(parts) <= 45:
                continue
            try:
                px = float(parts[3] or 0) or float(parts[4] or 0)
                float_mv = float(parts[44] or 0)
                total_mv = float(parts[45] or 0)
            except ValueError:
                continue
            if px <= 0 or (total_mv <= 0 and float_mv <= 0):
                continue
            if total_mv <= 0:
                total_mv = float_mv
            if float_mv <= 0:
                float_mv = total_mv
            with _INTRADAY_LOCK:
                cache[code] = {
                    "total_shares": round(total_mv / px, 6),
                    "float_shares": round(float_mv / px, 6),
                }
                updated = True
    if updated:
        with _INTRADAY_LOCK:
            try:
                SHARES_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                SHARES_CACHE_PATH.write_text(
                    json.dumps(cache, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8",
                )
            except Exception:
                pass


def _get_stock_shares(code: str) -> dict[str, float] | None:
    cache = _load_shares_cache()
    if code in cache:
        return cache[code]
    _batch_fetch_shares([code])
    return cache.get(code)


def _kpl_post_trend(code: str, date: str) -> dict[str, Any] | None:
    """Fetch 241-minute trend via thread-local HTTPS Keep-Alive connection (eliminates TLS handshake)."""
    body = urlencode(
        {
            "a": "GetStockTrend",
            "c": "StockL2History",
            "StockID": code,
            "Day": date,
            "apiv": "w38",
            "PhoneOSNew": "2",
            "VerSion": "5.17.0.9",
        }
    ).encode("utf-8")
    headers = {
        "User-Agent": "lhb/5.17.9 (com.kaipanla.www; build:0; iOS 16.6.0) Alamofire/4.9.1",
        "Content-Type": "application/x-www-form-urlencoded",
        "Connection": "keep-alive",
    }
    for attempt in range(2):
        conn: http.client.HTTPSConnection | None = getattr(_INTRADAY_TLS, "kpl_conn", None)
        if conn is None:
            conn = http.client.HTTPSConnection("apphis.longhuvip.com", timeout=5.5)
            _INTRADAY_TLS.kpl_conn = conn
        try:
            conn.request("POST", "/w1/api/index.php", body=body, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            if resp.status != 200:
                return None
            return json.loads(raw.decode("utf-8", errors="ignore"))
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            _INTRADAY_TLS.kpl_conn = None
            if attempt == 1:
                return None
    return None


def _lookup_pool_metrics(code: str, date: str) -> tuple[float | None, float | None]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT amount_yi, turnover_rate FROM daily_limit_pool WHERE trade_date=? AND code=? LIMIT 1",
            (date, code),
        ).fetchone()
        if not row:
            return None, None
        amt = float(row[0]) if row[0] is not None else None
        tr = float(row[1]) if row[1] is not None else None
        return amt, tr
    except Exception:
        return None, None
    finally:
        conn.close()


def _put_intraday_mem(mem_key: tuple[str, str], payload: dict[str, Any]) -> tuple[dict[str, Any], bytes, bytes]:
    raw, gz = _encode_json_pair(payload)
    entry = (payload, raw, gz)
    with _INTRADAY_LOCK:
        if len(_INTRADAY_MEM_CACHE) >= 360:
            _INTRADAY_MEM_CACHE.pop(next(iter(_INTRADAY_MEM_CACHE)))
        _INTRADAY_MEM_CACHE[mem_key] = entry
    return entry


def _load_day_bundle_cached(date: str) -> tuple[dict[str, Any], bytes, bytes] | None:
    """Load day-bundled intraday JSON from data/intraday_days/{date}.json with mtime/size auto-refresh."""
    if not _DATE_RE.match(date):
        return None
    p = INTRADAY_DAYS_DIR / f"{date}.json"
    if not p.exists():
        return None
    try:
        st = p.stat()
        mtime, size = st.st_mtime, st.st_size
    except OSError:
        return None
    hit = _INTRADAY_DAY_CACHE.get(date)
    if hit is not None and hit[0] == mtime and hit[1] == size:
        return hit[2], hit[3], hit[4]
    try:
        raw = p.read_bytes()
        doc = json.loads(raw.decode("utf-8"))
        if not isinstance(doc, dict):
            return None
        gz = gzip.compress(raw, compresslevel=5) if len(raw) >= 512 else b""
        with _INTRADAY_LOCK:
            if len(_INTRADAY_DAY_CACHE) >= 120:
                _INTRADAY_DAY_CACHE.pop(next(iter(_INTRADAY_DAY_CACHE)))
            _INTRADAY_DAY_CACHE[date] = (mtime, size, doc, raw, gz)
        return doc, raw, gz
    except Exception:
        return None


def get_intraday_day_pair(date: str) -> tuple[bytes, bytes]:
    """Return pre-encoded (raw, gz) day-bundled intraday JSON (or empty '{}' if not bundled yet)."""
    loaded = _load_day_bundle_cached(date)
    if loaded is not None:
        return loaded[1], loaded[2]
    # Fallback: merge any individual files already in data/raw_intraday/{date}/*.json
    if _DATE_RE.match(date):
        raw_dir = INTRADAY_DIR / date
        if raw_dir.exists():
            merged: dict[str, Any] = {}
            for fp in raw_dir.glob("*.json"):
                try:
                    doc = json.loads(fp.read_text(encoding="utf-8"))
                    if isinstance(doc, dict) and doc.get("points"):
                        merged[fp.stem] = doc
                except Exception:
                    pass
            if merged:
                return _encode_json_pair(merged)
    return b"{}", b""


def get_intraday_pair(code: str, date: str) -> tuple[bytes, bytes] | None:
    """Return pre-encoded (raw, gz) intraday JSON with day-bundle lookup + deduped keep-alive fallback."""
    if not _CODE_RE.match(code) or not _DATE_RE.match(date):
        return None

    mem_key = (date, code)
    hit = _INTRADAY_MEM_CACHE.get(mem_key)
    if hit is not None:
        return hit[1], hit[2]

    # Fast path 1: check day-bundled local cache (0.1ms!)
    loaded_day = _load_day_bundle_cached(date)
    if loaded_day is not None and code in loaded_day[0]:
        entry = _put_intraday_mem(mem_key, loaded_day[0][code])
        return entry[1], entry[2]

    disk_path = INTRADAY_DIR / date / f"{code}.json"
    if disk_path.exists():
        try:
            doc = json.loads(disk_path.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and doc.get("points"):
                entry = _put_intraday_mem(mem_key, doc)
                return entry[1], entry[2]
        except Exception:
            pass

    # Deduplicate concurrent requests for the same (date, code) (e.g. background warmer + live click)
    wait_ev: threading.Event | None = None
    own_ev: threading.Event | None = None
    with _INTRADAY_LOCK:
        hit = _INTRADAY_MEM_CACHE.get(mem_key)
        if hit is not None:
            return hit[1], hit[2]
        existing_ev = _INTRADAY_INFLIGHT.get(mem_key)
        if existing_ev is not None:
            wait_ev = existing_ev
        else:
            own_ev = threading.Event()
            _INTRADAY_INFLIGHT[mem_key] = own_ev

    if wait_ev is not None:
        wait_ev.wait(timeout=6.5)
        hit = _INTRADAY_MEM_CACHE.get(mem_key)
        return (hit[1], hit[2]) if hit is not None else None

    try:
        # Run shares lookup concurrently on dedicated live pool (never blocked by bg warmer!)
        shares_cache = _load_shares_cache()
        shares_fut = _LIVE_POOL.submit(_get_stock_shares, code) if code not in shares_cache else None
        raw_json = _kpl_post_trend(code, date)
        shares = shares_fut.result(timeout=5.0) if shares_fut is not None else shares_cache.get(code)
        if not raw_json:
            return None

        trend = raw_json.get("trend") or []
        if not isinstance(trend, list) or len(trend) < 2:
            return None

        points: list[list[Any]] = []
        for row in trend:
            if not isinstance(row, list) or len(row) < 4:
                continue
            try:
                px = round(float(row[1]), 3)
                avg = round(float(row[2]), 3)
                vol = int(float(row[3] or 0))
                d_flag = int(row[4]) if len(row) > 4 and row[4] is not None else 0
                points.append([px, avg, vol, d_flag])
            except Exception:
                continue

        if len(points) < 2:
            return None

        preclose = float(raw_json.get("preclose_px") or 0)
        if preclose <= 0:
            preclose = float(raw_json.get("begin_px") or points[0][0] or 0)
        close_px = points[-1][0]
        px_vals = [p[0] for p in points]
        high_px = max(px_vals)
        low_px = min(px_vals)
        pct = round((close_px - preclose) / preclose * 100.0, 2) if preclose > 0 else 0.0

        pool_amt, pool_tr = _lookup_pool_metrics(code, date)
        total_turnover = float(raw_json.get("total_turnover") or 0)
        amount_yi = (
            round(pool_amt, 2)
            if pool_amt is not None
            else (round(total_turnover / 1e8, 2) if total_turnover > 0 else None)
        )

        total_mv = round(shares["total_shares"] * close_px, 1) if shares and shares.get("total_shares") else None
        float_mv = round(shares["float_shares"] * close_px, 1) if shares and shares.get("float_shares") else None

        turnover = round(pool_tr, 2) if pool_tr is not None else None
        if turnover is None and float_mv and float_mv > 0 and amount_yi is not None:
            turnover = round(amount_yi / float_mv * 100.0, 2)

        payload: dict[str, Any] = {
            "code": code,
            "date": date,
            "preclose": round(preclose, 3),
            "price": round(close_px, 2),
            "pct": pct,
            "high": round(high_px, 2),
            "low": round(low_px, 2),
            "amount_yi": amount_yi,
            "turnover": turnover,
            "total_mv": total_mv,
            "float_mv": float_mv,
            "points": points,
        }

        entry = _put_intraday_mem(mem_key, payload)
        try:
            disk_path.parent.mkdir(parents=True, exist_ok=True)
            disk_path.write_bytes(entry[1])
        except Exception:
            pass
        return entry[1], entry[2]
    finally:
        if own_ev is not None:
            own_ev.set()
            with _INTRADAY_LOCK:
                _INTRADAY_INFLIGHT.pop(mem_key, None)


def get_intraday_payload(code: str, date: str) -> dict[str, Any] | None:
    pair = get_intraday_pair(code, date)
    if not pair:
        return None
    hit = _INTRADAY_MEM_CACHE.get((date, code))
    return hit[0] if hit is not None else json.loads(pair[0].decode("utf-8"))


def _warm_day_intraday_async(date: str, codes: list[str]) -> None:
    """Silently batch-warm any missing core ladder stocks' intraday charts in parallel."""
    if not date or not codes or date in _WARMED_INTRADAY_DATES:
        return
    # If day bundle already covers all core codes, skip background network work completely!
    loaded = _load_day_bundle_cached(date)
    if loaded is not None:
        missing = [c for c in codes if c not in loaded[0]]
        if not missing:
            with _INTRADAY_LOCK:
                _WARMED_INTRADAY_DATES.add(date)
            return
        codes = missing
    with _INTRADAY_LOCK:
        if date in _WARMED_INTRADAY_DATES:
            return
        _WARMED_INTRADAY_DATES.add(date)

    def _run() -> None:
        try:
            # Step 1: 1 single batch HTTP call (~80ms) fetches shares for ALL missing stocks on this day
            _batch_fetch_shares(codes)
            # Step 2: Parallel keep-alive Kaipanla fetches across 12 background worker threads
            futs = [_BG_WARM_POOL.submit(get_intraday_pair, c, date) for c in codes]
            for f in futs:
                try:
                    f.result(timeout=8.0)
                except Exception:
                    pass
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True, name=f"warm-id-{date}").start()


_ST_NAME_RE = re.compile(r"^(\*?ST|S\*?ST)", re.IGNORECASE)


def _load_index_klines() -> dict[str, dict[str, float]]:
    global _INDEX_KLINE_CACHE
    if _INDEX_KLINE_CACHE is not None:
        return _INDEX_KLINE_CACHE
    out: dict[str, dict[str, float]] = {}
    if INDEX_KLINE_PATH.exists():
        try:
            raw = json.loads(INDEX_KLINE_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for sym, rows in raw.items():
                    out[sym] = {str(r[0]): float(r[1]) for r in (rows or []) if len(r) >= 2 and float(r[1]) > 0}
        except Exception:
            pass
    _INDEX_KLINE_CACHE = out
    return out


def _fetch_single_kline_live(code: str) -> tuple[list[str], list[float], dict[str, int]] | None:
    if not _CODE_RE.match(code):
        return None
    sym = _qt_symbol(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,2025-07-01,2026-12-31,420,qfq"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5.5) as resp:
            doc = json.loads(resp.read().decode("utf-8", errors="ignore"))
        node = (doc.get("data") or {}).get(sym) or {}
        rows = node.get("qfqday") or node.get("day") or []
        parsed: list[list[Any]] = []
        for r in rows:
            if isinstance(r, list) and len(r) >= 3:
                dt = str(r[0])
                cl = round(float(r[2]), 4)
                if len(dt) == 10 and cl > 0:
                    parsed.append([dt, cl])
        if not parsed:
            return None
        KLINE_DIR.mkdir(parents=True, exist_ok=True)
        (KLINE_DIR / f"{code}.json").write_text(
            json.dumps({"code": code, "days": parsed}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        dates = [str(d[0]) for d in parsed]
        closes = [float(d[1]) for d in parsed]
        val = (dates, closes, {dt: i for i, dt in enumerate(dates)})
        _KLINE_CACHE[code] = val
        return val
    except Exception:
        return None


def _board_deviation_rules(code: str, name: str) -> dict[str, Any]:
    is_st = bool(_ST_NAME_RE.match((name or "").strip()))
    if code.startswith(("8", "4", "92")):
        return {
            "supported": False,
            "board": "北交所",
            "index_sym": "",
            "index_name": "",
            "limit_pct": 30.0,
            "thresh10": 100.0,
            "thresh30": 200.0,
            "short_thresh": 40.0,
            "short_max": 0,
        }
    if code.startswith("68"):
        return {
            "supported": True,
            "board": "科创板",
            "index_sym": "sh000688",
            "index_name": "科创50",
            "limit_pct": 20.0,
            "thresh10": 100.0,
            "thresh30": 200.0,
            "short_thresh": 30.0,
            "short_max": 3,
        }
    if code.startswith("30"):
        return {
            "supported": True,
            "board": "创业板",
            "index_sym": "sz399102",
            "index_name": "创业板综",
            "limit_pct": 20.0,
            "thresh10": 100.0,
            "thresh30": 200.0,
            "short_thresh": 30.0,
            "short_max": 3,
        }
    if code.startswith("60"):
        return {
            "supported": True,
            "board": "沪主板",
            "index_sym": "sh000002",
            "index_name": "上证A指",
            "limit_pct": 5.0 if is_st else 10.0,
            "thresh10": 50.0 if is_st else 100.0,
            "thresh30": 100.0 if is_st else 200.0,
            "short_thresh": 12.0 if is_st else 20.0,
            "short_max": 4,
        }
    return {
        "supported": True,
        "board": "深主板",
        "index_sym": "sz399107",
        "index_name": "深证A指",
        "limit_pct": 5.0 if is_st else 10.0,
        "thresh10": 50.0 if is_st else 100.0,
        "thresh30": 100.0 if is_st else 200.0,
        "short_thresh": 12.0 if is_st else 20.0,
        "short_max": 4,
    }


def compute_stock_deviation(
    code: str,
    name: str,
    target_date: str,
    allow_fetch: bool = False,
) -> dict[str, Any] | None:
    """Compute exact 10D/30D serious-anomaly deviation & next-day safe ceiling price/pct."""
    rules = _board_deviation_rules(code, name)
    if not rules["supported"]:
        if allow_fetch:
            return {
                "code": code,
                "name": name,
                "supported": False,
                "note": "北交所无10日100%/30日200%停牌红线",
            }
        return None

    idx_map = _load_index_klines().get(rules["index_sym"])
    if not idx_map:
        return None

    kl = _load_kline(code)
    if (kl is None or target_date not in kl[2]) and allow_fetch:
        kl = _fetch_single_kline_live(code)
    if kl is None:
        return None

    dates, closes, pos_map = kl
    end_idx = pos_map.get(target_date)
    if end_idx is None:
        # Stock may have been suspended on target_date; use last available date <= target_date if close
        if not allow_fetch:
            return None
        cand = [i for i, d in enumerate(dates) if d <= target_date]
        if not cand:
            return None
        end_idx = cand[-1]

    start_slice = max(0, end_idx - 75)
    dts: list[str] = []
    sc: list[float] = []
    ic: list[float] = []
    for i in range(start_slice, end_idx + 1):
        dt = dates[i]
        iv = idx_map.get(dt)
        sv = closes[i]
        if iv and iv > 0 and sv > 0:
            dts.append(dt)
            sc.append(sv)
            ic.append(iv)

    n = len(sc)
    if n < 3:
        return None
    t = n - 1

    thresh10 = rules["thresh10"]
    thresh30 = rules["thresh30"]
    short_thresh = rules["short_thresh"]
    short_max = rules["short_max"]
    limit_pct = rules["limit_pct"]

    reset10 = 0
    reset30 = 0
    reset3 = 0
    short_triggers: list[int] = []
    last_trig10 = ""
    last_trig30 = ""
    today_trig10 = False
    today_trig30 = False
    cur_dev10 = 0.0
    cur_dev30 = 0.0
    cur_short_cnt = 0

    for i in range(1, n):
        # 1) Ordinary 3-day anomaly tracking
        s3_start = max(reset3, i - 3)
        max_dev3 = -999.0
        for b in range(s3_start, i):
            dv = ((sc[i] / sc[b] - 1.0) - (ic[i] / ic[b] - 1.0)) * 100.0
            if dv > max_dev3:
                max_dev3 = dv
        if max_dev3 >= short_thresh:
            short_triggers.append(i)
            reset3 = i

        # 2) 10-day serious anomaly check (cumulative deviation >= thresh10 OR N ordinary anomalies in 10d)
        s10_start = max(reset10, i - 10)
        max_dev10 = -999.0
        for b in range(s10_start, i):
            dv = ((sc[i] / sc[b] - 1.0) - (ic[i] / ic[b] - 1.0)) * 100.0
            if dv > max_dev10:
                max_dev10 = dv
        short_in_10 = sum(1 for idx_tr in short_triggers if idx_tr > s10_start and idx_tr <= i)

        # 3) 30-day serious anomaly check
        s30_start = max(reset30, i - 30)
        max_dev30 = -999.0
        for b in range(s30_start, i):
            dv = ((sc[i] / sc[b] - 1.0) - (ic[i] / ic[b] - 1.0)) * 100.0
            if dv > max_dev30:
                max_dev30 = dv

        if i == t:
            cur_dev10 = round(max_dev10, 1)
            cur_dev30 = round(max_dev30, 1)
            cur_short_cnt = short_in_10
            if max_dev10 >= thresh10 or (short_max > 0 and short_in_10 >= short_max):
                today_trig10 = True
            if max_dev30 >= thresh30:
                today_trig30 = True
        else:
            if max_dev10 >= thresh10 or (short_max > 0 and short_in_10 >= short_max):
                reset10 = i
                last_trig10 = dts[i]
            if max_dev30 >= thresh30:
                reset30 = i
                last_trig30 = dts[i]

    # Compute tomorrow (t+1) safe ceiling assuming benchmark index stays flat (ic[t+1] == ic[t])
    eff_r10 = t if today_trig10 else reset10
    b10_start = max(eff_r10, t - 9)
    safe_px10 = min(sc[b] * (ic[t] / ic[b] + thresh10 / 100.0) for b in range(b10_start, t + 1))
    safe_pct10 = (safe_px10 / sc[t] - 1.0) * 100.0

    eff_r30 = t if today_trig30 else reset30
    b30_start = max(eff_r30, t - 29)
    safe_px30 = min(sc[b] * (ic[t] / ic[b] + thresh30 / 100.0) for b in range(b30_start, t + 1))
    safe_pct30 = (safe_px30 / sc[t] - 1.0) * 100.0

    if safe_pct10 <= safe_pct30:
        bind_rule = "10d"
        bind_safe_pct = safe_pct10
        bind_safe_px = safe_px10
    else:
        bind_rule = "30d"
        bind_safe_pct = safe_pct30
        bind_safe_px = safe_px30

    # Check if tomorrow's limit-up would trigger the N-th ordinary 3-day anomaly
    short_next_danger = False
    if not today_trig10 and short_max > 0:
        next_short_in_10 = sum(1 for idx_tr in short_triggers if idx_tr > b10_start and idx_tr <= t)
        if next_short_in_10 >= short_max - 1:
            b3_start = max(reset3, t - 2)
            p_lim = sc[t] * (1.0 + limit_pct / 100.0)
            for b in range(b3_start, t + 1):
                dv = ((p_lim / sc[b] - 1.0) - (ic[t] / ic[b] - 1.0)) * 100.0
                if dv >= short_thresh:
                    short_next_danger = True
                    break

    two_board_cap = 35.0 if limit_pct >= 20.0 else (10.5 if limit_pct <= 5.0 else 21.0)
    if today_trig10 or today_trig30:
        status = "triggered"
    elif bind_safe_pct <= limit_pct or short_next_danger:
        status = "critical"
    elif bind_safe_pct <= two_board_cap:
        status = "warning"
    else:
        status = "safe"

    return {
        "code": code,
        "name": name,
        "supported": True,
        "close": round(sc[t], 2),
        "limit_pct": limit_pct,
        "index_name": rules["index_name"],
        "thresh10": int(thresh10),
        "thresh30": int(thresh30),
        "dev10": cur_dev10,
        "dev30": cur_dev30,
        "safe_pct10": round(safe_pct10, 1),
        "safe_px10": round(safe_px10, 2),
        "safe_pct30": round(safe_pct30, 1),
        "safe_px30": round(safe_px30, 2),
        "bind_rule": bind_rule,
        "bind_safe_pct": round(bind_safe_pct, 1),
        "bind_safe_px": round(bind_safe_px, 2),
        "short_cnt": cur_short_cnt,
        "short_max": short_max,
        "short_next_danger": short_next_danger,
        "trig10_today": today_trig10,
        "trig30_today": today_trig30,
        "last_trig10": last_trig10 if (last_trig10 and (t - reset10) <= 10) else "",
        "last_trig30": last_trig30 if (last_trig30 and (t - reset30) <= 15) else "",
        "status": status,
    }


def _trace_run_dates(
    conn: sqlite3.Connection,
    codes: list[str],
    ref_date: str,
    target_heights: dict[str, int],
) -> tuple[dict[str, str], dict[str, str]]:
    """Trace consecutive-board runs backwards to exact 1B (first_board_date) and 2B dates.

    Handles both normal consecutive runs and suspended-then-resumed runs by stepping
    strictly along board_height = h, h-1, ..., 1 in daily_limit_pool (<= 45 calendar days per step).
    """
    if not codes:
        return {}, {}
    ph = ",".join("?" for _ in codes)
    # Fetch up to ~90 calendar days back so even 20-board + multi-week suspension runs resolve cleanly
    try:
        y, m, d = map(int, ref_date.split("-"))
        min_dt = dt_date.fromordinal(dt_date(y, m, d).toordinal() - 120).isoformat()
    except Exception:
        min_dt = "2024-01-01"

    rows = conn.execute(
        f"""
        SELECT code, trade_date, board_height
        FROM daily_limit_pool
        WHERE code IN ({ph}) AND trade_date <= ? AND trade_date >= ?
        ORDER BY code ASC, trade_date DESC
        """,
        (*codes, ref_date, min_dt),
    ).fetchall()

    by_code: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for r in rows:
        by_code[r["code"]].append((str(r["trade_date"]), int(r["board_height"] or 1)))

    fb_map: dict[str, str] = {}
    b2_map: dict[str, str] = {}
    for code, start_h in target_heights.items():
        if start_h < 2:
            continue
        hist = by_code.get(code) or []
        cur_h = start_h
        last_ord: int | None = None
        d2: str | None = None
        d1: str | None = None
        for td, bh in hist:
            if bh != cur_h:
                continue
            try:
                cur_ord = dt_date.fromisoformat(td).toordinal()
            except Exception:
                continue
            if last_ord is not None and (last_ord - cur_ord) > 45:
                break
            last_ord = cur_ord
            if cur_h == 2:
                d2 = td
            if cur_h == 1:
                d1 = td
                break
            cur_h -= 1
        if d1:
            fb_map[code] = d1
        if d2:
            b2_map[code] = d2
    return fb_map, b2_map


def _compute_day_replenishments(
    conn: sqlite3.Connection,
    date: str,
    raw_stocks: dict[str, dict[str, Any]],
    stock_meta: dict[str, dict[str, Any]],
    tags_by_code: dict[str, list[dict[str, Any]]],
    ma_by_code: dict[str, list[dict[str, Any]]],
) -> None:
    """Annotate multi-board ladder stocks (>=2B, non-ST) with 5B+ replenishment ('补') hits.

    Exact 32-theme + 5B-threshold rule:
      1) Find candidate's exact first_board_date (fb_date).
      2) Gather all active >=5B non-ST leaders on fb_date:
         - Still limiting up on fb_date with board_height >= 5 ('N连板'), OR
         - Was >=5B on prev_trade_date(fb_date), broke on fb_date, and was NOT suspended ('N板断板').
      3) Each leader's unique main theme is fixed on its 2B date (fallback: ref_date driver -> 1st stock_tag).
      4) If leader's unique main theme hits ANY valid attribute of candidate on fb_date
         (cleaned 32-word stock_tags + active ma_events <= fb_date + permanent 字辈/地域),
         mark candidate with st['replenish'] explaining the exact hit chain & evidence.
    """
    cands: dict[str, int] = {}
    for code, st in raw_stocks.items():
        h = int(st.get("height") or 1)
        nm = str(st.get("name") or "")
        if h >= 2 and "ST" not in nm.upper():
            cands[code] = h
    if not cands:
        return

    fb_map, _ = _trace_run_dates(conn, list(cands.keys()), date, cands)
    if not fb_map:
        return

    obs_dates = sorted(set(fb_map.values()))
    all_dates = [
        str(r[0])
        for r in conn.execute(
            "SELECT DISTINCT trade_date FROM daily_limit_pool WHERE trade_date <= ? ORDER BY trade_date ASC",
            (date,),
        ).fetchall()
    ]
    date_pos = {d: i for i, d in enumerate(all_dates)}

    # Gather >=5B leaders (active + same-day broken non-suspended) for each unique observation date
    leaders_by_obs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    leader_trace_req: dict[tuple[str, str], int] = {}  # (code, ref_date) -> height

    for fb_dt in obs_dates:
        idx = date_pos.get(fb_dt)
        prev_fb_dt = all_dates[idx - 1] if (idx is not None and idx > 0) else None

        active_codes_on_fb: set[str] = set()
        for r in conn.execute(
            """
            SELECT code, name, board_height
            FROM daily_limit_pool
            WHERE trade_date = ?
            """,
            (fb_dt,),
        ).fetchall():
            c = str(r["code"])
            active_codes_on_fb.add(c)
            h = int(r["board_height"] or 1)
            nm = _clean_text(r["name"]) or c
            if h >= 5 and "ST" not in nm.upper():
                leaders_by_obs[fb_dt].append(
                    {
                        "code": c,
                        "name": nm,
                        "height": h,
                        "status": f"{h}连板",
                        "is_broken": False,
                        "ref_date": fb_dt,
                    }
                )
                leader_trace_req[(c, fb_dt)] = h

        if prev_fb_dt:
            for r in conn.execute(
                """
                SELECT code, name, board_height
                FROM daily_limit_pool
                WHERE trade_date = ? AND board_height >= 5
                """,
                (prev_fb_dt,),
            ).fetchall():
                c = str(r["code"])
                if c in active_codes_on_fb:
                    continue
                nm = _clean_text(r["name"]) or c
                if "ST" in nm.upper():
                    continue
                # Exclude suspended stocks: if kline spans past fb_dt and fb_dt is absent -> suspended
                kl = _load_kline(c)
                if kl is not None:
                    kl_dates, _, kl_pos = kl
                    if kl_dates and kl_dates[-1] >= fb_dt and fb_dt not in kl_pos:
                        continue
                h = int(r["board_height"] or 5)
                leaders_by_obs[fb_dt].append(
                    {
                        "code": c,
                        "name": nm,
                        "height": h,
                        "status": f"{h}板断板",
                        "is_broken": True,
                        "ref_date": prev_fb_dt,
                    }
                )
                leader_trace_req[(c, prev_fb_dt)] = h

    if not leader_trace_req:
        return

    # Resolve each leader's fixed 2B main theme
    leader_2b_date: dict[tuple[str, str], str] = {}
    by_ref_date: dict[str, dict[str, int]] = defaultdict(dict)
    for (lc, lref), lh in leader_trace_req.items():
        by_ref_date[lref][lc] = lh
    for lref, cmap in by_ref_date.items():
        _, b2_sub = _trace_run_dates(conn, list(cmap.keys()), lref, cmap)
        for lc, d2 in b2_sub.items():
            leader_2b_date[(lc, lref)] = d2

    drv_lookup_pairs: set[tuple[str, str]] = set()
    leader_codes_all: set[str] = set()
    for (lc, lref) in leader_trace_req:
        leader_codes_all.add(lc)
        drv_lookup_pairs.add((lc, lref))
        if (lc, lref) in leader_2b_date:
            drv_lookup_pairs.add((lc, leader_2b_date[(lc, lref)]))

    drv_map: dict[tuple[str, str], str] = {}
    if leader_codes_all:
        l_dates = sorted({dt for _, dt in drv_lookup_pairs})
        ph_c = ",".join("?" for _ in leader_codes_all)
        ph_d = ",".join("?" for _ in l_dates)
        for r in conn.execute(
            f"""
            SELECT trade_date, code, driver
            FROM daily_stock_driver
            WHERE code IN ({ph_c}) AND trade_date IN ({ph_d})
              AND driver IS NOT NULL AND driver != ''
            """,
            (*leader_codes_all, *l_dates),
        ).fetchall():
            drv_map[(str(r["code"]), str(r["trade_date"]))] = _clean_text(r["driver"])

    leader_fallback_tag: dict[str, str] = {}
    if leader_codes_all:
        ph_c = ",".join("?" for _ in leader_codes_all)
        for r in conn.execute(
            f"SELECT code, tag FROM stock_tags WHERE code IN ({ph_c}) ORDER BY id ASC",
            (*leader_codes_all,),
        ).fetchall():
            c = str(r["code"])
            if c not in leader_fallback_tag and r["tag"]:
                leader_fallback_tag[c] = _clean_text(r["tag"])

    for fb_dt, l_list in leaders_by_obs.items():
        for ld in l_list:
            lc, lref = ld["code"], ld["ref_date"]
            d2 = leader_2b_date.get((lc, lref))
            main_t = (
                (drv_map.get((lc, d2)) if d2 else "")
                or drv_map.get((lc, lref))
                or leader_fallback_tag.get(lc, "")
            )
            ld["main_theme"] = main_t
        l_list.sort(key=lambda x: (-x["height"], int(x["is_broken"]), x["code"]))

    # Match each candidate against its first_board_date high-board leaders
    for code, fb_dt in fb_map.items():
        l_list = leaders_by_obs.get(fb_dt)
        if not l_list:
            continue
        st = raw_stocks[code]
        meta = stock_meta.get(code)
        cand_name = st["name"]

        # Candidate's full valid attribute -> evidence map as of fb_dt
        cand_ev: dict[str, str] = {}
        for t_row in tags_by_code.get(code, []):
            t = _clean_text(t_row.get("tag"))
            if t and t not in cand_ev:
                cand_ev[t] = _clean_text(t_row.get("evidence"))
        for m in ma_by_code.get(code, []):
            mfd = _clean_text(m.get("from_date"))
            if mfd and mfd > fb_dt:
                continue
            ma_ev = f"{m['event_type']}：{m['target_name']}"
            cand_ev.setdefault("并购", ma_ev)
            tl1 = _clean_text(m.get("target_l1"))
            if tl1 and tl1 not in cand_ev:
                cand_ev[tl1] = ma_ev
        for itag, iev in extract_intrinsic_tags(
            code,
            cand_name,
            meta.get("province") if meta else None,
            meta.get("city") if meta else None,
            meta.get("controller_province") if meta else None,
            meta.get("controller_type") if meta else None,
        ):
            if itag not in cand_ev:
                cand_ev[itag] = iev

        cand_main = st.get("driver") or st.get("primary_theme") or ""
        hits: list[dict[str, Any]] = []
        seen_hit: set[tuple[str, str]] = set()
        for ld in l_list:
            if ld["code"] == code:
                continue
            l_theme = ld.get("main_theme") or ""
            if not l_theme or l_theme not in cand_ev:
                continue
            hk = (ld["code"], l_theme)
            if hk in seen_hit:
                continue
            seen_hit.add(hk)
            kind = "同向补涨" if (cand_main and cand_main == l_theme) else "跨线补涨"
            hits.append(
                {
                    "leader_code": ld["code"],
                    "leader_name": ld["name"],
                    "leader_height": ld["height"],
                    "leader_status": ld["status"],
                    "theme": l_theme,
                    "kind": kind,
                    "evidence": cand_ev.get(l_theme, ""),
                }
            )

        if hits:
            st["replenish"] = {
                "fb_date": fb_dt,
                "kind": "跨线补涨" if any(h["kind"] == "跨线补涨" for h in hits) else "同向补涨",
                "hits": hits,
            }


def compute_day_deviations(
    conn: sqlite3.Connection,
    date: str,
    raw_stocks: dict[str, dict[str, Any]],
    broken_boards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Scan today's core ladder + recent 30d active strong stocks for 卡异动 alerts."""
    if not _load_index_klines():
        return []

    cand_names: dict[str, str] = {}
    for code, st in raw_stocks.items():
        cand_names[code] = st["name"]
    broken_map: dict[str, dict[str, Any]] = {}
    for b in broken_boards:
        c = b.get("code")
        if c:
            broken_map[c] = b
            cand_names.setdefault(c, b.get("name") or c)

    # Also include stocks with >= 2 limit-ups in the past 35 calendar days (~25 trading days)
    # so resting / trend-control ("卡异动洗盘") stocks not limiting up today are caught too!
    recent_dates = [
        str(r[0])
        for r in conn.execute(
            "SELECT DISTINCT trade_date FROM daily_limit_pool WHERE trade_date <= ? ORDER BY trade_date DESC LIMIT 30",
            (date,),
        ).fetchall()
    ]
    if recent_dates:
        start_dt = recent_dates[-1]
        for r in conn.execute(
            """
            SELECT code, MAX(name) AS name
            FROM daily_limit_pool
            WHERE trade_date >= ? AND trade_date <= ?
            GROUP BY code
            HAVING COUNT(*) >= 2 OR MAX(board_height) >= 2
            """,
            (start_dt, date),
        ):
            c = str(r["code"])
            if c not in cand_names:
                cand_names[c] = _clean_text(r["name"]) or c

    alerts: list[dict[str, Any]] = []
    for code, name in cand_names.items():
        res = compute_stock_deviation(code, name, date, allow_fetch=False)
        if not res or res.get("status") not in ("triggered", "critical", "warning"):
            continue
        st = raw_stocks.get(code)
        br = broken_map.get(code)
        res["height"] = st["height"] if st else 0
        res["boards_desc"] = st["boards_desc"] if st else (f"昨{br['prev_height']}板断" if br else "")
        res["theme"] = st["primary_theme"] if st else (br.get("theme") or "" if br else "")
        res["is_today_core"] = bool(st)
        alerts.append(res)

    status_rank = {"triggered": 0, "critical": 1, "warning": 2}
    alerts.sort(
        key=lambda x: (
            status_rank.get(x["status"], 9),
            -(max(x["dev10"] / max(1, x["thresh10"]), x["dev30"] / max(1, x["thresh30"])))
            if x["status"] == "triggered"
            else x["bind_safe_pct"],
            -x.get("height", 0),
        )
    )
    return alerts[:36]


class SuperBoardHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        # Quiet concise logs
        return

    def _accepts_gzip(self) -> bool:
        ae = self.headers.get("Accept-Encoding") or ""
        return "gzip" in ae.lower()

    def _send_encoded(
        self, raw: bytes, gz: bytes, content_type: str, cache_control: str, status: int = 200
    ) -> None:
        use_gz = bool(gz) and self._accepts_gzip()
        body = gz if use_gz else raw
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        if use_gz:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        raw, gz = _encode_json_pair(payload)
        self._send_encoded(raw, gz, "application/json; charset=utf-8", "no-store", status=status)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        mime, _ = mimetypes.guess_type(str(path))
        compressible = False
        if path.suffix == ".js":
            mime = "application/javascript; charset=utf-8"
            compressible = True
        elif path.suffix == ".css":
            mime = "text/css; charset=utf-8"
            compressible = True
        elif path.suffix == ".html":
            mime = "text/html; charset=utf-8"
            compressible = True
        elif path.suffix == ".json":
            mime = "application/json; charset=utf-8"
            compressible = True
        data = path.read_bytes()
        gz = gzip.compress(data, compresslevel=5) if compressible and len(data) >= 512 else b""
        cc = "public, max-age=86400" if path.suffix in (".jpg", ".jpeg", ".png", ".webp", ".svg") else "no-cache"
        self._send_encoded(data, gz, mime or "application/octet-stream", cc)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/dates":
            raw, gz = _get_cached_dates_pair()
            self._send_encoded(raw, gz, "application/json; charset=utf-8", "no-cache")
            return
        if path == "/api/day":
            qs = parse_qs(parsed.query)
            date = qs.get("date", [None])[0]
            raw, gz = _get_cached_day_pair(date)
            self._send_encoded(raw, gz, "application/json; charset=utf-8", "no-cache")
            return
        if path == "/api/search-index":
            raw, gz = _get_cached_search_pair()
            self._send_encoded(raw, gz, "application/json; charset=utf-8", "no-cache")
            return
        if path == "/api/stock":
            qs = parse_qs(parsed.query)
            code = (qs.get("code", [""])[0] or "").strip()
            prof = get_stock_profile(code) if code else None
            if not prof:
                self._send_json({"error": "not_found"}, status=404)
            else:
                self._send_json(prof)
            return
        if path == "/api/deviation-stock":
            qs = parse_qs(parsed.query)
            code = (qs.get("code", [""])[0] or "").strip()
            date = (qs.get("date", [""])[0] or "").strip()
            name = (qs.get("name", [""])[0] or "").strip()
            if not code or not date:
                self._send_json({"error": "bad_params"}, status=400)
                return
            if not name:
                prof = get_stock_profile(code)
                name = prof["name"] if prof else code
            res = compute_stock_deviation(code, name, date, allow_fetch=True)
            if not res:
                self._send_json({"error": "not_found"}, status=404)
            else:
                self._send_json(res)
            return
        if path == "/api/intraday-day":
            qs = parse_qs(parsed.query)
            date = (qs.get("date", [""])[0] or "").strip()
            raw, gz = get_intraday_day_pair(date) if date else (b"{}", b"")
            self._send_encoded(raw, gz, "application/json; charset=utf-8", "no-cache")
            return
        if path == "/api/intraday":
            qs = parse_qs(parsed.query)
            code = (qs.get("code", [""])[0] or "").strip()
            date = (qs.get("date", [""])[0] or "").strip()
            pair = get_intraday_pair(code, date) if code and date else None
            if not pair:
                self._send_json({"error": "not_found"}, status=404)
            else:
                self._send_encoded(pair[0], pair[1], "application/json; charset=utf-8", "public, max-age=3600")
            return

        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (WEB_DIR / rel).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())):
            self.send_error(403)
            return
        self._send_file(target)


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def export_static_site(limit: int = 400) -> None:
    """Export compact static JSON snapshots into web/data/ for GitHub Pages."""
    _DAY_DISPLAY_CACHE.clear()
    _DAY_THEME_STATS_CACHE.clear()
    out_data = WEB_DIR / "data"
    out_days = out_data / "days"
    out_days.mkdir(parents=True, exist_ok=True)
    (WEB_DIR / ".nojekyll").write_text("", encoding="utf-8")

    all_dates = get_available_dates(limit=limit)[:limit]
    payloads_by_date: dict[str, dict[str, Any]] = {}
    for d_info in reversed(all_dates):
        dt = d_info["date"]
        payload = get_day_payload(dt)
        payloads_by_date[dt] = payload
        (out_days / f"{dt}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    for d_info in all_dates:
        dt = d_info["date"]
        day_pl = payloads_by_date.get(dt) or {}
        st_map = day_pl.get("stocks") or {}
        for ldr in d_info.get("top_leaders") or []:
            st = st_map.get(ldr.get("code"))
            if st:
                exact_theme = _clean_text(st.get("primary_theme") or st.get("driver"))
                if exact_theme:
                    ldr["theme"] = exact_theme
        if day_pl.get("mood"):
            d_info["mood"] = day_pl["mood"]

    (out_data / "dates.json").write_text(
        json.dumps({"dates": all_dates}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    export_search_and_profiles(out_data)
    # Copy day-bundled intraday caches into web/data/intraday/ for zero-latency static GitHub Pages charts
    if INTRADAY_DAYS_DIR.exists():
        out_id = out_data / "intraday"
        out_id.mkdir(parents=True, exist_ok=True)
        exported_id = 0
        for d_info in all_dates:
            dt = d_info["date"]
            src = INTRADAY_DAYS_DIR / f"{dt}.json"
            if src.exists():
                (out_id / f"{dt}.json").write_bytes(src.read_bytes())
                exported_id += 1
        if exported_id:
            print(f"Exported {exported_id} day-bundled intraday caches to {out_id}")
    print(f"Exported {len(all_dates)} trading days to {out_data}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Super-Board Mobile Web Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--export-site", action="store_true", help="Export static site JSONs to web/data/ for GitHub Pages")
    parser.add_argument("--days", type=int, default=400, help="Number of recent trading days to export (from 2025-10-01 onward)")
    args = parser.parse_args()

    if args.export_site:
        export_static_site(limit=args.days)
        return

    server = ThreadingHTTPServer((args.host, args.port), SuperBoardHandler)
    threading.Thread(target=_warm_server_cache, daemon=True).start()
    lan_ip = _local_ip()
    print(f"Super-Board Mobile UI running:")
    print(f"  Local : http://127.0.0.1:{args.port}")
    print(f"  Mobile: http://{lan_ip}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
