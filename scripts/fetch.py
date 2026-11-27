"""Fetch Kaipanla daily limit ladder skeleton (pure stdlib) + full F10 & CNINFO PDF evidence."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from build_db import ensure_db
from common import DB_PATH, ROOT, ULTRA_BOARD_RAW, clean_stock_name
from driver_rules import is_core_stock

SHANGHAI_TZ = timezone(timedelta(hours=8))
F10_DIR = ROOT / "data/raw_f10"
ANN_DIR = ROOT / "data/raw_ann"
RAW_ANN_DAY_DIR = ROOT / "data/raw_ann_day"
KLINE_DIR = ROOT / "data/raw_kline"
MARKET_RAW_DIR = ROOT / "data/market_raw"
NEWS_RAW_DIR = ROOT / "data/raw_news"
ORG_MAP_PATH = ROOT / "data/cninfo_org_map.json"

NOISE_NOTICE_KWS = (
    "三方监管", "四方监管", "监管协议", "专户", "可转债", "债券", "赎回",
    "转股", "付息", "信用评级", "限售股", "解禁", "上市流通", "发行情况报告书",
    "募集说明书", "上市公告书", "网下配售", "询价转让",
)

KPL_HISTORY_URL = "https://apphis.longhuvip.com/w1/api/index.php"
KPL_LIVE_URL = "https://apphq.longhuvip.com/w1/api/index.php"
KPL_HEADERS = {
    "User-Agent": "lhb/5.21.0.2 (com.kaipanla.www; build:0; iOS 16.6) Alamofire/4.9.1",
    "Content-Type": "application/x-www-form-urlencoded",
}

TITLE_INCLUDE = (
    "澄清", "异动", "异常波动", "风险提示", "终止", "收购", "重组", "控制权",
    "股份转让", "问询", "监管函", "关注函", "对外投资", "设立子公司", "合资",
    "参股", "框架协议", "战略合作", "合作协议", "中标", "定点", "重大合同",
    "更名", "资产出售", "剥离", "资产注入", "并购",
)
TITLE_EXCLUDE = (
    "法律意见书", "法律意见", "核查意见", "核查报告", "股权激励", "股票期权",
    "限制性股票", "员工持股", "监事会", "独立董事", "股东大会", "董事会决议",
    "审计委员会", "减持", "质押", "担保", "闲置募集", "募集资金", "独立财务顾问",
    "评估报告", "资产评估", "估值报告", "审计报告", "验资报告", "会计师事务所",
    "保荐", "回购", "权益分派", "分红", "续聘", "理财", "现金管理", "银行授信",
    "日常关联交易", "关联交易预计", "诉讼", "仲裁", "政府补助", "募集资金存放",
    "管理制度", "制度", "工作细则", "章程", "议事规则",
    "三方监管", "四方监管", "监管协议", "专户", "可转债", "债券", "赎回",
    "转股", "付息", "信用评级", "限售股", "解禁", "上市流通", "发行情况报告书",
    "募集说明书", "上市公告书", "网下配售", "询价转让", "财务报告", "备考", "摘要",
)
SIGNAL_REGEX = re.compile(
    r"(不涉及|未涉及|未开展|无合作|未供货|无直接|无关联|终止|取消|占比|送样|探索|研发|布局|拓展|战略合作|合资|子公司|产线|验证|试产|订单|中标|定点|协议|尚未形成|未形成规模|重大影响|收购|重组|控制权|参股|股权|并表|过户)"
)

_THREAD_LOCAL = threading.local()
_FITZ_LOCK = threading.Lock()
_CNINFO_RATE_LOCK = threading.Lock()
_CNINFO_LAST_TS = 0.0


def _kpl_post(url: str, params: dict[str, Any]) -> dict[str, Any]:
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=KPL_HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_msg_map(msg_doc: dict[str, Any] | None) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    if not msg_doc:
        return out
    for grp in msg_doc.get("list") or []:
        for row in grp.get("StockList") or []:
            if not isinstance(row, list) or len(row) < 18:
                continue
            code = str(row[0]).strip()
            topic = str(row[16] or "").strip()
            reason = re.sub(r"\s+", " ", str(row[17] or "")).strip()
            if code and code not in out:
                out[code] = (topic, reason)
    return out


def _ingest_day_dir(conn: sqlite3.Connection, day: str, day_dir: Path) -> int:
    zt_p = day_dir / "zt_pool.json"
    if not zt_p.exists():
        return 0
    zt_doc = json.loads(zt_p.read_text(encoding="utf-8-sig"))
    msg_p = day_dir / "historical_messages.json"
    msg_doc = json.loads(msg_p.read_text(encoding="utf-8-sig")) if msg_p.exists() else None
    msg_map = _parse_msg_map(msg_doc)

    fanbao_codes: set[str] = set()
    lad_p = day_dir / "sector_ladder.json"
    if lad_p.exists():
        lad_doc = json.loads(lad_p.read_text(encoding="utf-8-sig"))
        for fb in lad_doc.get("fanbao_all") or []:
            if fb.get("code"):
                fanbao_codes.add(str(fb["code"]))

    rows = zt_doc.get("stocks") or []
    to_insert = []
    for s in rows:
        code = str(s.get("code") or "").strip()
        if not code:
            continue
        name = clean_stock_name(s.get("name"))
        ts = s.get("first_limit_ts")
        flt = datetime.fromtimestamp(float(ts), SHANGHAI_TZ).strftime("%H:%M:%S") if ts else ""
        amt = s.get("amount")
        amt_yi = round(float(amt) / 1e8, 2) if amt is not None else None
        raw = s.get("raw") or []
        is_one = 1 if (flt == "09:25:00" and (len(raw) < 17 or raw[16] == 0)) else 0
        is_fb = 1 if (s.get("is_fanbao") or code in fanbao_codes) else 0
        topic, reason = msg_map.get(code, (str(s.get("theme") or ""), ""))
        to_insert.append(
            (
                day,
                code,
                name,
                int(s.get("boards") or 1),
                str(s.get("boards_desc") or ""),
                flt,
                amt_yi,
                float(s["turnover_rate"]) if s.get("turnover_rate") is not None else None,
                is_one,
                is_fb,
                topic,
                reason,
            )
        )
    conn.executemany(
        """
        INSERT OR REPLACE INTO daily_limit_pool(
            trade_date, code, name, board_height, boards_desc, first_limit_time,
            amount_yi, turnover_rate, is_one_word, is_fanbao, kpl_topic, kpl_reason
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        to_insert,
    )
    return len(to_insert)


def fetch_standalone_day(day: str) -> Path:
    day_dir = MARKET_RAW_DIR / day
    day_dir.mkdir(parents=True, exist_ok=True)
    stocks_by_code: dict[str, dict[str, Any]] = {}
    for pid in range(1, 6):
        params = {
            "c": "HisHomeDingPan", "a": "DailyLimitPerformance", "Date": day, "Day": day,
            "PidType": str(pid), "Order": "0", "st": "2000", "Index": "0", "Type": "4",
            "PhoneOSNew": "1", "apiv": "w42", "VerSion": "5.21.0.2",
        }
        body = _kpl_post(KPL_HISTORY_URL, params)
        if str(body.get("errcode", "0")) == "1020":
            live_p = dict(params, c="HomeDingPan")
            body = _kpl_post(KPL_LIVE_URL, live_p)
        for r in (body.get("info") or [[]])[0]:
            if len(r) < 23:
                continue
            c = str(r[0])
            stocks_by_code[c] = {
                "code": c, "name": clean_stock_name(r[1]), "boards": int(r[15]),
                "boards_desc": r[18] or "", "theme": r[5], "first_limit_ts": r[4],
                "amount": r[11], "turnover_rate": r[14], "is_fanbao": False, "raw": r,
            }
    zt_doc = {"date": day, "count": len(stocks_by_code), "stocks": list(stocks_by_code.values())}
    (day_dir / "zt_pool.json").write_text(json.dumps(zt_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Fetch historical_messages (first try His then Live)
    msg_p = {"c": "HisHomeDingPan", "a": "GetYTFP_ZTYY", "Date": day, "Day": day, "PhoneOSNew": "1", "apiv": "w42", "VerSion": "5.21.0.2"}
    try:
        msg_body = _kpl_post(KPL_HISTORY_URL, msg_p)
        if str(msg_body.get("errcode", "0")) == "1020":
            msg_body = _kpl_post(KPL_LIVE_URL, dict(msg_p, c="HomeDingPan"))
        (day_dir / "historical_messages.json").write_text(json.dumps(msg_body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass
    return day_dir


def sync_market(from_ultra: bool, date: str | None) -> None:
    conn = ensure_db()
    total_rows = 0
    days_done = 0
    if from_ultra:
        for p in sorted(ULTRA_BOARD_RAW.glob("20*")):
            if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name):
                cnt = _ingest_day_dir(conn, p.name, p)
                if cnt:
                    days_done += 1
                    total_rows += cnt
        conn.commit()
    elif date:
        ultra_dir = ULTRA_BOARD_RAW / date
        if (ultra_dir / "zt_pool.json").exists():
            cnt = _ingest_day_dir(conn, date, ultra_dir)
            source = str(ultra_dir)
        else:
            local_dir = fetch_standalone_day(date)
            cnt = _ingest_day_dir(conn, date, local_dir)
            source = str(local_dir)
        conn.commit()
        days_done = 1
        total_rows = cnt
        print(json.dumps({"date": date, "rows": cnt, "source": source}, ensure_ascii=False))
        conn.close()
        return

    latest = conn.execute("SELECT MAX(trade_date), COUNT(*) FROM daily_limit_pool").fetchone()
    latest_cnt = conn.execute("SELECT COUNT(*) FROM daily_limit_pool WHERE trade_date=?", (latest[0],)).fetchone()[0] if latest[0] else 0
    conn.close()
    print(json.dumps({"days_imported": days_done, "total_rows": total_rows, "db_rows": latest[1], "latest_date": latest[0], "latest_day_count": latest_cnt}, ensure_ascii=False))


# ==================== Evidence Fetching (F10 + CNINFO PDF) ====================

def _get_session():
    import requests
    from requests.adapters import HTTPAdapter

    sess = getattr(_THREAD_LOCAL, "session", None)
    if sess is None:
        sess = requests.Session()
        adapter = HTTPAdapter(pool_connections=32, pool_maxsize=32)
        sess.mount("https://", adapter)
        sess.mount("http://", adapter)
        sess.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0.0.0 Safari/537.36"})
        _THREAD_LOCAL.session = sess
    return sess


def _secucode(code: str) -> str:
    if code.startswith(("8", "4", "92")):
        return "BJ" + code
    if code.startswith(("6", "9")):
        return "SH" + code
    return "SZ" + code


def _fetch_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    sess = _get_session()
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            r = sess.get(url, timeout=15, headers=headers)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last_exc = exc
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"fetch failed ({url}): {last_exc}")


def _extract_mix(zygc: list[dict[str, Any]], dt: str | None) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {"industry": [], "product": [], "region": []}
    if not dt:
        return out
    tmap = {"1": "industry", "2": "product", "3": "region"}
    for x in zygc:
        if (x.get("REPORT_DATE") or "")[:10] == dt:
            k = tmap.get(str(x.get("MAINOP_TYPE")))
            if k:
                ratio = x.get("MBI_RATIO")
                rev = x.get("MAIN_BUSINESS_INCOME")
                out[k].append(
                    {
                        "name": x.get("ITEM_NAME"),
                        "ratio_pct": round(float(ratio) * 100, 2) if ratio is not None else None,
                        "rev_yi": round(float(rev) / 1e8, 2) if rev is not None else None,
                    }
                )
    for k in out:
        out[k].sort(key=lambda r: r["ratio_pct"] if r["ratio_pct"] is not None else -1.0, reverse=True)
    return out


def _fetch_bj_f10_fallback(code: str, sc: str) -> dict[str, Any] | None:
    secucode_dot = f"{code}.BJ"
    base = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
    hdr = {"Referer": "https://emweb.securities.eastmoney.com/"}
    org_resp = _fetch_json(f"{base}?reportName=RPT_F10_BASIC_ORGINFO&columns=ALL&filter=(SECUCODE%3D%22{secucode_dot}%22)", hdr)
    org_rows = (org_resp.get("result") or {}).get("data") or []
    if not org_rows:
        return None
    org = org_rows[0]
    try:
        zygc_resp = _fetch_json(f"{base}?reportName=RPT_F10_FN_MAINOP&columns=ALL&pageSize=60&filter=(SECUCODE%3D%22{secucode_dot}%22)", hdr)
        zygc = (zygc_resp.get("result") or {}).get("data") or []
    except Exception:
        zygc = []
    try:
        cc_resp = _fetch_json(f"{base}?reportName=RPT_F10_CORETHEME_CONTENT&columns=ALL&pageSize=30&filter=(SECUCODE%3D%22{secucode_dot}%22)", hdr)
        cc_rows = (cc_resp.get("result") or {}).get("data") or []
    except Exception:
        cc_rows = []
    try:
        ctrl_resp = _fetch_json(f"{base}?reportName=RPT_F10_EH_SJKZR&columns=ALL&pageSize=5&filter=(SECUCODE%3D%22{secucode_dot}%22)", hdr)
        ctrl_rows = (ctrl_resp.get("result") or {}).get("data") or []
        controller = ctrl_rows[0].get("HOLDER_NAME") if ctrl_rows else None
    except Exception:
        controller = None

    dates = sorted({(x.get("REPORT_DATE") or "")[:10] for x in zygc if x.get("REPORT_DATE")}, reverse=True)
    latest_dt = dates[0] if dates else None
    annual_dt = next((d for d in dates if d.endswith("12-31")), latest_dt)
    return {
        "code": code,
        "secucode": sc,
        "v": 2,
        "f10_status": "ok",
        "name": clean_stock_name(org.get("SECURITY_NAME_ABBR")),
        "province_raw": org.get("PROVINCE"),
        "reg_address": org.get("REG_ADDRESS") or org.get("ADDRESS"),
        "em_industry": org.get("EM2016") or org.get("INDUSTRYCSRC1"),
        "controller_name": controller,
        "latest_dt": latest_dt,
        "latest_mix": _extract_mix(zygc, latest_dt),
        "annual_dt": annual_dt,
        "annual_mix": _extract_mix(zygc, annual_dt) if annual_dt and annual_dt != latest_dt else None,
        "business_scope": (org.get("BUSINESS_SCOPE") or "").strip(),
        "business_review": (org.get("MAIN_BUSINESS") or org.get("ORG_PROFILE") or "").strip(),
        "core_conception": [
            {"keyword": (x.get("KEYWORD") or "").strip(), "content": (x.get("MAINPOINT_CONTENT") or "").strip()}
            for x in cc_rows
            if x.get("KEYWORD") or x.get("MAINPOINT_CONTENT")
        ],
    }


def fetch_f10(code: str, refresh: bool = False) -> dict[str, Any]:
    path = F10_DIR / f"{code}.json"
    if path.exists() and not refresh:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("v") == 2 and doc.get("f10_status") in ("ok", "missing_or_delisted"):
                return doc
        except Exception:
            pass
    sc = _secucode(code)
    hdr = {"Referer": "https://emweb.securities.eastmoney.com/"}
    try:
        ba = _fetch_json(f"https://emweb.securities.eastmoney.com/PC_HSF10/BusinessAnalysis/PageAjax?code={sc}", hdr)
        cs = _fetch_json(f"https://emweb.securities.eastmoney.com/PC_HSF10/CompanySurvey/PageAjax?code={sc}", hdr)
        try:
            sr = _fetch_json(f"https://emweb.securities.eastmoney.com/PC_HSF10/ShareholderResearch/PageAjax?code={sc}", hdr)
        except Exception:
            sr = {}
        try:
            cc = _fetch_json(f"https://emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax?code={sc}", hdr)
        except Exception:
            cc = {}
    except Exception as exc:
        doc = {"code": code, "secucode": sc, "f10_status": "error", "error": str(exc)}
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return doc

    jbzl_list = cs.get("jbzl") or []
    if not jbzl_list:
        if sc.startswith("BJ"):
            try:
                bj_doc = _fetch_bj_f10_fallback(code, sc)
                if bj_doc:
                    tmp = path.with_suffix(".json.tmp")
                    tmp.write_text(json.dumps(bj_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    tmp.replace(path)
                    return bj_doc
            except Exception:
                pass
        doc = {"code": code, "secucode": sc, "v": 2, "f10_status": "missing_or_delisted"}
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return doc

    jbzl = jbzl_list[0]
    zyfw = ((ba.get("zyfw") or [{}])[0].get("BUSINESS_SCOPE") or "").strip()
    jyps_list = ba.get("jyps") or []
    jyps = (jyps_list[0].get("BUSINESS_REVIEW") or "").strip() if jyps_list else ""
    zygc = ba.get("zygcfx") or []
    dates = sorted({(x.get("REPORT_DATE") or "")[:10] for x in zygc if x.get("REPORT_DATE")}, reverse=True)
    latest_dt = dates[0] if dates else None
    annual_dt = next((d for d in dates if d.endswith("12-31")), latest_dt)
    sjkzr = sr.get("sjkzr") or []
    controller = sjkzr[0].get("HOLDER_NAME") if sjkzr else None

    doc = {
        "code": code,
        "secucode": sc,
        "v": 2,
        "f10_status": "ok",
        "name": clean_stock_name(jbzl.get("SECURITY_NAME_ABBR")),
        "province_raw": jbzl.get("PROVINCE"),
        "reg_address": jbzl.get("REG_ADDRESS"),
        "em_industry": jbzl.get("EM2016"),
        "controller_name": controller,
        "latest_dt": latest_dt,
        "latest_mix": _extract_mix(zygc, latest_dt),
        "annual_dt": annual_dt,
        "annual_mix": _extract_mix(zygc, annual_dt) if annual_dt and annual_dt != latest_dt else None,
        "business_scope": zyfw,
        "business_review": jyps,
        "core_conception": [
            {"keyword": (x.get("KEYWORD") or "").strip(), "content": (x.get("MAINPOINT_CONTENT") or "").strip()}
            for x in (cc.get("hxtc") or [])
            if x.get("KEYWORD") or x.get("MAINPOINT_CONTENT")
        ],
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return doc


def _extract_signal_windows(text: str, max_windows: int = 6, max_chars: int = 3000) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if not clean:
        return ""
    windows: list[tuple[int, int]] = []
    for m in SIGNAL_REGEX.finditer(clean):
        s = max(0, m.start() - 80)
        e = min(len(clean), m.end() + 200)
        if windows and s <= windows[-1][1] + 20:
            windows[-1] = (windows[-1][0], max(windows[-1][1], e))
        else:
            windows.append((s, e))
        if len(windows) >= max_windows:
            break
    if not windows:
        return clean[:max_chars]
    return " | ".join(clean[s:e] for s, e in windows)[:max_chars]


def _extract_pdf_text(pdf_bytes: bytes, max_pages: int = 20) -> str:
    try:
        import fitz

        with _FITZ_LOCK:
            fitz.TOOLS.mupdf_display_errors(False)
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            parts = [page.get_text() for page in doc[:max_pages]]
            doc.close()
        return " ".join(parts)
    except Exception:
        return ""


def _load_org_map() -> dict[str, str]:
    if ORG_MAP_PATH.exists():
        return json.loads(ORG_MAP_PATH.read_text(encoding="utf-8"))
    sess = _get_session()
    org_map: dict[str, str] = {}
    for url in ("https://www.cninfo.com.cn/new/data/szse_stock.json", "https://www.cninfo.com.cn/new/data/bj_stock.json"):
        try:
            r = sess.get(url, timeout=20)
            if r.status_code == 200 and r.text.strip().startswith("{"):
                for item in r.json().get("stockList", []):
                    org_map[str(item["code"])] = str(item["orgId"])
        except Exception:
            continue
    ORG_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    ORG_MAP_PATH.write_text(json.dumps(org_map, ensure_ascii=False) + "\n", encoding="utf-8")
    return org_map


def _cninfo_query_page(sess, stock_param: str, col: str, start_dt: str, end_dt: str, page_num: int) -> dict[str, Any] | None:
    global _CNINFO_LAST_TS
    for attempt in range(4):
        with _CNINFO_RATE_LOCK:
            now = time.monotonic()
            wait = 0.48 - (now - _CNINFO_LAST_TS)
            if wait > 0:
                time.sleep(wait)
            _CNINFO_LAST_TS = time.monotonic()
        try:
            r = sess.post(
                "https://www.cninfo.com.cn/new/hisAnnouncement/query",
                data={
                    "stock": stock_param, "tabName": "fulltext", "pageSize": 30, "pageNum": page_num,
                    "column": col, "category": "", "searchkey": "", "seDate": f"{start_dt}~{end_dt}", "isHLtitle": "false",
                },
                headers={"X-Requested-With": "XMLHttpRequest", "Referer": "https://www.cninfo.com.cn/"},
                timeout=(8, 15),
            )
            if r.status_code in (403, 429):
                time.sleep(2.5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            time.sleep(1.2 * (attempt + 1))
    return None


def fetch_ann_cninfo(code: str, org_map: dict[str, str], refresh: bool = False) -> dict[str, Any]:
    path = ANN_DIR / f"{code}.json"
    if path.exists() and not refresh:
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("ann_status") == "ok":
                ns = cached.get("notices") or []
                if not ns or all((n.get("full_text") or "").strip() for n in ns):
                    return cached
        except Exception:
            pass
    sess = _get_session()
    end_dt = datetime.now().strftime("%Y-%m-%d")
    start_dt = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
    one_yr_ago = (datetime.now() - timedelta(days=380)).strftime("%Y-%m-%d")
    col = "sse" if code.startswith(("6", "9")) else ("szse" if code.startswith(("0", "3")) else "bj")
    org_id = org_map.get(code, "")
    stock_param = f"{code},{org_id}" if org_id else code

    anns: list[dict[str, Any]] = []
    for page_num in (1, 2):
        page_resp = _cninfo_query_page(sess, stock_param, col, start_dt, end_dt, page_num)
        if page_resp is None:
            if page_num == 1:
                return {"code": code, "ann_status": "error", "notices": []}
            break
        batch = page_resp.get("announcements") or []
        anns.extend(batch)
        if len(batch) < 30:
            break
        last_ts = batch[-1].get("announcementTime")
        if isinstance(last_ts, (int, float)):
            last_dt = datetime.fromtimestamp(last_ts / 1000.0).strftime("%Y-%m-%d")
            if last_dt < one_yr_ago:
                break

    candidates: list[dict[str, Any]] = []
    for a in anns:
        title = re.sub(r"<[^>]+>", "", str(a.get("announcementTitle") or "")).strip()
        if any(bad in title for bad in TITLE_EXCLUDE) or not any(kw in title for kw in TITLE_INCLUDE):
            continue
        if "财务报告" in title or "备考" in title or "摘要" in title:
            continue
        ts = a.get("announcementTime")
        dt = datetime.fromtimestamp(ts / 1000.0).strftime("%Y-%m-%d") if isinstance(ts, (int, float)) else ""
        score = (
            3 if any(k in title for k in ("澄清", "问询", "回复", "终止"))
            else (2 if any(k in title for k in ("收购", "重组", "控制权", "股份转让", "对外投资", "合资", "参股", "战略合作", "合作协议", "中标", "定点")) else 1)
        )
        candidates.append({"date": dt, "title": title, "adjunct_url": a.get("adjunctUrl") or "", "score": score})

    candidates.sort(key=lambda r: (r["score"], r["date"]), reverse=True)
    selected: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for c in candidates:
        st = c["title"][:24]
        if st in seen_titles and len(candidates) > 5:
            continue
        seen_titles.add(st)
        selected.append(c)
        if len(selected) >= 5:
            break

    pdf_failures = 0
    for item in selected:
        adj = item.get("adjunct_url") or ""
        if not adj.lower().endswith(".pdf"):
            item["full_text"] = ""
            continue
        pdf_url = "https://static.cninfo.com.cn/" + adj.lstrip("/")
        raw_txt = ""
        got_pdf = False
        for attempt in range(3):
            try:
                pr = sess.get(pdf_url, timeout=(8, 15))
                if pr.status_code == 200 and pr.content[:4] == b"%PDF":
                    got_pdf = True
                    raw_txt = _extract_pdf_text(pr.content, max_pages=20)
                    break
            except Exception:
                time.sleep(0.5 * (attempt + 1))
        if not got_pdf:
            pdf_failures += 1
        clean_txt = re.sub(r"[ \t]+", " ", raw_txt).strip()
        if len(clean_txt) > 18000:
            item["full_text"] = clean_txt[:10000] + "\n...[中间略]...\n" + _extract_signal_windows(clean_txt[10000:], max_windows=12, max_chars=8000)
        else:
            item["full_text"] = clean_txt

    status = "ok" if pdf_failures == 0 else "partial"
    doc = {"code": code, "source": "cninfo", "ann_status": status, "notices": selected}
    if status == "ok":
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
    return doc


def fetch_evidence_cmd(codes: list[str], f10_only: bool = False, refresh: bool = False) -> None:
    F10_DIR.mkdir(parents=True, exist_ok=True)
    ANN_DIR.mkdir(parents=True, exist_ok=True)
    f10_ok = 0
    with ThreadPoolExecutor(max_workers=20) as ex:
        for fut in as_completed([ex.submit(fetch_f10, c, refresh) for c in codes]):
            if fut.result().get("f10_status") == "ok":
                f10_ok += 1
    ann_ok = 0
    if not f10_only:
        need = codes if refresh else [c for c in codes if not (ANN_DIR / f"{c}.json").exists()]
        if need:
            org_map = _load_org_map()
            done_cnt = 0
            with ThreadPoolExecutor(max_workers=4) as ex:
                for fut in as_completed([ex.submit(fetch_ann_cninfo, c, org_map, refresh) for c in need]):
                    done_cnt += 1
                    if fut.result().get("ann_status") == "ok":
                        ann_ok += 1
                    if done_cnt % 50 == 0 or done_cnt == len(need):
                        print(f"[ann progress] {done_cnt}/{len(need)} (ok={ann_ok})", flush=True)
        ann_ok += len(codes) - len(need)
    print(json.dumps({"total": len(codes), "f10_ok": f10_ok, "ann_ok": ann_ok if not f10_only else "skipped"}, ensure_ascii=False))


def _prev_trade_day(day: str) -> str:
    if DB_PATH.exists():
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        row = conn.execute("SELECT MAX(trade_date) FROM daily_limit_pool WHERE trade_date < ?", (day,)).fetchone()
        conn.close()
        if row and row[0]:
            return str(row[0])
    dt = datetime.strptime(day, "%Y-%m-%d").date()
    delta = 3 if dt.weekday() == 0 else (2 if dt.weekday() == 6 else 1)
    return (dt - timedelta(days=delta)).isoformat()


def fetch_intraday_news(day: str, max_pages: int = 30, refresh: bool = False) -> Path:
    NEWS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_p = NEWS_RAW_DIR / f"{day}.json"
    if out_p.exists() and not refresh:
        try:
            doc = json.loads(out_p.read_text(encoding="utf-8"))
            if doc.get("trade_date") == day and doc.get("count", 0) > 0:
                return out_p
        except Exception:
            pass
    prev_day = _prev_trade_day(day)
    start_ts = f"{prev_day} 15:00:00"
    end_ts = f"{day} 15:00:00"
    end_epoch = datetime.strptime(end_ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI_TZ).timestamp()
    sort_end = str(int((end_epoch + 2) * 1_000_000))
    kept: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for _ in range(max_pages):
        url = (
            "https://np-weblist.eastmoney.com/comm/web/getFastNewsList"
            f"?client=web&biz=web_724&fastColumn=101&sortEnd={urllib.parse.quote(str(sort_end))}&pageSize=50&req_trace=1"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        data_obj = body.get("data") or {}
        lst = data_obj.get("fastNewsList") or []
        if not lst:
            break
        for it in lst:
            show_t = str(it.get("showTime") or "").strip()
            if start_ts < show_t <= end_ts:
                title = re.sub(r"\s+", " ", str(it.get("title") or "")).strip()
                summary = re.sub(r"\s+", " ", str(it.get("summary") or "")).strip()
                key = (show_t, title)
                if title and key not in seen:
                    seen.add(key)
                    kept.append({"time": show_t, "title": title, "summary": summary})
        oldest_t = str(lst[-1].get("showTime") or "").strip()
        next_sort = str(data_obj.get("sortEnd") or "")
        if (oldest_t and oldest_t <= start_ts) or not next_sort or next_sort == sort_end:
            break
        sort_end = next_sort

    kept.sort(key=lambda x: (x["time"], x["title"]))
    NEWS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_p = NEWS_RAW_DIR / f"{day}.json"
    doc = {"trade_date": day, "window": [start_ts, end_ts], "count": len(kept), "items": kept}
    tmp = out_p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out_p)
    print(json.dumps({"date": day, "window": [start_ts, end_ts], "count": len(kept), "path": str(out_p)}, ensure_ascii=False))
    return out_p


def _fetch_one_ann_day(code: str, col: str, stock_param: str, prev_day: str, day: str) -> tuple[str, list[dict[str, str]], bool]:
    sess = _get_session()
    resp = _cninfo_query_page(sess, stock_param, col, prev_day, day, 1)
    if resp is None:
        return code, [], False
    items: list[dict[str, str]] = []
    seen_t: set[str] = set()
    for a in resp.get("announcements") or []:
        title = re.sub(r"<[^>]+>", "", str(a.get("announcementTitle") or "")).strip()
        if not title or any(k in title for k in NOISE_NOTICE_KWS):
            continue
        ts = a.get("announcementTime")
        if not isinstance(ts, (int, float)):
            continue
        dt = datetime.fromtimestamp(ts / 1000.0, tz=SHANGHAI_TZ).strftime("%Y-%m-%d")
        if dt not in (prev_day, day):
            continue
        if title not in seen_t:
            seen_t.add(title)
            items.append({"date": dt, "title": title})
    return code, items, True


def fetch_ann_day(day: str, refresh: bool = False) -> Path:
    RAW_ANN_DAY_DIR.mkdir(parents=True, exist_ok=True)
    out_p = RAW_ANN_DAY_DIR / f"{day}.json"
    if out_p.exists() and not refresh:
        try:
            doc = json.loads(out_p.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                return out_p
        except Exception:
            pass

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    codes = [
        r[0]
        for r in conn.execute(
            "SELECT code, board_height, is_fanbao, boards_desc FROM daily_limit_pool WHERE trade_date=? ORDER BY code",
            (day,),
        ).fetchall()
        if is_core_stock(r[1], r[2], r[3])
    ]
    conn.close()
    prev_day = _prev_trade_day(day)
    org_map = _load_org_map()

    out: dict[str, list[dict[str, str]]] = {}
    ok_cnt = 0
    err_cnt = 0
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = []
        for code in codes:
            col = "sse" if code.startswith(("6", "9")) else ("szse" if code.startswith(("0", "3")) else "bj")
            org_id = org_map.get(code, "")
            stock_param = f"{code},{org_id}" if org_id else code
            futs.append(ex.submit(_fetch_one_ann_day, code, col, stock_param, prev_day, day))
        for fut in as_completed(futs):
            code, items, ok = fut.result()
            out[code] = items
            if ok:
                ok_cnt += 1
            else:
                err_cnt += 1

    ordered = {c: out.get(c, []) for c in codes}
    tmp = out_p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out_p)
    notice_total = sum(len(v) for v in ordered.values())
    print(json.dumps({"date": day, "window": [prev_day, day], "stocks": len(codes), "ok": ok_cnt, "errors": err_cnt, "notices": notice_total}, ensure_ascii=False))
    return out_p


def _tencent_symbol(code: str) -> str:
    if code.startswith("6"):
        return f"sh{code}"
    if code.startswith(("0", "3")):
        return f"sz{code}"
    return f"bj{code}"


def fetch_kline_one(code: str, start_dt: str = "2026-05-01", end_dt: str = "2026-12-31", refresh: bool = False) -> tuple[str, bool]:
    KLINE_DIR.mkdir(parents=True, exist_ok=True)
    out_p = KLINE_DIR / f"{code}.json"
    if out_p.exists() and not refresh:
        try:
            doc = json.loads(out_p.read_text(encoding="utf-8"))
            if doc.get("code") == code and doc.get("days"):
                return code, True
        except Exception:
            pass
    sc = _tencent_symbol(code)
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sc},day,{start_dt},{end_dt},320,qfq"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            node = (body.get("data") or {}).get(sc) or {}
            rows = node.get("qfqday") or node.get("day") or []
            days = [[str(r[0]), float(r[2])] for r in rows if isinstance(r, list) and len(r) >= 3]
            # Append today's quote close if fqkline CDN hasn't propagated the latest bar yet
            if days:
                try:
                    q_req = urllib.request.Request(f"https://qt.gtimg.cn/q={sc}", headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(q_req, timeout=5) as qr:
                        q_txt = qr.read().decode("gbk", errors="ignore")
                    parts = q_txt.split("~")
                    if len(parts) > 31 and parts[3] and len(parts[30]) >= 8:
                        q_dt = f"{parts[30][:4]}-{parts[30][4:6]}-{parts[30][6:8]}"
                        q_px = float(parts[3])
                        if q_px > 0 and q_dt > days[-1][0] and q_dt <= end_dt:
                            days.append([q_dt, q_px])
                except Exception:
                    pass
                tmp = out_p.with_suffix(".json.tmp")
                tmp.write_text(json.dumps({"code": code, "days": days}, ensure_ascii=False), encoding="utf-8")
                tmp.replace(out_p)
                return code, True
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return code, False


def fetch_kline_cmd(codes: list[str], start_dt: str = "2026-05-01", end_dt: str = "2026-12-31", refresh: bool = False) -> None:
    ok_cnt = 0
    err_cnt = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        for fut in as_completed([ex.submit(fetch_kline_one, c, start_dt, end_dt, refresh) for c in codes]):
            _, ok = fut.result()
            if ok:
                ok_cnt += 1
            else:
                err_cnt += 1
    print(json.dumps({"total": len(codes), "ok": ok_cnt, "errors": err_cnt}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("market")
    pm.add_argument("--from-ultra", action="store_true")
    pm.add_argument("--date", type=str, default=None)

    pe = sub.add_parser("evidence")
    pe.add_argument("--codes", nargs="*", default=None)
    pe.add_argument("--codes-file", type=Path, default=None)
    pe.add_argument("--date", type=str, default=None)
    pe.add_argument("--f10-only", action="store_true")
    pe.add_argument("--refresh", action="store_true")

    pn = sub.add_parser("news")
    pn.add_argument("--date", type=str, default=None)
    pn.add_argument("--month", type=str, default=None)

    pa = sub.add_parser("ann-day")
    pa.add_argument("--date", type=str, default=None)
    pa.add_argument("--month", type=str, default=None)
    pa.add_argument("--refresh", action="store_true")

    pk = sub.add_parser("kline")
    pk.add_argument("--codes", nargs="*", default=None)
    pk.add_argument("--fanbao", action="store_true", help="Fetch daily qfq klines for all fanbao stocks since 2026-06-01")
    pk.add_argument("--start", type=str, default="2026-05-01")
    pk.add_argument("--end", type=str, default="2026-12-31")
    pk.add_argument("--refresh", action="store_true")

    args = parser.parse_args()
    if args.cmd == "market":
        sync_market(args.from_ultra, args.date)
    elif args.cmd == "evidence":
        if args.codes_file:
            codes = [str(c) for c in json.loads(args.codes_file.read_text(encoding="utf-8"))]
        elif args.date:
            conn = ensure_db()
            codes = [r[0] for r in conn.execute("SELECT DISTINCT code FROM daily_limit_pool WHERE trade_date=? ORDER BY code", (args.date,)).fetchall()]
            conn.close()
        else:
            codes = list(args.codes or [])
        fetch_evidence_cmd(codes, f10_only=args.f10_only, refresh=args.refresh)
    elif args.cmd == "news":
        if args.month:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            days = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT trade_date FROM daily_limit_pool WHERE trade_date LIKE ? ORDER BY trade_date ASC",
                    (f"{args.month}-%",),
                ).fetchall()
            ]
            conn.close()
            for d in days:
                fetch_intraday_news(d)
        elif args.date:
            fetch_intraday_news(args.date)
        else:
            raise SystemExit("news requires --date or --month")
    elif args.cmd == "ann-day":
        if args.month:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            days = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT trade_date FROM daily_limit_pool WHERE trade_date LIKE ? ORDER BY trade_date ASC",
                    (f"{args.month}-%",),
                ).fetchall()
            ]
            conn.close()
            for d in days:
                fetch_ann_day(d, refresh=args.refresh)
        else:
            target = args.date
            if not target:
                conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
                row = conn.execute("SELECT MAX(trade_date) FROM daily_limit_pool").fetchone()
                conn.close()
                target = str(row[0]) if row and row[0] else ""
            if not target:
                raise SystemExit("ann-day found no trade_date")
            fetch_ann_day(target, refresh=args.refresh)
    elif args.cmd == "kline":
        if args.fanbao:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            codes = [
                r[0]
                for r in conn.execute(
                    """
                    SELECT DISTINCT code FROM daily_limit_pool
                    WHERE trade_date >= '2026-06-01'
                      AND (is_fanbao = 1 OR boards_desc LIKE '%天%板%')
                    ORDER BY code
                    """
                ).fetchall()
            ]
            conn.close()
        else:
            codes = list(args.codes or [])
        fetch_kline_cmd(codes, start_dt=args.start, end_dt=args.end, refresh=args.refresh)


if __name__ == "__main__":
    main()
