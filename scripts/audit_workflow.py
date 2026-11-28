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

【核心定位与审计铁律：A 股游资题材归类视角（跟随盘面，区别于传统申万/东财行业归类）】
- **跟随盘面才是游资产业链行为**：本库按 **A 股游资与超短线资金的炒作视角** 归类题材。**拿不准时先还原盘面**：结合 `limit_up_topic_counts` 与每次涨停当日的 `day_top_sectors` / `day_leaders`，先看清它反复跟着哪个板块动，再用 F10/公告印证联动抓手，以“跨领域想象力（底层能力同源复用 + 新实控人/产业战投背景映射）”为唯一尺子。
1. `tags`（全动态纯净题材唯一列表，按独立实锤逻辑如实收录，去重，按当下市场核心度与近期催化强度从高到低排序）：
   - 唯一标准词表（33 词）：
     - 23 个一级赛道：{json.dumps(TAXONOMY["l1_list"], ensure_ascii=False)}
     - 10 个跨界分组：{json.dumps(TAXONOMY["dynamic_groups"], ensure_ascii=False)}
   - **关键归口（统一收口标准词）**：
     - 洁净室、光刻胶/光刻机、先进封装/玻璃基板、存储/HBM、培育钻石/金刚石散热（MPCVD/热沉）、半导体设备材料，以及 OLED/LCD 显示面板、Mini/Micro-LED、硅基 OLED、偏光片/光学膜/滤光片/导光板等光电显示器件 → **`芯片`**；
     - 液冷、AIDC、算力租赁、算力电源、服务器/算力基础设施 → **`算力`**；
     - 光模块/CPO、PCB、覆铜板(CCL)、电子铜箔、光纤光缆、高速连接器，以及 MLCC/电阻电容/电感/晶振/电极箔/离型膜等被动元器件 → **`通信`**（IC 封装载板归 `芯片`）；
     - 智能电网/特高压/输变电、核电与可控核聚变、发电运营及电网侧独立储能电站 → **`电力`**；
     - 锂电（固态电池/钠电/锂矿/电池材料）、光伏制造（硅料/组件/玻璃/边框/设备/太空光伏）与储能系统/充电桩 → **`锂电光伏`**（制氢/储运/燃料电池归 **`氢能源`**）；石油开采/油服/炼化及天然气/LNG/城燃 → **`油气`**；
     - 港口与海运/油运/集运/干散货远洋运输，以及纯血快递、跨境与多式联运货运、大宗供应链物流与外贸货代 → **`航运物流`**（港机/叉车/分拣设备厂归 `基建`/`机械设备`/`机器人`，百货地产水泥附带物流园不入；跨境电商与消费商社归 `消费`）；轨交与公路铁路设施归 `基建`，民航出行归 `消费`；
     - 房地产开发、物业服务、地产经纪，以及家居家具、地板、卫浴、门窗、幕墙、瓷砖、吊顶、定制家居、家装建材、装饰原纸、电梯、房屋检测、住宅精装修装饰与浮法平板玻璃等地产后周期链 → **`地产链`**（`消费` 专注食品饮料/百货零售/跨境电商/免税旅游/纺织服装/品牌家电日化/文创潮玩/造纸包装；`基建` 专注大型建筑工程施工/路桥轨交高速/水泥管材/水利工程/建筑节能/工程机械；钢铁/黑色金属归 `有色`）；
     - 无人驾驶/Robotaxi、车路云、L2+/L3/L4 自动驾驶、激光雷达/毫米波雷达、线控底盘/转向制动、智驾域控/智能座舱域控 → **`智能驾驶`**；汽车整车、汽配（内饰/压铸/热管理/底盘/线束/车灯）及车载显示 → **`汽车链`**；
     - 减速器/伺服/丝杠/微型传动/传感视觉、物理AI视觉终端、工业/人形/扫地清洁机器人、工业母机/数控机床、工业自动化产线 → **`机器人`**；通用与专用工业装备（工业制冷/纺机/包机/压机/绕线机/泵阀/轴承基础件/工业照明/金属容器）→ **`机械设备`**（橡胶轮胎/胶管归 `化工`）；
     - 纯软件/大模型/AI智能体/SaaS/信创、对外商业化 AI 产品内容服务、AI 眼镜/智能音箱等端侧 AI 交互终端，以及影视/游戏/出版/广电/广告营销/在线教育等文化传媒主业标的 → 统一归 **`AI应用`**（非文化传媒主业仅按其自身真实对外 AI 业务判断；强垂直软件归对应行业）。

2. **准入与活跃主业分层**：
   - **通道① 底层能力同源复用**：只要公司产品、设备、工艺、材料、洁净室或实体可输出到目标赛道，且有客观动作（涵盖研发项目、样机试制、提供样品/送样、开发验证、产线适配、新设/参股实体、战略合作、量产供货或近 1 年盘面实锤）→ **从研发、试制、送样、验证到量产全周期一律判作【有】**。
   - **通道② 新实控人 / 新控股股东 / 知名产业战投背景映射**：已完成控股权变更或引入明确产业实体/独角兽战投，且盘面围绕其产业背景映射炒作，直接按入主方或战投方核心赛道打标。
   - **活跃主业与旧壳分层**：
     - 已转型并形成鲜明高景气新主线的标的，其近 1 年无盘面炒作的传统旧壳主业（如顺灏的烟标、哈森的女鞋、大胜达的纸箱、全筑的传统家装、粤宏远A的传统地产链、雪人集团的传统消费/油气）沉淀在 `audit_notes` 备查，让 `tags` 聚焦活跃主线；
     - 市场仍在炒作的活跃主业（如盛达资源`有色`、杭州解百`消费`、天圣制药`医药`、赤天化`化工`、骏亚科技`通信`、利君股份`军工`、克来机电`机器人`等）正常保留在 `tags` 中。
   - **`from_date` 与长期保留**：必填 `YYYY-MM-DD`（有近期涨停或公告的取最近一次有效催化/公告日；纯主业取最新定期报告日如 `2026-06-30`/`2026-08-31`）；**已核实的真实产业逻辑与新实控人映射长期保留、不按年限自动淘汰，除非官方主动否认、终止或剥离**。

3. **4 类噪音剔除标准**：
   - ① **官方公告明确否认**：仅当官方公告明确否认“未开展、无技术储备、无布局打算、无任何合作”时予以剔除；异动/风险提示公告中的“尚处提供样品/送样验证/研发试制/开发验证/前期投入/未批量生产/尚未形成收入/占比极低”以及控股权变更公告中的“未来 12/36 个月内无借壳或资产注入计划”属常规合规提示，正常保留对应赛道；
   - ② **非传媒主业的纯买家内部赋能**：企业仅在内部接入外部工具降本增效（如非传媒企业内部接 DeepSeek 写文案/客服/画图/辅助湿实验，或买设备自用），未形成对外输出能力；
   - ③ **纯行政/生活泛服务**：给发射场/机房盖办公楼食堂、物业、常规绿电直供、纯代理分销；
   - ④ **行情软件非题材词**：业绩增长、超跌、ST摘帽、次新股、并购重组词（并购放 `ma_events`）；真实产业逻辑不因几年无新进展而淘汰，除非被官方主动否认或剥离终止。

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
