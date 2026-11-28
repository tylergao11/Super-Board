/* ==========================================================================
   SUPER-BOARD · Editorial Paper UI · Full-Height Ladder · Hub & Search Sheets
   ========================================================================== */

(() => {
  const STOCK_SHARD_COUNT = 16;
  const RECENT_SEARCH_KEY = "sb_recent_searches_v1";
  const DAY_CACHE_MAX = 60;
  const SPLASH_START_TS = performance.now();

  const SECTOR_ALIASES = {
    芯片: ["半导体", "光刻机", "光刻胶", "存储", "封测", "hbm", "面板", "oled", "晶圆", "靶材", "洁净室", "led"],
    算力: ["aidc", "液冷", "数据中心", "服务器", "智算", "算力租赁", "柴发", "bbu", "云存储"],
    通信: ["光模块", "cpo", "pcb", "覆铜板", "电子布", "光纤", "光缆", "连接器", "晶振", "mlcc", "6g", "5g"],
    AI应用: ["ai", "人工智能", "大模型", "智能体", "saas", "软件", "信创", "传媒", "影视", "游戏", "出版", "教育", "广告"],
    机器人: ["人形", "具身", "减速器", "伺服", "丝杠", "机器视觉", "物理ai", "工业母机", "机床", "电子皮肤"],
    智能驾驶: ["无人驾驶", "自动驾驶", "智驾", "robotaxi", "激光雷达", "毫米波", "车路云", "线控底盘", "v2x"],
    汽车链: ["汽车", "汽配", "整车", "新能源车", "压铸", "车灯", "重卡", "客车", "摩托车"],
    机械设备: ["机械", "压缩机", "泵阀", "液压", "轴承", "纺机", "容器", "通用设备"],
    军工: ["国防", "军用", "船舶", "战机", "导弹", "航发", "海工"],
    航运物流: ["港口", "航运", "海运", "油运", "集运", "快递", "物流", "货代", "外贸"],
    电力: ["电网", "特高压", "核电", "核聚变", "变压器", "风电", "水电", "火电", "绿电", "虚拟电厂"],
    锂电光伏: ["锂电", "光伏", "储能", "固态电池", "钠电", "电池", "硅料", "逆变器", "充电桩", "碳酸锂", "太空光伏"],
    油气: ["石油", "天然气", "燃气", "lng", "油服", "炼化", "城燃"],
    煤炭: ["焦炭", "焦煤", "煤机", "煤炭"],
    化工: ["化纤", "轮胎", "农药", "化肥", "氟化工", "磷化工", "聚氨酯", "民爆", "染料"],
    有色: ["黄金", "白银", "铜", "铝", "稀土", "钨", "钼", "锡", "锌", "铅", "钢铁", "铁矿", "小金属", "贵金属"],
    医药: ["医疗", "创新药", "中药", "制药", "器械", "疫苗", "血制品", "cxo", "生物医药"],
    消费: ["零售", "百货", "食品", "饮料", "白酒", "家电", "纺织", "服装", "免税", "旅游", "造纸", "包装", "宠物", "跨境电商"],
    农业: ["猪肉", "养猪", "种业", "养殖", "渔业", "畜牧", "饲料", "水产"],
    环保: ["水务", "固废", "污水", "环卫", "垃圾发电", "再生资源"],
    金融: ["证券", "券商", "银行", "保险", "数字货币", "跨境支付", "多元金融", "金融科技", "互金"],
    地产链: ["房地产", "地产", "物业", "装修", "家居", "家具", "电梯", "瓷砖", "卫浴", "玻璃", "防水"],
    基建: ["水泥", "水利", "路桥", "轨交", "高速", "工程机械", "管材", "建筑"],
    商业航天: ["航天", "卫星", "火箭", "星链", "太空算力", "spacex", "商业卫星"],
    低空经济: ["低空", "无人机", "evtol", "飞行汽车", "通航"],
    华为链: ["华为", "鸿蒙", "昇腾", "鲲鹏", "海思", "欧拉"],
    端侧AI: ["端侧", "ai眼镜", "ai手机", "aipc", "ai玩具", "智能眼镜", "豆包", "穿戴", "光波导", "端侧芯片", "ai终端", "rokid", "雷鸟", "ai耳机", "ai音箱"],
    海洋经济: ["海洋", "深海", "海水淡化", "海洋牧场"],
    氢能源: ["氢能", "制氢", "燃料电池", "sofc", "加氢"],
    量子科技: ["量子", "量子计算", "量子通信"],
    脑机接口: ["脑机", "脑电", "神经接口"],
    海峡两岸: ["两岸", "福建", "台湾", "平潭", "厦门"],
    冰雪经济: ["冰雪", "滑雪", "制雪", "造雪", "冰场"],
    国企改革: ["国改", "央企", "地方国企", "国资", "市值管理"],
    中字头: ["中字头", "中国字头", "央企中字头"],
    数字辈: ["数字", "数字玄学", "一二三", "百千万"],
    动物: ["动物园", "生肖", "动物玄学", "马字辈", "牛字辈", "蛇字辈"],
    海南: ["自贸港", "海南封关", "海口", "三亚"],
    东北: ["东北振兴", "东三省", "辽宁", "吉林", "黑龙江"],
    西部大开发: ["西部", "大西部", "成渝", "西北", "西南"],
    雄安: ["雄安新区", "河北", "保定", "京津冀"],
  };

  const state = {
    dates: [], // descending: index 0 = newest trading day
    dateSet: new Set(),
    day: null,
    targetDate: "",
    focusTheme: "",
    ladderMetrics: false,
    recentBrokenOpen: false,
    dayCache: new Map(), // date -> day payload (LRU)
    dayInFlight: new Map(), // date -> Promise<day>
    modalStack: [], // { type: 'hub'|'search'|'ma-list'|'catalyst'|'theme'|'stock', ... }
    searchIndex: null,
    searchIndexPromise: null,
    stockProfileCache: new Map(), // code -> profile
    stockShardCache: new Map(), // '00'..'15' -> dict
    stockShardPromises: new Map(),
    intradayCache: new Map(), // `${date}:${code}` -> payload
    intradayInFlight: new Map(), // `${date}:${code}` -> Promise
    intradayDayLoaded: new Set(), // date -> day bundle fetched
    intradayDayInFlight: new Map(), // date -> Promise
  };

  const $ = (id) => document.getElementById(id);
  const elSplash = $("splash-screen");
  const elSplashAvatar = $("splash-avatar");
  const elSplashProgress = $("splash-progress");
  const elBrandAvatar = $("brand-avatar");
  const elDayLoadingBar = $("day-loading-bar");
  const elShell = $("app-shell");
  const elSearchBtn = $("search-btn");
  const elDateLatest = $("date-latest");
  const elDatePrev = $("date-prev");
  const elDateNext = $("date-next");
  const elDateBtn = $("date-btn");
  const elDateLabel = $("date-label");
  const elHubBar = $("hub-bar");
  const elHomeTools = $("home-tools");
  const elLadderModeBtn = $("ladder-mode-btn");
  const elLadderFocusBar = $("ladder-focus-bar");
  const elLadderScroll = $("ladder-scroll");
  const elLadderList = $("ladder-list");

  const elBackdrop = $("sheet-backdrop");
  const elSheet = $("sheet-container");
  const elSheetDrag = $("sheet-drag-zone");
  const elSheetHeader = $("sheet-header");
  const elSheetBody = $("sheet-body");

  const elDateBackdrop = $("date-backdrop");
  const elDateSheet = $("date-sheet");
  const elDateClose = $("date-close");
  const elDateYearTabs = $("date-year-tabs");
  const elDateCycleWrap = $("date-cycle-wrap");
  const elDateMonthGrid = $("date-month-grid");
  const elDateList = $("date-list");

  const esc = (s) =>
    String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const shortDate = (iso) => (iso && iso.length >= 10 ? iso.slice(5).replace("-", ".") : iso || "--.--");

  function topbarDateLabel(iso) {
    if (!iso || iso.length < 10) return iso || "--.--";
    const latestYear = state.dates[0]?.date?.slice(0, 4);
    if (latestYear && iso.slice(0, 4) !== latestYear) {
      return `${iso.slice(2, 4)}.${iso.slice(5, 7)}.${iso.slice(8, 10)}`;
    }
    return iso.slice(5).replace("-", ".");
  }

  const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  function weekdayLabel(iso) {
    if (!iso || iso.length < 10) return "";
    const parts = iso.split("-").map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) return "";
    const dt = new Date(parts[0], parts[1] - 1, parts[2]);
    return WEEKDAYS[dt.getDay()] || "";
  }

  function formatThemeLabel(t) {
    const s = String(t || "");
    return s.endsWith("本地") && s.length >= 4 ? s.slice(0, -2) : s;
  }

  function isBoilerplateEvidence(ev) {
    const txt = String(ev?.text || "").trim();
    return (
      txt.startsWith("常驻地域属性：") ||
      txt.startsWith("常驻经典字辈：") ||
      txt.startsWith("常驻股东属性：") ||
      txt.startsWith("常驻字头属性：") ||
      txt.startsWith("常驻玄学")
    );
  }

  function getMarketBoard(code) {
    const c = String(code || "");
    if (c.startsWith("30")) return { key: "cyb", short: "创", label: "创业板 20cm" };
    if (c.startsWith("68")) return { key: "kcb", short: "科", label: "科创板 20cm" };
    if (c.startsWith("8") || c.startsWith("4") || c.startsWith("92")) {
      return { key: "bj", short: "北", label: "北交所 30cm" };
    }
    return null;
  }

  function isStStock(name) {
    return /^(\*?ST|S\*?ST)/i.test(String(name || "").trim());
  }

  function boardBadgeHtml(code, full = false, name = "") {
    const b = getMarketBoard(code);
    const st = isStStock(name);
    let out = "";
    if (b) {
      out += `<span class="mkt-badge mkt-${b.key}" title="${b.label}">${full ? b.label : b.short}</span>`;
    }
    if (st) {
      const stTitle = b ? `ST (${b.label})` : "ST 风险警示 5%";
      const stText = full ? (b ? "ST" : "ST 5%") : "ST";
      out += `<span class="mkt-badge mkt-st" title="${stTitle}">${stText}</span>`;
    }
    return out;
  }

  // #1 最强发酵 = 朱砂红 (heat-1), #2 第二发酵 = 琥珀橙 (heat-2), 其余常规墨色
  const heatCls = (rank) => (rank === 1 ? "heat-1" : rank === 2 ? "heat-2" : "");
  const themeHeatCls = (themeName) => heatCls(state.day?.themes?.[themeName]?.heat_rank);

  // ========================================================================
  // Motion helpers (View Transitions with graceful fallback)
  // ========================================================================
  const elMainLayout = $("main-layout");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const canVT = typeof document.startViewTransition === "function" && !reduceMotion;
  let vtToken = 0;
  let activeVT = null;

  function withTransition(kind, update) {
    if (!canVT) {
      update();
      return Promise.resolve(false);
    }
    if (activeVT) {
      try {
        activeVT.skipTransition();
      } catch {}
      activeVT = null;
    }
    const root = document.documentElement;
    const token = ++vtToken;
    root.dataset.vt = kind;
    let ran = false;
    const run = () => {
      if (ran) return;
      ran = true;
      update();
    };
    let vt;
    try {
      vt = document.startViewTransition(run);
      activeVT = vt;
    } catch {
      delete root.dataset.vt;
      run();
      return Promise.resolve(false);
    }
    vt.updateCallbackDone.catch(run);
    vt.ready.catch(() => {});
    return vt.finished
      .catch(() => {})
      .then(() => {
        run();
        if (activeVT === vt) activeVT = null;
        if (token === vtToken) delete root.dataset.vt;
        return true;
      });
  }

  function replayClass(el, cls) {
    if (!el) return;
    el.classList.remove("day-in-older", "day-in-newer");
    void el.offsetWidth;
    el.classList.add(cls);
    el.addEventListener("animationend", () => el.classList.remove(cls), { once: true });
  }

  function playEntrance() {
    if (reduceMotion) return;
    const stamp = (el, i) => {
      el.style.setProperty("--i", Math.min(i, 14));
      el.classList.add("enter");
      el.addEventListener(
        "animationend",
        () => {
          el.classList.remove("enter");
          el.style.removeProperty("--i");
        },
        { once: true }
      );
    };
    if (elHubBar) stamp(elHubBar, 0);
    Array.from(elLadderList.children).forEach((el, i) => stamp(el, i + 1));
  }

  // Detect local Python API server vs static GitHub Pages hosting
  const USE_LIVE_API =
    /^(localhost|127\.|192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(window.location.hostname) &&
    window.location.port !== "";

  // ========================================================================
  // Global Search Index & Stock Archive Profile Loaders (Live + Static)
  // ========================================================================

  function stockShardId(code) {
    const digits = String(code || "").replace(/\D/g, "");
    const n = digits ? parseInt(digits, 10) % STOCK_SHARD_COUNT : 0;
    return String(n).padStart(2, "0");
  }

  function loadSearchIndex() {
    if (state.searchIndex) return Promise.resolve(state.searchIndex);
    if (state.searchIndexPromise) return state.searchIndexPromise;
    const url = USE_LIVE_API ? "./api/search-index" : "./data/search_index.json";
    state.searchIndexPromise = fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("search_index_failed");
        return res.json();
      })
      .then((data) => {
        const l1 = data.l1 || [];
        const dynamic = data.dynamic || [];
        const zibei = data.zibei || [];
        const intrinsic = data.intrinsic || [];
        const regions = data.regions || [];
        const allSectors = [...l1, ...dynamic];
        const stocks = (data.stocks || []).map((row) => ({
          code: row[0],
          name: row[1],
          nameLower: String(row[1] || "").toLowerCase(),
          province: row[2] || "",
          tags: row[3] || [],
          maL1: row[4] || [],
          lastDate: row[5] || "",
          maxHeight: row[6] || 0,
          luCount: row[7] || 0,
          py: String(row[8] || "").toLowerCase(),
        }));
        const bySector = new Map();
        for (const s of [...allSectors, ...intrinsic, ...zibei, ...regions]) bySector.set(s, []);
        for (const item of stocks) {
          const seen = new Set();
          for (const t of item.tags) {
            if (!seen.has(t)) {
              seen.add(t);
              if (!bySector.has(t)) bySector.set(t, []);
              bySector.get(t).push({ ...item, isMa: false });
            }
          }
          for (const t of item.maL1) {
            if (!seen.has(t)) {
              seen.add(t);
              if (!bySector.has(t)) bySector.set(t, []);
              bySector.get(t).push({ ...item, isMa: true });
            }
          }
        }
        const maEvents = (data.ma_events || []).map((row) => ({
          code: row[0],
          name: row[1],
          nameLower: String(row[1] || "").toLowerCase(),
          province: row[2] || "",
          type: row[3] || "",
          target: row[4] || "",
          targetLower: String(row[4] || "").toLowerCase(),
          targetL1: row[5] || "",
          fromDate: row[6] || "",
        }));
        state.searchIndex = {
          l1,
          dynamic,
          intrinsic,
          zibei,
          regions,
          allSectors,
          sectorSet: new Set(allSectors),
          sectorCounts: data.sector_counts || {},
          stocks,
          maEvents,
          bySector,
        };
        return state.searchIndex;
      })
      .catch(() => {
        state.searchIndexPromise = null;
        return null;
      });
    return state.searchIndexPromise;
  }

  async function fetchStockProfile(code) {
    if (!code) return null;
    if (state.stockProfileCache.has(code)) return state.stockProfileCache.get(code);

    if (USE_LIVE_API) {
      try {
        const res = await fetch(`./api/stock?code=${encodeURIComponent(code)}`);
        if (!res.ok) return null;
        const prof = await res.json();
        state.stockProfileCache.set(code, prof);
        return prof;
      } catch {
        return null;
      }
    }

    const sid = stockShardId(code);
    let shard = state.stockShardCache.get(sid);
    if (!shard) {
      let prom = state.stockShardPromises.get(sid);
      if (!prom) {
        prom = fetch(`./data/stocks/${sid}.json`)
          .then((r) => (r.ok ? r.json() : {}))
          .catch(() => ({}));
        state.stockShardPromises.set(sid, prom);
      }
      shard = await prom;
      state.stockShardCache.set(sid, shard);
    }
    const prof = shard[code] || null;
    if (prof) state.stockProfileCache.set(code, prof);
    return prof;
  }

  // ========================================================================
  // Intraday Minute Chart Loader & Static SVG Renderer (Intraday-Only!)
  // ========================================================================

  function putIntradayCache(date, code, data) {
    if (!date || !code || !data || !Array.isArray(data.points) || data.points.length < 2) return;
    const key = `${date}:${code}`;
    if (state.intradayCache.has(key)) state.intradayCache.delete(key);
    state.intradayCache.set(key, data);
    while (state.intradayCache.size > 900) {
      state.intradayCache.delete(state.intradayCache.keys().next().value);
    }
  }

  function prefetchIntradayDay(date) {
    if (!date || state.intradayDayLoaded.has(date)) return Promise.resolve();
    if (state.intradayDayInFlight.has(date)) return state.intradayDayInFlight.get(date);
    const url = USE_LIVE_API
      ? `./api/intraday-day?date=${encodeURIComponent(date)}`
      : `./data/intraday/${encodeURIComponent(date)}.json`;
    const prom = fetch(url)
      .then((res) => (res.ok ? res.json() : null))
      .then((bundle) => {
        if (bundle && typeof bundle === "object") {
          let cnt = 0;
          for (const [code, payload] of Object.entries(bundle)) {
            if (payload && Array.isArray(payload.points) && payload.points.length >= 2) {
              putIntradayCache(date, code, payload);
              cnt++;
            }
          }
          if (cnt > 0 || !USE_LIVE_API) {
            state.intradayDayLoaded.add(date);
          }
        }
      })
      .catch(() => {})
      .finally(() => {
        state.intradayDayInFlight.delete(date);
      });
    state.intradayDayInFlight.set(date, prom);
    return prom;
  }

  function fetchIntraday(code, date) {
    if (!code || !date) return Promise.resolve(null);
    const key = `${date}:${code}`;
    if (state.intradayCache.has(key)) {
      const hit = state.intradayCache.get(key);
      state.intradayCache.delete(key);
      state.intradayCache.set(key, hit);
      return Promise.resolve(hit);
    }
    // If this day's bundle is currently in flight, wait briefly for it before firing a single-stock call
    if (state.intradayDayInFlight.has(date)) {
      return state.intradayDayInFlight.get(date).then(() => {
        if (state.intradayCache.has(key)) return state.intradayCache.get(key);
        return USE_LIVE_API ? fetchIntradaySingle(code, date) : null;
      });
    }
    if (!USE_LIVE_API) {
      return prefetchIntradayDay(date).then(() => state.intradayCache.get(key) || null);
    }
    return fetchIntradaySingle(code, date);
  }

  function fetchIntradaySingle(code, date) {
    const key = `${date}:${code}`;
    if (state.intradayCache.has(key)) return Promise.resolve(state.intradayCache.get(key));
    if (state.intradayInFlight.has(key)) {
      return state.intradayInFlight.get(key);
    }
    const url = `./api/intraday?code=${encodeURIComponent(code)}&date=${encodeURIComponent(date)}`;
    const prom = fetch(url)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data && Array.isArray(data.points) && data.points.length >= 2) {
          putIntradayCache(date, code, data);
          return data;
        }
        return null;
      })
      .catch(() => null)
      .finally(() => {
        state.intradayInFlight.delete(key);
      });
    state.intradayInFlight.set(key, prom);
    return prom;
  }

  function prefetchIntraday(code, date) {
    if (!code || !date || !USE_LIVE_API) return;
    const key = `${date}:${code}`;
    if (state.intradayCache.has(key) || state.intradayInFlight.has(key) || state.intradayDayInFlight.has(date)) return;
    fetchIntradaySingle(code, date).catch(() => {});
  }

  function getDayLadderOrder(d) {
    if (!d) return [];
    const seen = new Set();
    const list = [];
    const pushItem = (code, name) => {
      if (!code || seen.has(code)) return;
      seen.add(code);
      list.push({ code, name: name || code });
    };
    for (const tier of d.ladder || []) {
      for (const c of tier.codes || []) {
        pushItem(c, d.stocks?.[c]?.name);
      }
    }
    for (const c of d.fanbao_boards || []) {
      pushItem(c, d.stocks?.[c]?.name);
    }
    for (const b of d.broken_boards || []) {
      pushItem(b.code, b.name);
    }
    return list;
  }

  function fmtYiVal(v) {
    if (v == null || Number.isNaN(Number(v))) return "--";
    const n = Number(v);
    if (n >= 1000) return `${Math.round(n)}亿`;
    if (n >= 100) return `${n.toFixed(1)}亿`;
    return `${n.toFixed(2)}亿`;
  }

  function fmtMvVal(v) {
    if (v == null || Number.isNaN(Number(v))) return "--";
    const n = Number(v);
    if (n >= 1000) return `${Math.round(n)}亿`;
    return `${n.toFixed(1)}亿`;
  }

  function renderIntradayCardHtml(data) {
    const pts = data.points || [];
    const pre = Number(data.preclose || data.price || 1);
    const px = Number(data.price || pre);
    const pct = Number(data.pct ?? 0);
    const hi = Number(data.high ?? px);
    const lo = Number(data.low ?? px);
    const dirCls = pct > 0.005 ? "is-up" : pct < -0.005 ? "is-down" : "is-flat";
    const strokeCol = pct > 0.005 ? "#c8342d" : pct < -0.005 ? "#1f6e43" : "#111111";
    const fillCol = pct > 0.005 ? "#c8342d" : pct < -0.005 ? "#1f6e43" : "#111111";
    const pctText = `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;

    const W = 336;
    const x0 = 2;
    const x1 = 334;
    const plotW = x1 - x0;
    const pyTop = 8;
    const pyBot = 86;
    const pyMid = (pyTop + pyBot) / 2;
    const halfH = (pyBot - pyTop) / 2;
    const vyTop = 94;
    const vyBot = 114;
    const volH = vyBot - vyTop;

    const maxDev = Math.max(Math.abs(hi - pre), Math.abs(lo - pre), pre * 0.015) * 1.06;
    const spanPct = pre > 0 ? (maxDev / pre) * 100 : 10;
    const totalSlots = Math.max(240, pts.length - 1);
    const midX = (x0 + (120 / totalSlots) * plotW).toFixed(1);

    const clampY = (y) => Math.max(pyTop, Math.min(pyBot, y));
    const mapX = (i) => x0 + (i / totalSlots) * plotW;
    const mapY = (val) => clampY(pyMid - ((val - pre) / maxDev) * halfH);

    const priceCoords = [];
    const avgCoords = [];
    let maxVol = 1;
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i];
      const vx = mapX(i).toFixed(1);
      priceCoords.push(`${vx},${mapY(p[0]).toFixed(1)}`);
      avgCoords.push(`${vx},${mapY(p[1]).toFixed(1)}`);
      if (p[2] > maxVol) maxVol = p[2];
    }

    const firstX = mapX(0).toFixed(1);
    const lastX = mapX(pts.length - 1).toFixed(1);
    const areaPath = `M${priceCoords[0]} L${priceCoords.join(" L")} L${lastX},${pyBot} L${firstX},${pyBot} Z`;

    const volLines = [];
    for (let i = 0; i < pts.length; i++) {
      const v = pts[i][2] || 0;
      if (v <= 0) continue;
      const h = Math.max(1.2, (v / maxVol) * volH);
      const vx = mapX(i).toFixed(1);
      const yTop = (vyBot - h).toFixed(1);
      const dFlag = pts[i][3];
      const col = dFlag === 1 ? "rgba(217,45,32,0.52)" : dFlag === 2 ? "rgba(15,118,110,0.5)" : "rgba(17,17,17,0.22)";
      volLines.push(`<line x1="${vx}" y1="${vyBot}" x2="${vx}" y2="${yTop}" stroke="${col}" stroke-width="1"/>`);
    }

    const gradId = `idg-${esc(data.code)}-${esc(data.date)}`;
    const trText = data.turnover != null ? `${Number(data.turnover).toFixed(1)}%` : "--";

    return `
      <div class="intraday-card">
        <div class="intraday-head">
          <div class="intraday-quote ${dirCls}">
            <span class="intraday-px">${px.toFixed(2)}</span>
            <span class="intraday-pct">${pctText}</span>
          </div>
          <div class="intraday-quick">
            <span><em>额</em>${esc(fmtYiVal(data.amount_yi))}</span>
            <span class="id-sep">·</span>
            <span><em>换</em>${esc(trText)}</span>
          </div>
        </div>
        <div class="intraday-mv-row">
          <div class="intraday-mv-group">
            <span><em>总值</em>${esc(fmtMvVal(data.total_mv))}</span>
            <span class="id-sep">·</span>
            <span><em>流通</em>${esc(fmtMvVal(data.float_mv))}</span>
          </div>
          <div class="intraday-hl">
            <span>高 ${hi.toFixed(2)}</span>
            <span>低 ${lo.toFixed(2)}</span>
          </div>
        </div>
        <svg class="intraday-svg" viewBox="0 0 ${W} 126" preserveAspectRatio="none" aria-label="日内分时图">
          <defs>
            <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="${fillCol}" stop-opacity="0.11"/>
              <stop offset="100%" stop-color="${fillCol}" stop-opacity="0.0"/>
            </linearGradient>
          </defs>
          <rect x="0.5" y="1" width="${W - 1}" height="89" rx="4" fill="#fafaf7" stroke="rgba(17,17,17,0.08)" stroke-width="0.8"/>
          <line x1="${x0}" y1="${pyTop}" x2="${x1}" y2="${pyTop}" stroke="rgba(17,17,17,0.06)" stroke-width="0.7" stroke-dasharray="2,2"/>
          <line x1="${x0}" y1="${pyMid}" x2="${x1}" y2="${pyMid}" stroke="rgba(17,17,17,0.22)" stroke-width="0.8" stroke-dasharray="2.5,2.5"/>
          <line x1="${x0}" y1="${pyBot}" x2="${x1}" y2="${pyBot}" stroke="rgba(17,17,17,0.06)" stroke-width="0.7" stroke-dasharray="2,2"/>
          <line x1="${midX}" y1="2" x2="${midX}" y2="89" stroke="rgba(17,17,17,0.07)" stroke-width="0.7" stroke-dasharray="2,2"/>
          <path d="${areaPath}" fill="url(#${gradId})"/>
          <polyline points="${avgCoords.join(" ")}" fill="none" stroke="#d97706" stroke-width="1" stroke-opacity="0.72" stroke-linejoin="round"/>
          <polyline points="${priceCoords.join(" ")}" fill="none" stroke="${strokeCol}" stroke-width="1.45" stroke-linejoin="round" stroke-linecap="round"/>
          <text x="5" y="${pyTop + 7}" class="id-axis-lbl is-up">+${spanPct.toFixed(1)}%</text>
          <text x="5" y="${pyMid - 2.5}" class="id-axis-lbl">0.0%</text>
          <text x="5" y="${pyBot - 1.5}" class="id-axis-lbl is-down">-${spanPct.toFixed(1)}%</text>
          <line x1="0.5" y1="${vyBot + 0.5}" x2="${W - 0.5}" y2="${vyBot + 0.5}" stroke="rgba(17,17,17,0.09)" stroke-width="0.7"/>
          ${volLines.join("")}
          <text x="2" y="124" class="id-time-lbl" text-anchor="start">09:30</text>
          <text x="${midX}" y="124" class="id-time-lbl" text-anchor="middle">11:30</text>
          <text x="${W - 2}" y="124" class="id-time-lbl" text-anchor="end">15:00</text>
        </svg>
      </div>
    `;
  }

  function mountIntradayChart(slotId, code, date, entry) {
    const slot = $(slotId);
    if (!slot || !code || !date) return;
    const key = `${date}:${code}`;
    if (state.intradayCache.has(key)) {
      const hit = state.intradayCache.get(key);
      if (hit) slot.innerHTML = renderIntradayCardHtml(hit);
      return;
    }
    slot.innerHTML = `
      <div class="intraday-card is-loading">
        <div class="intraday-skel-top"></div>
        <div class="intraday-skel-box"></div>
      </div>
    `;
    fetchIntraday(code, date).then((data) => {
      if (currentModalEntry() !== entry || entry.id !== code) return;
      const curSlot = $(slotId);
      if (!curSlot) return;
      if (data) {
        curSlot.innerHTML = renderIntradayCardHtml(data);
      } else {
        curSlot.innerHTML = "";
      }
    });
  }

  function loadRecentSearches() {
    try {
      const raw = localStorage.getItem(RECENT_SEARCH_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr.slice(0, 8) : [];
    } catch {
      return [];
    }
  }

  function saveRecentSearch(item) {
    try {
      const prev = loadRecentSearches().filter((x) => !(x.kind === item.kind && x.id === item.id));
      prev.unshift(item);
      localStorage.setItem(RECENT_SEARCH_KEY, JSON.stringify(prev.slice(0, 8)));
    } catch {
      // ignore storage quota errors
    }
  }

  function clearRecentSearches() {
    try {
      localStorage.removeItem(RECENT_SEARCH_KEY);
    } catch {
      // ignore
    }
  }

  // ========================================================================
  // Splash Screen Silky FLIP Hand-off & Idle Background Prefetching
  // ========================================================================

  const runIdle =
    typeof window.requestIdleCallback === "function"
      ? (fn) => window.requestIdleCallback(fn, { timeout: 900 })
      : (fn) => setTimeout(fn, 120);

  let splashDismissed = false;

  function dismissSplash() {
    if (splashDismissed) return;
    splashDismissed = true;
    if (!elSplash) {
      elShell.classList.remove("splash-pending");
      return;
    }

    const finalize = () => {
      elShell.classList.remove("splash-pending", "splash-revealing");
      elSplash.remove();
    };

    if (reduceMotion || !elSplashAvatar || !elBrandAvatar) {
      elShell.classList.remove("splash-pending");
      elSplash.classList.add("is-fading");
      setTimeout(finalize, 260);
      return;
    }

    const elapsed = performance.now() - SPLASH_START_TS;
    // Wait long enough (~0.76s) for the framed fresco bloom & wordmark to settle crisply
    const minWait = Math.max(0, 760 - elapsed);

    setTimeout(() => {
      // Ensure layout is up-to-date before computing exact FLIP target coordinates
      const from = elSplashAvatar.getBoundingClientRect();
      const to = elBrandAvatar.getBoundingClientRect();

      if (!from.width || !to.width) {
        finalize();
        return;
      }

      const dx = to.left + to.width / 2 - (from.left + from.width / 2);
      const dy = to.top + to.height / 2 - (from.top + from.height / 2);
      const scale = to.width / from.width;

      // Freeze framed fresco at settled 1.0 state before morphing smoothly into top-left medallion
      elSplashAvatar.style.animation = "none";
      elSplashAvatar.style.opacity = "1";
      elSplashAvatar.style.filter = "none";
      elSplashAvatar.style.borderRadius = "2px";
      elSplashAvatar.style.transform = "translate3d(0, 0, 0) scale(1)";
      void elSplashAvatar.offsetWidth;

      elSplash.classList.add("is-gliding");
      elShell.classList.add("splash-revealing");

      requestAnimationFrame(() => {
        elSplashAvatar.style.transform = `translate3d(${dx.toFixed(2)}px, ${dy.toFixed(2)}px, 0) scale(${scale.toFixed(4)})`;
        elSplashAvatar.style.borderRadius = "50%";
      });

      let done = false;
      const onDone = () => {
        if (done) return;
        done = true;
        finalize();
      };
      elSplashAvatar.addEventListener(
        "transitionend",
        (ev) => {
          if (ev.propertyName === "transform") onDone();
        },
        { passive: true }
      );
      setTimeout(onDone, 760);
    }, minWait);
  }

  function dayUrlFor(date) {
    return USE_LIVE_API
      ? date
        ? `./api/day?date=${encodeURIComponent(date)}`
        : "./api/day"
      : `./data/days/${encodeURIComponent(date || state.dates[0]?.date || "")}.json`;
  }

  function putDayCache(dt, day) {
    if (!dt || !day) return;
    if (state.dayCache.has(dt)) state.dayCache.delete(dt);
    state.dayCache.set(dt, day);
    while (state.dayCache.size > DAY_CACHE_MAX) {
      const oldestKey = state.dayCache.keys().next().value;
      state.dayCache.delete(oldestKey);
    }
  }

  function fetchDayData(date) {
    const key = date || state.dates[0]?.date || "";
    if (key && state.dayCache.has(key)) {
      const cached = state.dayCache.get(key);
      // Touch LRU
      state.dayCache.delete(key);
      state.dayCache.set(key, cached);
      return Promise.resolve(cached);
    }
    if (key && state.dayInFlight.has(key)) {
      return state.dayInFlight.get(key);
    }
    const prom = fetch(dayUrlFor(key))
      .then((res) => {
        if (!res.ok) throw new Error("day_fetch_failed");
        return res.json();
      })
      .then((day) => {
        const realKey = day?.date || key;
        if (realKey) putDayCache(realKey, day);
        if (key && key !== realKey) putDayCache(key, day);
        return day;
      })
      .finally(() => {
        if (key) state.dayInFlight.delete(key);
      });
    if (key) state.dayInFlight.set(key, prom);
    return prom;
  }

  function prefetchDay(date) {
    if (!date || !state.dateSet.has(date)) return;
    if (state.dayCache.has(date) || state.dayInFlight.has(date)) return;
    fetchDayData(date).catch(() => {});
  }

  let prefetchToken = 0;
  function prefetchNeighbors(date) {
    const idx = state.dates.findIndex((d) => d.date === date);
    if (idx < 0) return;
    const token = ++prefetchToken;
    // Prioritize immediate prev/next, then 2-3 steps out
    const offsets = [1, -1, 2, -2, 3];
    const queue = offsets
      .map((off) => state.dates[idx + off]?.date)
      .filter((dt) => dt && !state.dayCache.has(dt) && !state.dayInFlight.has(dt));

    let i = 0;
    const step = () => {
      if (token !== prefetchToken || i >= queue.length) return;
      prefetchDay(queue[i++]);
      if (i < queue.length) {
        setTimeout(() => runIdle(step), 55);
      }
    };
    if (queue.length) runIdle(step);
  }

  // ========================================================================
  // Data Fetching & Trading-Day Stepping (0ms Cached + Instant Prefetch)
  // ========================================================================

  let splashPct = 0.08;
  let splashCap = 0.46;
  let splashTickTimer = null;

  function applySplashProgress(p) {
    splashPct = Math.min(1, Math.max(splashPct, p));
    if (elSplashProgress) {
      elSplashProgress.style.transform = `scaleX(${splashPct.toFixed(4)})`;
    }
  }

  function setSplashStage(floor, cap) {
    splashCap = Math.max(splashCap, cap);
    applySplashProgress(floor);
    if (!splashTickTimer) {
      splashTickTimer = setInterval(() => {
        if (splashDismissed || !elSplashProgress) {
          clearInterval(splashTickTimer);
          splashTickTimer = null;
          return;
        }
        const rem = splashCap - splashPct;
        if (rem > 0.008) {
          applySplashProgress(splashPct + rem * 0.16);
        }
      }, 160);
    }
  }

  function completeSplashProgress() {
    if (splashTickTimer) {
      clearInterval(splashTickTimer);
      splashTickTimer = null;
    }
    applySplashProgress(1);
  }

  async function init() {
    bindEvents();
    setSplashStage(0.18, 0.48);
    try {
      const datesUrl = USE_LIVE_API ? "./api/dates" : "./data/dates.json";
      const res = await fetch(datesUrl);
      setSplashStage(0.46, 0.62);
      const json = await res.json();
      state.dates = json.dates || [];
      state.dateSet = new Set(state.dates.map((d) => d.date));
      const preferred =
        state.dates.find((d) => d.news_count > 0 && d.tagged > 0) ||
        state.dates[0];
      setSplashStage(0.62, 0.9);
      await loadDay(preferred ? preferred.date : "");
      completeSplashProgress();
      dismissSplash();
      // Quietly preload global search index after initial launch glide settles
      setTimeout(() => runIdle(() => loadSearchIndex()), 1450);
    } catch {
      completeSplashProgress();
      elLadderList.innerHTML = `<div class="empty-state">数据加载失败</div>`;
      dismissSplash();
    }
  }

  function currentDateIndex() {
    const cur = state.targetDate || state.day?.date;
    if (!cur) return -1;
    return state.dates.findIndex((d) => d.date === cur);
  }

  function updateStepperButtons() {
    const idx = currentDateIndex();
    elDateNext.disabled = idx <= 0;
    elDatePrev.disabled = idx < 0 || idx >= state.dates.length - 1;
    if (elDateLatest) elDateLatest.classList.toggle("hidden", idx <= 0);
  }

  let dayReqSeq = 0;
  let loadBarTimer = null;

  function showLoadBarDelayed() {
    clearTimeout(loadBarTimer);
    loadBarTimer = setTimeout(() => {
      if (elDayLoadingBar) elDayLoadingBar.classList.add("is-active");
      elDateBtn.classList.add("is-loading");
    }, 90);
  }

  function hideLoadBar() {
    clearTimeout(loadBarTimer);
    if (elDayLoadingBar) elDayLoadingBar.classList.remove("is-active");
    elDateBtn.classList.remove("is-loading");
  }

  function applyDayView(day, dir, keepModal = false) {
    state.day = day;
    state.targetDate = day.date || state.targetDate;
    state.focusTheme = "";
    elLadderScroll.scrollTop = 0;
    if (!keepModal) {
      closeAllSheets(true);
    }
    renderTier1();
    if (keepModal && state.modalStack.length) {
      renderCurrentModal();
    } else if (dir && !reduceMotion) {
      replayClass(elMainLayout, `day-in-${dir}`);
    }
    prefetchNeighbors(day.date);
    // Load the entire day's bundled core intraday charts in 1 tiny (~22KB) request -> 0ms instant tap!
    if (day?.date) {
      const warmDate = day.date;
      prefetchIntradayDay(warmDate).then(() => {
        if (!USE_LIVE_API || state.day?.date !== warmDate) return;
        // Fallback prefetch only for any top stocks not yet in the day bundle
        getDayLadderOrder(day)
          .slice(0, 6)
          .forEach((x) => {
            if (!state.intradayCache.has(`${warmDate}:${x.code}`)) {
              prefetchIntraday(x.code, warmDate);
            }
          });
      });
      // Also silently pre-warm adjacent ±1 trading days' bundles when idle
      const idx = state.dates.findIndex((d) => d.date === warmDate);
      if (idx >= 0) {
        const adj = [state.dates[idx + 1]?.date, state.dates[idx - 1]?.date].filter(Boolean);
        setTimeout(() => runIdle(() => adj.forEach((dt) => prefetchIntradayDay(dt))), 400);
      }
    }
  }

  async function loadDay(date, dir = null, opts = {}) {
    const keepModal = Boolean(opts && opts.keepModal);
    const reqDate = date || state.dates[0]?.date || "";
    const seq = ++dayReqSeq;
    state.targetDate = reqDate;

    // Instant topbar feedback even during rapid tapping
    if (reqDate) {
      elDateLabel.textContent = topbarDateLabel(reqDate);
      updateStepperButtons();
    }

    // Hot path: synchronous 0ms render from memory LRU cache!
    if (reqDate && state.dayCache.has(reqDate)) {
      hideLoadBar();
      const cached = state.dayCache.get(reqDate);
      state.dayCache.delete(reqDate);
      state.dayCache.set(reqDate, cached);
      applyDayView(cached, dir, keepModal);
      return;
    }

    showLoadBarDelayed();
    try {
      const day = await fetchDayData(reqDate);
      if (seq !== dayReqSeq) return; // superseded by newer rapid click
      hideLoadBar();
      applyDayView(day, dir, keepModal);
    } catch {
      if (seq !== dayReqSeq) return;
      hideLoadBar();
      if (!state.day) {
        elLadderList.innerHTML = `<div class="empty-state">数据加载失败</div>`;
      }
    }
  }

  function jumpToDate(dt, opts = {}) {
    if (!dt || !state.dateSet.has(dt)) return;
    const keepModal = Boolean(opts && opts.keepModal);
    const current = state.targetDate || state.day?.date || "";
    if (dt === current) {
      if (!keepModal) closeAllSheets();
      return;
    }
    const from = currentDateIndex();
    const to = state.dates.findIndex((x) => x.date === dt);
    const dir = from < 0 || to < 0 ? null : to > from ? "older" : "newer";
    loadDay(dt, dir, { keepModal });
  }

  // ========================================================================
  // Helpers for Hot Sectors & Hot News (with fallback for older JSON shapes)
  // ========================================================================

  function getHotSectors(d) {
    if (!d) return [];
    if (Array.isArray(d.hot_sectors) && d.hot_sectors.length) return d.hot_sectors.slice(0, 8);
    // Fallback if viewing an older snapshot without hot_sectors
    return (d.catalysts || []).slice(0, 8).map((c) => ({
      id: c.id,
      kind: c.kind || "theme",
      name: c.title,
      heat_rank: c.heat_rank || 99,
      zt_total: c.total || 0,
      core_total: c.total || 0,
      driver_count: c.total || 0,
      multi: c.multi || 0,
      fanbao: Math.max(0, (c.total || 0) - (c.multi || 0)),
      max_height: c.max_height || 1,
      headline: c.headline || "",
      leaders: c.leaders || [],
      catalyst_id: c.id,
    }));
  }

  function getHotNews(d) {
    if (!d) return [];
    if (Array.isArray(d.hot_news) && d.hot_news.length) return d.hot_news;
    const out = [];
    let rk = 1;
    for (const c of d.catalysts || []) {
      const items = c.news && c.news.length ? c.news : [{ headline: c.headline, detail: "" }];
      for (const nw of items) {
        out.push({
          rank: rk++,
          headline: nw.headline || c.headline,
          detail: nw.detail || "",
          theme: c.theme || c.title,
          target_type: c.kind === "event" ? "catalyst" : "theme",
          target_id: c.kind === "event" ? c.id : c.theme || c.title,
          heat_rank: c.heat_rank || 99,
          leaders: c.leaders || [],
        });
      }
    }
    return out;
  }

  const _fbMapCache = new WeakMap();
  function getTodayFirstBoardMap(d) {
    if (!d) return new Map();
    if (_fbMapCache.has(d)) return _fbMapCache.get(d);
    const map = new Map();
    if (d.themes) {
      for (const th of Object.values(d.themes)) {
        for (const fb of th.first_boards || []) {
          if (!map.has(fb.code)) map.set(fb.code, fb);
        }
      }
    }
    _fbMapCache.set(d, map);
    return map;
  }

  const _fbSetCache = new WeakMap();
  function getTodayFirstBoardSet(d) {
    if (!d) return new Set();
    if (_fbSetCache.has(d)) return _fbSetCache.get(d);
    const set = new Set(Array.isArray(d.first_board_codes) ? d.first_board_codes : []);
    if (d.themes) {
      for (const th of Object.values(d.themes)) {
        for (const fb of th.first_boards || []) set.add(fb.code);
      }
    }
    _fbSetCache.set(d, set);
    return set;
  }

  function stockArchiveStatusHtml(item, todayCore, isTodayFb) {
    if (todayCore) {
      const lbl = todayCore.height >= 2 ? `今日${todayCore.height}板` : "今日反包";
      return `<span class="sr-badge is-today">${lbl}</span>`;
    }
    if (isTodayFb) {
      return `<span class="sr-badge is-fb">今日首板</span>`;
    }
    return "";
  }

  // ========================================================================
  // Tier 1 Rendering (Compact Hot-Sector Pulse Bar + Full-Height Ladder)
  // ========================================================================

  function renderTier1() {
    const d = state.day;
    if (!d) return;

    elDateLabel.textContent = topbarDateLabel(d.date);
    updateStepperButtons();
    renderHubBar();
    renderHomeTools();
    renderLadderFocusBar();
    renderLadder();
  }

  function getLadderQuickThemes(d) {
    if (!d) return [];
    const counts = new Map();
    const seen = new Set();
    for (const tier of d.ladder || []) {
      for (const code of tier.codes || []) {
        if (seen.has(code)) continue;
        seen.add(code);
        const st = d.stocks[code];
        if (!st) continue;
        const p = st.primary_theme;
        if (p) counts.set(p, (counts.get(p) || 0) + 1);
      }
    }
    const list = Array.from(counts.entries())
      .filter(([, cnt]) => cnt >= 2)
      .sort((a, b) => {
        const ra = d.themes?.[a[0]]?.heat_rank ?? 99;
        const rb = d.themes?.[b[0]]?.heat_rank ?? 99;
        if (b[1] !== a[1]) return b[1] - a[1];
        return ra - rb;
      })
      .slice(0, 4)
      .map(([t]) => t);

    // Ensure currently focused theme stays visible as active pill even if single-stock
    if (state.focusTheme && !list.includes(state.focusTheme)) {
      list.unshift(state.focusTheme);
      if (list.length > 4) list.pop();
    }
    return list;
  }

  function renderLadderFocusBar() {
    if (!elLadderFocusBar) return;
    const d = state.day;
    const themes = getLadderQuickThemes(d);
    if (!themes.length) {
      elLadderFocusBar.innerHTML = "";
      return;
    }
    elLadderFocusBar.innerHTML = themes
      .map((t) => {
        const active = state.focusTheme === t;
        const hCls = themeHeatCls(t);
        return `
          <button class="focus-pill ${active ? "active" : ""} ${hCls}" type="button" data-focus-theme="${esc(t)}" aria-pressed="${active}">
            ${esc(formatThemeLabel(t))}${active ? `<span class="focus-x">×</span>` : ""}
          </button>
        `;
      })
      .join("");
  }

  function toggleFocusTheme(theme) {
    const next = !theme || state.focusTheme === theme ? "" : theme;
    state.focusTheme = next;
    renderLadderFocusBar();
    applyLadderFocusState();
  }

  function applyLadderFocusState() {
    const ft = state.focusTheme;
    elLadderList.classList.toggle("has-focus", Boolean(ft));
    elLadderList.dataset.focusHeat = ft ? themeHeatCls(ft) : "";
    elLadderList.querySelectorAll(".stock-cell[data-code]").forEach((cell) => {
      if (!ft) {
        cell.classList.remove("is-focused", "is-focus-secondary", "is-dimmed");
        return;
      }
      const primary = cell.getAttribute("data-primary-theme") || "";
      const allThemes = (cell.getAttribute("data-all-themes") || "").split("|").filter(Boolean);
      if (primary === ft) {
        cell.classList.add("is-focused");
        cell.classList.remove("is-focus-secondary", "is-dimmed");
      } else if (allThemes.includes(ft)) {
        cell.classList.add("is-focus-secondary");
        cell.classList.remove("is-focused", "is-dimmed");
      } else {
        cell.classList.add("is-dimmed");
        cell.classList.remove("is-focused", "is-focus-secondary");
      }
    });
  }

  function renderHubBar() {
    const d = state.day;
    const sectors = getHotSectors(d);
    const topPreview = sectors.slice(0, 4);

    const previewHtml = topPreview.length
      ? topPreview
          .map((s, idx) => {
            const cls = heatCls(s.heat_rank);
            const sep = idx > 0 ? `<span class="hub-preview-sep">·</span>` : "";
            return `${sep}<span class="hub-preview-name ${cls}">${esc(formatThemeLabel(s.name))}</span>`;
          })
          .join("")
      : `<span class="hub-preview-empty">暂无板块</span>`;

    elHubBar.innerHTML = `
      <button class="hub-bar-main" type="button" data-open-hub="sectors" aria-label="打开热门板块与今日催化">
        <span class="hub-bar-label">今日热点</span>
        <span class="hub-bar-preview">${previewHtml}</span>
        <svg class="hub-chev" viewBox="0 0 12 12" width="11" height="11" fill="none" aria-hidden="true">
          <path d="M4.5 2.5L8 6L4.5 9.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
    `;
  }

  const LIB_FILIGREE_SVG = `<svg class="lib-fleur-svg" viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true"><path d="M8 1.4C8.9 4.5 11.5 7.1 14.6 8C11.5 8.9 8.9 11.5 8 14.6C7.1 11.5 4.5 8.9 1.4 8C4.5 7.1 7.1 4.5 8 1.4Z" stroke="currentColor" stroke-width="1.15" stroke-linejoin="round"/><circle cx="8" cy="8" r="1.35" fill="currentColor"/></svg>`;

  function renderHomeTools() {
    if (!elHomeTools) return;
    const d = state.day;
    const devs = d?.deviations || [];
    const urgentCnt = devs.filter((x) => x.status === "triggered" || x.status === "critical").length;
    elHomeTools.innerHTML = `
      <button class="home-tool-btn is-lib-featured" type="button" data-open-tool="sectors-lib">
        <span class="lib-corner tl" aria-hidden="true"></span>
        <span class="lib-corner br" aria-hidden="true"></span>
        ${LIB_FILIGREE_SVG}
        <span class="ht-title">题材库</span>
      </button>
      <button class="home-tool-btn ${urgentCnt > 0 ? "has-alert" : ""}" type="button" data-open-tool="deviation">
        <span class="ht-title">异动监控</span>
        ${urgentCnt > 0 ? `<span class="ht-badge">${urgentCnt}</span>` : ""}
      </button>
      <button class="home-tool-btn" type="button" data-open-tool="ma-list">
        <span class="ht-title">并购重组</span>
      </button>
    `;
  }

  function getDayDeviationMap(d) {
    const map = new Map();
    for (const x of d?.deviations || []) {
      if (x && x.code) map.set(x.code, x);
    }
    return map;
  }

  function devBadgeHtml(code, devMap) {
    const x = devMap && devMap.get(code);
    if (!x) return "";
    if (x.status === "triggered") {
      return `<span class="dev-mini-badge is-trig" title="已触严重异动">异</span>`;
    }
    if (x.status === "critical") {
      const tip = x.short_next_danger ? `明板触${x.short_max}次异动` : `明上限 +${x.bind_safe_pct}%`;
      return `<span class="dev-mini-badge is-crit" title="${esc(tip)}">异</span>`;
    }
    return `<span class="dev-mini-badge is-warn" title="临近异动 · 安全 +${esc(x.bind_safe_pct)}%">异</span>`;
  }

  function stockDevStripHtml(code) {
    const x = (state.day?.deviations || []).find((it) => it.code === code);
    if (!x) return "";
    let cls = "is-warn";
    let mainTxt = `安全 +${x.bind_safe_pct}% · 明卡线 ${Number(x.bind_safe_px).toFixed(2)}`;
    if (x.trig10_today || x.trig30_today) {
      cls = "is-trig";
      mainTxt = `${x.trig10_today ? "已触10日" : "已触30日"} · 次日重算`;
    } else if (x.status === "critical") {
      cls = "is-crit";
      mainTxt =
        x.bind_safe_pct < x.limit_pct
          ? `明上限 ${x.bind_safe_pct >= 0 ? "+" : ""}${x.bind_safe_pct}% · 卡线 ${Number(x.bind_safe_px).toFixed(2)}`
          : `明板触${x.short_max}次异动`;
    }
    return `
      <button class="stock-dev-strip ${cls}" type="button" data-open-deviation="1">
        <span class="sds-left">
          <span class="sds-tag">异动监控</span>
          <span class="sds-num">10日 ${x.dev10 >= 0 ? "+" : ""}${x.dev10}%</span>
        </span>
        <span class="sds-right">${esc(mainTxt)}<em>›</em></span>
      </button>
    `;
  }

  function stockReplenishHtml(st) {
    const rep = st?.replenish;
    if (!rep || !Array.isArray(rep.hits) || !rep.hits.length) return "";
    const fbShort = rep.fb_date ? rep.fb_date.slice(5).replace("-", ".") : "";
    const itemsHtml = rep.hits
      .map((h) => {
        const isCross = h.kind === "跨线补涨";
        const kindCls = isCross ? "is-cross" : "is-same";
        return `
          <div class="rep-card">
            <div class="rep-top">
              <div class="rep-leader-row">
                <span class="rep-verb">命中</span>
                <button class="rep-leader-btn" type="button" data-jump-stock="${esc(h.leader_code)}">${esc(h.leader_name)}</button>
                <span class="rep-leader-status">${esc(h.leader_status)}</span>
              </div>
              <span class="rep-kind-tag ${kindCls}">${esc(h.kind)}</span>
            </div>
            <div class="rep-link-line">
              <span>高标主炒</span>
              <button class="rep-theme-chip ${themeHeatCls(h.theme)}" type="button" data-jump-theme="${esc(h.theme)}">${esc(formatThemeLabel(h.theme))}</button>
              <span class="rep-arrow">→</span>
              <span>本股具备该属性</span>
            </div>
            ${h.evidence ? `<div class="rep-ev-text">${esc(h.evidence)}</div>` : ""}
          </div>
        `;
      })
      .join("");
    return `
      <div class="s-block">
        <h4 class="s-block-title rep-block-head">
          <span>补涨来源</span>
          ${
            rep.fb_date
              ? `<button class="rep-fb-btn" type="button" data-jump-date="${esc(rep.fb_date)}">首板日 ${esc(fbShort)} ›</button>`
              : ""
          }
        </h4>
        <div class="rep-list">${itemsHtml}</div>
      </div>
    `;
  }

  function stockCellHtml(st, inFanbaoRow = false, devMap = null) {
    const owTag = st.is_one_word ? `<span class="ow-tag">一字</span>` : "";
    const showDesc = (inFanbaoRow || st.is_fanbao) && st.boards_desc && st.boards_desc !== "首板" && st.boards_desc !== `${st.height}连板`;
    const fbTag = showDesc ? `<span class="fb-desc-tag">${esc(st.boards_desc)}</span>` : "";
    const devTag = devBadgeHtml(st.code, devMap);
    const repTag = st.replenish ? `<span class="rep-mini-badge" title="5板高标补涨">补</span>` : "";
    const dThemes =
      st.display_themes && st.display_themes.length
        ? st.display_themes
        : st.primary_theme
          ? [{ name: st.primary_theme, heat_rank: st.primary_heat_rank }]
          : [];

    const themesInner = dThemes
      .slice(0, 1)
      .map((item) => {
        const tHeat = heatCls(item.heat_rank);
        return `<span class="cell-theme ${tHeat}" data-cell-theme="${esc(item.name)}">${esc(formatThemeLabel(item.name))}</span>`;
      })
      .join("");

    const timeHtml = st.first_time ? `<span class="cell-time">${esc(st.first_time)}</span>` : "";
    let bottomHtml = "";
    if (state.ladderMetrics) {
      const amtStr = st.amount_yi > 0 ? `${Number(st.amount_yi).toFixed(1)}亿` : "--";
      const turnStr = st.turnover > 0 ? `${Number(st.turnover).toFixed(1)}%` : "--";
      const primaryHeat = dThemes[0] ? heatCls(dThemes[0].heat_rank) : "";
      bottomHtml = `
        <div class="cell-bottom is-metrics">
          <span class="cell-metrics-left">
            <span class="cm-dot ${primaryHeat}" aria-hidden="true"></span>
            <span class="cm-val">${amtStr}</span>
            <span class="cm-sep">·</span>
            <span class="cm-val">${turnStr}</span>
          </span>
          ${timeHtml}
        </div>
      `;
    } else if (themesInner || timeHtml) {
      bottomHtml = `<div class="cell-bottom"><div class="cell-themes">${themesInner}</div>${timeHtml}</div>`;
    }
    const primaryT = dThemes[0]?.name || st.primary_theme || "";
    const allT = (st.themes || []).join("|");
    return `
      <div class="stock-cell" role="button" tabindex="0"
           data-code="${esc(st.code)}"
           data-primary-theme="${esc(primaryT)}"
           data-all-themes="${esc(allT)}">
        <span class="cell-main">
          <span class="cell-name">${esc(st.name)}</span>
          ${boardBadgeHtml(st.code, false, st.name)}
          ${devTag}
          ${repTag}
          ${fbTag}
          ${owTag}
        </span>
        ${bottomHtml}
      </div>
    `;
  }

  function formatPctTag(pct, isNuclear = false) {
    if (pct === null || pct === undefined || Number.isNaN(Number(pct))) return "";
    const n = Number(pct);
    const sign = n > 0 ? "+" : "";
    const txt = `${sign}${n.toFixed(1)}%`;
    if (isNuclear || n <= -8.5) {
      return `<span class="broken-pct is-nuc">${txt}<em>核</em></span>`;
    }
    if (n < 0) {
      return `<span class="broken-pct is-down">${txt}</span>`;
    }
    return `<span class="broken-pct is-up">${txt}</span>`;
  }

  function brokenCellHtml(b, devMap = null) {
    const themeLbl = b.theme ? formatThemeLabel(b.theme) : "";
    const devTag = devBadgeHtml(b.code, devMap);
    const pctHtml = formatPctTag(b.pct_chg, b.is_nuclear);
    const bottomInner =
      themeLbl || pctHtml
        ? `<div class="cell-bottom">
             <div class="cell-themes">${themeLbl ? `<span class="cell-theme" data-cell-theme="${esc(b.theme)}">${esc(themeLbl)}</span>` : ""}</div>
             ${pctHtml}
           </div>`
        : "";
    return `
      <div class="stock-cell is-broken ${b.is_nuclear ? "is-nuclear-cell" : ""}" role="button" tabindex="0"
           data-code="${esc(b.code)}"
           data-primary-theme="${esc(b.theme || "")}"
           data-all-themes="${esc(b.theme || "")}">
        <span class="cell-main">
          <span class="cell-name">${esc(b.name)}</span>
          ${boardBadgeHtml(b.code, false, b.name)}
          ${devTag}
          <span class="broken-h-tag">昨${b.prev_height}板</span>
        </span>
        ${bottomInner}
      </div>
    `;
  }

  function recentBrokenCellHtml(b, devMap = null) {
    const themeLbl = b.theme ? formatThemeLabel(b.theme) : "";
    const devTag = devBadgeHtml(b.code, devMap);
    const trailParts = (b.trail || [])
      .filter((x) => x.pct !== null && x.pct !== undefined)
      .map((x) => {
        const n = Number(x.pct);
        const cls = n <= -8.5 ? "is-nuc" : n < 0 ? "is-down" : "is-up";
        return `<span class="rb-pt ${cls}">${n > 0 ? "+" : ""}${n.toFixed(1)}%</span>`;
      });
    const trailHtml = trailParts.length ? `<span class="rb-trail">${trailParts.join('<span class="rb-arr">→</span>')}</span>` : "";
    return `
      <div class="stock-cell is-broken is-recent-broken" role="button" tabindex="0"
           data-code="${esc(b.code)}"
           data-primary-theme="${esc(b.theme || "")}"
           data-all-themes="${esc(b.theme || "")}">
        <span class="cell-main">
          <span class="cell-name">${esc(b.name)}</span>
          ${boardBadgeHtml(b.code, false, b.name)}
          ${devTag}
          <span class="broken-h-tag">前${b.days_ago}日·${b.prev_height}板</span>
        </span>
        <div class="cell-bottom">
          <div class="cell-themes">${themeLbl ? `<span class="cell-theme" data-cell-theme="${esc(b.theme)}">${esc(themeLbl)}</span>` : ""}</div>
          ${trailHtml}
        </div>
      </div>
    `;
  }

  function renderLadder() {
    const d = state.day;
    const maxH = d.summary.max_height || 0;
    const devMap = getDayDeviationMap(d);
    const tiersHtml = [];

    let prevHeight = null;
    for (const tier of d.ladder || []) {
      const stocks = tier.codes.map((c) => d.stocks[c]).filter(Boolean);
      if (!stocks.length) continue;

      if (prevHeight !== null && prevHeight - tier.height > 1) {
        tiersHtml.push(`
          <div class="tier-gap-row" aria-label="高度断层">
            <span class="tier-gap-axis" aria-hidden="true"></span>
            <div class="tier-gap-line"><span>断层</span></div>
          </div>
        `);
      }

      const isPeak = tier.height === maxH && maxH >= 3;
      const axisCls = isPeak ? "peak" : "";

      tiersHtml.push(`
        <div class="tier-row ${isPeak ? "is-peak" : ""}">
          <div class="tier-axis ${axisCls}">
            <span class="axis-num">${tier.height}</span><span class="axis-unit">板</span>
          </div>
          <div class="tier-grid">
            ${stocks.map((st) => stockCellHtml(st, false, devMap)).join("")}
          </div>
        </div>
      `);
      prevHeight = tier.height;
    }

    const fanbaoStocks = (d.fanbao_boards || []).map((c) => d.stocks[c]).filter(Boolean);
    if (fanbaoStocks.length) {
      tiersHtml.push(`
        <div class="tier-row">
          <div class="tier-axis fanbao">
            <span class="axis-unit">反包</span>
          </div>
          <div class="tier-grid">
            ${fanbaoStocks.map((st) => stockCellHtml(st, true, devMap)).join("")}
          </div>
        </div>
      `);
    }

    const brokenList = d.broken_boards || [];
    const recentBroken = d.recent_broken || [];
    if (brokenList.length || recentBroken.length) {
      const recentHtml = recentBroken.length
        ? `
          <div class="recent-broken-wrap">
            <button class="recent-broken-toggle ${state.recentBrokenOpen ? "is-open" : ""}" type="button" data-toggle-recent-broken="1" aria-expanded="${state.recentBrokenOpen}">
              <span>前2日断板高标 · ${recentBroken.length}只</span>
              <span class="rb-chev" aria-hidden="true">▾</span>
            </button>
            ${
              state.recentBrokenOpen
                ? `<div class="tier-grid recent-broken-grid">${recentBroken.map((b) => recentBrokenCellHtml(b, devMap)).join("")}</div>`
                : ""
            }
          </div>
        `
        : "";

      tiersHtml.push(`
        <div class="tier-row">
          <div class="tier-axis broken">
            <span class="axis-unit">断板</span>
          </div>
          <div class="broken-col">
            ${brokenList.length ? `<div class="tier-grid">${brokenList.map((b) => brokenCellHtml(b, devMap)).join("")}</div>` : ""}
            ${recentHtml}
          </div>
        </div>
      `);
    }

    elLadderList.innerHTML = tiersHtml.length
      ? tiersHtml.join("")
      : `<div class="empty-state">暂无连板/反包</div>`;
    applyLadderFocusState();
  }

  // ========================================================================
  // Tier 2: Bottom Sheet Navigation & Spring Lifecycle
  // ========================================================================

  let sheetOpenGen = 0;
  let sheetClearTimer = null;

  function openModal(entry) {
    sheetOpenGen++;
    clearTimeout(sheetClearTimer);
    state.modalStack = [entry];
    elSheet.dataset.dir = "";
    elSheetBody.classList.remove("vt-swap");
    renderCurrentModal();

    requestAnimationFrame(() => {
      elShell.classList.add("receded");
      elBackdrop.classList.add("open");
      elSheet.classList.add("open");
      elSheet.setAttribute("aria-hidden", "false");
    });
  }

  function swapModal(dir, mutate) {
    elSheet.dataset.dir = dir;
    elSheetBody.classList.toggle("vt-swap", canVT);
    withTransition(dir, () => {
      mutate();
      renderCurrentModal();
    });
  }

  function pushModal(entry) {
    swapModal("push", () => state.modalStack.push(entry));
  }

  function popModal() {
    if (state.modalStack.length <= 1) {
      closeAllSheets();
      return;
    }
    swapModal("pop", () => state.modalStack.pop());
  }

  function closeAllSheets(instant = false) {
    const gen = ++sheetOpenGen;
    clearTimeout(sheetClearTimer);
    state.modalStack = [];
    elShell.classList.remove("receded", "dragging");
    elBackdrop.classList.remove("open", "dragging");
    elSheet.classList.remove("open", "dragging");
    elSheet.style.transform = "";
    elShell.style.transform = "";
    elBackdrop.style.opacity = "";
    elSheet.setAttribute("aria-hidden", "true");
    closeDateSheet();
    if (instant) {
      elSheetHeader.innerHTML = "";
      elSheetBody.innerHTML = "";
    } else {
      // Clear off-screen modal DOM once close transition completes so main scroll stays light
      sheetClearTimer = setTimeout(() => {
        if (gen === sheetOpenGen && !elSheet.classList.contains("open")) {
          elSheetHeader.innerHTML = "";
          elSheetBody.innerHTML = "";
        }
      }, 390);
    }
  }

  function currentModalEntry() {
    return state.modalStack[state.modalStack.length - 1] || null;
  }

  function renderCurrentModal() {
    const entry = currentModalEntry();
    if (!entry || !state.day) return;
    elSheetBody.scrollTop = 0;

    if (entry.type === "brand") {
      renderBrandModal(entry);
    } else if (entry.type === "hub") {
      renderHubModal(entry);
    } else if (entry.type === "search") {
      renderSearchModal(entry);
    } else if (entry.type === "sectors-lib") {
      renderSectorsLibModal(entry);
    } else if (entry.type === "deviation") {
      renderDeviationModal(entry);
    } else if (entry.type === "ma-list") {
      renderMaListModal(entry);
    } else if (entry.type === "catalyst" || entry.type === "theme") {
      renderThemeModal(entry);
    } else if (entry.type === "stock") {
      renderStockModal(entry);
    }
  }

  // ========================================================================
  // Modal View Brand: Framed Renaissance Fresco & Daily Market Pulse
  // ========================================================================

  function renderBrandModal() {
    const d = state.day;
    const isLatest = currentDateIndex() <= 0;
    const hasBack = state.modalStack.length > 1;

    elSheetHeader.innerHTML = `
      <div class="sheet-header-row">
        <div class="sheet-title-group">
          ${hasBack ? `<button class="sheet-back-btn" id="modal-back" type="button" aria-label="返回">‹</button>` : ""}
          <h3 class="sheet-title brand-sheet-title">文艺复兴</h3>
          <span class="brand-sheet-latin">RENAISSANCE</span>
        </div>
        <button class="sheet-close-btn" id="modal-close" type="button" aria-label="关闭">×</button>
      </div>
    `;
    bindModalHeaderButtons();

    elSheetBody.innerHTML = `
      <div class="brand-modal">
        <div class="brand-gallery-stage">
          <div class="brand-gallery-frame">
            <img src="./assets/avatar.jpg?v=3" alt="文艺复兴 · 湿壁画" width="212" height="212" />
          </div>
          <div class="brand-gallery-caption">
            <span class="brand-cap-cn">文艺复兴</span>
            <span class="brand-cap-dot" aria-hidden="true">·</span>
            <span class="brand-cap-date">${esc(d?.date || "--")}</span>
          </div>
        </div>

        ${!isLatest ? `<div class="brand-actions"><button class="brand-act-btn is-primary" type="button" data-brand-act="latest">回到最新交易日</button></div>` : ""}
      </div>
    `;

    elSheetBody.querySelectorAll("[data-brand-act]").forEach((btn) => {
      btn.addEventListener("click", () => {
        closeAllSheets();
        if (state.dates.length) jumpToDate(state.dates[0].date);
      });
    });
  }

  // ========================================================================
  // Modal View 0: Combined Hub Modal (热门板块 + 今日催化 + 首板前排)
  // ========================================================================

  function renderHubModal(entry) {
    const d = state.day;
    const sectors = getHotSectors(d);
    const news = getHotNews(d);
    const validTabs = ["sectors", "catalysts", "first"];
    const activeTab = validTabs.includes(entry.tab) ? entry.tab : "sectors";
    entry.tab = activeTab;

    const hasBack = state.modalStack.length > 1;
    elSheetHeader.innerHTML = `
      <div class="sheet-header-row">
        <div class="sheet-title-group">
          ${hasBack ? `<button class="sheet-back-btn" id="modal-back" type="button" aria-label="返回">‹</button>` : ""}
          <div class="seg-tabs" role="tablist" aria-label="热点、催化与首板前排切换">
            <button class="seg-tab ${activeTab === "sectors" ? "active" : ""}" type="button" role="tab" aria-selected="${activeTab === "sectors"}" data-hub-tab="sectors">
              <span>热门板块</span>
            </button>
            <button class="seg-tab ${activeTab === "catalysts" ? "active" : ""}" type="button" role="tab" aria-selected="${activeTab === "catalysts"}" data-hub-tab="catalysts">
              <span>今日催化</span>
            </button>
            <button class="seg-tab ${activeTab === "first" ? "active" : ""}" type="button" role="tab" aria-selected="${activeTab === "first"}" data-hub-tab="first">
              <span>首板前排</span>
            </button>
          </div>
        </div>
        <button class="sheet-close-btn" id="modal-close" type="button" aria-label="关闭">×</button>
      </div>
    `;

    bindModalHeaderButtons();
    bindEvidenceToggles(elSheetBody);
    elSheetHeader.querySelectorAll("[data-hub-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const nextTab = btn.getAttribute("data-hub-tab");
        if (nextTab && nextTab !== entry.tab) {
          entry.tab = nextTab;
          elSheetHeader.querySelectorAll("[data-hub-tab]").forEach((b) => {
            const on = b.getAttribute("data-hub-tab") === nextTab;
            b.classList.toggle("active", on);
            b.setAttribute("aria-selected", String(on));
          });
          elSheetBody.scrollTop = 0;
          renderHubBody(entry, sectors, news);
        }
      });
    });

    renderHubBody(entry, sectors, news);
  }

  function leaderChipsHtml(leaders) {
    return (leaders || [])
      .slice(0, 3)
      .map((l) => {
        const ow = l.is_one_word ? `<span class="mini-ow">一字</span>` : "";
        const hLbl = l.height >= 2 ? `${l.height}B` : l.height === 1 ? "首/反" : "";
        if (l.code) {
          return `<button class="cat-leader-chip is-tappable" type="button" data-leader-code="${esc(l.code)}">${esc(l.name)}${boardBadgeHtml(l.code, false, l.name)}${hLbl ? `<em>${hLbl}</em>` : ""}${ow}</button>`;
        }
        return `<span class="cat-leader-chip">${esc(l.name)}${boardBadgeHtml(l.code, false, l.name)}${hLbl ? `<em>${hLbl}</em>` : ""}${ow}</span>`;
      })
      .join("");
  }

  function bindLeaderChipClicks(root) {
    root.querySelectorAll("[data-leader-code]").forEach((chip) => {
      chip.addEventListener("click", (e) => {
        e.stopPropagation();
        const code = chip.getAttribute("data-leader-code");
        if (code) {
          pushModal({ type: "stock", id: code, intraday: true, navList: getDayLadderOrder(state.day) });
        }
      });
    });
  }

  function hubTrendSparkHtml(trend, curDate, hCls) {
    if (!Array.isArray(trend) || trend.length < 2) return "";
    const maxZt = Math.max(1, ...trend.map((x) => x.zt || 0));
    const bars = trend
      .map((x) => {
        const zt = x.zt || 0;
        const pct = zt > 0 ? Math.max(20, Math.round((zt / maxZt) * 100)) : 8;
        const isCur = x.d === curDate;
        const isEmpty = zt <= 0;
        return `<span class="ht-bar ${isCur ? "is-cur" : ""} ${isEmpty ? "is-zero" : ""}" style="height:${pct}%" title="${esc(shortDate(x.d))} 涨停${zt}${x.h >= 2 ? ` · ${x.h}板` : ""}"></span>`;
      })
      .join("");
    return `<span class="hub-trend-mini ${hCls}" aria-label="近5日热度轨迹">${bars}</span>`;
  }

  function renderHubBody(entry, sectors, news) {
    const d = state.day;
    if (entry.tab === "sectors") {
      if (!sectors.length) {
        elSheetBody.innerHTML = `<div class="modal-view"><div class="empty-state">当日暂无热门板块</div></div>`;
        return;
      }
      const cardsHtml = sectors
        .map((s, idx) => {
          const hCls = heatCls(s.heat_rank);
          const rankNum = String(idx + 1).padStart(2, "0");
          const statParts = [];
          if (s.zt_total) statParts.push(`涨停<b>${s.zt_total}</b>`);
          if (s.tier_shape) {
            statParts.push(`梯队<b>${esc(s.tier_shape)}</b>`);
          } else if (s.max_height >= 2) {
            statParts.push(`最高<b>${s.max_height}板</b>`);
          }
          const evBadge = s.kind === "event" ? `<span class="hub-kind-badge">事件</span>` : "";
          const streakBadge =
            s.streak_days >= 2 ? `<span class="hub-streak-badge ${hCls}">连${s.streak_days}日</span>` : "";
          const trendSpark = hubTrendSparkHtml(s.trend || d?.themes?.[s.name]?.trend, d?.date, hCls);
          const leadersHtml = leaderChipsHtml(s.leaders);

          return `
            <div class="catalyst-card hub-sector-card ${hCls}" role="button" tabindex="0"
              data-sector-kind="${esc(s.kind)}"
              data-sector-id="${esc(s.kind === "event" ? s.id : s.name)}"
              data-cat-id="${esc(s.catalyst_id || "")}">
              <div class="cat-top">
                <span class="cat-name-wrap">
                  <span class="cat-rank-tag">${rankNum}</span>
                  <span class="cat-name">${esc(formatThemeLabel(s.name))}</span>
                  ${evBadge}
                  ${streakBadge}
                </span>
                <span class="hub-sector-right">
                  ${trendSpark}
                  <span class="hub-sector-stats">${statParts.join('<span class="hub-stat-dot">·</span>')}</span>
                </span>
              </div>
              ${s.headline ? `<div class="cat-headline">${esc(s.headline)}</div>` : ""}
              ${leadersHtml ? `<div class="cat-leaders">${leadersHtml}</div>` : ""}
            </div>
          `;
        })
        .join("");

      elSheetBody.innerHTML = `
        <div class="modal-view">
          <div class="hub-list">${cardsHtml}</div>
        </div>
      `;

      bindLeaderChipClicks(elSheetBody);
      elSheetBody.querySelectorAll("[data-sector-id]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const kind = btn.getAttribute("data-sector-kind");
          const id = btn.getAttribute("data-sector-id");
          const catId = btn.getAttribute("data-cat-id");
          if (kind === "event") {
            pushModal({ type: "catalyst", id });
          } else {
            pushModal({ type: "theme", id, catalystId: catId || null, tab: "day" });
          }
        });
      });
      return;
    }

    if (entry.tab === "first") {
      const fbAll = Array.isArray(d?.first_boards) ? d.first_boards : [];
      if (!fbAll.length) {
        elSheetBody.innerHTML = `<div class="modal-view"><div class="empty-state">当日暂无主线首板前排</div></div>`;
        return;
      }
      const themeOrder = [];
      for (const fb of fbAll) {
        if (fb.theme && !themeOrder.includes(fb.theme)) themeOrder.push(fb.theme);
      }
      const activeFilter = entry.fbFilter && themeOrder.includes(entry.fbFilter) ? entry.fbFilter : "";
      const list = activeFilter ? fbAll.filter((x) => x.theme === activeFilter) : fbAll;
      const fbNavList = list.map((x) => ({ code: x.code, name: x.name }));

      const filterHtml =
        themeOrder.length > 1
          ? `
            <div class="dev-filter-tabs">
              <button class="dev-filter-btn ${!activeFilter ? "active" : ""}" type="button" data-fb-filter="">全部 ${fbAll.length}</button>
              ${themeOrder
                .map((t) => {
                  const cnt = fbAll.filter((x) => x.theme === t).length;
                  return `<button class="dev-filter-btn ${activeFilter === t ? "active" : ""}" type="button" data-fb-filter="${esc(t)}">${esc(formatThemeLabel(t))} ${cnt}</button>`;
                })
                .join("")}
            </div>
          `
          : "";

      const rowsHtml = list
        .map((fb) => {
          const hCls = heatCls(fb.heat_rank);
          const ow = fb.is_one_word ? `<span class="ow-tag">一字</span>` : "";
          const amt = fb.amount_yi > 0 ? `${Number(fb.amount_yi).toFixed(1)}亿` : "--";
          const turn = fb.turnover > 0 ? `${Number(fb.turnover).toFixed(1)}%` : "--";
          return `
            <button class="fb-front-row" type="button" data-fb-code="${esc(fb.code)}">
              <span class="fbf-left">
                <span class="fbf-name-line">
                  <span class="fbf-name">${esc(fb.name)}</span>
                  ${boardBadgeHtml(fb.code, false, fb.name)}
                  ${ow}
                </span>
                <span class="fbf-theme ${hCls}">${esc(formatThemeLabel(fb.theme))}</span>
              </span>
              <span class="fbf-right">
                <span class="fbf-time">${esc(fb.first_time || "--:--")}</span>
                <span class="fbf-metrics">${amt}<em>·</em>${turn}</span>
              </span>
            </button>
          `;
        })
        .join("");

      elSheetBody.innerHTML = `
        <div class="modal-view">
          ${filterHtml}
          <div class="fb-front-list">${rowsHtml}</div>
        </div>
      `;

      elSheetBody.querySelectorAll("[data-fb-filter]").forEach((btn) => {
        btn.addEventListener("click", () => {
          entry.fbFilter = btn.getAttribute("data-fb-filter") || "";
          renderHubBody(entry, sectors, news);
        });
      });

      elSheetBody.querySelectorAll("[data-fb-code]").forEach((row) => {
        const code = row.getAttribute("data-fb-code");
        if (code && d?.date) {
          row.addEventListener("touchstart", () => prefetchIntraday(code, d.date), { passive: true });
          row.addEventListener("pointerenter", () => prefetchIntraday(code, d.date), { passive: true });
        }
        row.addEventListener("click", () => {
          if (code) pushModal({ type: "stock", id: code, intraday: true, navList: fbNavList });
        });
      });
      return;
    }

    // Tab: 今日催化
    if (!news.length) {
      elSheetBody.innerHTML = `<div class="modal-view"><div class="empty-state">当日暂无催化消息</div></div>`;
      return;
    }

    const newsCardsHtml = news
      .map((n, idx) => {
        const hCls = heatCls(n.heat_rank);
        const rankNum = String(n.rank || idx + 1).padStart(2, "0");
        const hasTarget = Boolean(n.target_type && n.target_id);
        const leadersHtml = leaderChipsHtml(n.leaders);
        return `
          <div class="catalyst-card hub-news-card ${hCls} ${hasTarget ? "is-clickable" : ""}"
               ${hasTarget ? `role="button" tabindex="0" data-news-type="${esc(n.target_type)}" data-news-id="${esc(n.target_id)}"` : ""}>
            <div class="cat-top">
              <span class="cat-name-wrap">
                <span class="cat-rank-tag">${rankNum}</span>
                ${n.theme ? `<span class="hub-news-theme ${hCls}">${esc(formatThemeLabel(n.theme))}</span>` : ""}
              </span>
            </div>
            <div class="hub-news-hl">${esc(n.headline)}</div>
            ${n.detail ? `<div class="hub-news-dt">${esc(n.detail)}</div>` : ""}
            ${leadersHtml ? `<div class="cat-leaders">${leadersHtml}</div>` : ""}
          </div>
        `;
      })
      .join("");

    elSheetBody.innerHTML = `
      <div class="modal-view">
        <div class="hub-list">${newsCardsHtml}</div>
      </div>
    `;

    bindLeaderChipClicks(elSheetBody);
    elSheetBody.querySelectorAll("[data-news-id]").forEach((card) => {
      card.addEventListener("click", () => {
        const tType = card.getAttribute("data-news-type");
        const tId = card.getAttribute("data-news-id");
        if (tType === "theme") {
          pushModal({ type: "theme", id: tId, tab: "day" });
        } else if (tType === "catalyst") {
          pushModal({ type: "catalyst", id: tId });
        }
      });
    });
  }

  // ========================================================================
  // Modal View S: Global Search Modal (股票名称/代码 + 板块查询)
  // ========================================================================

  function renderSearchModal(entry) {
    const hasBack = state.modalStack.length > 1;
    const initQuery = entry.query || "";

    elSheetHeader.innerHTML = `
      <div class="search-header-row">
        ${hasBack ? `<button class="sheet-back-btn" id="modal-back" type="button" aria-label="返回">‹</button>` : ""}
        <div class="search-input-wrap">
          <svg class="search-input-icon" viewBox="0 0 16 16" width="14" height="14" fill="none" aria-hidden="true">
            <circle cx="7" cy="7" r="4.6" stroke="currentColor" stroke-width="1.5"/>
            <path d="M10.5 10.5L13.8 13.8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
          <input id="search-input" class="search-input" type="search" inputmode="search"
                 autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"
                 placeholder="搜股票名称、代码或板块…" value="${esc(initQuery)}" />
          <button id="search-clear" class="search-clear-btn ${initQuery ? "" : "hidden"}" type="button" aria-label="清空">×</button>
        </div>
        <button class="sheet-close-btn" id="modal-close" type="button" aria-label="关闭">×</button>
      </div>
    `;

    elSheetBody.innerHTML = `<div class="modal-view" id="search-results"></div>`;
    bindModalHeaderButtons();
    bindEvidenceToggles(elSheetBody);

    const inputEl = $("search-input");
    const clearEl = $("search-clear");

    let isComposing = false;
    let searchRaf = 0;
    const scheduleSearch = (q) => {
      cancelAnimationFrame(searchRaf);
      searchRaf = requestAnimationFrame(() => renderSearchResults(q));
    };

    const onQueryChange = () => {
      const q = inputEl.value;
      entry.query = q;
      clearEl.classList.toggle("hidden", !q);
      if (!isComposing) scheduleSearch(q);
    };

    inputEl.addEventListener("compositionstart", () => {
      isComposing = true;
    });
    inputEl.addEventListener("compositionend", () => {
      isComposing = false;
      onQueryChange();
    });
    inputEl.addEventListener("input", onQueryChange);
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const firstHit = elSheetBody.querySelector("#search-results .sr-card");
        if (firstHit) {
          e.preventDefault();
          inputEl.blur();
          firstHit.click();
        }
      }
    });
    clearEl.addEventListener("click", () => {
      inputEl.value = "";
      onQueryChange();
      inputEl.focus();
    });

    if (state.searchIndex) {
      renderSearchResults(initQuery);
    } else {
      const box = $("search-results");
      if (box) box.innerHTML = `<div class="empty-state">加载全库索引…</div>`;
      loadSearchIndex().then(() => {
        if (currentModalEntry() === entry) {
          renderSearchResults(entry.query || "");
        }
      });
    }

    // Focus input softly after sheet open starts
    setTimeout(() => {
      if (currentModalEntry() === entry && document.activeElement !== inputEl && !initQuery) {
        inputEl.focus({ preventScroll: true });
      }
    }, 120);
  }

  function highlightMatch(text, query) {
    const raw = String(text ?? "");
    const q = query.trim();
    if (!q) return esc(raw);
    const idx = raw.toLowerCase().indexOf(q.toLowerCase());
    if (idx < 0) return esc(raw);
    return (
      esc(raw.slice(0, idx)) +
      `<mark class="s-hl">${esc(raw.slice(idx, idx + q.length))}</mark>` +
      esc(raw.slice(idx + q.length))
    );
  }

  function matchSectors(q, idx) {
    const ql = q.toLowerCase();
    const d = state.day;
    const out = [];
    const seen = new Set();

    // Standard 33 sectors + intrinsic (国企改革) + classic zibei + regions (name match or alias match)
    const searchableSectors = [...idx.allSectors, ...(idx.intrinsic || []), ...(idx.zibei || []), ...(idx.regions || [])];
    for (const s of searchableSectors) {
      if (seen.has(s)) continue;
      const disp = formatThemeLabel(s);
      const sl = s.toLowerCase();
      const dl = disp.toLowerCase();
      let score = 0;
      let matchedAlias = "";
      if (dl === ql || sl === ql) score = 100;
      else if (dl.startsWith(ql) || sl.startsWith(ql)) score = 85;
      else if (dl.includes(ql) || sl.includes(ql)) score = 70;
      else {
        const aliases = SECTOR_ALIASES[s] || [];
        for (const a of aliases) {
          if (a === ql) {
            score = 65;
            matchedAlias = a;
            break;
          }
          if (a.includes(ql) || (ql.length >= 2 && ql.includes(a))) {
            score = 55;
            matchedAlias = a;
            break;
          }
        }
      }
      if (score > 0) {
        seen.add(s);
        const th = d?.themes?.[s];
        const isStd = idx.sectorSet.has(s);
        out.push({
          kind: "theme",
          id: s,
          name: disp,
          matchedAlias,
          score: score + (isStd ? 8 : 0) + (th?.zt_total ? 10 : 0),
          heatRank: th?.heat_rank || 99,
          ztTotal: th?.zt_total || 0,
          maxHeight: th?.max_height || 0,
          dbCount: idx.sectorCounts[s] || 0,
        });
      }
    }

    // Also match today's active temporary event themes (e.g. 平准稳市 / 金字辈)
    for (const hs of getHotSectors(d)) {
      const disp = formatThemeLabel(hs.name);
      if (hs.kind === "event" && !seen.has(hs.name) && (disp.toLowerCase().includes(ql) || hs.name.toLowerCase().includes(ql))) {
        out.push({
          kind: "catalyst",
          id: hs.id,
          name: disp,
          matchedAlias: "",
          score: 80,
          heatRank: hs.heat_rank || 99,
          ztTotal: hs.zt_total || 0,
          maxHeight: hs.max_height || 0,
          dbCount: 0,
        });
      }
    }

    out.sort((a, b) => b.score - a.score || a.heatRank - b.heatRank || b.dbCount - a.dbCount);
    return out;
  }

  function matchStocks(q, idx) {
    const ql = q.toLowerCase();
    const isAsciiAlpha = /^[a-z]+$/.test(ql);
    const d = state.day;
    const fbSet = getTodayFirstBoardSet(d);
    const results = [];

    for (const item of idx.stocks) {
      let score = 0;
      if (item.code === ql || item.nameLower === ql) score = 100;
      else if (isAsciiAlpha && item.py && item.py === ql) score = 96;
      else if (item.nameLower.startsWith(ql) || item.code.startsWith(ql)) score = 85;
      else if (isAsciiAlpha && item.py && item.py.startsWith(ql)) score = 82;
      else if (item.nameLower.includes(ql) || item.code.includes(ql)) score = 70;
      else if (isAsciiAlpha && ql.length >= 2 && item.py && item.py.includes(ql)) score = 68;
      if (!score) continue;

      const todayCore = d?.stocks?.[item.code];
      const isTodayFb = fbSet.has(item.code);
      if (todayCore) score += 20 + todayCore.height;
      else if (isTodayFb) score += 12;

      results.push({ item, score, todayCore, isTodayFb });
    }

    results.sort(
      (a, b) =>
        b.score - a.score ||
        b.item.maxHeight - a.item.maxHeight ||
        b.item.luCount - a.item.luCount ||
        (b.item.lastDate || "").localeCompare(a.item.lastDate || "")
    );
    return results.slice(0, 40);
  }

  function renderSearchResults(rawQuery) {
    const box = $("search-results");
    if (!box) return;
    const idx = state.searchIndex;
    if (!idx) {
      box.innerHTML = `<div class="empty-state">索引加载失败</div>`;
      return;
    }

    const q = String(rawQuery || "").trim();
    const d = state.day;

    // Empty query: Ultra-clean Search (only Recent Searches + quiet prompt; 题材库/卡异动/并购重组 live on home strip)
    if (!q) {
      const recents = loadRecentSearches();
      const recentHtml = recents.length
        ? `
          <div class="s-block">
            <h4 class="s-block-title">
              <span>最近查询</span>
              <button class="text-action-btn" id="clear-recent-btn" type="button">清空</button>
            </h4>
            <div class="s-tag-wrap">
              ${recents
                .map(
                  (r) => `
                  <button class="s-theme-pill recent-pill" type="button"
                          data-recent-kind="${esc(r.kind)}" data-recent-id="${esc(r.id)}" data-recent-name="${esc(formatThemeLabel(r.name))}">
                    <span>${esc(formatThemeLabel(r.name))}</span>
                    ${r.kind === "stock" ? `<span class="cnt">${esc(r.id)}</span>` : ""}
                  </button>
                `
                )
                .join("")}
            </div>
          </div>
        `
        : `<div class="search-empty-hint">输入股票名称、代码或板块名即时检索</div>`;

      box.innerHTML = recentHtml;

      const clearBtn = $("clear-recent-btn");
      if (clearBtn) {
        clearBtn.addEventListener("click", () => {
          clearRecentSearches();
          renderSearchResults("");
        });
      }
      bindSearchResultClicks(box);
      return;
    }

    // Active query: match sectors & stocks
    const matchedSectors = matchSectors(q, idx);
    const matchedStocks = matchStocks(q, idx);

    if (!matchedSectors.length && !matchedStocks.length) {
      box.innerHTML = `<div class="empty-state">未找到“${esc(q)}”相关的股票或板块</div>`;
      return;
    }

    const sectorsHtml = matchedSectors.length
      ? `
        <div class="s-block">
          <h4 class="s-block-title"><span>板块</span></h4>
          <div class="search-list">
            ${matchedSectors
              .map((s) => {
                const hCls = heatCls(s.heatRank);
                const todayStat =
                  s.ztTotal > 0
                    ? `<span class="sr-badge ${hCls}">今日${s.ztTotal}涨停${s.maxHeight >= 2 ? ` · ${s.maxHeight}板` : ""}</span>`
                    : "";
                return `
                  <button class="sr-card sr-sector-card ${hCls}" type="button"
                          data-search-sector-kind="${esc(s.kind)}" data-search-sector="${esc(s.id)}" data-search-sector-name="${esc(s.name)}">
                    <div class="sr-main">
                      <span class="sr-name ${hCls}">${highlightMatch(s.name, q)}</span>
                    </div>
                    <div class="sr-right">
                      ${todayStat}
                      <span class="sr-arrow">›</span>
                    </div>
                  </button>
                `;
              })
              .join("")}
          </div>
        </div>
      `
      : "";

    const stocksHtml = matchedStocks.length
      ? `
        <div class="s-block">
          <h4 class="s-block-title"><span>个股</span></h4>
          <div class="search-list">
            ${matchedStocks
              .map(({ item, todayCore, isTodayFb }) => {
                const statusBadge = stockArchiveStatusHtml(item, todayCore, isTodayFb);
                const tagsHtml = item.tags
                  .slice(0, 4)
                  .map((t) => `<span class="sr-tag ${themeHeatCls(t)}">${esc(formatThemeLabel(t))}</span>`)
                  .join("");
                const maHtml = item.maL1
                  .filter((t) => !item.tags.includes(t))
                  .slice(0, 2)
                  .map((t) => `<span class="sr-tag is-ma">拟·${esc(formatThemeLabel(t))}</span>`)
                  .join("");

                return `
                  <button class="sr-card sr-stock-card" type="button"
                          data-search-stock="${esc(item.code)}" data-search-stock-name="${esc(item.name)}">
                    <div class="sr-stock-top">
                      <span class="sr-main">
                        <span class="sr-name">${highlightMatch(item.name, q)}</span>
                        ${boardBadgeHtml(item.code, false, item.name)}
                        <span class="sr-code">${highlightMatch(item.code, q)}</span>
                        ${item.province ? `<span class="sr-prov">${esc(item.province)}</span>` : ""}
                      </span>
                      <span class="sr-right">${statusBadge}</span>
                    </div>
                    ${tagsHtml || maHtml ? `<div class="sr-tags">${tagsHtml}${maHtml}</div>` : ""}
                  </button>
                `;
              })
              .join("")}
          </div>
        </div>
      `
      : "";

    box.innerHTML = `${sectorsHtml}${stocksHtml}`;
    bindSearchResultClicks(box);
  }

  function bindSearchResultClicks(box) {
    box.querySelectorAll("[data-search-sector]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const kind = btn.getAttribute("data-search-sector-kind") || "theme";
        const id = btn.getAttribute("data-search-sector");
        const name = btn.getAttribute("data-search-sector-name") || id;
        if (!id) return;
        saveRecentSearch({ kind: "sector", id, name });
        if (kind === "catalyst") {
          pushModal({ type: "catalyst", id });
        } else {
          const hasToday = Boolean(state.day?.themes?.[id]?.zt_total || state.day?.themes?.[id]?.total);
          pushModal({ type: "theme", id, tab: hasToday ? "day" : "all" });
        }
      });
    });

    box.querySelectorAll("[data-search-stock]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const code = btn.getAttribute("data-search-stock");
        const name = btn.getAttribute("data-search-stock-name") || code;
        if (!code) return;
        saveRecentSearch({ kind: "stock", id: code, name });
        pushModal({ type: "stock", id: code, intraday: false });
      });
    });

    box.querySelectorAll("[data-recent-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const kind = btn.getAttribute("data-recent-kind");
        const id = btn.getAttribute("data-recent-id");
        if (kind === "stock") {
          pushModal({ type: "stock", id, intraday: false });
        } else {
          const hasToday = Boolean(state.day?.themes?.[id]?.zt_total || state.day?.themes?.[id]?.total);
          pushModal({ type: "theme", id, tab: hasToday ? "day" : "all" });
        }
      });
    });
  }

  // ========================================================================
  // Modal View L: 题材库 (未来题材 18 + 传统题材 15 + 地域题材 12 + 玄学题材 8)
  // ========================================================================

  const FUTURE_THEMES = [
    "芯片", "算力", "通信", "AI应用",
    "端侧AI", "机器人", "智能驾驶", "锂电光伏",
    "金融", "商业航天", "低空经济", "华为链",
    "海洋经济", "氢能源", "量子科技", "脑机接口",
    "冰雪经济", "国企改革",
  ];

  const TRADITIONAL_THEMES = [
    "电力", "汽车链", "机械设备", "军工",
    "航运物流", "油气", "煤炭", "化工",
    "有色", "医药", "消费", "农业",
    "环保", "地产链", "基建",
  ];

  const REGION_THEMES = [
    "海峡两岸", "海南", "东北", "西部大开发",
    "雄安", "深圳", "上海", "杭州",
    "湖北", "西藏", "新疆", "重庆",
  ];

  const MYSTIC_THEMES = [
    "中字头", "数字辈", "动物", "华字辈",
    "东方字辈", "龙字辈", "金字辈", "羊字辈",
  ];

  function renderSectorsLibModal(entry) {
    const hasBack = state.modalStack.length > 1;
    elSheetHeader.innerHTML = `
      <div class="sheet-header-row">
        <div class="sheet-title-group">
          ${hasBack ? `<button class="sheet-back-btn" id="modal-back" type="button" aria-label="返回">‹</button>` : ""}
          <span class="lib-head-emblem" aria-hidden="true">${LIB_FILIGREE_SVG}</span>
          <h3 class="sheet-title lib-sheet-title">题材库</h3>
          <span class="lib-sheet-latin">CODEX</span>
        </div>
        <button class="sheet-close-btn" id="modal-close" type="button" aria-label="关闭">×</button>
      </div>
    `;
    bindModalHeaderButtons();

    if (!state.searchIndex) {
      loadSearchIndex();
    }

    const d = state.day;
    const renderTiles = (list) =>
      list
        .map((s) => {
          const th = d?.themes?.[s];
          const tCls = heatCls(th?.heat_rank);
          const ztCnt = th?.zt_total || 0;
          return `
            <button class="sector-tile ${tCls} ${ztCnt > 0 ? "has-zt" : ""}" type="button" data-lib-sector="${esc(s)}">
              <span>${esc(s)}</span>
              ${ztCnt > 0 ? `<em class="st-zt">${ztCnt}</em>` : ""}
            </button>
          `;
        })
        .join("");

    const cornerSvg = `<svg class="codex-corner-svg" viewBox="0 0 18 18" width="16" height="16" fill="none" aria-hidden="true"><path d="M1.5 16.5V4.8C1.5 3 3 1.5 4.8 1.5H16.5" stroke="currentColor" stroke-width="1.1"/><path d="M4.8 11.5V6.2C4.8 5.4 5.4 4.8 6.2 4.8H11.5" stroke="currentColor" stroke-width="0.9" opacity="0.68"/><circle cx="4.8" cy="4.8" r="1.15" fill="currentColor"/></svg>`;
    const renderPlate = (title, sub, list, isPrimary = false) => `
      <section class="sector-group codex-plate ${isPrimary ? "is-primary" : ""}">
        <span class="codex-c tl" aria-hidden="true">${cornerSvg}</span>
        <span class="codex-c tr" aria-hidden="true">${cornerSvg}</span>
        <span class="codex-c bl" aria-hidden="true">${cornerSvg}</span>
        <span class="codex-c br" aria-hidden="true">${cornerSvg}</span>
        <div class="sector-group-head codex-head">
          <span class="codex-rule" aria-hidden="true"></span>
          <span class="sector-group-title">${esc(title)}</span>
          ${sub ? `<span class="codex-sub">${esc(sub)}</span>` : ""}
          <span class="codex-rule" aria-hidden="true"></span>
        </div>
        <div class="sector-matrix">${renderTiles(list)}</div>
      </section>
    `;

    elSheetBody.innerHTML = `
      <div class="modal-view sector-lib-view">
        ${renderPlate("未来题材", "XVIII", FUTURE_THEMES, true)}
        ${renderPlate("传统题材", "XV", TRADITIONAL_THEMES, true)}
        ${renderPlate("地域题材", "", REGION_THEMES, false)}
        ${renderPlate("玄学题材", "", MYSTIC_THEMES, false)}
      </div>
    `;

    elSheetBody.querySelectorAll("[data-lib-sector]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-lib-sector");
        if (!id) return;
        const hasToday = Boolean(d?.themes?.[id]?.zt_total || d?.themes?.[id]?.total);
        pushModal({ type: "theme", id, tab: hasToday ? "day" : "all" });
      });
    });
  }

  // ========================================================================
  // Modal View D: 卡异动 (10日100% / 30日200% Serious Deviation Monitor + Calc)
  // ========================================================================

  function deviationCardHtml(x) {
    if (!x) return "";
    if (x.supported === false) {
      return `
        <div class="dev-card">
          <div class="dev-top">
            <span class="dev-left">
              <span class="dev-name">${esc(x.name || x.code)}</span>
              ${boardBadgeHtml(x.code, false, x.name)}
            </span>
            <span class="dev-status is-safe">北交所</span>
          </div>
          <div class="dev-note">${esc(x.note || "北交所无10日100%/30日200%停牌红线")}</div>
        </div>
      `;
    }

    let statusHtml = "";
    if (x.trig10_today && x.trig30_today) {
      statusHtml = `<span class="dev-status is-trig">已触双线</span>`;
    } else if (x.trig10_today) {
      statusHtml = `<span class="dev-status is-trig">已触10日</span>`;
    } else if (x.trig30_today) {
      statusHtml = `<span class="dev-status is-trig">已触30日</span>`;
    } else if (x.status === "critical" && x.bind_safe_pct < x.limit_pct) {
      const sign = x.bind_safe_pct >= 0 ? "+" : "";
      statusHtml = `<span class="dev-status is-crit">明上限 ${sign}${x.bind_safe_pct}%</span>`;
    } else if (x.short_next_danger) {
      statusHtml = `<span class="dev-status is-crit">明板触${x.short_max}次</span>`;
    } else if (x.status === "warning") {
      statusHtml = `<span class="dev-status is-warn">安全 +${x.bind_safe_pct}%</span>`;
    } else {
      statusHtml = `<span class="dev-status is-safe">安全 +${x.bind_safe_pct}%</span>`;
    }

    const t10 = x.thresh10 || 100;
    const t30 = x.thresh30 || 200;
    const p10 = Math.max(0, Math.min(100, Math.round((Math.max(0, x.dev10) / t10) * 100)));
    const p30 = Math.max(0, Math.min(100, Math.round((Math.max(0, x.dev30) / t30) * 100)));
    const g10Cls = p10 >= 85 ? "is-hot" : p10 >= 65 ? "is-warm" : "";
    const g30Cls = p30 >= 85 ? "is-hot" : p30 >= 70 ? "is-warm" : "";

    const boardTxt =
      x.boards_desc && x.boards_desc !== "首板"
        ? x.boards_desc
        : x.height >= 2
          ? `${x.height}板`
          : "";

    const priceColHtml =
      x.trig10_today || x.trig30_today
        ? `
          <span class="dev-safe-px"><em>状态</em>次日重算</span>
          <span class="dev-cur-px">收 ${Number(x.close).toFixed(2)}</span>
        `
        : `
          <span class="dev-safe-px"><em>明卡线</em>${Number(x.bind_safe_px).toFixed(2)}</span>
          <span class="dev-cur-px">收 ${Number(x.close).toFixed(2)} · ${x.bind_rule === "30d" ? "30日限" : "10日限"}</span>
        `;

    const notes = [];
    if (x.short_max > 0 && x.short_cnt >= x.short_max - 1) {
      notes.push(`10日普通异动 ${x.short_cnt}/${x.short_max}次`);
    }
    if (x.last_trig10) notes.push(`${shortDate(x.last_trig10)}已触10日(重算中)`);
    if (x.last_trig30) notes.push(`${shortDate(x.last_trig30)}已触30日(重算中)`);

    const cardCls = x.status === "triggered" ? "is-triggered" : x.status === "critical" ? "is-critical" : "";
    return `
      <button class="dev-card ${cardCls}" type="button" data-dev-code="${esc(x.code)}">
        <div class="dev-top">
          <span class="dev-left">
            <span class="dev-name">${esc(x.name)}</span>
            ${boardBadgeHtml(x.code, false, x.name)}
            ${boardTxt ? `<span class="dev-board-tag">${esc(boardTxt)}</span>` : ""}
            ${x.theme ? `<span class="dev-theme-lbl">${esc(formatThemeLabel(x.theme))}</span>` : ""}
          </span>
          ${statusHtml}
        </div>
        <div class="dev-mid">
          <div class="dev-gauges">
            <div class="dev-gauge ${g10Cls}">
              <span class="dev-gauge-txt">10日<b>${x.dev10 >= 0 ? "+" : ""}${x.dev10}%</b></span>
              <span class="dev-bar-track"><span class="dev-bar-fill" style="width:${p10}%"></span></span>
            </div>
            <div class="dev-gauge ${g30Cls}">
              <span class="dev-gauge-txt">30日<b>${x.dev30 >= 0 ? "+" : ""}${x.dev30}%</b></span>
              <span class="dev-bar-track"><span class="dev-bar-fill" style="width:${p30}%"></span></span>
            </div>
          </div>
          <div class="dev-price-col">${priceColHtml}</div>
        </div>
        ${notes.length ? `<div class="dev-note">${esc(notes.join(" · "))}</div>` : ""}
      </button>
    `;
  }

  function renderDeviationModal(entry) {
    const d = state.day;
    const hasBack = state.modalStack.length > 1;
    const allDevs = Array.isArray(d?.deviations) ? d.deviations : [];
    const activeFilter = entry.filter || "all";
    entry.filter = activeFilter;

    elSheetHeader.innerHTML = `
      <div class="sheet-header-row">
        <div class="sheet-title-group">
          ${hasBack ? `<button class="sheet-back-btn" id="modal-back" type="button" aria-label="返回">‹</button>` : ""}
          <h3 class="sheet-title">异动监控</h3>
          <span class="dev-date-chip">${esc(shortDate(d?.date))}</span>
        </div>
        <button class="sheet-close-btn" id="modal-close" type="button" aria-label="关闭">×</button>
      </div>
      <div class="sheet-header-search">
        <input id="dev-calc-input" class="sector-filter-input" type="search"
               autocomplete="off" placeholder="单股速查：输入名称或代码测算异动空间…" />
      </div>
      <div class="dev-filter-tabs in-header" role="tablist">
        <button class="dev-filter-btn ${activeFilter === "all" ? "active" : ""}" type="button" data-dev-filter="all">全部预警</button>
        <button class="dev-filter-btn ${activeFilter === "10d" ? "active" : ""}" type="button" data-dev-filter="10d">10日100%</button>
        <button class="dev-filter-btn ${activeFilter === "30d" ? "active" : ""}" type="button" data-dev-filter="30d">30日200%</button>
      </div>
    `;
    bindModalHeaderButtons();

    elSheetBody.innerHTML = `
      <div class="modal-view">
        <div id="dev-calc-suggest" class="dev-calc-suggest"></div>
        <div id="dev-calc-result" class="dev-calc-result"></div>
        <div id="dev-list-box" class="dev-list"></div>
        <div class="dev-footnote">基准：沪(上证A指) · 深(深证A指) · 创(创业板综) · 科(科创50)，按次日指数平盘测算</div>
      </div>
    `;

    const listBox = $("dev-list-box");
    const calcInput = $("dev-calc-input");
    const sugBox = $("dev-calc-suggest");
    const resBox = $("dev-calc-result");

    const bindDevCards = (root, navList) => {
      root.querySelectorAll("[data-dev-code]").forEach((btn) => {
        const code = btn.getAttribute("data-dev-code");
        if (code && d?.date) {
          btn.addEventListener("touchstart", () => prefetchIntraday(code, d.date), { passive: true });
        }
        btn.addEventListener("click", () => {
          if (!code) return;
          pushModal({ type: "stock", id: code, intraday: true, navList });
        });
      });
    };

    const drawList = () => {
      let rows = allDevs;
      if (entry.filter === "10d") {
        rows = allDevs.filter(
          (x) =>
            x.trig10_today ||
            x.bind_rule === "10d" ||
            x.short_next_danger ||
            x.dev10 >= (x.thresh10 || 100) * 0.55
        );
      } else if (entry.filter === "30d") {
        rows = allDevs.filter(
          (x) =>
            x.trig30_today ||
            x.bind_rule === "30d" ||
            x.dev30 >= (x.thresh30 || 200) * 0.65
        );
      }

      if (!rows.length) {
        listBox.innerHTML = `<div class="empty-state compact">当日无临近压线标的</div>`;
        return;
      }

      const navList = rows.map((x) => ({ code: x.code, name: x.name }));
      listBox.innerHTML = rows.map(deviationCardHtml).join("");
      bindDevCards(listBox, navList);
    };

    elSheetHeader.querySelectorAll("[data-dev-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const f = btn.getAttribute("data-dev-filter") || "all";
        if (f === entry.filter) return;
        entry.filter = f;
        elSheetHeader.querySelectorAll("[data-dev-filter]").forEach((b) => {
          b.classList.toggle("active", b.getAttribute("data-dev-filter") === f);
        });
        elSheetBody.scrollTop = 0;
        drawList();
      });
    });

    const querySingleDeviation = async (code, name) => {
      sugBox.innerHTML = "";
      calcInput.value = name;
      calcInput.blur();
      const localHit = allDevs.find((x) => x.code === code);
      if (localHit) {
        resBox.innerHTML = `
          <div class="dev-calc-head"><span>单股测算结果</span><button class="text-action-btn" id="dev-calc-clear" type="button">收起</button></div>
          ${deviationCardHtml(localHit)}
        `;
        bindDevCards(resBox, [{ code: localHit.code, name: localHit.name }]);
        const clr = $("dev-calc-clear");
        if (clr) clr.addEventListener("click", () => { resBox.innerHTML = ""; calcInput.value = ""; });
        return;
      }
      if (!USE_LIVE_API) {
        resBox.innerHTML = `<div class="empty-state compact">${esc(name)} 未进入当日预警区（距异动红线较远）</div>`;
        return;
      }
      resBox.innerHTML = `<div class="empty-state compact">正在测算 ${esc(name)} 异动空间…</div>`;
      try {
        const resp = await fetch(
          `./api/deviation-stock?code=${encodeURIComponent(code)}&date=${encodeURIComponent(d.date)}&name=${encodeURIComponent(name)}`
        );
        if (currentModalEntry() !== entry) return;
        if (!resp.ok) {
          resBox.innerHTML = `<div class="empty-state compact">暂无 ${esc(name)} 当日行情数据</div>`;
          return;
        }
        const data = await resp.json();
        resBox.innerHTML = `
          <div class="dev-calc-head"><span>单股测算结果</span><button class="text-action-btn" id="dev-calc-clear" type="button">收起</button></div>
          ${deviationCardHtml(data)}
        `;
        bindDevCards(resBox, [{ code: data.code, name: data.name }]);
        const clr = $("dev-calc-clear");
        if (clr) clr.addEventListener("click", () => { resBox.innerHTML = ""; calcInput.value = ""; });
      } catch {
        resBox.innerHTML = `<div class="empty-state compact">测算失败，请稍后重试</div>`;
      }
    };

    const drawSuggestions = () => {
      const q = String(calcInput.value || "").trim().toLowerCase();
      if (!q) {
        sugBox.innerHTML = "";
        return;
      }
      elSheetBody.scrollTop = 0;
      const idx = state.searchIndex;
      if (!idx) {
        loadSearchIndex().then(() => {
          if (currentModalEntry() === entry) drawSuggestions();
        });
        return;
      }
      const hits = idx.stocks
        .filter((s) => s.code.includes(q) || s.nameLower.includes(q))
        .slice(0, 6);
      if (!hits.length) {
        sugBox.innerHTML = "";
        return;
      }
      sugBox.innerHTML = hits
        .map(
          (s) => `
          <button class="dev-sug-row" type="button" data-sug-code="${esc(s.code)}" data-sug-name="${esc(s.name)}">
            <span><b>${esc(s.name)}</b> ${boardBadgeHtml(s.code, false, s.name)}</span>
            <span class="sr-code">${esc(s.code)}</span>
          </button>
        `
        )
        .join("");
      sugBox.querySelectorAll("[data-sug-code]").forEach((btn) => {
        btn.addEventListener("click", () => {
          querySingleDeviation(btn.getAttribute("data-sug-code"), btn.getAttribute("data-sug-name"));
        });
      });
    };

    calcInput.addEventListener("input", drawSuggestions);
    calcInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const first = sugBox.querySelector("[data-sug-code]");
        if (first) {
          e.preventDefault();
          first.click();
        }
      }
    });

    if (!state.searchIndex) loadSearchIndex();
    drawList();
  }

  // ========================================================================
  // Modal View M: Pending M&A / Control-Change Events List (筹划并购)
  // ========================================================================

  function renderMaListModal(entry) {
    const hasBack = state.modalStack.length > 1;
    const initFilter = entry.filter || "";
    elSheetHeader.innerHTML = `
      <div class="sheet-header-row">
        <div class="sheet-title-group">
          ${hasBack ? `<button class="sheet-back-btn" id="modal-back" type="button" aria-label="返回">‹</button>` : ""}
          <h3 class="sheet-title">并购重组</h3>
        </div>
        <button class="sheet-close-btn" id="modal-close" type="button" aria-label="关闭">×</button>
      </div>
      <div class="sheet-header-search">
        <input id="ma-filter-input" class="sector-filter-input" type="search"
               autocomplete="off" placeholder="筛选股票、重组对象或赛道…"
               value="${esc(initFilter)}" />
      </div>
    `;
    bindModalHeaderButtons();

    const idx = state.searchIndex;
    if (!idx) {
      elSheetBody.innerHTML = `<div class="modal-view"><div class="empty-state">加载并购列表…</div></div>`;
      loadSearchIndex().then((loaded) => {
        if (loaded && currentModalEntry() === entry) renderMaListModal(entry);
      });
      return;
    }

    const d = state.day;
    const fbSet = getTodayFirstBoardSet(d);
    const list = idx.maEvents || [];
    let limit = 60;

    elSheetBody.innerHTML = `
      <div class="modal-view">
        <div id="ma-list-box" class="search-list"></div>
      </div>
    `;

    const inputEl = $("ma-filter-input");
    const box = $("ma-list-box");

    const draw = () => {
      const q = String(entry.filter || "").trim().toLowerCase();
      const filtered = q
        ? list.filter(
            (x) =>
              x.nameLower.includes(q) ||
              x.code.includes(q) ||
              x.targetLower.includes(q) ||
              (x.targetL1 && x.targetL1.toLowerCase().includes(q)) ||
              (x.type && x.type.toLowerCase().includes(q))
          )
        : list;

      if (!filtered.length) {
        box.innerHTML = `<div class="empty-state">无匹配并购记录</div>`;
        return;
      }

      const shown = filtered.slice(0, limit);
      const rowsHtml = shown
        .map((m) => {
          const todayCore = d?.stocks?.[m.code];
          const isTodayFb = fbSet.has(m.code);
          const statusBadge = stockArchiveStatusHtml(m, todayCore, isTodayFb);
          const l1Cls = m.targetL1 ? themeHeatCls(m.targetL1) : "";
          return `
            <button class="sr-card ma-list-card" type="button" data-ma-code="${esc(m.code)}">
              <div class="sr-stock-top">
                <span class="sr-main">
                  <span class="sr-name">${esc(m.name)}</span>
                  ${boardBadgeHtml(m.code, false, m.name)}
                  <span class="sr-code">${esc(m.code)}</span>
                </span>
                <span class="sr-right">
                  ${statusBadge}
                  ${m.fromDate ? `<span class="sr-meta">${esc(m.fromDate)}</span>` : ""}
                </span>
              </div>
              <div class="ma-list-meta">
                <span class="ma-type-chip">${esc(m.type)}</span>
                ${m.targetL1 ? `<span class="sr-tag ${l1Cls}">${esc(formatThemeLabel(m.targetL1))}</span>` : ""}
              </div>
              <div class="ma-list-target">${esc(m.target)}</div>
            </button>
          `;
        })
        .join("");

      const moreBtn =
        filtered.length > shown.length
          ? `<button class="load-more-btn" id="ma-load-more" type="button">展开更多</button>`
          : "";

      box.innerHTML = rowsHtml + moreBtn;

      box.querySelectorAll("[data-ma-code]").forEach((btn) => {
        btn.addEventListener("click", () => {
          pushModal({ type: "stock", id: btn.getAttribute("data-ma-code"), intraday: false });
        });
      });

      const more = $("ma-load-more");
      if (more) {
        more.addEventListener("click", () => {
          limit += 80;
          draw();
        });
      }
    };

    inputEl.addEventListener("input", () => {
      entry.filter = inputEl.value;
      limit = 60;
      draw();
    });

    draw();
  }

  // ========================================================================
  // Modal View A: Unified Sector / Theme Modal (当日梯队 + 全库标的)
  // ========================================================================

  function resolveThemeContext(entry) {
    const d = state.day;
    if (entry.type === "catalyst") {
      const cat = (d.catalysts || []).find((c) => c.id === entry.id);
      if (cat) {
        const th = cat.theme ? (d.themes || {})[cat.theme] : null;
        return {
          isEvent: cat.kind === "event",
          title: cat.title,
          themeName: cat.theme || cat.title,
          heatRank: cat.heat_rank || 99,
          codes: cat.codes || [],
          news: cat.news || [],
          ztTotal: th ? th.zt_total || th.total : cat.total || 0,
          firstBoards: th ? th.first_boards || [] : [],
          firstBoardTotal: th ? th.first_board_total || 0 : 0,
          trend: th ? th.trend || [] : [],
        };
      }
    }
    const th = (d.themes || {})[entry.id];
    if (th) {
      return {
        isEvent: false,
        title: th.name,
        themeName: th.name,
        heatRank: th.heat_rank || 99,
        codes: th.codes || [],
        news: th.news || [],
        ztTotal: th.zt_total || th.total || 0,
        firstBoards: th.first_boards || [],
        firstBoardTotal: th.first_board_total || 0,
        trend: th.trend || [],
      };
    }
    return {
      isEvent: false,
      title: entry.id,
      themeName: entry.id,
      heatRank: 99,
      codes: [],
      news: [],
      ztTotal: 0,
      firstBoards: [],
      firstBoardTotal: 0,
      trend: [],
    };
  }

  function renderThemeModal(entry) {
    const ctx = resolveThemeContext(entry);
    if (!ctx) return;

    const d = state.day;
    const hCls = heatCls(ctx.heatRank);
    const hasToday = ctx.codes.length > 0 || ctx.firstBoards.length > 0 || ctx.news.length > 0;
    const canShowAllTab = !ctx.isEvent;

    if (!entry.tab) {
      entry.tab = hasToday ? "day" : canShowAllTab ? "all" : "day";
    }
    if (!canShowAllTab) entry.tab = "day";

    const hasBack = state.modalStack.length > 1;
    const dbCount = state.searchIndex?.sectorCounts?.[ctx.themeName];

    elSheetHeader.innerHTML = `
      <div class="sheet-header-row">
        <div class="sheet-title-group">
          ${hasBack ? `<button class="sheet-back-btn" id="modal-back" type="button" aria-label="返回">‹</button>` : ""}
          <h3 class="sheet-title ${hCls}">${esc(formatThemeLabel(ctx.title))}</h3>
        </div>
        <button class="sheet-close-btn" id="modal-close" type="button" aria-label="关闭">×</button>
      </div>
      ${
        canShowAllTab
          ? `
            <div class="sheet-subtabs" role="tablist">
              <button class="subtab-btn ${entry.tab === "day" ? "active" : ""}" type="button" role="tab" aria-selected="${entry.tab === "day"}" data-theme-tab="day">
                当日 ${shortDate(d.date)}${ctx.ztTotal ? ` (${ctx.ztTotal})` : ""}
              </button>
              <button class="subtab-btn ${entry.tab === "all" ? "active" : ""}" type="button" role="tab" aria-selected="${entry.tab === "all"}" data-theme-tab="all">
                全库标的<span id="theme-all-cnt">${dbCount != null ? ` (${dbCount})` : ""}</span>
              </button>
            </div>
          `
          : ""
      }
    `;

    bindModalHeaderButtons();
    bindEvidenceToggles(elSheetBody);

    // Preload searchIndex quietly so the DB count badge populates if not yet loaded
    if (canShowAllTab && !state.searchIndex) {
      loadSearchIndex().then((idx) => {
        if (!idx || currentModalEntry() !== entry) return;
        const cntEl = $("theme-all-cnt");
        const c = idx.sectorCounts[ctx.themeName];
        if (cntEl && c != null) cntEl.textContent = ` (${c})`;
        if (entry.tab === "all") renderThemeAllStocks(entry, ctx);
      });
    }

    elSheetHeader.querySelectorAll("[data-theme-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const nextTab = btn.getAttribute("data-theme-tab");
        if (nextTab && nextTab !== entry.tab) {
          entry.tab = nextTab;
          elSheetHeader.querySelectorAll("[data-theme-tab]").forEach((b) => {
            const on = b.getAttribute("data-theme-tab") === nextTab;
            b.classList.toggle("active", on);
            b.setAttribute("aria-selected", String(on));
          });
          elSheetBody.scrollTop = 0;
          if (nextTab === "day") {
            renderThemeDayBody(entry, ctx);
          } else {
            renderThemeAllStocks(entry, ctx);
          }
        }
      });
    });

    if (entry.tab === "all" && canShowAllTab) {
      renderThemeAllStocks(entry, ctx);
    } else {
      renderThemeDayBody(entry, ctx);
    }
  }

  function renderThemeDayBody(entry, ctx) {
    const d = state.day;
    const hCls = heatCls(ctx.heatRank);
    const allStocks = ctx.codes.map((c) => d.stocks[c]).filter(Boolean);

    const byHeight = new Map();
    for (const st of allStocks) {
      if (!byHeight.has(st.height)) byHeight.set(st.height, []);
      byHeight.get(st.height).push(st);
    }
    const heights = Array.from(byHeight.keys()).sort((a, b) => b - a);

    const newsHtml = ctx.news.length
      ? `
        <div class="news-dispatch ${hCls}">
          ${ctx.news
            .map(
              (n) => `
              <div class="news-item">
                <div class="news-hl">${esc(n.headline)}</div>
                <div class="news-dt">${esc(n.detail)}</div>
              </div>
            `
            )
            .join("")}
        </div>
      `
      : "";

    const tiersDom = [];
    let cardIdx = 0;

    heights.forEach((h, idx) => {
      if (idx > 0) {
        const prevH = heights[idx - 1];
        if (prevH - h > 1) {
          const gapLabel = prevH - h === 2 ? `${prevH - 1}板断层` : `${h + 1}~${prevH - 1}板断层`;
          tiersDom.push(`
            <div class="c-gap-row">
              <span class="c-gap-pill">${gapLabel}</span>
            </div>
          `);
        }
      }

      const list = byHeight.get(h);

      const nodesHtml = list
        .map((st) => {
          const descText = st.boards_desc && st.boards_desc !== `${st.height}连板` ? st.boards_desc : "";
          const subText = [descText, st.province].filter(Boolean).join(" · ");
          const delay = Math.min(cardIdx * 24, 200);
          cardIdx++;

          return `
            <button class="c-node entering" style="animation-delay:${delay}ms" type="button" data-node-code="${esc(st.code)}">
              <div class="c-node-top">
                <span class="c-node-name-wrap">
                  <span class="c-node-name">${esc(st.name)}</span>
                  ${boardBadgeHtml(st.code, false, st.name)}
                  ${st.is_one_word ? `<span class="ow-tag">一字</span>` : ""}
                </span>
                <span class="c-node-time">${esc(st.first_time)}</span>
              </div>
              ${subText ? `<div class="c-node-sub">${esc(subText)}</div>` : ""}
            </button>
          `;
        })
        .join("");

      tiersDom.push(`
        <div class="c-tier">
          <div class="c-tier-head">
            <span class="h-tag">${h === 1 ? "反包" : `${h}板`}</span>
          </div>
          <div class="c-tier-grid">
            ${nodesHtml}
          </div>
        </div>
      `);
    });

    const fbList = ctx.firstBoards || [];
    const fbCardHtml = (fb) => `
      <button class="c-node c-fb-node" type="button" data-node-code="${esc(fb.code)}">
        <div class="c-node-top">
          <span class="c-node-name-wrap">
            <span class="c-node-name">${esc(fb.name)}</span>
            ${boardBadgeHtml(fb.code, false, fb.name)}
            ${fb.is_one_word ? `<span class="ow-tag">一字</span>` : ""}
          </span>
          <span class="c-node-time">${esc(fb.first_time)}</span>
        </div>
      </button>
    `;
    const initialFbCount = 24;
    const fbHtml = fbList.length
      ? `
        <div class="c-tier c-fb-tier">
          <div class="c-tier-head">
            <span class="h-tag">当日首板</span>
          </div>
          <div id="theme-fb-grid" class="c-tier-grid">
            ${fbList.slice(0, initialFbCount).map(fbCardHtml).join("")}
          </div>
          ${
            fbList.length > initialFbCount
              ? `<button class="load-more-btn" id="theme-fb-more" type="button">展开全部首板（${fbList.length}）</button>`
              : ""
          }
        </div>
      `
      : "";

    const hotRailSectors = !ctx.isEvent
      ? getHotSectors(d).filter((s) => s.kind === "theme")
      : [];
    const quickRailHtml =
      hotRailSectors.length >= 2
        ? `
          <div class="sector-quick-rail" role="tablist" aria-label="快速切换今日热门板块">
            ${hotRailSectors
              .map((s) => {
                const active = s.name === ctx.themeName;
                const sHeat = !active ? heatCls(s.heat_rank) : "";
                return `
                  <button class="sq-pill ${active ? "active" : ""} ${sHeat}" type="button"
                          data-quick-sector="${esc(s.name)}" data-quick-cat="${esc(s.catalyst_id || "")}"
                          aria-selected="${active}">
                    <span>${esc(formatThemeLabel(s.name))}</span>
                    ${s.zt_total ? `<em class="sq-cnt">${s.zt_total}</em>` : ""}
                  </button>
                `;
              })
              .join("")}
          </div>
        `
        : "";

    const emptyHtml =
      !tiersDom.length && !fbList.length
        ? `<div class="empty-state">当日无涨停标的${!ctx.isEvent ? `<br/><button class="inline-switch-btn" id="jump-all-tab" type="button">查看全库标的 ›</button>` : ""}</div>`
        : "";

    elSheetBody.innerHTML = `
      <div class="modal-view">
        ${quickRailHtml}
        ${newsHtml}
        <div class="converge-tiers">
          ${tiersDom.join("")}
          ${fbHtml}
          ${emptyHtml}
        </div>
      </div>
    `;

    const sectorNavList = [];
    const navSeen = new Set();
    for (const h of heights) {
      for (const st of byHeight.get(h) || []) {
        if (!navSeen.has(st.code)) {
          navSeen.add(st.code);
          sectorNavList.push({ code: st.code, name: st.name });
        }
      }
    }
    for (const fb of fbList) {
      if (fb.code && !navSeen.has(fb.code)) {
        navSeen.add(fb.code);
        sectorNavList.push({ code: fb.code, name: fb.name });
      }
    }

    const bindNodes = (root) => {
      root.querySelectorAll("[data-node-code]").forEach((btn) => {
        const code = btn.getAttribute("data-node-code");
        if (code && d?.date) {
          btn.addEventListener("touchstart", () => prefetchIntraday(code, d.date), { passive: true });
          btn.addEventListener("pointerenter", () => prefetchIntraday(code, d.date), { passive: true });
        }
        btn.addEventListener("click", () => {
          pushModal({ type: "stock", id: code, intraday: true, navList: sectorNavList });
        });
      });
    };
    bindNodes(elSheetBody);

    elSheetBody.querySelectorAll("[data-quick-sector]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const nextId = btn.getAttribute("data-quick-sector");
        if (!nextId || nextId === ctx.themeName) return;
        const catId = btn.getAttribute("data-quick-cat") || null;
        entry.type = "theme";
        entry.id = nextId;
        entry.catalystId = catId;
        entry.tab = "day";
        renderCurrentModal();
      });
    });
    const activeSq = elSheetBody.querySelector(".sq-pill.active");
    if (activeSq) {
      activeSq.scrollIntoView({ inline: "center", block: "nearest", behavior: "instant" });
    }

    const fbMoreBtn = $("theme-fb-more");
    if (fbMoreBtn) {
      fbMoreBtn.addEventListener("click", () => {
        const grid = $("theme-fb-grid");
        if (!grid) return;
        grid.innerHTML = fbList.map(fbCardHtml).join("");
        bindNodes(grid);
        fbMoreBtn.remove();
      });
    }

    const jumpAllBtn = $("jump-all-tab");
    if (jumpAllBtn) {
      jumpAllBtn.addEventListener("click", () => {
        const allTabBtn = elSheetHeader.querySelector('[data-theme-tab="all"]');
        if (allTabBtn) allTabBtn.click();
      });
    }
  }

  function threeMonthsAgoIso(refIso) {
    const base = refIso && refIso.length >= 10 ? refIso : state.dates[0]?.date || "2026-11-27";
    const [y, m, day] = base.split("-").map(Number);
    const dt = new Date(y, m - 1, day);
    dt.setDate(dt.getDate() - 92);
    const yy = dt.getFullYear();
    const mm = String(dt.getMonth() + 1).padStart(2, "0");
    const dd = String(dt.getDate()).padStart(2, "0");
    return `${yy}-${mm}-${dd}`;
  }

  function renderThemeAllStocks(entry, ctx) {
    const idx = state.searchIndex;
    if (!idx) {
      elSheetBody.innerHTML = `<div class="modal-view"><div class="empty-state">加载全库标的…</div></div>`;
      loadSearchIndex().then((loaded) => {
        if (loaded && currentModalEntry() === entry && entry.tab === "all") {
          renderThemeAllStocks(entry, ctx);
        }
      });
      return;
    }

    const d = state.day;
    const fbSet = getTodayFirstBoardSet(d);
    const cutoff3m = threeMonthsAgoIso(d?.date);
    const rawList = (idx.bySector.get(ctx.themeName) || []).slice();
    rawList.sort((a, b) => {
      const aCore = d?.stocks?.[a.code]?.height || 0;
      const bCore = d?.stocks?.[b.code]?.height || 0;
      if (bCore !== aCore) return bCore - aCore;
      const aFb = fbSet.has(a.code) ? 1 : 0;
      const bFb = fbSet.has(b.code) ? 1 : 0;
      if (bFb !== aFb) return bFb - aFb;
      const dtCmp = (b.lastDate || "").localeCompare(a.lastDate || "");
      if (dtCmp !== 0) return dtCmp;
      return b.maxHeight - a.maxHeight || b.luCount - a.luCount;
    });

    const active3mCount = rawList.filter((x) => x.lastDate && x.lastDate >= cutoff3m).length;
    if (entry.onlyActive == null) {
      entry.onlyActive = active3mCount >= 6 && rawList.length > active3mCount;
    }

    const initFilter = entry.filter || "";
    let limit = 60;

    elSheetBody.innerHTML = `
      <div class="modal-view">
        <div class="sector-filter-bar has-toggle">
          <input id="sector-filter-input" class="sector-filter-input" type="search"
                 autocomplete="off" placeholder="筛选股票名、代码或省份…"
                 value="${esc(initFilter)}" />
          ${
            active3mCount > 0 && active3mCount < rawList.length
              ? `<button id="sector-active-toggle" class="filter-toggle-btn ${entry.onlyActive ? "active" : ""}" type="button" aria-pressed="${entry.onlyActive}">近3月活跃</button>`
              : ""
          }
        </div>
        <div id="sector-all-list" class="search-list"></div>
      </div>
    `;

    const filterInput = $("sector-filter-input");
    const toggleBtn = $("sector-active-toggle");
    const listBox = $("sector-all-list");

    const draw = () => {
      const q = String(entry.filter || "").trim().toLowerCase();
      let pool = entry.onlyActive
        ? rawList.filter(
            (x) =>
              (x.lastDate && x.lastDate >= cutoff3m) ||
              Boolean(d?.stocks?.[x.code]) ||
              fbSet.has(x.code)
          )
        : rawList;
      const filtered = q
        ? pool.filter(
            (x) =>
              x.nameLower.includes(q) ||
              x.code.includes(q) ||
              (x.province && x.province.toLowerCase().includes(q))
          )
        : pool;

      if (!filtered.length) {
        listBox.innerHTML = `<div class="empty-state">无匹配标的</div>`;
        return;
      }

      const shown = filtered.slice(0, limit);
      const rowsHtml = shown
        .map((item) => {
          const todayCore = d?.stocks?.[item.code];
          const isTodayFb = fbSet.has(item.code);
          const badge = stockArchiveStatusHtml(item, todayCore, isTodayFb);
          const otherTags = item.tags
            .filter((t) => t !== ctx.themeName)
            .slice(0, 3)
            .map((t) => `<span class="sr-tag ${themeHeatCls(t)}">${esc(formatThemeLabel(t))}</span>`)
            .join("");
          const maBadge = item.isMa ? `<span class="sr-tag is-ma">拟并购</span>` : "";

          return `
            <button class="sr-card sr-stock-card" type="button" data-all-code="${esc(item.code)}">
              <div class="sr-stock-top">
                <span class="sr-main">
                  <span class="sr-name">${esc(item.name)}</span>
                  ${boardBadgeHtml(item.code, false, item.name)}
                  <span class="sr-code">${esc(item.code)}</span>
                  ${item.province ? `<span class="sr-prov">${esc(item.province)}</span>` : ""}
                </span>
                <span class="sr-right">${badge}</span>
              </div>
              ${maBadge || otherTags ? `<div class="sr-tags">${maBadge}${otherTags}</div>` : ""}
            </button>
          `;
        })
        .join("");

      const moreBtn =
        filtered.length > shown.length
          ? `<button class="load-more-btn" id="sector-load-more" type="button">展开更多（剩余 ${filtered.length - shown.length} 只）</button>`
          : "";

      listBox.innerHTML = rowsHtml + moreBtn;

      listBox.querySelectorAll("[data-all-code]").forEach((btn) => {
        btn.addEventListener("click", () => {
          pushModal({ type: "stock", id: btn.getAttribute("data-all-code"), intraday: false });
        });
      });

      const more = $("sector-load-more");
      if (more) {
        more.addEventListener("click", () => {
          limit += 80;
          draw();
        });
      }
    };

    filterInput.addEventListener("input", () => {
      entry.filter = filterInput.value;
      limit = 60;
      draw();
    });

    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        entry.onlyActive = !entry.onlyActive;
        toggleBtn.classList.toggle("active", entry.onlyActive);
        toggleBtn.setAttribute("aria-pressed", String(entry.onlyActive));
        limit = 60;
        draw();
      });
    }

    draw();
  }

  // ========================================================================
  // Modal View B: Stock Full-Profile (Today's Ladder + Full-DB Archive)
  // ========================================================================

  function historyBlockHtml(history) {
    if (!history || !history.length) return "";
    const curDate = state.day?.date || "";
    const rows = history
      .map((h) => {
        const canJump = state.dateSet.has(h.date);
        const isCurrent = h.date === curDate;
        const bLbl =
          h.boards_desc && h.boards_desc !== "首板"
            ? h.boards_desc
            : h.height >= 2
              ? `${h.height}连板`
              : "首板";
        const reasonTxt = h.reason ? String(h.reason) : "";
        const inner = `
          <span class="hist-left">
            ${isCurrent ? `<span class="hist-cur-dot" aria-label="当前"></span>` : ""}
            <span class="hist-date">${esc(topbarDateLabel(h.date))}</span>
            ${reasonTxt ? `<span class="hist-reason">${esc(reasonTxt)}</span>` : ""}
          </span>
          <span class="hist-right">
            <span class="hist-board ${h.height >= 3 ? "is-high" : ""}">${esc(bLbl)}</span>
            ${h.is_one_word ? `<span class="ow-tag">一字</span>` : ""}
            ${h.first_time ? `<span class="hist-time">${esc(h.first_time)}</span>` : ""}
            ${canJump && !isCurrent ? `<span class="hist-go">›</span>` : ""}
          </span>
        `;
        if (canJump && !isCurrent) {
          return `<button class="hist-row is-clickable" type="button" data-jump-date="${esc(h.date)}">${inner}</button>`;
        }
        return `<div class="hist-row ${isCurrent ? "is-current" : ""}">${inner}</div>`;
      })
      .join("");

    return `
      <div class="s-block">
        <h4 class="s-block-title"><span>近期涨停轨迹</span></h4>
        <div class="hist-list">${rows}</div>
      </div>
    `;
  }

  function bindHistoryDateClicks(container) {
    container.querySelectorAll("[data-jump-date]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const dt = btn.getAttribute("data-jump-date");
        if (dt) jumpToDate(dt);
      });
    });
  }

  function renderEvidenceItemHtml(ev, showDate = false) {
    const tCls = themeHeatCls(ev.theme);
    const txt = String(ev.text || "");
    const longText = txt.length > 52;
    return `
      <div class="ev-item ${longText ? "is-collapsible is-clamped" : ""}" ${longText ? 'role="button" tabindex="0" data-ev-toggle="1"' : ""}>
        <div class="ev-head">
          <span class="ev-tag ${tCls}">${esc(formatThemeLabel(ev.theme))}</span>
          ${showDate && ev.from_date ? `<span class="ev-pct">${esc(ev.from_date)}</span>` : ""}
          ${ev.pct != null ? `<span class="ev-pct">营收 ${ev.pct}%</span>` : ""}
          ${longText ? `<span class="ev-expand-hint">展开</span>` : ""}
        </div>
        <div class="ev-text">${esc(txt)}</div>
      </div>
    `;
  }

  function bindEvidenceToggles(root) {
    root.querySelectorAll("[data-ev-toggle]").forEach((card) => {
      card.addEventListener("click", () => {
        const clamped = card.classList.toggle("is-clamped");
        const hint = card.querySelector(".ev-expand-hint");
        if (hint) hint.textContent = clamped ? "展开" : "收起";
      });
    });
  }

  function renderStockModal(entry) {
    const d = state.day;
    const st = d.stocks[entry.id];
    if (!st) {
      renderArchiveStockModal(entry);
      return;
    }

    const hasBack = state.modalStack.length > 1;

    elSheetHeader.innerHTML = `
      <div class="sheet-header-row">
        <div class="sheet-title-group">
          ${hasBack ? `<button class="sheet-back-btn" id="modal-back" type="button" aria-label="返回">‹</button>` : ""}
          <h3 class="sheet-title">${esc(st.name)}</h3>
          ${boardBadgeHtml(st.code, true, st.name)}
          <span class="sheet-height-badge">${st.height}板</span>
          ${st.replenish ? `<span class="rep-mini-badge is-header" title="5板高标补涨">补</span>` : ""}
          ${st.is_one_word ? `<span class="ow-tag">一字</span>` : ""}
        </div>
        <button class="sheet-close-btn" id="modal-close" type="button" aria-label="关闭">×</button>
      </div>
      <div class="sheet-stats">
        <span>${esc(st.code)}</span>
      </div>
    `;

    const themePillsHtml = (st.themes || [])
      .map((t) => {
        const th = d.themes[t];
        const cnt = th ? th.zt_total || th.total : 0;
        const tCls = themeHeatCls(t);
        return `
          <button class="s-theme-pill ${tCls}" type="button" data-jump-theme="${esc(t)}">
            <span>${esc(formatThemeLabel(t))}</span>
            ${cnt ? `<span class="cnt">${cnt}</span>` : ""}
          </button>
        `;
      })
      .join("");

    const maHtml = (st.ma_events || []).length
      ? (st.ma_events || [])
          .map(
            (m) => `
            <div class="ma-card">
              <div class="ma-top">
                <span class="ma-badge">${esc(m.type)}${m.target_l1 ? ` · ${esc(m.target_l1)}` : ""}</span>
                <span class="ma-date">${esc(m.from_date)}</span>
              </div>
              <div class="ma-target">${esc(m.target)}</div>
            </div>
          `
          )
          .join("")
      : "";

    const realEvidences = (st.evidences || []).filter((ev) => !isBoilerplateEvidence(ev));
    const evsHtml = realEvidences.length
      ? realEvidences.map((ev) => renderEvidenceItemHtml(ev, false)).join("")
      : "";

    const driverHtml = st.driver
      ? `<div class="s-block">
           <h4 class="s-block-title"><span>今日驱动</span></h4>
           <div class="ev-item">
             <div class="ev-head">
               <span class="ev-tag ${themeHeatCls(st.driver)}">${esc(formatThemeLabel(st.driver))}</span>
             </div>
             ${st.driver_basis ? `<div class="ev-text">${esc(st.driver_basis)}</div>` : ""}
           </div>
         </div>`
      : "";

    const showIntraday = entry.intraday === true && Boolean(d?.date);
    const devStripHtml = showIntraday ? stockDevStripHtml(st.code) : "";
    const repHtml = showIntraday ? stockReplenishHtml(st) : "";

    elSheetBody.innerHTML = `
      <div class="modal-view">
        ${showIntraday ? `<div id="stock-intraday-slot"></div>` : ""}
        ${devStripHtml}
        ${repHtml}
        ${driverHtml}
        ${
          themePillsHtml
            ? `<div class="s-block">
                 <h4 class="s-block-title"><span>关联题材</span></h4>
                 <div class="s-tag-wrap">${themePillsHtml}</div>
               </div>`
            : ""
        }
        ${
          maHtml || evsHtml
            ? `<div class="s-block">
                 <h4 class="s-block-title"><span>核心档案</span></h4>
                 ${maHtml}
                 <div class="ev-list">${evsHtml}</div>
               </div>`
            : ""
        }
        <div id="stock-history-slot"></div>
      </div>
    `;

    bindModalHeaderButtons();
    bindEvidenceToggles(elSheetBody);

    if (showIntraday) {
      mountIntradayChart("stock-intraday-slot", st.code, d.date, entry);
      const devStripBtn = elSheetBody.querySelector("[data-open-deviation]");
      if (devStripBtn) {
        devStripBtn.addEventListener("click", () => pushModal({ type: "deviation", filter: "all" }));
      }
    }

    elSheetBody.querySelectorAll("[data-jump-theme]").forEach((el) => {
      el.addEventListener("click", () => {
        const t = el.getAttribute("data-jump-theme");
        if (t) {
          const hasToday = Boolean(d.themes?.[t]?.zt_total || d.themes?.[t]?.total);
          pushModal({ type: "theme", id: t, tab: hasToday ? "day" : "all" });
        }
      });
    });

    elSheetBody.querySelectorAll("[data-jump-stock]").forEach((el) => {
      el.addEventListener("click", () => {
        const targetCode = el.getAttribute("data-jump-stock");
        if (targetCode) {
          pushModal({ type: "stock", id: targetCode, intraday: Boolean(d.stocks?.[targetCode]) });
        }
      });
    });

    elSheetBody.querySelectorAll("[data-jump-date]").forEach((el) => {
      el.addEventListener("click", () => {
        const dt = el.getAttribute("data-jump-date");
        if (dt) jumpToDate(dt);
      });
    });

    // Lazily append recent limit-up history
    fetchStockProfile(st.code).then((prof) => {
      if (!prof?.history?.length || currentModalEntry() !== entry) return;
      const slot = $("stock-history-slot");
      if (!slot) return;
      slot.innerHTML = historyBlockHtml(prof.history);
      bindHistoryDateClicks(slot);
    });
  }

  function renderArchiveStockModal(entry) {
    const code = entry.id;
    const hasBack = state.modalStack.length > 1;
    const fbToday = getTodayFirstBoardMap(state.day).get(code);
    const brokenToday = (state.day?.broken_boards || []).find((b) => b.code === code);
    const recentBrokenItem = (state.day?.recent_broken || []).find((b) => b.code === code);
    const isTodayFb = Boolean(fbToday) || getTodayFirstBoardSet(state.day).has(code);
    const showIntraday = entry.intraday === true && Boolean(state.day?.date);

    elSheetHeader.innerHTML = `
      <div class="sheet-header-row">
        <div class="sheet-title-group">
          ${hasBack ? `<button class="sheet-back-btn" id="modal-back" type="button" aria-label="返回">‹</button>` : ""}
          <h3 class="sheet-title">${esc(fbToday?.name || brokenToday?.name || recentBrokenItem?.name || code)}</h3>
        </div>
        <button class="sheet-close-btn" id="modal-close" type="button" aria-label="关闭">×</button>
      </div>
    `;
    elSheetBody.innerHTML = `
      <div class="modal-view">
        ${showIntraday ? `<div id="stock-intraday-slot"></div>` : ""}
        <div class="empty-state">加载个股档案…</div>
      </div>
    `;
    bindModalHeaderButtons();
    if (showIntraday) {
      mountIntradayChart("stock-intraday-slot", code, state.day.date, entry);
    }

    fetchStockProfile(code).then((prof) => {
      if (currentModalEntry() !== entry || entry.id !== code) return;
      if (!prof) {
        elSheetBody.innerHTML = `
          <div class="modal-view">
            ${showIntraday ? `<div id="stock-intraday-slot"></div>` : ""}
            <div class="empty-state">未找到 ${esc(code)} 的档案</div>
          </div>
        `;
        if (showIntraday) mountIntradayChart("stock-intraday-slot", code, state.day.date, entry);
        return;
      }

      const d = state.day;
      const badgeHtml = isTodayFb
        ? `<span class="sheet-height-badge">今日首板</span>${fbToday?.is_one_word ? `<span class="ow-tag">一字</span>` : ""}`
        : brokenToday
          ? `<span class="sheet-height-badge">昨${brokenToday.prev_height}板断板</span>`
          : recentBrokenItem
            ? `<span class="sheet-height-badge">前${recentBrokenItem.days_ago}日${recentBrokenItem.prev_height}板断板</span>`
            : "";

      elSheetHeader.innerHTML = `
        <div class="sheet-header-row">
          <div class="sheet-title-group">
            ${hasBack ? `<button class="sheet-back-btn" id="modal-back" type="button" aria-label="返回">‹</button>` : ""}
            <h3 class="sheet-title">${esc(prof.name)}</h3>
            ${boardBadgeHtml(prof.code, true, prof.name)}
            ${badgeHtml}
          </div>
          <button class="sheet-close-btn" id="modal-close" type="button" aria-label="关闭">×</button>
        </div>
        <div class="sheet-stats">
          <span>${esc(prof.code)}</span>
        </div>
      `;
      bindModalHeaderButtons();

      const themePillsHtml = (prof.themes || [])
        .map((t) => {
          const th = d?.themes?.[t];
          const cnt = th ? th.zt_total || th.total : 0;
          const tCls = themeHeatCls(t);
          return `
            <button class="s-theme-pill ${tCls}" type="button" data-jump-theme="${esc(t)}">
              <span>${esc(formatThemeLabel(t))}</span>
              ${cnt ? `<span class="cnt">今日${cnt}</span>` : ""}
            </button>
          `;
        })
        .join("");

      const maHtml = (prof.ma_events || []).length
        ? prof.ma_events
            .map(
              (m) => `
              <div class="ma-card">
                <div class="ma-top">
                  <span class="ma-badge">${esc(m.type)}${m.target_l1 ? ` · ${esc(m.target_l1)}` : ""}</span>
                  <span class="ma-date">${esc(m.from_date)}</span>
                </div>
                <div class="ma-target">${esc(m.target)}</div>
              </div>
            `
            )
            .join("")
        : "";

      const realProfEvs = (prof.evidences || []).filter((ev) => !isBoilerplateEvidence(ev));
      const evsHtml = realProfEvs.length
        ? realProfEvs.map((ev) => renderEvidenceItemHtml(ev, true)).join("")
        : "";

      const devStripHtml = showIntraday ? stockDevStripHtml(code) : "";
      elSheetBody.innerHTML = `
        <div class="modal-view">
          ${showIntraday ? `<div id="stock-intraday-slot"></div>` : ""}
          ${devStripHtml}
          ${
            themePillsHtml
              ? `<div class="s-block">
                   <h4 class="s-block-title"><span>纯净题材</span></h4>
                   <div class="s-tag-wrap">${themePillsHtml}</div>
                 </div>`
              : `<div class="s-block"><div class="empty-state compact">暂无纯净题材标签（仅记录涨停轨迹）</div></div>`
          }
          ${
            maHtml || evsHtml
              ? `<div class="s-block">
                   <h4 class="s-block-title"><span>核心档案</span></h4>
                   ${maHtml}
                   <div class="ev-list">${evsHtml}</div>
                 </div>`
              : ""
          }
          ${historyBlockHtml(prof.history)}
        </div>
      `;

      if (showIntraday) {
        mountIntradayChart("stock-intraday-slot", code, d.date, entry);
        const devStripBtn = elSheetBody.querySelector("[data-open-deviation]");
        if (devStripBtn) {
          devStripBtn.addEventListener("click", () => pushModal({ type: "deviation", filter: "all" }));
        }
      }

      elSheetBody.querySelectorAll("[data-jump-theme]").forEach((el) => {
        el.addEventListener("click", () => {
          const t = el.getAttribute("data-jump-theme");
          if (t) {
            const hasToday = Boolean(d?.themes?.[t]?.zt_total || d?.themes?.[t]?.total);
            pushModal({ type: "theme", id: t, tab: hasToday ? "day" : "all" });
          }
        });
      });

      bindHistoryDateClicks(elSheetBody);
      bindEvidenceToggles(elSheetBody);
    });
  }

  function bindModalHeaderButtons() {
    const closeBtn = $("modal-close");
    if (closeBtn) closeBtn.addEventListener("click", () => closeAllSheets());
    const backBtn = $("modal-back");
    if (backBtn) backBtn.addEventListener("click", () => popModal());
  }

  // ========================================================================
  // Date Picker Sheet (Year + Month -> Trading Days with Leader & Main Theme)
  // ========================================================================

  const datePickerState = {
    year: "",
    month: "", // "YYYY-MM"
  };

  function buildDateCalendarIndex() {
    const years = [];
    const monthsByYear = new Map(); // "YYYY" -> ["YYYY-MM", ...] descending
    const daysByMonth = new Map(); // "YYYY-MM" -> [d, ...] descending
    for (const d of state.dates) {
      if (!d.date || d.date.length < 7) continue;
      const yr = d.date.slice(0, 4);
      const ym = d.date.slice(0, 7);
      if (!monthsByYear.has(yr)) {
        years.push(yr);
        monthsByYear.set(yr, []);
      }
      if (!daysByMonth.has(ym)) {
        monthsByYear.get(yr).push(ym);
        daysByMonth.set(ym, []);
      }
      daysByMonth.get(ym).push(d);
    }
    return { years, monthsByYear, daysByMonth };
  }

  function renderDateLeadersHtml(d) {
    const rawList = Array.isArray(d.top_leaders) ? d.top_leaders : [];
    const total = d.top_leader_count || rawList.length;
    if (!rawList.length) return "";

    const items = rawList.slice(0, 2).map((x) =>
      typeof x === "string"
        ? { code: "", name: x, theme: "" }
        : { code: x.code || "", name: x.name || "", theme: x.theme || "" }
    );

    if (items.length === 1 && total <= 1) {
      const it = items[0];
      return `
        <span class="date-leader-item">
          <span class="date-leader-name">${esc(it.name)}</span>
          ${boardBadgeHtml(it.code, false, it.name)}
          ${it.theme ? `<span class="date-leader-theme">${esc(formatThemeLabel(it.theme))}</span>` : ""}
        </span>
      `;
    }

    const extraTag = total > 2 ? `<span class="date-leader-more">等${total}</span>` : "";
    return `
      <span class="date-leader-stack">
        ${items
          .map(
            (it, idx) => `
            <span class="date-leader-item">
              <span class="date-leader-name">${esc(it.name)}</span>
              ${boardBadgeHtml(it.code, false, it.name)}
              ${it.theme ? `<span class="date-leader-theme">${esc(formatThemeLabel(it.theme))}</span>` : ""}
              ${idx === items.length - 1 ? extraTag : ""}
            </span>
          `
          )
          .join("")}
      </span>
    `;
  }

  function renderDateCycleBar(cal, current) {
    if (!elDateCycleWrap) return;
    const monthDays = cal.daysByMonth.get(datePickerState.month) || [];
    const anchorDate = monthDays[0]?.date || state.dates[0]?.date || "";
    const anchorIdx = state.dates.findIndex((x) => x.date === anchorDate);
    const sliceDesc = anchorIdx >= 0 ? state.dates.slice(anchorIdx, anchorIdx + 20) : state.dates.slice(0, 20);
    const items = sliceDesc.slice().reverse();
    if (items.length < 2) {
      elDateCycleWrap.innerHTML = "";
      return;
    }
    const maxH = Math.max(2, ...items.map((x) => x.max_height || 1));
    const peakItem = sliceDesc.reduce((best, x) => ((x.max_height || 0) > (best.max_height || 0) ? x : best), sliceDesc[0]);
    const peakLeader = peakItem?.top_leaders?.[0];
    const peakName = typeof peakLeader === "string" ? peakLeader : peakLeader?.name || "";

    const curDayInfo = state.dates.find((x) => x.date === current) || sliceDesc[0];
    const mood = (current === state.day?.date ? state.day?.mood : null) || curDayInfo?.mood || null;
    const fmtRate = (v) => (v !== null && v !== undefined ? `${Number(v).toFixed(0)}%` : "--");

    let moodStripHtml = "";
    if (mood) {
      const ztCnt = curDayInfo?.total ?? state.day?.summary?.total ?? 0;
      const zbCnt = mood.zb_count;
      const sealStr = mood.seal_rate !== null && mood.seal_rate !== undefined ? `封板${mood.seal_rate}%` : "";
      const p12Sub = mood.p12_base ? `${mood.p12_hit}/${mood.p12_base}` : "--";
      const mSub = mood.multi_base ? `${mood.multi_hit}/${mood.multi_base}` : "--";
      const nucCnt = mood.nuclear_count || 0;
      const brkCnt = mood.broken_count || 0;
      moodStripHtml = `
        <div class="cycle-mood-strip" aria-label="当日情绪与晋级率">
          <div class="cm-cell">
            <span class="cm-k">涨停/炸板</span>
            <span class="cm-v">${ztCnt}<em>/${zbCnt ?? "--"}</em></span>
            ${sealStr ? `<span class="cm-s">${sealStr}</span>` : ""}
          </div>
          <div class="cm-cell">
            <span class="cm-k">1进2</span>
            <span class="cm-v">${fmtRate(mood.p12_rate)}</span>
            <span class="cm-s">${p12Sub}</span>
          </div>
          <div class="cm-cell">
            <span class="cm-k">连板晋级</span>
            <span class="cm-v">${fmtRate(mood.multi_rate)}</span>
            <span class="cm-s">${mSub}</span>
          </div>
          <div class="cm-cell ${nucCnt > 0 ? "is-nuc-warn" : ""}">
            <span class="cm-k">高标断板</span>
            <span class="cm-v">${brkCnt}只</span>
            <span class="cm-s">${nucCnt > 0 ? `核按钮 ${nucCnt}` : "无核杀"}</span>
          </div>
        </div>
      `;
    }

    elDateCycleWrap.innerHTML = `
      <div class="cycle-head">
        <span class="cycle-title">近${items.length}日情绪周期</span>
        <span class="cycle-peak">峰值 <b>${peakItem.max_height}板</b>${peakName ? ` · ${esc(peakName)}` : ""}</span>
      </div>
      <div class="cycle-bars">
        ${items
          .map((d) => {
            const h = d.max_height || 1;
            const pct = Math.max(14, Math.round((h / maxH) * 100));
            const isCur = d.date === current;
            const isPeak = h === maxH;
            const hasNuc = Boolean(d.mood && d.mood.nuclear_count > 0);
            return `
              <button class="cycle-col ${isCur ? "is-cur" : ""} ${isPeak ? "is-peak" : ""} ${hasNuc ? "has-nuc" : ""}"
                      type="button" data-cycle-date="${esc(d.date)}"
                      title="${esc(d.date)} ${h}板${hasNuc ? ` · 核按钮${d.mood.nuclear_count}` : ""}">
                <span class="cycle-num">${h}</span>
                <span class="cycle-track"><span class="cycle-fill" style="height:${pct}%"></span></span>
              </button>
            `;
          })
          .join("")}
      </div>
      <div class="cycle-foot">
        <span>${esc(shortDate(items[0].date))}</span>
        <span>${esc(shortDate(items[items.length - 1].date))}</span>
      </div>
      ${moodStripHtml}
    `;

    elDateCycleWrap.querySelectorAll("[data-cycle-date]").forEach((btn) => {
      const dt = btn.getAttribute("data-cycle-date");
      btn.addEventListener("pointerenter", () => prefetchDay(dt), { passive: true });
      btn.addEventListener("click", () => {
        closeDateSheet();
        if (dt && dt !== current) {
          const from = currentDateIndex();
          const to = state.dates.findIndex((x) => x.date === dt);
          loadDay(dt, from < 0 || to < 0 ? null : to > from ? "older" : "newer");
        }
      });
    });
  }

  function renderDatePickerView(cal) {
    const current = state.day?.date || "";
    const curMonth = current.slice(0, 7);

    // Year tabs
    if (cal.years.length > 1) {
      elDateYearTabs.innerHTML = cal.years
        .map(
          (yr) => `
          <button class="date-yr-btn ${yr === datePickerState.year ? "active" : ""}"
                  type="button" role="tab" aria-selected="${yr === datePickerState.year}"
                  data-pick-year="${esc(yr)}">${esc(yr)}</button>
        `
        )
        .join("");
      elDateYearTabs.classList.remove("hidden");
    } else {
      elDateYearTabs.innerHTML = cal.years[0] ? `<span class="date-yr-single">${esc(cal.years[0])}年</span>` : "";
      elDateYearTabs.classList.remove("hidden");
    }

    // Month grid for selected year
    const months = cal.monthsByYear.get(datePickerState.year) || [];
    if (!months.includes(datePickerState.month)) {
      datePickerState.month = months.includes(curMonth) ? curMonth : months[0] || "";
    }

    elDateMonthGrid.innerHTML = months
      .map((ym) => {
        const mNum = parseInt(ym.slice(5, 7), 10);
        const isActive = ym === datePickerState.month;
        const hasCurrent = ym === curMonth && !isActive;
        return `
          <button class="date-mo-btn ${isActive ? "active" : ""} ${hasCurrent ? "has-cur" : ""}"
                  type="button" role="tab" aria-selected="${isActive}"
                  data-pick-month="${esc(ym)}">${mNum}月</button>
        `;
      })
      .join("");

    // Day list for selected month + 20-day height cycle strip
    renderDateCycleBar(cal, current);
    const monthDays = cal.daysByMonth.get(datePickerState.month) || [];
    elDateList.innerHTML = monthDays
      .map((d) => {
        const leadersHtml = renderDateLeadersHtml(d);
        const hCls = d.max_height >= 6 ? "is-high" : "";
        const wk = weekdayLabel(d.date);
        return `
          <button class="date-row ${d.date === current ? "active" : ""}" type="button" data-pick-date="${esc(d.date)}">
            <span class="date-row-left">
              <span class="date-md">${esc(shortDate(d.date))}</span>
              ${wk ? `<span class="date-wk">${esc(wk)}</span>` : ""}
            </span>
            <span class="date-row-right">
              ${leadersHtml}
              <span class="date-height-badge ${hCls}">${d.max_height}板</span>
            </span>
          </button>
        `;
      })
      .join("");

    elDateYearTabs.querySelectorAll("[data-pick-year]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const yr = btn.getAttribute("data-pick-year");
        if (yr && yr !== datePickerState.year) {
          datePickerState.year = yr;
          const ms = cal.monthsByYear.get(yr) || [];
          datePickerState.month = ms.includes(curMonth) ? curMonth : ms[0] || "";
          elDateList.scrollTop = 0;
          renderDatePickerView(cal);
        }
      });
    });

    elDateMonthGrid.querySelectorAll("[data-pick-month]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const ym = btn.getAttribute("data-pick-month");
        if (ym && ym !== datePickerState.month) {
          datePickerState.month = ym;
          elDateList.scrollTop = 0;
          renderDatePickerView(cal);
        }
      });
    });

    elDateList.querySelectorAll("[data-pick-date]").forEach((btn) => {
      const dt = btn.getAttribute("data-pick-date");
      btn.addEventListener("pointerenter", () => prefetchDay(dt), { passive: true });
      btn.addEventListener("click", () => {
        closeDateSheet();
        if (dt && dt !== current) {
          const from = currentDateIndex();
          const to = state.dates.findIndex((x) => x.date === dt);
          loadDay(dt, from < 0 || to < 0 ? null : to > from ? "older" : "newer");
        }
      });
    });

    // Quietly prefetch top 3 days of the visible month in background
    monthDays.slice(0, 3).forEach((d) => prefetchDay(d.date));
  }

  function openDateSheet() {
    const cal = buildDateCalendarIndex();
    const current = state.day?.date || state.dates[0]?.date || "";
    datePickerState.year = current.slice(0, 4) || cal.years[0] || "";
    datePickerState.month = current.slice(0, 7) || "";
    renderDatePickerView(cal);

    elDateList.scrollTop = 0;
    const activeRow = elDateList.querySelector(".date-row.active");
    if (activeRow) {
      elDateList.scrollTop = Math.max(
        0,
        activeRow.offsetTop - elDateList.offsetTop - elDateList.clientHeight / 2 + activeRow.offsetHeight / 2
      );
    }

    elDateBackdrop.classList.add("open");
    elDateSheet.classList.add("open");
    elDateSheet.setAttribute("aria-hidden", "false");
  }

  function closeDateSheet() {
    elDateBackdrop.classList.remove("open");
    elDateSheet.classList.remove("open");
    elDateSheet.setAttribute("aria-hidden", "true");
  }

  // ========================================================================
  // Global Events & Touch Swipe-Down Dismiss
  // ========================================================================

  function bindEvents() {
    if (elDateLatest) {
      elDateLatest.addEventListener("pointerenter", () => prefetchDay(state.dates[0]?.date), { passive: true });
      elDateLatest.addEventListener("click", () => {
        if (state.dates.length) jumpToDate(state.dates[0].date);
      });
    }

    const prefetchStep = (delta) => {
      const idx = currentDateIndex();
      const target = state.dates[idx + delta]?.date;
      if (target) prefetchDay(target);
    };

    elDatePrev.addEventListener("pointerenter", () => prefetchStep(1), { passive: true });
    elDatePrev.addEventListener("click", () => {
      const idx = currentDateIndex();
      if (idx >= 0 && idx < state.dates.length - 1) {
        loadDay(state.dates[idx + 1].date, "older");
      }
    });

    elDateNext.addEventListener("pointerenter", () => prefetchStep(-1), { passive: true });
    elDateNext.addEventListener("click", () => {
      const idx = currentDateIndex();
      if (idx > 0) {
        loadDay(state.dates[idx - 1].date, "newer");
      }
    });

    // Mobile horizontal swipe on ladder to flip trading days smoothly
    let swipeX0 = 0;
    let swipeY0 = 0;
    let swipeT0 = 0;
    elLadderScroll.addEventListener(
      "touchstart",
      (e) => {
        if (e.touches.length !== 1) return;
        swipeX0 = e.touches[0].clientX;
        swipeY0 = e.touches[0].clientY;
        swipeT0 = performance.now();
      },
      { passive: true }
    );
    elLadderScroll.addEventListener(
      "touchend",
      (e) => {
        if (!swipeT0 || elSheet.classList.contains("open") || elDateSheet.classList.contains("open")) return;
        const t = e.changedTouches[0];
        if (!t) return;
        const dx = t.clientX - swipeX0;
        const dy = t.clientY - swipeY0;
        const dt = performance.now() - swipeT0;
        swipeT0 = 0;
        if (dt < 450 && Math.abs(dx) > 58 && Math.abs(dx) > Math.abs(dy) * 1.8) {
          const idx = currentDateIndex();
          if (dx > 0 && idx >= 0 && idx < state.dates.length - 1) {
            loadDay(state.dates[idx + 1].date, "older");
          } else if (dx < 0 && idx > 0) {
            loadDay(state.dates[idx - 1].date, "newer");
          }
        }
      },
      { passive: true }
    );

    // Topbar Brand Medallion -> Framed Fresco & Daily Market Overview Sheet
    if (elBrandAvatar) {
      const openBrand = () => openModal({ type: "brand" });
      elBrandAvatar.addEventListener("click", openBrand);
      elBrandAvatar.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          openBrand();
        }
      });
    }

    // Topbar Search Button -> Tier-2 Search Sheet
    elSearchBtn.addEventListener("click", () => {
      openModal({ type: "search", query: "" });
    });

    // Compact Hot-Sectors / Catalysts Pulse Bar -> Full-Row Tap Opens Hub Sheet
    elHubBar.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-open-hub]");
      if (!btn) return;
      const tab = btn.getAttribute("data-open-hub") || "sectors";
      openModal({ type: "hub", tab });
    });

    // Home Core Tools Strip (题材库 | 卡异动 | 并购重组)
    if (elHomeTools) {
      elHomeTools.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-open-tool]");
        if (!btn) return;
        const tool = btn.getAttribute("data-open-tool");
        if (tool === "sectors-lib") {
          openModal({ type: "sectors-lib" });
        } else if (tool === "deviation") {
          openModal({ type: "deviation", filter: "all" });
        } else if (tool === "ma-list") {
          openModal({ type: "ma-list", filter: "" });
        }
      });
    }

    // Main Ladder Volume/Turnover PK Mode Toggle
    if (elLadderModeBtn) {
      elLadderModeBtn.addEventListener("click", () => {
        state.ladderMetrics = !state.ladderMetrics;
        elLadderModeBtn.classList.toggle("active", state.ladderMetrics);
        elLadderModeBtn.setAttribute("aria-pressed", String(state.ladderMetrics));
        renderLadder();
      });
    }

    // Main Ladder Focus Theme Pills (1-tap highlight same-theme cards across all tiers)
    if (elLadderFocusBar) {
      elLadderFocusBar.addEventListener("click", (e) => {
        const pill = e.target.closest("[data-focus-theme]");
        if (!pill) return;
        toggleFocusTheme(pill.getAttribute("data-focus-theme"));
      });
    }

    // Pre-fetch intraday chart immediately on touchstart / hover for instant tap response
    const warmCellIntraday = (e) => {
      const cell = e.target.closest("[data-code]");
      if (!cell || !state.day?.date) return;
      prefetchIntraday(cell.getAttribute("data-code"), state.day.date);
    };
    elLadderList.addEventListener("touchstart", warmCellIntraday, { passive: true });
    elLadderList.addEventListener("mouseover", warmCellIntraday, { passive: true });

    // Tier-1 Ladder Stock Card: toggle recent broken / focus theme / open Intraday Stock Modal
    elLadderList.addEventListener("click", (e) => {
      const rbToggle = e.target.closest("[data-toggle-recent-broken]");
      if (rbToggle) {
        state.recentBrokenOpen = !state.recentBrokenOpen;
        renderLadder();
        return;
      }
      const themeEl = e.target.closest("[data-cell-theme]");
      if (themeEl) {
        e.stopPropagation();
        toggleFocusTheme(themeEl.getAttribute("data-cell-theme"));
        return;
      }
      const cell = e.target.closest("[data-code]");
      if (!cell) return;
      openModal({
        type: "stock",
        id: cell.getAttribute("data-code"),
        intraday: true,
        navList: getDayLadderOrder(state.day),
      });
    });

    // Mobile single-hand gestures inside Bottom Sheet:
    // 1) iOS-native left-edge swipe right -> popModal() / close sheet
    // 2) Horizontal swipe inside Hub modal -> toggle 热门板块 ⇄ 今日催化
    let sheetSwipeX0 = 0;
    let sheetSwipeY0 = 0;
    let sheetSwipeT0 = 0;
    let sheetSwipeIgnore = false;
    elSheetBody.addEventListener(
      "touchstart",
      (e) => {
        if (e.touches.length !== 1 || !elSheet.classList.contains("open")) return;
        sheetSwipeIgnore = Boolean(e.target.closest(".sector-quick-rail, .modal-filter-rail"));
        sheetSwipeX0 = e.touches[0].clientX;
        sheetSwipeY0 = e.touches[0].clientY;
        sheetSwipeT0 = performance.now();
      },
      { passive: true }
    );
    elSheetBody.addEventListener(
      "touchend",
      (e) => {
        if (!sheetSwipeT0 || sheetSwipeIgnore || !elSheet.classList.contains("open")) {
          sheetSwipeT0 = 0;
          return;
        }
        const t = e.changedTouches[0];
        if (!t) return;
        const dx = t.clientX - sheetSwipeX0;
        const dy = t.clientY - sheetSwipeY0;
        const dt = performance.now() - sheetSwipeT0;
        sheetSwipeT0 = 0;
        if (dt > 480 || Math.abs(dx) < 58 || Math.abs(dx) < Math.abs(dy) * 1.8) return;

        const rect = elSheet.getBoundingClientRect();
        const relStartX = sheetSwipeX0 - rect.left;
        if (relStartX < 46 && dx > 60) {
          popModal();
          return;
        }
        const entry = currentModalEntry();
        if (entry && entry.type === "hub") {
          const order = ["sectors", "catalysts", "first"];
          const curIdx = Math.max(0, order.indexOf(entry.tab));
          const nextIdx = dx < 0 ? Math.min(order.length - 1, curIdx + 1) : Math.max(0, curIdx - 1);
          const targetTab = order[nextIdx];
          if (targetTab !== entry.tab) {
            const tabBtn = elSheetHeader.querySelector(`[data-hub-tab="${targetTab}"]`);
            if (tabBtn) tabBtn.click();
          }
        }
      },
      { passive: true }
    );

    elDateBtn.addEventListener("click", openDateSheet);
    elDateClose.addEventListener("click", closeDateSheet);
    elDateBackdrop.addEventListener("click", closeDateSheet);

    elBackdrop.addEventListener("click", () => closeAllSheets());
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (elSheet.classList.contains("open") || elDateSheet.classList.contains("open")) {
          closeAllSheets();
        } else if (state.focusTheme) {
          toggleFocusTheme("");
        }
        return;
      }
      const inField = e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
      if (!inField && (e.key === "/" || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k"))) {
        e.preventDefault();
        openModal({ type: "search", query: "" });
        return;
      }
      const anySheetOpen = elSheet.classList.contains("open") || elDateSheet.classList.contains("open");
      if (!inField && !anySheetOpen) {
        if (e.key === "ArrowLeft") {
          const idx = currentDateIndex();
          if (idx >= 0 && idx < state.dates.length - 1) {
            e.preventDefault();
            loadDay(state.dates[idx + 1].date, "older");
          }
        } else if (e.key === "ArrowRight") {
          const idx = currentDateIndex();
          if (idx > 0) {
            e.preventDefault();
            loadDay(state.dates[idx - 1].date, "newer");
          }
        }
      }
    });

    // 120fps rAF-batched Swipe-Down Drag Gesture (Header/Handle + Body when scrollTop <= 0)
    let dragStartX = 0;
    let dragStartY = 0;
    let dragStartT = 0;
    let dragSheetH = 520;
    let currentDy = 0;
    let dragging = false;
    let dragFromBody = false;
    let dragRaf = 0;

    const applySheetDragFrame = () => {
      dragRaf = 0;
      if (!dragging) return;
      elSheet.style.transform = `translate3d(0, ${currentDy}px, 0)`;
      const p = Math.min(1, Math.max(0, currentDy) / dragSheetH);
      elBackdrop.style.opacity = String(1 - p);
      elShell.style.transform = `scale(${(0.955 + 0.045 * p).toFixed(4)}) translate3d(0, ${(6 * (1 - p)).toFixed(2)}px, 0)`;
    };

    const beginSheetDrag = (x, y, fromBody) => {
      dragging = true;
      dragFromBody = fromBody;
      dragStartX = x;
      dragStartY = y;
      dragStartT = performance.now();
      dragSheetH = Math.max(1, elSheet.offsetHeight);
      currentDy = 0;
      elSheet.classList.add("dragging");
      elShell.classList.add("dragging");
      elBackdrop.classList.add("dragging");
    };

    const onTouchStart = (e) => {
      if (!elSheet.classList.contains("open") || e.touches.length !== 1) return;
      if (e.target.closest("button, input, label")) return;
      beginSheetDrag(e.touches[0].clientX, e.touches[0].clientY, false);
    };

    const onTouchMove = (e) => {
      if (!dragging) return;
      const dy = e.touches[0].clientY - dragStartY;
      currentDy = dy < 0 ? dy * 0.16 : dy;
      if (!dragRaf) dragRaf = requestAnimationFrame(applySheetDragFrame);
    };

    const onTouchEnd = () => {
      if (!dragging) return;
      dragging = false;
      dragFromBody = false;
      cancelAnimationFrame(dragRaf);
      dragRaf = 0;
      const dt = Math.max(1, performance.now() - dragStartT);
      const velocity = currentDy / dt;
      elSheet.classList.remove("dragging");
      elShell.classList.remove("dragging");
      elBackdrop.classList.remove("dragging");
      elShell.style.transform = "";
      elBackdrop.style.opacity = "";
      if (currentDy > 95 || velocity > 0.45) {
        closeAllSheets();
      } else {
        elSheet.style.transform = "";
      }
    };

    [elSheetDrag, elSheetHeader].forEach((zone) => {
      zone.addEventListener("touchstart", onTouchStart, { passive: true });
      zone.addEventListener("touchmove", onTouchMove, { passive: true });
      zone.addEventListener("touchend", onTouchEnd, { passive: true });
      zone.addEventListener("touchcancel", onTouchEnd, { passive: true });
    });

    // Seamless Pull-to-Dismiss from Sheet Body when scrolled to top (one-hand mobile ergonomics)
    let bodyArm = false;
    let bodyX0 = 0;
    let bodyY0 = 0;
    elSheetBody.addEventListener(
      "touchstart",
      (e) => {
        if (!elSheet.classList.contains("open") || e.touches.length !== 1) return;
        if (elSheetBody.scrollTop <= 1 && !e.target.closest("input, textarea")) {
          bodyArm = true;
          bodyX0 = e.touches[0].clientX;
          bodyY0 = e.touches[0].clientY;
        } else {
          bodyArm = false;
        }
      },
      { passive: true }
    );
    elSheetBody.addEventListener(
      "touchmove",
      (e) => {
        if (dragging && dragFromBody) {
          const dy = e.touches[0].clientY - dragStartY;
          if (dy <= 0) {
            currentDy = 0;
          } else {
            e.preventDefault();
            currentDy = dy;
          }
          if (!dragRaf) dragRaf = requestAnimationFrame(applySheetDragFrame);
          return;
        }
        if (!bodyArm) return;
        const dx = e.touches[0].clientX - bodyX0;
        const dy = e.touches[0].clientY - bodyY0;
        if (Math.abs(dx) > 10 || dy < -4) {
          bodyArm = false;
          return;
        }
        if (dy > 10 && Math.abs(dy) > Math.abs(dx) * 1.4 && elSheetBody.scrollTop <= 1) {
          bodyArm = false;
          e.preventDefault();
          beginSheetDrag(e.touches[0].clientX, e.touches[0].clientY, true);
        }
      },
      { passive: false }
    );
    elSheetBody.addEventListener(
      "touchend",
      () => {
        bodyArm = false;
        if (dragging && dragFromBody) onTouchEnd();
      },
      { passive: true }
    );
    elSheetBody.addEventListener(
      "touchcancel",
      () => {
        bodyArm = false;
        if (dragging && dragFromBody) onTouchEnd();
      },
      { passive: true }
    );

    // Date Picker Sheet Native Swipe-Down Dismiss (Handle/Head + List at top)
    let dDragY0 = 0;
    let dDragT0 = 0;
    let dDragH = 420;
    let dDragDy = 0;
    let dDragging = false;
    let dDragRaf = 0;

    const applyDateDragFrame = () => {
      dDragRaf = 0;
      if (!dDragging) return;
      elDateSheet.style.transform = `translate3d(0, ${dDragDy}px, 0)`;
      const p = Math.min(1, Math.max(0, dDragDy) / dDragH);
      elDateBackdrop.style.opacity = String(1 - p);
    };

    const endDateDrag = () => {
      if (!dDragging) return;
      dDragging = false;
      cancelAnimationFrame(dDragRaf);
      dDragRaf = 0;
      const dt = Math.max(1, performance.now() - dDragT0);
      const vel = dDragDy / dt;
      elDateSheet.classList.remove("dragging");
      elDateBackdrop.classList.remove("dragging");
      elDateBackdrop.style.opacity = "";
      if (dDragDy > 82 || vel > 0.42) {
        elDateSheet.style.transform = "";
        closeDateSheet();
      } else {
        elDateSheet.style.transform = "";
      }
    };

    const dateTopZones = elDateSheet.querySelectorAll(".sheet-drag-zone, .date-sheet-head");
    dateTopZones.forEach((zone) => {
      zone.addEventListener(
        "touchstart",
        (e) => {
          if (!elDateSheet.classList.contains("open") || e.touches.length !== 1) return;
          if (e.target.closest("button")) return;
          dDragging = true;
          dDragY0 = e.touches[0].clientY;
          dDragT0 = performance.now();
          dDragH = Math.max(1, elDateSheet.offsetHeight);
          dDragDy = 0;
          elDateSheet.classList.add("dragging");
          elDateBackdrop.classList.add("dragging");
        },
        { passive: true }
      );
      zone.addEventListener(
        "touchmove",
        (e) => {
          if (!dDragging) return;
          const dy = e.touches[0].clientY - dDragY0;
          dDragDy = dy < 0 ? dy * 0.14 : dy;
          if (!dDragRaf) dDragRaf = requestAnimationFrame(applyDateDragFrame);
        },
        { passive: true }
      );
      zone.addEventListener("touchend", endDateDrag, { passive: true });
      zone.addEventListener("touchcancel", endDateDrag, { passive: true });
    });
  }

  init();
})();
