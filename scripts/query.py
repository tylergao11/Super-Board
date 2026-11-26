"""Clean Markdown table query CLI for Super-Board."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from common import DB_PATH


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def _fmt_static(rows: list[sqlite3.Row]) -> str:
    parts = []
    for r in rows:
        parts.append(r["l1"] if r["weight"] == "主营" else f"{r['l1']}[{r['weight']}]")
    return "、".join(parts) or "-"


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
        parts.append(f"{r['target_name']}{tl1}[{r['status']}]")
    return "；".join(parts) or "-"


def _fmt_excl(rows: list[sqlite3.Row]) -> str:
    return "；".join(f"{r['tag']}({r['reason_type']})" for r in rows) or "-"


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

    multi = sum(1 for r in pool if r["board_height"] >= 2)
    lines = [
        f"# {date} 涨停梯队纯净题材表（共 {len(pool)} 只：连板 {multi} 只 + 首板 {len(pool) - multi} 只）",
        "",
        "| 代码 | 名称 | 高度 | 首封 | 开盘啦催化 | 省份(国资) | 静态(我一直有) | 动态分组 | 并购重组(对象+状态) | 显性排雷 |",
        "|---|---|---:|---|---|---|---|---|---|---|",
    ]
    untagged = []
    alerts = []
    for r in pool:
        code = r["code"]
        st = c.execute("SELECT * FROM stocks WHERE code=?", (code,)).fetchone()
        cat = r["kpl_topic"] or "-"
        if not st:
            untagged.append(f"{code} {r['name']}({r['board_height']}板/{cat})")
            lines.append(f"| `{code}` | {r['name']} | {r['board_height']}板 | {r['first_limit_time']} | {cat} | 未入库 | - | - | - | - |")
            continue
        prov = st["province"]
        if st["controller_province"] and st["controller_province"] != prov:
            prov = f"{prov}({st['controller_province']}国资)"
        s_rows = c.execute("SELECT * FROM static_tags WHERE code=? ORDER BY CASE weight WHEN '主营' THEN 0 WHEN '副业' THEN 1 ELSE 2 END, revenue_pct DESC", (code,)).fetchall()
        d_rows = c.execute("SELECT * FROM dynamic_tags WHERE code=? AND to_date IS NULL", (code,)).fetchall()
        m_rows = c.execute("SELECT * FROM ma_events WHERE code=? ORDER BY from_date DESC", (code,)).fetchall()
        e_rows = c.execute("SELECT * FROM exclusions WHERE code=?", (code,)).fetchall()

        for e in e_rows:
            if e["tag"] and cat and (e["tag"] in cat or cat in e["tag"]):
                alerts.append(f"- **碰撞预警**：`{code} {st['name']}` 今日催化 `{cat}` 命中排雷 `{e['tag']}({e['reason_type']})` —— {e['evidence'][:60]}")

        lines.append(
            f"| `{code}` | {st['name']} | {r['board_height']}板 | {r['first_limit_time']} | {cat} | {prov} | {_fmt_static(s_rows)} | {_fmt_dyn(d_rows)} | {_fmt_ma(m_rows)} | {_fmt_excl(e_rows)} |"
        )
    if alerts:
        lines += ["", "## 排雷碰撞提示"] + alerts
    if untagged:
        lines += ["", f"## 待补充入库股票（{len(untagged)} 只）", "、".join(untagged)]
    c.close()
    return "\n".join(lines)


def query_theme(name: str) -> str:
    c = _conn()
    like = f"%{name}%"
    s_rows = c.execute(
        """
        SELECT p.code, p.name, p.province, s.l1, s.weight, s.revenue_pct, s.evidence
        FROM static_tags s JOIN stocks p ON s.code=p.code
        WHERE s.l1 = ? OR s.evidence LIKE ?
        ORDER BY CASE s.weight WHEN '主营' THEN 0 WHEN '副业' THEN 1 ELSE 2 END, COALESCE(s.revenue_pct, 0) DESC, p.code
        """,
        (name, like),
    ).fetchall()
    d_rows = c.execute(
        """
        SELECT p.code, p.name, d.group_name, d.from_date, d.to_date, d.evidence
        FROM dynamic_tags d JOIN stocks p ON d.code=p.code
        WHERE d.group_name LIKE ? OR d.evidence LIKE ?
        ORDER BY COALESCE(d.to_date, '9999-12-31') DESC, d.from_date DESC
        """,
        (like, like),
    ).fetchall()
    m_rows = c.execute(
        """
        SELECT p.code, p.name, m.event_type, m.target_name, m.target_l1, m.status, m.from_date, m.to_date, m.evidence
        FROM ma_events m JOIN stocks p ON m.code=p.code
        WHERE m.target_l1 = ? OR m.target_name LIKE ? OR m.evidence LIKE ?
        ORDER BY m.from_date DESC
        """,
        (name, like, like),
    ).fetchall()
    e_rows = c.execute(
        """
        SELECT p.code, p.name, e.tag, e.reason_type, e.evidence_date, e.evidence
        FROM exclusions e JOIN stocks p ON e.code=p.code
        WHERE e.tag LIKE ? OR e.evidence LIKE ?
        ORDER BY p.code
        """,
        (like, like),
    ).fetchall()

    lines = [f"# 题材小表格：{name}", "", f"## 一、静态一直有（{len(s_rows)} 只）", "| 代码 | 名称 | 省份 | 大类 | 分量 | 占比 | 核心依据 |", "|---|---|---|---|---|---:|---|"]
    for r in s_rows:
        pct = f"{r['revenue_pct']}%" if r["revenue_pct"] is not None else "-"
        lines.append(f"| `{r['code']}` | {r['name']} | {r['province']} | {r['l1']} | {r['weight']} | {pct} | {r['evidence'][:80]} |")

    lines += ["", f"## 二、动态跨界分组（{len(d_rows)} 条）", "| 代码 | 名称 | 动态分组 | 有效期 | 依据 |", "|---|---|---|---|---|"]
    for r in d_rows:
        lines.append(f"| `{r['code']}` | {r['name']} | {r['group_name']} | {r['from_date']}~{r['to_date'] or '至今'} | {r['evidence'][:80]} |")

    lines += ["", f"## 三、并购重组对象关联（{len(m_rows)} 条）", "| 代码 | 名称 | 类型 | 重组对象 | 目标大类 | 状态 | 时间 | 依据 |", "|---|---|---|---|---|---|---|---|"]
    for r in m_rows:
        lines.append(f"| `{r['code']}` | {r['name']} | {r['event_type']} | {r['target_name']} | {r['target_l1'] or '-'} | {r['status']} | {r['from_date']}~{r['to_date'] or '至今'} | {r['evidence'][:70]} |")

    lines += ["", f"## 四、显性排雷名单（{len(e_rows)} 条）", "| 代码 | 名称 | 排雷词 | 原因 | 日期 | 依据 |", "|---|---|---|---|---|---|"]
    for r in e_rows:
        lines.append(f"| `{r['code']}` | {r['name']} | {r['tag']} | {r['reason_type']} | {r['evidence_date'] or '-'} | {r['evidence'][:80]} |")
    c.close()
    return "\n".join(lines)


def query_ma(status: str | None) -> str:
    c = _conn()
    sql = """
        SELECT m.*, p.name,
               (SELECT GROUP_CONCAT(l1, '、') FROM static_tags s WHERE s.code=m.code AND s.weight='主营') AS main_l1
        FROM ma_events m JOIN stocks p ON m.code=p.code
    """
    args = []
    if status:
        sql += " WHERE m.status = ?"
        args.append(status)
    sql += " ORDER BY CASE m.status WHEN '筹划中' THEN 0 WHEN '已完成' THEN 1 ELSE 2 END, m.from_date DESC"
    rows = c.execute(sql, args).fetchall()
    lines = [
        f"# 并购重组与控股权事件清单（共 {len(rows)} 条）",
        "",
        "| 代码 | 名称 | 原主营 | 事件类型 | 重组对象 | 对象大类 | 状态 | 时间 | 依据 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['code']}` | {r['name']} | {r['main_l1'] or '-'} | {r['event_type']} | {r['target_name']} | {r['target_l1'] or '-'} | {r['status']} | {r['from_date']}~{r['to_date'] or '至今'} | {r['evidence'][:70]} |"
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
        "## 静态（我一直有）",
    ]
    for r in c.execute("SELECT * FROM static_tags WHERE code=? ORDER BY CASE weight WHEN '主营' THEN 0 WHEN '副业' THEN 1 ELSE 2 END, revenue_pct DESC", (code,)):
        pct = f" ({r['revenue_pct']}%)" if r["revenue_pct"] is not None else ""
        lines.append(f"- **{r['l1']}** [{r['weight']}{pct}]: {r['evidence']}")
    lines.append("\n## 动态跨界分组")
    for r in c.execute("SELECT * FROM dynamic_tags WHERE code=?", (code,)):
        lines.append(f"- **{r['group_name']}** [{r['from_date']}~{r['to_date'] or '至今'}]: {r['evidence']}")
    lines.append("\n## 并购重组")
    for r in c.execute("SELECT * FROM ma_events WHERE code=?", (code,)):
        lines.append(f"- **{r['event_type']} -> {r['target_name']}** (目标:{r['target_l1'] or '-'} / {r['status']}, {r['from_date']}~{r['to_date'] or '至今'}): {r['evidence']}")
    lines.append("\n## 显性排雷")
    for r in c.execute("SELECT * FROM exclusions WHERE code=?", (code,)):
        lines.append(f"- **{r['tag']}** ({r['reason_type']}, {r['evidence_date'] or '-'}): {r['evidence']}")
    lines.append("\n## 近期涨停轨迹")
    for r in c.execute("SELECT * FROM daily_limit_pool WHERE code=? ORDER BY trade_date DESC LIMIT 10", (code,)):
        lines.append(f"- {r['trade_date']} {r['board_height']}板 {r['first_limit_time']} [{r['kpl_topic']}] {r['kpl_reason'][:80]}")
    c.close()
    return "\n".join(lines)


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
    pm.add_argument("--status", default=None)
    pm.add_argument("--out", type=Path, default=None)

    ps = sub.add_parser("stock")
    ps.add_argument("--code", required=True)

    args = parser.parse_args()
    if args.cmd == "daily":
        text = query_daily(args.date)
    elif args.cmd == "theme":
        text = query_theme(args.name)
    elif args.cmd == "ma":
        text = query_ma(args.status)
    else:
        text = query_stock(args.code)

    if getattr(args, "out", None):
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
