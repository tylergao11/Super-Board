"""Lightweight stdlib HTTP server & JSON serializer for Super-Board Mobile Web UI."""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import socket
import sqlite3
import urllib.request
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data/super_board.sqlite"
WEB_DIR = ROOT / "web"
ULTRA_BOARD_RAW = Path(r"C:\Ai\Ultra-Board\data\kaipanla\raw")
MOOD_CACHE_PATH = ROOT / "data/market_mood_cache.json"
_MOOD_CACHE: dict[str, dict[str, Any]] | None = None

# Map noisy market topic labels to clean unified Super-Board themes (never exposing dirty tags)
TOPIC_TO_PURE_THEME: list[tuple[str, str]] = [
    ("商业航天", "商业航天"),
    ("卫星", "商业航天"),
    ("火箭", "商业航天"),
    ("低空", "低空经济"),
    ("飞行汽车", "低空经济"),
    ("无人机", "低空经济"),
    ("人形机器人", "机器人"),
    ("机器人", "机器人"),
    ("具身", "机器人"),
    ("电子皮肤", "机器人"),
    ("丝杠", "机器人"),
    ("减速器", "机器人"),
    ("AI应用", "AI应用"),
    ("人工智能", "AI应用"),
    ("大模型", "AI应用"),
    ("智能体", "AI应用"),
    ("华为", "华为链"),
    ("昇腾", "华为链"),
    ("鸿蒙", "华为链"),
    ("信创", "国产替代/信创"),
    ("国产替代", "国产替代/信创"),
    ("光刻", "芯片"),
    ("半导体", "芯片"),
    ("芯片", "芯片"),
    ("GPU", "芯片"),
    ("存储", "芯片"),
    ("封装", "芯片"),
    ("算力", "算力"),
    ("数据中心", "算力"),
    ("AIDC", "算力"),
    ("液冷", "算力"),
    ("交换机", "算力"),
    ("光模块", "通信"),
    ("CPO", "通信"),
    ("通信", "通信"),
    ("PCB", "消费电子"),
    ("元器件", "消费电子"),
    ("消费电子", "消费电子"),
    ("苹果", "苹果链"),
    ("特斯拉", "特斯拉链"),
    ("英伟达", "英伟达链"),
    ("海洋", "海洋经济"),
    ("水产", "海洋经济"),
    ("渔业", "海洋经济"),
    ("氢能", "氢能源"),
    ("核聚变", "可控核聚变"),
    ("量子", "量子科技"),
    ("脑机", "脑机接口"),
    ("海峡", "海峡两岸"),
    ("福建", "海峡两岸"),
    ("并购", "并购"),
    ("重组", "并购"),
    ("股权转让", "并购"),
    ("要约", "并购"),
    ("控制权", "并购"),
    ("零售", "消费"),
    ("免税", "消费"),
    ("百货", "消费"),
    ("冰雪", "消费"),
    ("旅游", "消费"),
    ("食品", "消费"),
    ("酿酒", "消费"),
    ("造纸", "消费"),
    ("消费", "消费"),
    ("固态电池", "锂电"),
    ("锂电", "锂电"),
    ("储能", "锂电"),
    ("电池", "锂电"),
    ("光伏", "光伏"),
    ("风电", "电力"),
    ("核电", "电力"),
    ("绿电", "电力"),
    ("电力", "电力"),
    ("电网", "电力"),
    ("特高压", "电力"),
    ("军工", "军工"),
    ("航空", "军工"),
    ("航展", "军工"),
    ("舰载机", "军工"),
    ("智能驾驶", "汽车"),
    ("汽车", "汽车"),
    ("机械", "机械"),
    ("黄金", "有色"),
    ("稀土", "有色"),
    ("有色", "有色"),
    ("铜", "有色"),
    ("铝", "有色"),
    ("甲醇", "化工"),
    ("尿素", "化工"),
    ("染料", "化工"),
    ("化工", "化工"),
    ("医药", "医药"),
    ("创新药", "医药"),
    ("中药", "医药"),
    ("医疗", "医药"),
    ("农业", "农业"),
    ("猪肉", "农业"),
    ("环保", "环保"),
    ("石油", "石油"),
    ("油气", "石油"),
    ("煤炭", "煤炭"),
    ("地产", "地产"),
    ("房地产", "地产"),
    ("基建", "基建"),
    ("建筑", "基建"),
    ("金融", "金融"),
    ("券商", "金融"),
    ("银行", "金融"),
    ("传媒", "传媒"),
    ("游戏", "传媒"),
    ("影视", "传媒"),
    ("软件", "软件"),
    ("交运", "交运"),
    ("航运", "交运"),
    ("物流", "交运"),
]

THEME_ACCENTS: dict[str, str] = {
    "商业航天": "coral",
    "AI应用": "amber",
    "机器人": "cyan",
    "算力": "blue",
    "芯片": "indigo",
    "海洋经济": "teal",
    "消费": "rose",
    "并购": "violet",
    "通信": "violet",
    "华为链": "sky",
    "国产替代/信创": "sky",
    "军工": "emerald",
    "化工": "ochre",
    "医药": "mint",
    "电力": "lime",
    "有色": "amber",
    "锂电": "teal",
    "光伏": "ochre",
    "汽车": "cyan",
    "机械": "slate",
    "消费电子": "indigo",
    "软件": "blue",
    "传媒": "rose",
    "低空经济": "coral",
    "氢能源": "emerald",
    "可控核聚变": "violet",
    "海峡两岸": "coral",
}

NEWS_EVENT_SHORT_TITLES: list[tuple[str, str, str]] = [
    ("“金”字", "金字辈", "amber"),
    ("金字辈", "金字辈", "amber"),
    ("字辈", "字辈暗线", "amber"),
    ("羊年", "羊年暗线", "amber"),
    ("生肖", "生肖暗线", "amber"),
    ("并购", "并购", "violet"),
    ("股权转让", "并购", "violet"),
    ("要约", "并购", "violet"),
    ("SpaceX", "商业航天", "coral"),
    ("卫星", "商业航天", "coral"),
    ("航天", "商业航天", "coral"),
    ("神舟", "商业航天", "coral"),
    ("舰载机", "商业航天", "coral"),
    ("航展", "军工", "emerald"),
    ("宇树", "机器人", "cyan"),
    ("具身", "机器人", "cyan"),
    ("机器人", "机器人", "cyan"),
    ("PCB", "消费电子", "indigo"),
    ("覆铜板", "消费电子", "indigo"),
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
    ("冰雪", "消费", "rose"),
    ("灵顺寺", "消费", "rose"),
    ("零售", "消费", "rose"),
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
    return THEME_ACCENTS.get(theme, "slate")


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
                if tc is not None:
                    entry["zb_count"] = int(tc)
                    changed = True
        except Exception:
            pass

    if changed:
        cache[date] = entry
        _save_mood_cache()

    zb = entry.get("zb_count")
    zb_rate = None
    if zb is not None and (zt_count + zb) > 0:
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


def get_available_dates() -> list[dict[str, Any]]:
    conn = _conn()
    try:
        news_counts = {
            r["trade_date"]: r["cnt"]
            for r in conn.execute(
                "SELECT trade_date, COUNT(*) AS cnt FROM daily_hot_news GROUP BY trade_date"
            ).fetchall()
        }
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
            GROUP BY d.trade_date
            ORDER BY d.trade_date DESC
            LIMIT 60
            """
        ).fetchall()
        out = []
        for r in rows:
            td = r["trade_date"]
            tot = int(r["total"] or 0)
            mood = _get_day_mood(td, tot, fetch_remote=False)
            out.append(
                {
                    "date": td,
                    "total": tot,
                    "multi": int(r["multi"] or 0),
                    "one_word": int(r["one_word"] or 0),
                    "max_height": int(r["max_height"] or 1),
                    "zhaban_rate": mood["zhaban_rate"],
                    "tagged": int(r["tagged"] or 0),
                    "news_count": int(news_counts.get(td, 0)),
                }
            )
        return out
    finally:
        conn.close()


def _match_topic_to_themes(topic: str, candidate_themes: list[str]) -> str | None:
    if not topic or not candidate_themes:
        return None
    tset = set(candidate_themes)
    if topic in tset:
        return topic
    for kw, mapped in TOPIC_TO_PURE_THEME:
        if kw in topic and mapped in tset:
            return mapped
    return None


def _clean_kpl_reason(raw: str | None) -> str:
    if not raw:
        return ""
    s = _clean_text(raw)
    # Remove redundant leading "概念1+概念2；" prefix if present
    parts = re.split(r"[；;]", s, maxsplit=1)
    if len(parts) == 2 and len(parts[0]) <= 24:
        s = parts[1].strip()
    return s[:220]


def get_day_payload(date: str | None = None) -> dict[str, Any]:
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

        pool_rows = conn.execute(
            """
            SELECT *
            FROM daily_limit_pool
            WHERE trade_date = ?
            ORDER BY board_height DESC, is_one_word DESC, first_limit_time ASC, amount_yi DESC, code ASC
            """,
            (date,),
        ).fetchall()

        codes = [r["code"] for r in pool_rows]
        if not codes:
            return {
                "date": date,
                "summary": {"total": 0, "multi": 0, "one_word": 0, "max_height": 0},
                "catalysts": [],
                "ladder": [],
                "first_boards": [],
                "stocks": {},
                "themes": {},
            }

        placeholders = ",".join("?" * len(codes))
        stock_meta = {
            r["code"]: dict(r)
            for r in conn.execute(
                f"SELECT * FROM stocks WHERE code IN ({placeholders})", codes
            ).fetchall()
        }

        static_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in conn.execute(
            f"""
            SELECT code, l1, revenue_pct, evidence
            FROM static_tags
            WHERE code IN ({placeholders})
            ORDER BY COALESCE(revenue_pct, -1) DESC, id ASC
            """,
            codes,
        ).fetchall():
            static_by_code[r["code"]].append(dict(r))

        dyn_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in conn.execute(
            f"""
            SELECT code, group_name, from_date, evidence
            FROM dynamic_tags
            WHERE code IN ({placeholders}) AND (to_date IS NULL OR to_date = '')
            ORDER BY from_date DESC, id ASC
            """,
            codes,
        ).fetchall():
            dyn_by_code[r["code"]].append(dict(r))

        ma_by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in conn.execute(
            f"""
            SELECT code, event_type, target_name, target_l1, from_date, evidence
            FROM ma_events
            WHERE code IN ({placeholders})
            ORDER BY from_date DESC, id ASC
            """,
            codes,
        ).fetchall():
            ma_by_code[r["code"]].append(dict(r))

        news_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT rank, headline, detail, hit_count
                FROM daily_hot_news
                WHERE trade_date = ?
                ORDER BY rank ASC
                """,
                (date,),
            ).fetchall()
        ]

        # Pass 1: build unified pure themes per stock (zero static/dynamic split exposed)
        raw_stocks: dict[str, dict[str, Any]] = {}
        theme_members: dict[str, list[str]] = defaultdict(list)
        theme_multi: dict[str, int] = defaultdict(int)
        theme_one_word: dict[str, int] = defaultdict(int)
        theme_max_h: dict[str, int] = defaultdict(int)

        for r in pool_rows:
            code = r["code"]
            meta = stock_meta.get(code)
            st_list = static_by_code.get(code, [])
            dt_list = dyn_by_code.get(code, [])
            ma_list = ma_by_code.get(code, [])

            # Unified ordered pure themes list & factual evidences (no internal jargon)
            themes: list[str] = []
            seen_t: set[str] = set()
            evidences: list[dict[str, Any]] = []

            for d in dt_list:
                t = _clean_text(d["group_name"])
                if t and t not in seen_t:
                    seen_t.add(t)
                    themes.append(t)
                    evidences.append(
                        {
                            "theme": t,
                            "pct": None,
                            "text": _clean_text(d["evidence"]),
                        }
                    )

            for s in st_list:
                t = _clean_text(s["l1"])
                if t and t not in seen_t:
                    seen_t.add(t)
                    themes.append(t)
                    evidences.append(
                        {
                            "theme": t,
                            "pct": round(float(s["revenue_pct"]), 1)
                            if s["revenue_pct"] is not None
                            else None,
                            "text": _clean_text(s["evidence"]),
                        }
                    )

            if ma_list and "并购" not in seen_t:
                seen_t.add("并购")
                themes.append("并购")
                ma_summary = "；".join(
                    f"{m['event_type']}：{m['target_name']}" for m in ma_list[:2]
                )
                evidences.append(
                    {
                        "theme": "并购",
                        "pct": None,
                        "text": ma_summary,
                    }
                )

            # Graceful fallback for older untagged historical dates
            if not themes and r["kpl_topic"]:
                fallback_t = _clean_text(r["kpl_topic"])
                for kw, mapped in TOPIC_TO_PURE_THEME:
                    if kw in fallback_t:
                        fallback_t = mapped
                        break
                if fallback_t:
                    themes.append(fallback_t)

            h = int(r["board_height"] or 1)
            is_ow = bool(r["is_one_word"])
            for t in themes:
                theme_members[t].append(code)
                if h >= 2:
                    theme_multi[t] += 1
                if is_ow:
                    theme_one_word[t] += 1
                if h > theme_max_h[t]:
                    theme_max_h[t] = h

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

            raw_stocks[code] = {
                "code": code,
                "name": name,
                "height": h,
                "boards_desc": _clean_text(r["boards_desc"]),
                "first_time": first_time,
                "amount_yi": amount_yi,
                "turnover": turnover,
                "is_one_word": is_ow,
                "is_fanbao": bool(r["is_fanbao"]),
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
                "kpl_topic": _clean_text(r["kpl_topic"]),
                "intraday_reason": _clean_kpl_reason(r["kpl_reason"]),
                "primary_theme": "",
            }

        # Theme heat score for ranking primary_theme & catalysts
        def _theme_score(t: str) -> float:
            return (
                theme_max_h[t] * 5.0
                + theme_one_word[t] * 6.0
                + theme_multi[t] * 4.5
                + len(theme_members[t]) * 1.2
            )

        # Pass 2: pick single cleanest intraday hot theme (`primary_theme`) per stock
        for code, st in raw_stocks.items():
            matched = _match_topic_to_themes(st["kpl_topic"], st["themes"])
            if not matched and st["intraday_reason"]:
                matched = _match_topic_to_themes(st["intraday_reason"], st["themes"])
            if not matched and st["themes"]:
                # Prefer today's hottest pure theme among this stock's verified themes
                matched = max(st["themes"], key=_theme_score)
            st["primary_theme"] = matched or ""
            st["primary_accent"] = _accent_for(st["primary_theme"])

        # Count how many stocks have each theme as their actual intraday primary_theme
        primary_counts: dict[str, int] = defaultdict(int)
        primary_multi_counts: dict[str, int] = defaultdict(int)
        for st in raw_stocks.values():
            pt = st["primary_theme"]
            if pt:
                primary_counts[pt] += 1
                if st["height"] >= 2:
                    primary_multi_counts[pt] += 1

        # Pass 3: build Top Catalyst Cards (`daily_hot_news` merged with pure theme ladders)
        name_to_code = {st["name"]: code for code, st in raw_stocks.items()}
        theme_news_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
        event_catalysts: list[dict[str, Any]] = []

        for nw in news_rows:
            hl = _clean_text(nw["headline"])
            dt = _clean_text(nw["detail"])
            combined = f"{hl} {dt}"

            # Find all stocks in today's pool mentioned in this news item
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

            # Determine if this news maps to a pure theme present today
            mapped_theme: str | None = None
            event_label: str | None = None
            event_accent: str = "amber"
            for kw, label, acc in NEWS_EVENT_SHORT_TITLES:
                if kw in combined:
                    if label in theme_members:
                        mapped_theme = label
                    else:
                        event_label = label
                        event_accent = acc
                    break

            # Secondary inference from consensus pure theme of mentioned stocks
            if not mapped_theme and not event_label and mentioned:
                counts: dict[str, int] = defaultdict(int)
                for c in mentioned:
                    for t in raw_stocks[c]["themes"]:
                        counts[t] += 1
                if counts:
                    top_t, top_cnt = max(counts.items(), key=lambda kv: (kv[1], _theme_score(kv[0])))
                    if top_cnt >= max(1, len(mentioned) // 2):
                        mapped_theme = top_t

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
                # Keep meaningful event dark-lines (e.g. 2027羊年暗线 with 4 stocks, or high-board catalyst)
                max_h_m = max((raw_stocks[c]["height"] for c in mentioned), default=0)
                if len(mentioned) >= 2 or max_h_m >= 3:
                    ev_title = event_label or hl[:6]
                    ev_multi = sum(1 for c in mentioned if raw_stocks[c]["height"] >= 2)
                    ev_ow = sum(1 for c in mentioned if raw_stocks[c]["is_one_word"])
                    event_catalysts.append(
                        {
                            "id": f"event:{nw['rank']}",
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
                            "_score": 20.0 + int(nw.get("hit_count") or 1) * 3.0 + max_h_m * 3.0 + ev_ow * 5.0 - nw["rank"] * 0.6,
                        }
                    )

        catalysts: list[dict[str, Any]] = []
        included_themes: set[str] = set()

        def _make_theme_catalyst(t: str, news_list: list[dict[str, Any]]) -> dict[str, Any]:
            codes_t = list(theme_members[t])
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
                h_chain = "→".join(f"{x}板" for x in heights_present[:4])
                ow_note = "一字" if lead["is_one_word"] else ""
                headline = f"{lead['height']}板{ow_note}{lead['name']}领涨，梯队覆盖 {h_chain}"
                news_payload = []

            best_rank = min((n["rank"] for n in news_list), default=14)
            news_hits = sum(int(n.get("hit_count") or 1) for n in news_list)
            p_cnt = primary_counts.get(t, 0)
            pm_cnt = primary_multi_counts.get(t, 0)
            score = (
                (26.0 + news_hits * 2.5 if news_list else 0.0)
                + pm_cnt * 7.0
                + p_cnt * 2.4
                + ow_cnt * 5.0
                + max_h * 3.0
                + multi_cnt * 2.0
                - best_rank * 0.5
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

        # Add all news-backed pure themes
        for t, nlist in theme_news_map.items():
            included_themes.add(t)
            catalysts.append(_make_theme_catalyst(t, nlist))

        # Add high-momentum pure themes that genuinely drive today's intraday primary themes
        for t, members in theme_members.items():
            if t in included_themes:
                continue
            if primary_counts.get(t, 0) >= 2 or (primary_multi_counts.get(t, 0) >= 1 and theme_multi[t] >= 2):
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
                # For pure event catalysts, mark member stocks if they aren't already in rank 1/2
                c_item["event_rank"] = idx

        # Build complete theme index (for clicking ANY tag inside Stock Modal or Theme Modal!)
        themes_index: dict[str, dict[str, Any]] = {}
        for t, members in theme_members.items():
            sorted_m = sorted(
                members,
                key=lambda c: (
                    -raw_stocks[c]["height"],
                    -int(raw_stocks[c]["is_one_word"]),
                    raw_stocks[c]["first_time"],
                    -(raw_stocks[c]["amount_yi"] or 0),
                ),
            )
            news_list = [
                {"headline": n["headline"], "detail": n["detail"]}
                for n in theme_news_map.get(t, [])
            ]
            themes_index[t] = {
                "name": t,
                "accent": _accent_for(t),
                "heat_rank": theme_heat_rank.get(t, 99),
                "codes": sorted_m,
                "total": len(sorted_m),
                "multi": sum(1 for c in sorted_m if raw_stocks[c]["height"] >= 2),
                "one_word": sum(1 for c in sorted_m if raw_stocks[c]["is_one_word"]),
                "max_height": max((raw_stocks[c]["height"] for c in sorted_m), default=1),
                "news": news_list,
            }

        # Order each stock's themes so rank-1/rank-2 and primary_theme come first, and attach primary_heat_rank
        for st in raw_stocks.values():
            st["themes"].sort(
                key=lambda t: (
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
                # Check if stock carries rank-1 or rank-2 directly when primary wasn't top-2
                best_owned = min((theme_heat_rank.get(t, 99) for t in st["themes"]), default=99)
                st["best_heat_rank"] = best_owned
            else:
                st["best_heat_rank"] = pt_rank
            st["primary_heat_rank"] = pt_rank
            st.pop("kpl_topic", None)

        # Build ladder tiers (>=2板) & first_boards (1板)
        tiers_map: dict[int, list[str]] = defaultdict(list)
        first_boards: list[str] = []
        for r in pool_rows:
            code = r["code"]
            h = raw_stocks[code]["height"]
            if h >= 2:
                tiers_map[h].append(code)
            else:
                first_boards.append(code)

        ladder = [
            {"height": h, "codes": tiers_map[h]}
            for h in sorted(tiers_map.keys(), reverse=True)
        ]

        multi_total = sum(len(x["codes"]) for x in ladder)
        ow_total = sum(1 for st in raw_stocks.values() if st["is_one_word"])
        max_height = ladder[0]["height"] if ladder else (1 if first_boards else 0)
        mood = _get_day_mood(date, len(raw_stocks), fetch_remote=True)

        return {
            "date": date,
            "summary": {
                "total": len(raw_stocks),
                "multi": multi_total,
                "first": len(first_boards),
                "one_word": ow_total,
                "max_height": max_height,
                "zb_count": mood["zb_count"],
                "zhaban_rate": mood["zhaban_rate"],
                "dt_count": mood["dt_count"],
                "sign": mood["sign"],
            },
            "catalysts": catalysts,
            "ladder": ladder,
            "first_boards": first_boards,
            "stocks": raw_stocks,
            "themes": themes_index,
        }
    finally:
        conn.close()


class SuperBoardHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        # Quiet concise logs
        return

    def _send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        mime, _ = mimetypes.guess_type(str(path))
        if path.suffix == ".js":
            mime = "application/javascript; charset=utf-8"
        elif path.suffix == ".css":
            mime = "text/css; charset=utf-8"
        elif path.suffix == ".html":
            mime = "text/html; charset=utf-8"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/dates":
            self._send_json({"dates": get_available_dates()})
            return
        if path == "/api/day":
            qs = parse_qs(parsed.query)
            date = qs.get("date", [None])[0]
            self._send_json(get_day_payload(date))
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


def export_static_site(limit: int = 30) -> None:
    """Export compact static JSON snapshots into web/data/ for GitHub Pages."""
    out_data = WEB_DIR / "data"
    out_days = out_data / "days"
    out_days.mkdir(parents=True, exist_ok=True)
    (WEB_DIR / ".nojekyll").write_text("", encoding="utf-8")

    all_dates = get_available_dates()[:limit]
    exported_dates: list[dict[str, Any]] = []
    for d_info in all_dates:
        dt = d_info["date"]
        payload = get_day_payload(dt)
        (out_days / f"{dt}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        d_copy = dict(d_info)
        if payload["summary"].get("zhaban_rate") is not None:
            d_copy["zhaban_rate"] = payload["summary"]["zhaban_rate"]
        exported_dates.append(d_copy)

    (out_data / "dates.json").write_text(
        json.dumps({"dates": exported_dates}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Exported {len(exported_dates)} trading days to {out_data}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Super-Board Mobile Web Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--export-site", action="store_true", help="Export static site JSONs to web/data/ for GitHub Pages")
    parser.add_argument("--days", type=int, default=30, help="Number of recent trading days to export")
    args = parser.parse_args()

    if args.export_site:
        export_static_site(limit=args.days)
        return

    server = ThreadingHTTPServer((args.host, args.port), SuperBoardHandler)
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
