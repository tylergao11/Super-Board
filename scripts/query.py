"""Clean Markdown table query CLI for Super-Board."""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from common import DB_PATH


def _cutoff_1yr(date_str: str) -> str:
    return (datetime.strptime(date_str, "%Y-%m-%d").date() - timedelta(days=365)).isoformat()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def _fmt_static(rows: list[sqlite3.Row]) -> str:
    return "、".join(r["l1"] for r in rows) or "-"


def _fmt_dyn(rows: list[sqlite3.Row]) -> str:
    parts = []
    for r in rows:
        if r["to_date"]:
            parts.append(f"{r['group_name']}({r['to_date']}退)")
        else:
            parts.append(r["group_name"])
    return "、".join(parts) or "-"


def _fmt_ma(rows: list[sqlite3.Row]) -> str:
    parts = []
    for r in rows:
        tl1 = f"→{r['target_l1']}" if r["target_l1"] else ""
        parts.append(f"{r['target_name']}{tl1}")
    return "；".join(parts) or "-"


def query_daily(date: str) -> str:
    c = _conn()
    pool = c.execute(
        """
        SELECT * FROM daily_limit_pool
        WHERE trade_date = ?
        ORDER BY board_height DESC, first_limit_time ASC, code ASC
        """,
        (date,),
    ).fetchall()
    news_rows = c.execute(
        "SELECT rank, headline, detail, hit_count FROM daily_hot_news WHERE trade_date=? ORDER BY rank ASC",
        (date,),
    ).fetchall()

    multi = sum(1 for r in pool if r["board_height"] >= 2)
    lines = [
        f"# {date} 涨停梯队纯净题材表（共 {len(pool)} 只：连板 {multi} 只 + 首板 {len(pool) - multi} 只）",
        "",
    ]
    if news_rows:
        lines.append("## 当日热门消息")
        for nr in news_rows:
            lines.append(f"{nr['rank']}. **{nr['headline']}**：{nr['detail']}")
        lines.append("")

    lines += [
        "| 代码 | 名称 | 高度 | 首封 | 省份(国资) | 静态 | 动态分组 | 并购重组(对象) |",
        "|---|---|---:|---|---|---|---|---|",
    ]
    untagged = []
    for r in pool:
        code = r["code"]
        st = c.execute("SELECT * FROM stocks WHERE code=?", (code,)).fetchone()
        if not st:
            untagged.append(f"{code} {r['name']}({r['board_height']}板)")
            lines.append(f"| `{code}` | {r['name']} | {r['board_height']}板 | {r['first_limit_time']} | 未入库 | - | - | - |")
            continue
        prov = st["province"]
        if st["controller_province"] and st["controller_province"] != prov:
            prov = f"{prov}({st['controller_province']}国资)"
        s_rows = c.execute(
            "SELECT * FROM static_tags WHERE code=? ORDER BY COALESCE(revenue_pct, -1) DESC, id ASC",
            (code,),
        ).fetchall()
        d_rows = c.execute(
            "SELECT * FROM dynamic_tags WHERE code=? AND (to_date IS NULL OR to_date >= ?) AND from_date >= ?",
            (code, date, _cutoff_1yr(date)),
        ).fetchall()
        m_rows = c.execute("SELECT * FROM ma_events WHERE code=? ORDER BY from_date DESC, id ASC", (code,)).fetchall()

        lines.append(
            f"| `{code}` | {st['name']} | {r['board_height']}板 | {r['first_limit_time']} | {prov} | {_fmt_static(s_rows)} | {_fmt_dyn(d_rows)} | {_fmt_ma(m_rows)} |"
        )
    if untagged:
        lines += ["", f"## 待补充入库股票（{len(untagged)} 只）", "、".join(untagged)]
    c.close()
    return "\n".join(lines)


def query_theme(name: str) -> str:
    c = _conn()
    like = f"%{name}%"
    latest_row = c.execute("SELECT MAX(trade_date) FROM daily_limit_pool").fetchone()
    latest_dt = str(latest_row[0] or "2026-11-26")
    cutoff = _cutoff_1yr(latest_dt)
    s_rows = c.execute(
        """
        SELECT p.code, p.name, p.province, s.l1, s.revenue_pct, s.evidence
        FROM static_tags s JOIN stocks p ON s.code=p.code
        WHERE s.l1 = ? OR s.evidence LIKE ?
        ORDER BY COALESCE(s.revenue_pct, -1) DESC, p.code
        """,
        (name, like),
    ).fetchall()
    d_rows = c.execute(
        """
        SELECT p.code, p.name, d.group_name, d.from_date, d.to_date, d.evidence
        FROM dynamic_tags d JOIN stocks p ON d.code=p.code
        WHERE (d.group_name = ? OR d.evidence LIKE ?)
          AND (d.to_date IS NULL OR d.to_date >= ?)
          AND d.from_date >= ?
        ORDER BY d.from_date DESC, p.code ASC
        """,
        (name, like, latest_dt, cutoff),
    ).fetchall()
    m_rows = c.execute(
        """
        SELECT p.code, p.name, m.event_type, m.target_name, m.target_l1, m.from_date, m.evidence
        FROM ma_events m JOIN stocks p ON m.code=p.code
        WHERE m.target_l1 = ? OR m.target_name LIKE ? OR m.evidence LIKE ?
        ORDER BY m.from_date DESC, p.code ASC
        """,
        (name, like, like),
    ).fetchall()

    lines = [f"# 题材小表格：{name}", "", f"## 一、静态（{len(s_rows)} 只）", "| 代码 | 名称 | 省份 | 大类 | 占比 | 核心依据 |", "|---|---|---|---|---:|---|"]
    for r in s_rows:
        pct = f"{r['revenue_pct']}%" if r["revenue_pct"] is not None else "-"
        lines.append(f"| `{r['code']}` | {r['name']} | {r['province']} | {r['l1']} | {pct} | {r['evidence'][:80]} |")

    lines += ["", f"## 二、动态（近1年有效，{len(d_rows)} 条）", "| 代码 | 名称 | 动态分组 | 有效期 | 依据 |", "|---|---|---|---|---|"]
    for r in d_rows:
        lines.append(f"| `{r['code']}` | {r['name']} | {r['group_name']} | {r['from_date']}~{r['to_date'] or '至今'} | {r['evidence'][:80]} |")

    lines += ["", f"## 三、筹划中并购对象关联（{len(m_rows)} 条）", "| 代码 | 名称 | 类型 | 重组对象 | 目标大类 | 起始日 | 依据 |", "|---|---|---|---|---|---|---|"]
    for r in m_rows:
        lines.append(f"| `{r['code']}` | {r['name']} | {r['event_type']} | {r['target_name']} | {r['target_l1'] or '-'} | {r['from_date']} | {r['evidence'][:70]} |")
    c.close()
    return "\n".join(lines)


def query_ma() -> str:
    c = _conn()
    rows = c.execute(
        """
        SELECT m.*, p.name,
               (SELECT GROUP_CONCAT(l1, '、') FROM static_tags s WHERE s.code=m.code) AS static_l1
        FROM ma_events m JOIN stocks p ON m.code=p.code
        ORDER BY m.from_date DESC, m.code ASC
        """
    ).fetchall()
    lines = [
        f"# 筹划中并购重组与控股权事件清单（共 {len(rows)} 条）",
        "",
        "| 代码 | 名称 | 静态大类 | 事件类型 | 重组对象 | 对象大类 | 起始日 | 依据 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['code']}` | {r['name']} | {r['static_l1'] or '-'} | {r['event_type']} | {r['target_name']} | {r['target_l1'] or '-'} | {r['from_date']} | {r['evidence'][:70]} |"
        )
    c.close()
    return "\n".join(lines)


def query_stock(code: str) -> str:
    c = _conn()
    p = c.execute("SELECT * FROM stocks WHERE code=?", (code,)).fetchone()
    if not p:
        c.close()
        return f"未找到 {code}"
    lines = [
        f"# {p['code']} {p['name']}（{p['province']}{' / 国资:' + p['controller_province'] if p['controller_province'] and p['controller_province'] != p['province'] else ''} · {p['controller_type']} · 出海:{p['overseas_pct']}%）",
        f"- 实控人: {p['controller_name']} | 东财行业: {p['em_industry']} | 人工锁: {bool(p['manual_verified'])}",
        f"- 综合研判: {p['audit_notes']}",
        "",
        "## 静态",
    ]
    latest_row = c.execute("SELECT MAX(trade_date) FROM daily_limit_pool").fetchone()
    latest_dt = str(latest_row[0] or "2026-11-26")
    cutoff = _cutoff_1yr(latest_dt)
    for r in c.execute("SELECT * FROM static_tags WHERE code=? ORDER BY COALESCE(revenue_pct, -1) DESC, id ASC", (code,)):
        pct = f" ({r['revenue_pct']}%)" if r["revenue_pct"] is not None else ""
        lines.append(f"- **{r['l1']}**{pct}: {r['evidence']}")
    lines.append("\n## 动态（近1年有效）")
    for r in c.execute(
        "SELECT * FROM dynamic_tags WHERE code=? AND (to_date IS NULL OR to_date >= ?) AND from_date >= ? ORDER BY from_date DESC",
        (code, latest_dt, cutoff),
    ):
        lines.append(f"- **{r['group_name']}** [{r['from_date']}~{r['to_date'] or '至今'}]: {r['evidence']}")
    lines.append("\n## 筹划中并购重组")
    for r in c.execute("SELECT * FROM ma_events WHERE code=? ORDER BY from_date DESC, id ASC", (code,)):
        lines.append(f"- **{r['event_type']} -> {r['target_name']}** (目标:{r['target_l1'] or '-'}, {r['from_date']}起): {r['evidence']}")
    lines.append("\n## 近期涨停轨迹")
    for r in c.execute("SELECT * FROM daily_limit_pool WHERE code=? ORDER BY trade_date DESC LIMIT 10", (code,)):
        lines.append(f"- {r['trade_date']} {r['board_height']}板 {r['first_limit_time']} {r['kpl_reason'][:85]}")
    c.close()
    return "\n".join(lines)


def query_month(month: str, out_dir: Path) -> str:
    c = _conn()
    days = [
        r[0]
        for r in c.execute(
            "SELECT DISTINCT trade_date FROM daily_limit_pool WHERE trade_date LIKE ? ORDER BY trade_date ASC",
            (f"{month}-%",),
        ).fetchall()
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    idx_lines = [
        f"# {month} 全月每日复盘索引（共 {len(days)} 个交易日）",
        "",
        "| 日期 | 涨停家数 | 最高连板 | 领涨高标 | 当日热门消息前三 | 详情 |",
        "|---|---:|---:|---|---|---|",
    ]
    for d in days:
        pool = c.execute(
            "SELECT code, name, board_height FROM daily_limit_pool WHERE trade_date=? ORDER BY board_height DESC, first_limit_time ASC, code ASC",
            (d,),
        ).fetchall()
        max_h = max((r["board_height"] for r in pool), default=0)
        leaders = "、".join(f"{r['name']}({r['board_height']}板)" for r in pool if r["board_height"] == max_h)[:45]
        news_rows = c.execute(
            "SELECT headline FROM daily_hot_news WHERE trade_date=? ORDER BY rank ASC LIMIT 3",
            (d,),
        ).fetchall()
        top_news = "；".join(nr["headline"] for nr in news_rows) or "-"
        daily_md = query_daily(d)
        (out_dir / f"daily_{d}.md").write_text(daily_md + "\n", encoding="utf-8")
        idx_lines.append(f"| {d} | {len(pool)} | {max_h}板 | {leaders} | {top_news} | [daily_{d}.md](./daily_{d}.md) |")
    c.close()
    index_text = "\n".join(idx_lines)
    (out_dir / f"index_{month}.md").write_text(index_text + "\n", encoding="utf-8")
    return index_text


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    pd = sub.add_parser("daily")
    pd.add_argument("--date", required=True)
    pd.add_argument("--out", type=Path, default=None)

    pt = sub.add_parser("theme")
    pt.add_argument("--name", required=True)
    pt.add_argument("--out", type=Path, default=None)

    pm = sub.add_parser("ma")
    pm.add_argument("--out", type=Path, default=None)

    pmo = sub.add_parser("month")
    pmo.add_argument("--month", required=True)
    pmo.add_argument("--out-dir", type=Path, required=True)

    ps = sub.add_parser("stock")
    ps.add_argument("--code", required=True)

    args = parser.parse_args()
    if args.cmd == "daily":
        text = query_daily(args.date)
    elif args.cmd == "theme":
        text = query_theme(args.name)
    elif args.cmd == "ma":
        text = query_ma()
    elif args.cmd == "month":
        text = query_month(args.month, args.out_dir)
    else:
        text = query_stock(args.code)

    if getattr(args, "out", None):
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
