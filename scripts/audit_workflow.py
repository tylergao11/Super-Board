"""Pure-stdlib run_workflow script for Super-Board v2 full-dynamic migration & re-audit."""
import json
import sys
from pathlib import Path

ROOT = Path(args.get("root", r"d:\Super-Board")) if "args" in dir() else Path(r"d:\Super-Board")
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from common import load_taxonomy, validate_record  # noqa: E402

TAXONOMY = load_taxonomy(ROOT / "taxonomy.json")
SHARD_DIR = Path(args.get("shard_dir", str(ROOT / "data/shards"))) if "args" in dir() else (ROOT / "data/shards")
OUT_DIR = Path(args.get("out_dir", str(ROOT / "data/audit_out"))) if "args" in dir() else (ROOT / "data/audit_out")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PREFIX = args.get("prefix", "v2_full_dyn") if "args" in dir() else "v2_full_dyn"
WAVE_SIZE = int(args.get("wave_size", 30)) if "args" in dir() else 30
MIN_TAG_DATE = str(args.get("min_tag_date", "2025-11-26")) if "args" in dir() else "2025-11-26"

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "shard_id": {"type": "string"},
        "stocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "name": {"type": "string"},
                    "province": {"type": "string"},
                    "controller_type": {"type": "string"},
                    "tags": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tag": {"type": "string"},
                                "from_date": {"type": "string"},
                                "evidence": {"type": "string"},
                            },
                            "required": ["tag", "from_date", "evidence"],
                        },
                    },
                    "audit_notes": {"type": "string"},
                },
                "required": ["code", "name", "province", "controller_type", "tags", "audit_notes"],
            },
        },
    },
    "required": ["shard_id", "stocks"],
}

AUDIT_PROMPT = f"""你是 Super-Board v2「完全全动态纯净题材库」升级审计官（只读模式，**严禁调用任何工具**，通读每只股票的完整旧档案+历史被踢记录+近1年涨停轨迹后直接通过 finish 返回 JSON）。

【核心升级铁律：彻底废除静态/动态分裂，以“跨领域想象力（底层能力同源复用）”为唯一尺子】
1. `tags`（全动态纯净题材唯一列表，**不设死板的 4 条上限：有几个实锤可炒的真逻辑就如实给几个，去重，按当下市场核心度与近期催化强度从高到低排序**）：
   - 唯一允许词表（40 词 + 盘面共振 `XX字辈`）：
     - 25 个一级赛道：{json.dumps(TAXONOMY["l1_list"], ensure_ascii=False)}
     - 15 个跨界/字辈分组：{json.dumps(TAXONOMY["dynamic_groups"], ensure_ascii=False)}
   - **关键归口（不拆碎词）**：
     - 洁净室、光刻胶/光刻机、先进封装、存储/HBM、半导体设备材料 → **`芯片`**；
     - 液冷、AIDC、算力租赁、算力电源、服务器/算力基础设施 → **`算力`**；
     - 光模块/CPO、PCB、覆铜板(CCL)、电子铜箔、光纤光缆、高速连接 → **`通信`**（IC 封装载板归 `芯片`）；
     - 减速器/伺服/丝杠/微型传动/传感视觉/工业与人形机器人及自动化产线 → **`机器人`**；通用机床/液压/注塑机/紧固件/焊材归 **`工业设备`**；
     - 纯软件/大模型/AI智能体/SaaS/信创及对外商业化 AI 产品内容服务 → **`AI应用`**（强垂直软件归对应行业）。

2. **全行业一视同仁的准入与纠偏要求（必看！）**：
   - **恢复被旧“后道组装/测试/检测设备补丁”误杀的同源跨界标签**：
     - 输入中的 `recovered_prev_tags` 保留了旧版审计前曾有过的合法跨界标签；只要公司产品/设备/工艺/材料/洁净室确实可输出到该目标赛道、且有客观应用/订单/送样/产线/子公司实体（如克来机电光模块组装→`通信`、易天股份1.6T硅光倒装贴片机→`通信`、科瑞技术光芯片设备/AI眼镜产线→`通信`/`消费电子`、快克智能光模块/液冷产线→`通信`/`算力`、大族激光液冷焊接→`算力`、博杰股份机器人IMU测试→`机器人`、东方中科半导体测试→`芯片`、胜科纳米光器件失效分析→`通信`、闽发铝业新材料子公司拓展机器人铝型材→`机器人`、金螳螂半导体洁净室→`芯片`），**一律恢复/保留**！
   - **允许 0% 营收的真跨界想象力**：只要底层工艺/产能可同源输出且有实质动作（具体产品、送样、产线应用、新设/参股实体、战略合作或近 1 年盘面实锤），不卡财报 5% 门槛，也不卡 4 条数量上限，有几个真逻辑就如实全部入 `tags`（按当下市场最核心、催化最近排序）。
   - **果断清掉“早已被市场抛弃的僵尸旧壳主业”**：
     - 如果一只股票已经转型/形成了非常鲜明的高景气核心题材（近 1 年多次围绕新赛道涨停），而其传统老主业（如顺灏股份的烟标`消费`、哈森股份的女鞋`消费`、大胜达的纸箱`消费`、全筑股份的家装`基建`/`消费`、粤宏远A的传统`地产`、雪人集团的传统`消费`/`石油`、双成药业的退潮旧业等）在近 1 年盘面上根本没人炒，**从 `tags` 中剔除这些干扰视线的旧壳标签**（仅在 `audit_notes` 注明主营底色即可）！
     - 反之，若主业本身就是市场核心炒作逻辑（如盛达资源`有色`、杭州解百`消费`、天圣制药`医药`、赤天化`化工`、骏亚科技`通信`、利君股份`军工`、克来机电`机器人`/`汽车`等），正常保留在 `tags` 中！
   - **`from_date`**：必填 `YYYY-MM-DD`，必须 `>= {MIN_TAG_DATE}`（有近 1 年涨停或公告的取最近一次有效催化/公告日；纯主业无新公告的取最新定期报告日如 `2026-06-30` 或 `2026-08-31`）。

3. **唯一 4 条硬剔除红线（绝不恢复真噪音！）**：
   - ① 官方公告明确辟谣不涉及/无业务无合作（如金螳螂商业航天仅为办公楼餐厅、威派格澄清无液冷）；
   - ② **纯买家内部赋能**：内部接 DeepSeek 写文案/客服/画图/辅助湿实验、或买设备自用（原 `ai_app_cleanup` 剔掉的内部赋能噪音与端侧普通家电/设备自带AI算法，**不要恢复**进 `AI应用`！）；
   - ③ **纯行政/生活泛服务**：给发射场/机房盖办公楼食堂、物业、常规绿电直供、纯代理分销；
   - ④ **软件脏词与陈年僵尸**：业绩增长、超跌、ST摘帽、次新股、并购重组词（并购放 `ma_events` 不进 `tags`）、以及超 1 年毫无进展与催化的陈年老概念。

4. `province` 必须属于 {json.dumps(TAXONOMY["provinces"], ensure_ascii=False)}，`controller_type` 必须属于 {json.dumps(TAXONOMY["controller_types"], ensure_ascii=False)}。`audit_notes` 简明写清本次全动态整合与去壳/恢复依据。
"""


def _validate_with_ev(rec: dict, ev: dict | None) -> list[str]:
    merged = dict(rec)
    merged["ma_events"] = []
    return validate_record(merged, ev, TAXONOMY, min_tag_date=MIN_TAG_DATE)


def _is_valid(shard_id: str) -> bool:
    ev_p = SHARD_DIR / f"{shard_id}.json"
    out_p = OUT_DIR / f"{shard_id}.json"
    if not ev_p.exists() or not out_p.exists():
        return False
    try:
        ev_doc = json.loads(ev_p.read_text(encoding="utf-8"))
        out_doc = json.loads(out_p.read_text(encoding="utf-8"))
        ev_map = {s["code"]: s for s in ev_doc["stocks"]}
        got = set()
        for rec in out_doc.get("stocks", []):
            c = str(rec.get("code") or "")
            got.add(c)
            if _validate_with_ev(rec, ev_map.get(c)):
                return False
        return got == set(ev_map.keys())
    except Exception:
        return False


async def audit_shard(shard_id: str) -> dict:
    try:
        ev_doc = json.loads((SHARD_DIR / f"{shard_id}.json").read_text(encoding="utf-8"))
        stocks = ev_doc["stocks"]
        ev_by_code = {s["code"]: s for s in stocks}
        prompt = (
            AUDIT_PROMPT
            + f"\n请严格按 Super-Board v2 全动态规则审计分片 {shard_id} 全部 {len(stocks)} 只股票（严禁遗漏）：\n"
            + json.dumps(stocks, ensure_ascii=False, separators=(",", ":"))
        )
        a = agent(role=f"V2Audit {shard_id}", type_name="research")
        res = await a(prompt, OUTPUT_SCHEMA)
        for _ in range(2):
            errs = []
            got = set()
            for rec in res.get("stocks", []):
                c = str(rec.get("code") or "")
                got.add(c)
                errs.extend(_validate_with_ev(rec, ev_by_code.get(c)))
            missing = sorted(set(ev_by_code.keys()) - got)
            if missing:
                errs.append(f"遗漏股票: {missing}")
            if not errs:
                break
            res = await a("校验未通过，请逐条修正后重新输出完整全部股票JSON：\n" + "\n".join(errs[:35]), OUTPUT_SCHEMA)
        del a

        final_errs = []
        got = {str(r.get("code") or "") for r in res.get("stocks", [])}
        missing = sorted(set(ev_by_code.keys()) - got)
        if missing:
            final_errs.append(f"missing: {missing}")
        for rec in res.get("stocks", []):
            final_errs.extend(_validate_with_ev(rec, ev_by_code.get(str(rec.get("code") or ""))))
        if final_errs:
            return {"shard_id": shard_id, "ok": False, "error": str(final_errs[:8])}

        res["shard_id"] = shard_id
        (OUT_DIR / f"{shard_id}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"shard_id": shard_id, "ok": True, "count": len(res["stocks"])}
    except Exception as exc:
        return {"shard_id": shard_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


phase(f"Super-Board v2 Full-Dynamic Audit ({PREFIX})")
manifest = json.loads((SHARD_DIR / f"{PREFIX}_manifest.json").read_text(encoding="utf-8"))
all_shards = [s["shard_id"] for s in manifest["shards"]]
pending = [sid for sid in all_shards if not _is_valid(sid)]
log(f"Prefix={PREFIX}, total={len(all_shards)}, valid={len(all_shards)-len(pending)}, pending={len(pending)}")

failed = []
for i in range(0, len(pending), WAVE_SIZE):
    wave = pending[i : i + WAVE_SIZE]
    res_list = await parallel(wave, audit_shard)
    bad = [r for r in res_list if not r["ok"]]
    failed.extend(r["shard_id"] for r in bad)
    log(f"Wave {i//WAVE_SIZE+1}: ok={len(wave)-len(bad)}/{len(wave)}, failed={bad}")

if failed:
    log(f"Retrying {len(failed)} failed shards...")
    r_list = await parallel(failed, audit_shard)
    still_bad = [r for r in r_list if not r["ok"]]
    if still_bad:
        raise RuntimeError(f"Audit shards still failed after retry: {still_bad}")

log("Audit complete:", PREFIX, "total_shards=", len(all_shards))
