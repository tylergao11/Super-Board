/* ==========================================================================
   SUPER-BOARD · Editorial Paper UI · Vertical Catalysts · Pure Convergence
   ========================================================================== */

(() => {
  const state = {
    dates: [], // descending: index 0 = newest trading day
    day: null,
    fbExpanded: false,
    modalStack: [], // { type: 'catalyst'|'theme'|'stock', id }
  };

  const $ = (id) => document.getElementById(id);
  const elShell = $("app-shell");
  const elDatePrev = $("date-prev");
  const elDateNext = $("date-next");
  const elDateBtn = $("date-btn");
  const elDateLabel = $("date-label");
  const elCatCount = $("catalyst-count");
  const elCatList = $("catalyst-list");
  const elCatFade = $("catalyst-fade");
  const elMarketMood = $("market-mood");
  const elLadderScroll = $("ladder-scroll");
  const elLadderList = $("ladder-list");
  const elFbWrap = $("first-board-wrap");
  const elFbToggle = $("first-board-toggle");
  const elFbCount = $("fb-count");
  const elFbGrid = $("first-board-grid");

  const elBackdrop = $("sheet-backdrop");
  const elSheet = $("sheet-container");
  const elSheetDrag = $("sheet-drag-zone");
  const elSheetHeader = $("sheet-header");
  const elSheetBody = $("sheet-body");

  const elDateBackdrop = $("date-backdrop");
  const elDateSheet = $("date-sheet");
  const elDateClose = $("date-close");
  const elDateList = $("date-list");

  const esc = (s) =>
    String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const shortDate = (iso) => (iso && iso.length >= 10 ? iso.slice(5).replace("-", ".") : iso || "--.--");

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

  function withTransition(kind, update) {
    if (!canVT) {
      update();
      return Promise.resolve(false);
    }
    const root = document.documentElement;
    const token = ++vtToken;
    root.dataset.vt = kind;
    // Guarantee the DOM update runs exactly once, even if the transition is skipped or aborted
    let ran = false;
    const run = () => {
      if (ran) return;
      ran = true;
      update();
    };
    let vt;
    try {
      vt = document.startViewTransition(run);
    } catch {
      delete root.dataset.vt;
      run();
      return Promise.resolve(false);
    }
    vt.updateCallbackDone.catch(run);
    return vt.finished
      .catch(() => {})
      .then(() => {
        run();
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
    Array.from(elCatList.children).forEach((el, i) => stamp(el, i));
    Array.from(elLadderList.children).forEach((el, i) => stamp(el, i + 2));
  }

  // Detect local Python API server vs static GitHub Pages hosting
  const USE_LIVE_API =
    /^(localhost|127\.|192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(window.location.hostname) &&
    window.location.port !== "";

  // ========================================================================
  // Data Fetching & Trading-Day Stepping (auto-skips non-trading days)
  // ========================================================================

  async function init() {
    bindEvents();
    try {
      const datesUrl = USE_LIVE_API ? "./api/dates" : "./data/dates.json";
      const res = await fetch(datesUrl);
      const json = await res.json();
      state.dates = json.dates || [];
      const preferred =
        state.dates.find((d) => d.news_count > 0 && d.tagged > 0) ||
        state.dates[0];
      await loadDay(preferred ? preferred.date : "");
      playEntrance();
    } catch {
      elLadderList.innerHTML = `<div class="empty-state">数据加载失败</div>`;
    }
  }

  function currentDateIndex() {
    const cur = state.day?.date;
    if (!cur) return -1;
    return state.dates.findIndex((d) => d.date === cur);
  }

  function updateStepperButtons() {
    const idx = currentDateIndex();
    // state.dates is descending: idx - 1 is next newer trading day; idx + 1 is previous older trading day
    elDateNext.disabled = idx <= 0;
    elDatePrev.disabled = idx < 0 || idx >= state.dates.length - 1;
  }

  let loadingDay = false;

  async function loadDay(date, dir = null) {
    if (loadingDay) return;
    loadingDay = true;
    elDateBtn.classList.add("is-loading");
    try {
      const url = USE_LIVE_API
        ? date
          ? `./api/day?date=${encodeURIComponent(date)}`
          : "./api/day"
        : `./data/days/${encodeURIComponent(date || state.dates[0]?.date || "")}.json`;
      const res = await fetch(url);
      const day = await res.json();

      const apply = () => {
        state.day = day;
        // Sync freshly fetched zhaban_rate back into state.dates cache for the Date Picker
        const idx = currentDateIndex();
        if (idx >= 0 && state.day.summary?.zhaban_rate != null) {
          state.dates[idx].zhaban_rate = state.day.summary.zhaban_rate;
        }
        state.fbExpanded = false;
        if (elFbWrap) elFbWrap.classList.remove("expanded");
        elCatList.scrollTop = 0;
        elLadderScroll.scrollTop = 0;
        closeAllSheets(true);
        renderTier1();
      };

      if (dir && state.day) {
        const animated = await withTransition(`day-${dir}`, apply);
        if (!animated && !reduceMotion) replayClass(elMainLayout, `day-in-${dir}`);
      } else {
        apply();
      }
    } finally {
      loadingDay = false;
      elDateBtn.classList.remove("is-loading");
    }
  }

  // ========================================================================
  // Tier 1 Rendering (Vertical Dropdown Catalysts + Mood + Pure Ladder)
  // ========================================================================

  function renderTier1() {
    const d = state.day;
    if (!d) return;

    elDateLabel.textContent = shortDate(d.date);
    updateStepperButtons();
    renderMarketMood();
    renderCatalysts();
    renderLadder();
  }

  function renderMarketMood() {
    const s = state.day?.summary || {};
    const parts = [];
    if (s.max_height) {
      parts.push(`<span class="mood-chip">最高<b>${s.max_height}板</b></span>`);
    }
    if (s.zhaban_rate != null) {
      const rateCls = s.zhaban_rate >= 40 ? "mood-warn" : s.zhaban_rate <= 22 ? "mood-hot" : "";
      parts.push(`<span class="mood-dot"></span><span class="mood-chip ${rateCls}">炸板<b>${s.zhaban_rate}%</b></span>`);
    }
    if (s.total != null) {
      parts.push(`<span class="mood-dot"></span><span class="mood-chip">涨停<b>${s.total}</b></span>`);
    }
    elMarketMood.innerHTML = parts.join("");
  }

  function catalystCardHtml(c, idx) {
    const hCls = heatCls(c.heat_rank);
    const rankNum = String(idx + 1).padStart(2, "0");
    const leadMeta = c.max_height >= 2 ? `${c.max_height}板 · ${c.total}只` : `反包 · ${c.total}只`;

    const leadersHtml = (c.leaders || [])
      .slice(0, 3)
      .map((l) => {
        const ow = l.is_one_word ? `<span class="mini-ow">一字</span>` : "";
        const hLbl = l.height >= 2 ? `${l.height}B` : "反包";
        return `<span class="cat-leader-chip">${esc(l.name)}<em>${hLbl}</em>${ow}</span>`;
      })
      .join("");

    return `
      <button class="catalyst-card ${hCls}" type="button" data-cat-id="${esc(c.id)}">
        <div class="cat-top">
          <span class="cat-name-wrap">
            <span class="cat-rank-tag">${rankNum}</span>
            <span class="cat-name">${esc(c.title)}</span>
          </span>
          <span class="cat-stat">
            ${leadMeta}
            <svg viewBox="0 0 12 12" width="10" height="10" fill="none">
              <path d="M4.5 2.5L8 6L4.5 9.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </span>
        </div>
        <div class="cat-headline">${esc(c.headline)}</div>
        <div class="cat-leaders">${leadersHtml}</div>
      </button>
    `;
  }

  function updateCatalystFade() {
    if (!elCatFade || !elCatList) return;
    const atEnd = elCatList.scrollTop + elCatList.clientHeight >= elCatList.scrollHeight - 8;
    elCatFade.classList.toggle("at-end", atEnd);
  }

  function renderCatalysts() {
    const cats = state.day.catalysts || [];
    elCatCount.textContent = cats.length ? `${cats.length} 条` : "";
    if (!cats.length) {
      elCatList.innerHTML = `<div class="empty-state">暂无催化</div>`;
      updateCatalystFade();
      return;
    }

    elCatList.innerHTML = cats.map((c, i) => catalystCardHtml(c, i)).join("");
    requestAnimationFrame(updateCatalystFade);
  }

  function stockCellHtml(st, inFanbaoRow = false) {
    // Consecutive row: clean name + 一字 (plus N天M板 badge if also fanbao); Fanbao row: N天M板 + 首板至今涨幅
    const owTag = st.is_one_word ? `<span class="ow-tag">一字</span>` : "";
    const showDesc = (inFanbaoRow || st.is_fanbao) && st.boards_desc && st.boards_desc !== "首板" && st.boards_desc !== `${st.height}连板`;
    const fbTag = showDesc ? `<span class="fb-desc-tag">${esc(st.boards_desc)}</span>` : "";
    const fbGainTag =
      inFanbaoRow && st.fanbao_gain_pct != null
        ? `<span class="fb-gain-tag">${st.fanbao_gain_pct >= 0 ? "+" : ""}${st.fanbao_gain_pct}%</span>`
        : "";
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
        return `<span class="cell-theme ${tHeat}">${esc(item.name)}</span>`;
      })
      .join("");

    const themesHtml = themesInner ? `<div class="cell-themes">${themesInner}</div>` : "";
    return `
      <div class="stock-cell" role="button" tabindex="0" data-code="${esc(st.code)}">
        <span class="cell-main">
          <span class="cell-name">${esc(st.name)}</span>
          ${fbTag}
          ${fbGainTag}
          ${owTag}
        </span>
        ${themesHtml}
      </div>
    `;
  }

  function renderLadder() {
    const d = state.day;
    const maxH = d.summary.max_height || 0;
    const tiersHtml = [];

    for (const tier of d.ladder || []) {
      const stocks = tier.codes.map((c) => d.stocks[c]).filter(Boolean);
      if (!stocks.length) continue;

      const axisCls = tier.height === maxH && maxH >= 4 ? "peak" : "";
      const gridCls = stocks.length === 1 ? "single" : "";

      tiersHtml.push(`
        <div class="tier-row">
          <div class="tier-axis ${axisCls}">
            <span class="axis-num">${tier.height}</span><span class="axis-unit">板</span>
          </div>
          <div class="tier-grid ${gridCls}">
            ${stocks.map((st) => stockCellHtml(st, false)).join("")}
          </div>
        </div>
      `);
    }

    const fanbaoStocks = (d.fanbao_boards || []).map((c) => d.stocks[c]).filter(Boolean);
    if (fanbaoStocks.length) {
      const gridCls = fanbaoStocks.length === 1 ? "single" : "";
      tiersHtml.push(`
        <div class="tier-row">
          <div class="tier-axis fanbao">
            <span class="axis-unit">反包</span>
          </div>
          <div class="tier-grid ${gridCls}">
            ${fanbaoStocks.map((st) => stockCellHtml(st, true)).join("")}
          </div>
        </div>
      `);
    }

    elLadderList.innerHTML = tiersHtml.length
      ? tiersHtml.join("")
      : `<div class="empty-state">暂无连板/反包</div>`;
  }

  // ========================================================================
  // Tier 2: Bottom Sheet Navigation & Spring Lifecycle
  // ========================================================================

  function openModal(entry) {
    state.modalStack.push(entry);
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

  // In-sheet navigation: push slides forward (from right), pop slides back (from left)
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
    state.modalStack = [];
    elShell.classList.remove("receded", "dragging");
    elBackdrop.classList.remove("open", "dragging");
    elSheet.classList.remove("open", "dragging");
    elSheet.style.transform = "";
    elShell.style.transform = "";
    elShell.style.filter = "";
    elBackdrop.style.opacity = "";
    elSheet.setAttribute("aria-hidden", "true");
    closeDateSheet();
    if (instant) {
      elSheetHeader.innerHTML = "";
      elSheetBody.innerHTML = "";
    }
  }

  function renderCurrentModal() {
    const entry = state.modalStack[state.modalStack.length - 1];
    if (!entry || !state.day) return;
    elSheetBody.scrollTop = 0;

    if (entry.type === "catalyst" || entry.type === "theme") {
      renderThemeModal(entry);
    } else if (entry.type === "stock") {
      renderStockModal(entry);
    }
  }

  // ========================================================================
  // Modal View A: Pure Theme Convergence Modal (彻底屏蔽无关题材，纯净汇聚)
  // ========================================================================

  function resolveThemeContext(entry) {
    const d = state.day;
    if (entry.type === "catalyst") {
      const cat = (d.catalysts || []).find((c) => c.id === entry.id);
      if (cat) {
        return {
          title: cat.title,
          themeName: cat.theme || cat.title,
          heatRank: cat.heat_rank || 99,
          codes: cat.codes,
          news: cat.news || [],
        };
      }
    }
    const th = (d.themes || {})[entry.id];
    if (th) {
      return {
        title: th.name,
        themeName: th.name,
        heatRank: th.heat_rank || 99,
        codes: th.codes,
        news: th.news || [],
      };
    }
    return null;
  }

  function renderThemeModal(entry) {
    const ctx = resolveThemeContext(entry);
    if (!ctx) return;

    const d = state.day;
    const hCls = heatCls(ctx.heatRank);
    const allStocks = ctx.codes.map((c) => d.stocks[c]).filter(Boolean);
    const multiCnt = allStocks.filter((s) => s.height >= 2).length;
    const fanbaoCnt = allStocks.length - multiCnt;

    const hasBack = state.modalStack.length > 1;
    elSheetHeader.innerHTML = `
      <div class="sheet-header-row">
        <div class="sheet-title-group">
          ${hasBack ? `<button class="sheet-back-btn" id="modal-back" type="button" aria-label="返回">‹</button>` : ""}
          <h3 class="sheet-title ${hCls}">${esc(ctx.title)}</h3>
        </div>
        <button class="sheet-close-btn" id="modal-close" type="button" aria-label="关闭">×</button>
      </div>
      <div class="sheet-stats">
        <span>共 ${allStocks.length} 只</span>
        <span>连板 ${multiCnt}</span>
        ${fanbaoCnt > 0 ? `<span>反包 ${fanbaoCnt}</span>` : ""}
      </div>
    `;

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
      const gridCls = list.length === 1 ? "single" : "";

      const nodesHtml = list
        .map((st) => {
          const descText = st.boards_desc && st.boards_desc !== `${st.height}连板` ? st.boards_desc : "";
          const gainText = st.fanbao_gain_pct != null ? `波段${st.fanbao_gain_pct >= 0 ? "+" : ""}${st.fanbao_gain_pct}%` : "";
          const subText = [descText, gainText, st.province].filter(Boolean).join(" · ");
          const delay = Math.min(cardIdx * 28, 240);
          cardIdx++;

          return `
            <button class="c-node entering" style="animation-delay:${delay}ms" type="button" data-node-code="${esc(st.code)}">
              <div class="c-node-top">
                <span class="c-node-name-wrap">
                  <span class="c-node-name">${esc(st.name)}</span>
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
            <span>${list.length}只</span>
          </div>
          <div class="c-tier-grid ${gridCls}">
            ${nodesHtml}
          </div>
        </div>
      `);
    });

    elSheetBody.innerHTML = `
      <div class="modal-view">
        ${newsHtml}
        <div class="converge-tiers">
          ${tiersDom.length ? tiersDom.join("") : `<div class="empty-state">无标的</div>`}
        </div>
      </div>
    `;

    bindModalHeaderButtons();

    elSheetBody.querySelectorAll("[data-node-code]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const code = btn.getAttribute("data-node-code");
        pushModal({ type: "stock", id: code });
      });
    });
  }

  // ========================================================================
  // Modal View B: Stock Full-Profile & Multi-Theme Parallel Fermentation
  // ========================================================================

  function renderStockModal(entry) {
    const d = state.day;
    const st = d.stocks[entry.id];
    if (!st) return;

    const hasBack = state.modalStack.length > 1;
    const provLabel = st.controller_province
      ? `${st.province}(${st.controller_province}国资)`
      : st.province;
    const metaParts = [
      st.code,
      st.boards_desc || `${st.height}板`,
      st.fanbao_gain_pct != null ? `首板至今${st.fanbao_gain_pct >= 0 ? "+" : ""}${st.fanbao_gain_pct}%` : "",
      st.first_time ? `${st.first_time}封` : "",
      st.amount_yi != null ? `${st.amount_yi}亿` : "",
      st.turnover != null ? `换手${st.turnover}%` : "",
      provLabel,
      st.controller_type,
    ].filter(Boolean);

    elSheetHeader.innerHTML = `
      <div class="sheet-header-row">
        <div class="sheet-title-group">
          ${hasBack ? `<button class="sheet-back-btn" id="modal-back" type="button" aria-label="返回">‹</button>` : ""}
          <h3 class="sheet-title">${esc(st.name)}</h3>
          <span class="sheet-height-badge">${st.height}板</span>
          ${st.is_one_word ? `<span class="ow-tag">一字</span>` : ""}
        </div>
        <button class="sheet-close-btn" id="modal-close" type="button" aria-label="关闭">×</button>
      </div>
      <div class="sheet-stats">
        <span>${esc(metaParts.join(" · "))}</span>
      </div>
    `;

    const themePillsHtml = (st.themes || [])
      .map((t) => {
        const th = d.themes[t];
        const cnt = th ? th.total : 1;
        const tCls = themeHeatCls(t);
        return `
          <button class="s-theme-pill ${tCls}" type="button" data-jump-theme="${esc(t)}">
            <span>${esc(t)}</span>
            <span class="cnt">${cnt}</span>
          </button>
        `;
      })
      .join("");

    const activeLanes = (st.themes || [])
      .map((t) => {
        const th = d.themes[t];
        if (!th) return null;
        const peers = th.codes
          .filter((c) => c !== st.code)
          .map((c) => d.stocks[c])
          .filter(Boolean);
        if (!peers.length) return null;
        return {
          theme: t,
          heatCls: heatCls(th.heat_rank),
          multi: th.multi,
          first: th.total - th.multi,
          peers,
        };
      })
      .filter(Boolean);

    const peerAppearances = {};
    for (const lane of activeLanes) {
      for (const p of lane.peers) {
        peerAppearances[p.code] = (peerAppearances[p.code] || 0) + 1;
      }
    }

    const lanesHtml = activeLanes.length
      ? `
        <div class="s-block">
          <h4 class="s-block-title">
            <span>多线发酵</span>
            <span>${activeLanes.length} 条并行</span>
          </h4>
          <div class="lanes-list">
            ${activeLanes
              .map((lane, lIdx) => {
                const byH = new Map();
                for (const p of lane.peers) {
                  if (!byH.has(p.height)) byH.set(p.height, []);
                  byH.get(p.height).push(p);
                }
                const hs = Array.from(byH.keys()).sort((a, b) => b - a);
                const rowsHtml = hs
                  .map((h) => {
                    const pList = byH.get(h);
                    const maxShow = h >= 2 ? 4 : 3;
                    const shown = pList.slice(0, maxShow);
                    const extra = pList.length - shown.length;

                    const chips = shown
                      .map((p) => {
                        const isRes = (peerAppearances[p.code] || 0) >= 2;
                        return `
                          <button class="peer-chip ${isRes ? "is-resonance" : ""}" type="button" data-peer-code="${esc(p.code)}">
                            <span>${esc(p.name)}</span>
                            ${p.is_one_word ? `<span class="ow-tag">一字</span>` : ""}
                            ${isRes ? `<span class="res-badge">共振</span>` : ""}
                          </button>
                        `;
                      })
                      .join("");

                    const moreHtml = extra > 0
                      ? `<span class="peer-more" data-jump-theme="${esc(lane.theme)}">+${extra}</span>`
                      : "";

                    return `
                      <div class="lane-row">
                        <span class="lane-h">${h === 1 ? "反包" : `${h}板`}</span>
                        <div class="lane-peers">${chips}${moreHtml}</div>
                      </div>
                    `;
                  })
                  .join("");

                return `
                  <div class="lane-card ${lane.heatCls}" style="animation-delay:${lIdx * 45}ms">
                    <div class="lane-head" data-jump-theme="${esc(lane.theme)}">
                      <span class="lane-name">${esc(lane.theme)}</span>
                      <span class="lane-meta">
                        连${lane.multi}${lane.first > 0 ? ` · 反${lane.first}` : ""}
                        <svg viewBox="0 0 12 12" width="10" height="10" fill="none">
                          <path d="M4.5 2.5L8 6L4.5 9.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                      </span>
                    </div>
                    <div class="lane-rows">${rowsHtml}</div>
                  </div>
                `;
              })
              .join("")}
          </div>
        </div>
      `
      : "";

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

    const evsHtml = (st.evidences || []).length
      ? (st.evidences || [])
          .map((ev) => {
            const tCls = themeHeatCls(ev.theme);
            return `
              <div class="ev-item">
                <div class="ev-head">
                  <span class="ev-tag ${tCls}">${esc(ev.theme)}</span>
                  ${ev.pct != null ? `<span class="ev-pct">营收 ${ev.pct}%</span>` : ""}
                </div>
                <div class="ev-text">${esc(ev.text)}</div>
              </div>
            `;
          })
          .join("")
      : "";

    const srcNote =
      st.display_source === "prev"
        ? `沿用昨日 · 主位 ${st.primary_theme}`
        : st.display_source === "main"
          ? `主业 · 主位 ${st.primary_theme}`
          : "";
    const drv2Tag = st.driver2
      ? `<span class="ev-tag ${themeHeatCls(st.driver2)}">副 · ${esc(st.driver2)}</span>`
      : "";
    const driverHtml = st.driver
      ? `<div class="s-block">
           <h4 class="s-block-title"><span>今日驱动</span>${srcNote ? `<span>${esc(srcNote)}</span>` : ""}</h4>
           <div class="ev-item">
             <div class="ev-head">
               <span class="ev-tag ${themeHeatCls(st.driver)}">${esc(st.driver)}</span>
               ${drv2Tag}
               ${st.driver_basis_type ? `<span class="ev-pct">${esc(st.driver_basis_type)}</span>` : ""}
             </div>
             ${st.driver_basis ? `<div class="ev-text">${esc(st.driver_basis)}</div>` : ""}
           </div>
         </div>`
      : srcNote
        ? `<div class="s-block">
             <h4 class="s-block-title"><span>今日驱动</span><span>${esc(srcNote)}</span></h4>
           </div>`
        : "";

    elSheetBody.innerHTML = `
      <div class="modal-view">
        ${driverHtml}
        ${
          themePillsHtml
            ? `<div class="s-block">
                 <h4 class="s-block-title"><span>关联题材</span><span>${st.themes.length}</span></h4>
                 <div class="s-tag-wrap">${themePillsHtml}</div>
               </div>`
            : ""
        }
        ${lanesHtml}
        ${
          maHtml || evsHtml
            ? `<div class="s-block">
                 <h4 class="s-block-title"><span>核心档案</span>${st.industry ? `<span>${esc(st.industry)}</span>` : ""}</h4>
                 ${maHtml}
                 <div class="ev-list">${evsHtml}</div>
               </div>`
            : ""
        }
      </div>
    `;

    bindModalHeaderButtons();

    elSheetBody.querySelectorAll("[data-jump-theme]").forEach((el) => {
      el.addEventListener("click", () => {
        const t = el.getAttribute("data-jump-theme");
        if (t && d.themes[t]) pushModal({ type: "theme", id: t });
      });
    });

    elSheetBody.querySelectorAll("[data-peer-code]").forEach((el) => {
      el.addEventListener("click", () => {
        const c = el.getAttribute("data-peer-code");
        if (c && d.stocks[c]) pushModal({ type: "stock", id: c });
      });
    });
  }

  function bindModalHeaderButtons() {
    const closeBtn = $("modal-close");
    if (closeBtn) closeBtn.addEventListener("click", () => closeAllSheets());
    const backBtn = $("modal-back");
    if (backBtn) backBtn.addEventListener("click", () => popModal());
  }

  // ========================================================================
  // Date Picker Sheet (Shows Max Board + Zhaban Rate / Market Mood)
  // ========================================================================

  function openDateSheet() {
    const current = state.day?.date || "";
    elDateList.innerHTML = state.dates
      .map((d) => {
        const zbText = d.zhaban_rate != null ? `<span>炸板${d.zhaban_rate}%</span>` : "";
        return `
          <button class="date-row ${d.date === current ? "active" : ""}" type="button" data-pick-date="${esc(d.date)}">
            <span class="date-row-left">${esc(d.date)}</span>
            <span class="date-row-right">
              <span>最高${d.max_height}板</span>
              ${zbText}
              <span>涨${d.total}</span>
            </span>
          </button>
        `;
      })
      .join("");

    elDateList.querySelectorAll("[data-pick-date]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const dt = btn.getAttribute("data-pick-date");
        closeDateSheet();
        if (dt && dt !== current) {
          // state.dates is descending: a larger index means an older trading day
          const from = currentDateIndex();
          const to = state.dates.findIndex((x) => x.date === dt);
          loadDay(dt, from < 0 || to < 0 ? null : to > from ? "older" : "newer");
        }
      });
    });

    // Center the current trading day in the list before the sheet slides up
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
    // Trading-Day Prev / Next Stepper (auto-skips weekends & holidays)
    elDatePrev.addEventListener("click", () => {
      const idx = currentDateIndex();
      if (idx >= 0 && idx < state.dates.length - 1) {
        loadDay(state.dates[idx + 1].date, "older");
      }
    });

    elDateNext.addEventListener("click", () => {
      const idx = currentDateIndex();
      if (idx > 0) {
        loadDay(state.dates[idx - 1].date, "newer");
      }
    });

    // Track upper catalyst pane bottom fade visibility
    elCatList.addEventListener("scroll", updateCatalystFade, { passive: true });

    // Catalyst Card -> Pure Converged Theme Modal
    elCatList.addEventListener("click", (e) => {
      const card = e.target.closest("[data-cat-id]");
      if (!card) return;
      openModal({ type: "catalyst", id: card.getAttribute("data-cat-id") });
    });

    // Tier-1 Stock Row: tapping anywhere on a stock card opens that Stock's Full-Profile Modal
    const onLadderClick = (e) => {
      const cell = e.target.closest("[data-code]");
      if (!cell) return;
      openModal({ type: "stock", id: cell.getAttribute("data-code") });
    };
    elLadderList.addEventListener("click", onLadderClick);
    if (elFbGrid) elFbGrid.addEventListener("click", onLadderClick);

    if (elFbToggle && elFbWrap) {
      elFbToggle.addEventListener("click", () => {
        state.fbExpanded = !state.fbExpanded;
        elFbWrap.classList.toggle("expanded", state.fbExpanded);
      });
    }

    elDateBtn.addEventListener("click", openDateSheet);
    elDateClose.addEventListener("click", closeDateSheet);
    elDateBackdrop.addEventListener("click", closeDateSheet);

    elBackdrop.addEventListener("click", () => closeAllSheets());
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeAllSheets();
    });

    // Touch Swipe-Down Drag Gesture on Bottom Sheet Header/Handle
    let dragStartY = 0;
    let dragStartT = 0;
    let currentDy = 0;
    let dragging = false;

    const onTouchStart = (e) => {
      if (!elSheet.classList.contains("open")) return;
      if (e.target.closest("button")) return;
      dragging = true;
      dragStartY = e.touches[0].clientY;
      dragStartT = performance.now();
      currentDy = 0;
      elSheet.classList.add("dragging");
      elShell.classList.add("dragging");
      elBackdrop.classList.add("dragging");
    };

    const onTouchMove = (e) => {
      if (!dragging) return;
      const dy = e.touches[0].clientY - dragStartY;
      currentDy = dy < 0 ? dy * 0.16 : dy;
      elSheet.style.transform = `translate3d(0, ${currentDy}px, 0)`;
      // Backdrop fades and the receded page grows back as the sheet is pulled down
      const p = Math.min(1, Math.max(0, currentDy) / Math.max(1, elSheet.offsetHeight));
      elBackdrop.style.opacity = String(1 - p);
      elShell.style.transform = `scale(${0.955 + 0.045 * p}) translateY(${6 * (1 - p)}px)`;
      elShell.style.filter = `brightness(${0.92 + 0.08 * p})`;
    };

    const onTouchEnd = () => {
      if (!dragging) return;
      dragging = false;
      const dt = Math.max(1, performance.now() - dragStartT);
      const velocity = currentDy / dt;
      // Re-enable transitions and release inline styles together so everything springs from where the finger left it
      elSheet.classList.remove("dragging");
      elShell.classList.remove("dragging");
      elBackdrop.classList.remove("dragging");
      elShell.style.transform = "";
      elShell.style.filter = "";
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
    });
  }

  init();
})();
