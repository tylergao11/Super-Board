"""Pure-stdlib run_workflow orchestrator for Super-Board v2 full-dynamic tagging."""
import json
import sys
from pathlib import Path

ROOT = Path(args.get("root", r"c:\Ai\Super-Board")) if "args" in dir() else Path(r"c:\Ai\Super-Board")
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from common import load_taxonomy, validate_record  # noqa: E402
from build_db import upsert_from_tagged  # noqa: E402

TAXONOMY = load_taxonomy(ROOT / "taxonomy.json")
SHARD_DIR = ROOT / "data/shards"
TAGGED_DIR = ROOT / "data/tagged"
TAGGED_DIR.mkdir(parents=True, exist_ok=True)

PREFIX = args.get("prefix", "day_latest") if "args" in dir() else "day_latest"
WAVE_SIZE = int(args.get("wave_size", 40)) if "args" in dir() else 40
MIN_TAG_DATE = str(args.get("min_tag_date", "2025-11-26")) if "args" in dir() else "2025-11-26"
SKIP_COMPILE = bool(args.get("skip_compile", False)) if "args" in dir() else False

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
                    "city": {"type": ["string", "null"]},
                    "controller_type": {"type": "string"},
                    "overseas_pct": {"type": ["number", "null"]},
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
                    "ma_events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "event_type": {"type": "string"},
                                "target_name": {"type": "string"},
                                "target_l1": {"type": ["string", "null"]},
                                "from_date": {"type": "string"},
                                "evidence": {"type": "string"},
                            },
                            "required": ["event_type", "target_name", "from_date", "evidence"],
                        },
                    },
                    "audit_notes": {"type": "string"},
                },
                "required": [
                    "code", "name", "province", "controller_type",
                    "tags", "ma_events",
                ],
            },
        },
    },
    "required": ["shard_id", "stocks"],
}

RULES_PROMPT = f"""你是A股超短线全动态纯净题材库首席研判专家（只读模式，直接通过 finish 返回JSON）。
【绝对指令】本分片全部股票的完整未截断客观证据（含 F10 经营评述、核心题材、公告原文、近年涨停轨迹）已100%附在下方，**严禁调用任何工具（禁止 read_file / run_command 等）**，通读全文后一次性输出结构化 JSON！

【Super-Board 最高定位与打标铁律：A 股游资题材归类视角（跟随盘面，区别于传统申万/东财行业归类）】
- **跟随盘面才是游资产业链行为**：本库按 **A 股游资与超短线资金的炒作视角** 归类题材。**拿不准时先还原盘面**：结合 `limit_up_topic_counts`（历次高频跟随方向）与每次涨停当日的 `day_top_sectors` / `day_leaders`（同期领涨主线与高标），先弄清“每次拉哪个板块它就跟着动”，再用 F10/公告印证联动抓手（而非用传统券商/会计口径的静态分类去否定盘面共识）。
- 第一性原理为**“跨领域想象力（底层能力同源复用 + 新实控人/产业战投背景映射）”**：资金炒哪条线、认哪块增量想象力、谁与谁在盘面互相联动或压制，就按游资共识归口。
1. `tags`（全动态纯净题材唯一列表，按独立实锤逻辑如实收录，按当下市场核心度与近期催化强度从高到低排序）：
   - **唯一标准词表（33 个标准词）**：
     - 23 个一级赛道：{json.dumps(TAXONOMY["l1_list"], ensure_ascii=False)}
     - 10 个跨界分组：{json.dumps(TAXONOMY["dynamic_groups"], ensure_ascii=False)}
   - **关键归口（统一收口标准词）**：
     - 洁净室、光刻胶/光刻机、先进封装/玻璃基板、存储/HBM、培育钻石/金刚石散热（MPCVD/热沉）、半导体设备材料，以及 OLED/LCD 显示面板、Mini/Micro-LED、硅基 OLED、偏光片/光学膜/滤光片/导光板等光电显示器件 → **`芯片`**；
     - 液冷、AIDC、算力租赁、算力电源、服务器/算力基础设施 → **`算力`**；
     - 光模块/CPO、PCB、覆铜板(CCL)、电子铜箔、光纤光缆、高速连接器，以及 MLCC/电阻电容/电感/晶振/电极箔/离型膜等被动元器件 → **`通信`**（IC 封装载板归 `芯片`）；
     - 智能电网/特高压/输变电、核电与可控核聚变、发电运营及电网侧独立储能电站 → **`电力`**；
     - 锂电（固态电池/钠电/锂矿/电池材料）、光伏制造（硅料/组件/玻璃/边框/设备/太空光伏）与储能系统/充电桩 → **`锂电光伏`**（纯发电厂光伏电站/独立储能电站并网卖电归 **`电力`**，不重挂 `锂电光伏`；制氢/储运/燃料电池归 **`氢能源`**）；石油开采/油服/炼化及天然气/LNG/城燃 → **`油气`**（严禁使用旧词“石油”）；
     - 冰雪场馆制冷/造雪制冰装备、滑雪景区文旅及核心冰雪保畅载体 → **`冰雪经济`**；
     - 煤机归 **`煤炭`**，工程机械归 **`基建`**，电梯归 **`地产链`**，环保设备归 **`环保`**，油服设备归 **`油气`**，光伏/锂电设备归 **`锂电光伏`**，半导体设备归 **`芯片`**，切勿重复挂 **`机械设备`**；
     - 经官方公告或互动易确认通过直投或创投基金**间接参股**硬科技独角兽/拟上市核心标的（如宇树/摩尔线程/长鑫等），属于真实股权持有映射，正常保留对应赛道；
     - `kpl_concepts_hint` 仅作防漏线索、绝非标准答案：严禁因开盘啦乱挂假蹭词（如通用材料泛提及下游、口头“积极布局/探索/可适配”、自用 AI 提效/自用机器人、纯分销代理）而盲目打标！
     - 港口与海运/油运/集运/干散货远洋运输，以及纯血快递、跨境与多式联运货运、大宗供应链物流与外贸货代 → **`航运物流`**（港机/叉车/分拣设备厂归 `基建`/`机械设备`/`机器人`，百货地产水泥附带物流园不入；跨境电商与消费商社归 `消费`）；轨交与公路铁路设施归 `基建`，民航出行归 `消费`；
     - 房地产开发、物业服务、地产经纪，以及家居家具、地板、卫浴、门窗、幕墙、瓷砖、吊顶、定制家居、家装建材、装饰原纸、电梯、房屋检测、住宅精装修装饰与浮法平板玻璃等地产后周期链 → **`地产链`**（`消费` 专注食品饮料/百货零售/跨境电商/免税旅游/纺织服装/品牌家电日化/文创潮玩/造纸包装；`基建` 专注大型建筑工程施工/路桥轨交高速/水泥管材/水利工程/建筑节能/工程机械；钢铁/黑色金属归 `有色`）；
     - 无人驾驶/Robotaxi、车路云、L2+/L3/L4 自动驾驶、激光雷达/毫米波雷达、线控底盘/转向制动、智驾域控/智能座舱域控 → **`智能驾驶`**；汽车整车、汽配（内饰/压铸/热管理/底盘/线束/车灯）及车载显示 → **`汽车链`**；
     - 减速器/伺服/丝杠/微型传动/传感视觉、物理AI视觉终端、工业/人形/扫地清洁机器人、工业母机/数控机床、工业自动化产线 → **`机器人`**；通用与专用工业装备（工业制冷/纺机/包机/压机/绕线机/泵阀/轴承基础件/工业照明/金属容器）→ **`机械设备`**（橡胶轮胎/胶管归 `化工`）；
     - 纯软件/大模型/AI智能体/SaaS/信创、对外商业化 AI 产品内容服务、AI 眼镜/智能音箱等端侧 AI 交互终端，以及影视/游戏/出版/广电/广告营销/在线教育等文化传媒主业标的 → 统一归 **`AI应用`**（非文化传媒主业仅按其自身真实对外 AI 业务判断）；强垂直行业专用软件归对应行业（金融IT→`金融`、电网自动化→`电力`、军工信息化→`军工`、医疗IT→`医药`）。
   - **第一性原理（跨领域想象力 · 双通道并列）**：
     - **通道① 底层能力同源复用**：只要公司产品、工艺、产线、资质或实体可向目标赛道输出（含外围配套、材料、结构件、洁净室及专用/后道组装测试设备），且 F10/公告/投关/互动易或近 1 年盘面有实质动作（涵盖研发项目、样机试制、提供样品/送样、开发验证、产线适配、子公司/参股实体、产业合作、量产供货或盘面催化）→ **从研发、试制、送样、验证到量产全周期一律判作【有】**。
     - **通道② 新实控人 / 新控股股东 / 知名产业战投背景映射**：上市公司已完成控股权变更或引入知名产业实体/独角兽成为新控股股东/实控人/重要战投，且盘面围绕其产业背景映射炒作 → **直接按入主方或产业战投核心赛道打标**（筹划未过户阶段记入 `ma_events` 并写清 `target_l1`，交割完成后直接并入 `tags`）。
   - **活跃主业与旧壳分层**：
     - 市场仍在炒作的主业正常保留进 `tags`；
     - 已转型且近 1 年无盘面炒作的旧壳主业（如顺灏的烟标、哈森的女鞋、大胜达的纸箱、全筑的传统家装），沉淀在 `audit_notes` 备查，让 `tags` 聚焦活跃主线。
   - **`from_date` 与长期保留**：
     - 必填 `YYYY-MM-DD`，取最近一次确认/公告/涨停催化/定期报告日；**已核实的真实产业逻辑与新实控人背景映射长期保留，不设 12 个月/24 个月过期限制**，有新进展即刷新 `from_date`，仅在官方主动否认/终止/剥离时剔除。

2. `ma_events`（**专存当前筹划中/进行中**的并购重组与控股权拟变更，与 `tags` 独立分表）：
   - event_type：{json.dumps(TAXONOMY["ma_event_types"], ensure_ascii=False)}
   - 已完成并入 `tags`，已终止移出；必写 `target_name`、`target_l1`（未定标的填 `null`）、`from_date`、`evidence`。

3. 【4 类噪音剔除标准】
   - **官方公告明确否认**：仅当官方公告/澄清/问询函/互动易明确否认“未开展、无相关业务、无技术储备、无布局打算、无任何合作”时予以剔除。**推进表述与合规免责套话一律保留对应赛道**：公告写到“尚处于提供样品/送样验证/研发试制/开发验证/前期投入阶段、尚未批量生产、尚未形成收入、营收占比极低、对业绩无重大影响、不直接从事整机本体”证实公司正在推进该赛道；控股权变更公告中的“未来 12/36 个月内无借壳上市、重大资产重组或资产注入计划”属于交易所常规合规提示，不影响新实控人/产业战投背景映射标签收录。
   - **非传媒主业的纯买家内部赋能**：企业仅在内部采购或接入外部工具降本增效（如非传媒企业内部接 DeepSeek 写文案/客服/画图/辅助研发，或买机器人放自家仓库自用），未形成对外输出能力。
   - **纯行政/生活泛服务**：给发射场/机房盖办公楼食堂公寓、物业、办展、常规绿电直供、纯品牌经销代理。
   - **行情软件非题材词**：业绩增长、超跌、ST摘帽、次新股（已核实逻辑不因几年无新进展而淘汰，除非被官方主动否认或剥离终止）。

4. 基础档案：{json.dumps(TAXONOMY["provinces"], ensure_ascii=False)}；controller_type：{json.dumps(TAXONOMY["controller_types"], ensure_ascii=False)}。
"""


def _is_valid(shard_id: str) -> bool:
    ev_p = SHARD_DIR / f"{shard_id}.json"
    out_p = TAGGED_DIR / f"{shard_id}.json"
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
            if validate_record(rec, ev_map.get(c), TAXONOMY, min_tag_date=MIN_TAG_DATE):
                return False
        return got == set(ev_map.keys())
    except Exception:
        return False


async def tag_shard(shard_id: str) -> dict:
    try:
        ev_doc = json.loads((SHARD_DIR / f"{shard_id}.json").read_text(encoding="utf-8"))
        stocks = ev_doc["stocks"]
        ev_by_code = {s["code"]: s for s in stocks}
        prompt = (
            RULES_PROMPT
            + f"\n现在请对分片 {shard_id} 的全部 {len(stocks)} 只股票逐一深审打标，严禁遗漏：\n"
            + json.dumps(stocks, ensure_ascii=False, separators=(",", ":"))
        )
        a = agent(role=f"Tag {shard_id}", type_name="research")
        res = await a(prompt, OUTPUT_SCHEMA)
        for _ in range(2):
            errs = []
            got = set()
            for rec in res.get("stocks", []):
                c = str(rec.get("code") or "")
                got.add(c)
                errs.extend(validate_record(rec, ev_by_code.get(c), TAXONOMY, min_tag_date=MIN_TAG_DATE))
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
            final_errs.extend(validate_record(rec, ev_by_code.get(str(rec.get("code") or "")), TAXONOMY, min_tag_date=MIN_TAG_DATE))
        if final_errs:
            return {"shard_id": shard_id, "ok": False, "error": str(final_errs[:8])}

        res["shard_id"] = shard_id
        (TAGGED_DIR / f"{shard_id}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"shard_id": shard_id, "ok": True, "count": len(res["stocks"])}
    except Exception as exc:
        return {"shard_id": shard_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}


phase(f"Super-Board v2 Full-Dynamic Tagging ({PREFIX})")
manifest = json.loads((SHARD_DIR / f"{PREFIX}_manifest.json").read_text(encoding="utf-8"))
all_shards = [s["shard_id"] for s in manifest["shards"]]
pending = [sid for sid in all_shards if not _is_valid(sid)]
log(f"Prefix={PREFIX}, total={len(all_shards)}, valid={len(all_shards)-len(pending)}, pending={len(pending)}")

failed = []
for i in range(0, len(pending), WAVE_SIZE):
    wave = pending[i : i + WAVE_SIZE]
    res_list = await parallel(wave, tag_shard)
    bad = [r for r in res_list if not r["ok"]]
    failed.extend(r["shard_id"] for r in bad)
    log(f"Wave {i//WAVE_SIZE+1}: ok={len(wave)-len(bad)}/{len(wave)}, failed={bad}")

if failed:
    log(f"Retrying {len(failed)} failed shards...")
    r_list = await parallel(failed, tag_shard)
    still_bad = [r for r in r_list if not r["ok"]]
    if still_bad:
        raise RuntimeError(f"Shards still failed after retry: {still_bad}")

if SKIP_COMPILE:
    log(f"Skipping DB compile for {PREFIX} (skip_compile=True); tagged shards ready.")
else:
    phase(f"Compile Super-Board v2 DB ({PREFIX})")
    summary = upsert_from_tagged(PREFIX)
    log("Compile done:", json.dumps(summary, ensure_ascii=False))
