const form = document.querySelector("#ticker-form");
const input = document.querySelector("#ticker-input");
const runButton = document.querySelector("#run-button");
const refreshButton = document.querySelector("#refresh-button");
const briefRefreshButton = document.querySelector("#brief-refresh");
const statusNode = document.querySelector("#status");
const watchlistForm = document.querySelector("#watchlist-form");
const watchlistInput = document.querySelector("#watchlist-input");
const watchlistRunButton = document.querySelector("#watchlist-run");
const watchlistRefreshButton = document.querySelector("#watchlist-refresh");
let busyDepth = 0;

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadTicker(input.value, false);
});

refreshButton.addEventListener("click", () => {
  loadTicker(input.value, true);
});

briefRefreshButton.addEventListener("click", () => {
  loadBrief(input.value, true);
});

watchlistForm.addEventListener("submit", (event) => {
  event.preventDefault();
  loadWatchlist(false);
});

watchlistRefreshButton.addEventListener("click", () => {
  loadWatchlist(true);
});

function setBusy(isBusy) {
  busyDepth = isBusy ? busyDepth + 1 : Math.max(0, busyDepth - 1);
  const disabled = busyDepth > 0;
  runButton.disabled = disabled;
  refreshButton.disabled = disabled;
  briefRefreshButton.disabled = disabled;
  watchlistRunButton.disabled = disabled;
  watchlistRefreshButton.disabled = disabled;
}

async function loadTicker(rawTicker, refresh) {
  const ticker = rawTicker.trim().toUpperCase();
  if (!ticker) return;
  input.value = ticker;
  setBusy(true);
  statusNode.className = "status";
  statusNode.textContent = `${ticker} loading...`;
  try {
    const url = `/api/card?ticker=${encodeURIComponent(ticker)}${refresh ? "&refresh=1" : ""}`;
    const response = await fetch(url);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "request failed");
    }
    renderCard(payload.card);
    loadBrief(ticker, refresh);
    statusNode.textContent = payload.card.provenance.stale ? "STALE cache data" : "";
  } catch (error) {
    statusNode.className = "status error";
    statusNode.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function loadBrief(rawTicker, refresh) {
  const ticker = rawTicker.trim().toUpperCase();
  if (!ticker) return;
  const status = document.querySelector("#brief-status");
  const content = document.querySelector("#brief-content");
  status.className = "brief-status";
  status.textContent = "loading...";
  content.innerHTML = "";
  try {
    const url = `/api/brief?ticker=${encodeURIComponent(ticker)}${refresh ? "&refresh=1" : ""}`;
    const response = await fetch(url);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "brief request failed");
    }
    const brief = payload.brief || {};
    renderBrief(brief, status, content);
  } catch (error) {
    status.className = "brief-status error";
    status.textContent = error.message;
  }
}

async function loadWatchlist(refresh) {
  const tickers = parseTickers(watchlistInput.value);
  const status = document.querySelector("#watchlist-status");
  const briefNode = document.querySelector("#watchlist-brief");
  const tableNode = document.querySelector("#watchlist-table");
  if (!tickers.length) {
    status.className = "brief-status error";
    status.textContent = "请输入至少一个 ticker";
    return;
  }
  setBusy(true);
  status.className = "brief-status";
  status.textContent = `${tickers.join(", ")} loading...`;
  briefNode.innerHTML = "";
  tableNode.innerHTML = "";
  try {
    const url = `/api/watchlist?tickers=${encodeURIComponent(tickers.join(","))}${refresh ? "&refresh=1" : ""}`;
    const response = await fetch(url);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "watchlist request failed");
    }
    renderBrief(payload.brief || {}, status, briefNode);
    renderWatchlistTable(payload.cards || {}, payload.cross_section || {}, payload.failures || []);
  } catch (error) {
    status.className = "brief-status error";
    status.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

function renderBrief(brief, status, content) {
  const model = brief.provider && brief.model ? `${brief.provider} · ${brief.model}` : "local fallback";
  status.className = "brief-status";
  status.textContent = brief.from_cache ? `${model} · cached` : model;
  if (brief.validation && brief.validation.passed === false) {
    status.className = "brief-status warning";
    status.textContent = `叙述未通过忠实性校验 · ${brief.validation.violations.join("; ")}`;
  }
  if (!brief.available) {
    status.className = "brief-status muted";
    status.textContent = brief.error || "晨报不可用";
  }
  content.innerHTML = renderMarkdown(brief.display_text || brief.text || "晨报不可用");
}

function renderWatchlistTable(cardsByTicker, crossSection, failures) {
  const node = document.querySelector("#watchlist-table");
  const cards = Object.values(cardsByTicker).sort((left, right) => left.ticker.localeCompare(right.ticker));
  if (!cards.length) {
    node.innerHTML = failures.length ? `<div class="table-empty">${escapeHtml(failures.join("; "))}</div>` : "";
    return;
  }
  node.innerHTML = `
    <table class="watchlist-table">
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Stance</th>
          <th>Confidence</th>
          <th>Flags</th>
          <th>Close</th>
          <th>Day</th>
          <th>State</th>
          <th>RS Rank</th>
          <th>Attribution</th>
          <th>Earnings</th>
        </tr>
      </thead>
      <tbody>
        ${cards.map((card) => watchlistRow(card, crossSection[card.ticker] || {})).join("")}
      </tbody>
    </table>
    ${failures.length ? `<div class="table-failures">${escapeHtml(failures.join("; "))}</div>` : ""}
  `;
  node.querySelectorAll("[data-ticker]").forEach((button) => {
    button.addEventListener("click", () => loadTicker(button.dataset.ticker, false));
  });
}

function watchlistRow(card, ranks) {
  const judgement = card.judgement || {};
  return `
    <tr>
      <td><button class="ticker-link" type="button" data-ticker="${escapeHtml(card.ticker)}">${escapeHtml(card.ticker)}</button></td>
      <td>${escapeHtml(judgement.earnings_overlay ? `earnings_risk_event(${judgement.stance})` : judgement.stance || "-")}</td>
      <td>${escapeHtml(`${judgement.confidence || "-"} · ${Number(judgement.confidence_score || 0).toFixed(2)}`)}</td>
      <td>${escapeHtml((judgement.risk_flags || []).join(", ") || "none")}</td>
      <td>${money(card.close)}</td>
      <td class="${card.day_return_pct >= 0 ? "positive" : "negative"}">${pct(card.day_return_pct)}</td>
      <td>${escapeHtml(card.volume_price.state)}</td>
      <td>${rankText(ranks.rs_vs_qqq_pct_3m)}</td>
      <td>${escapeHtml(card.attribution.classification)}</td>
      <td>${value(card.days_to_next_earnings, 0)}</td>
    </tr>
  `;
}

function rankText(block) {
  if (!block || block.rank == null) return "N/A";
  return `${block.rank}/${block.n_effective}`;
}

function parseTickers(raw) {
  const seen = new Set();
  return raw
    .split(/[,\s]+/)
    .map((item) => item.trim().toUpperCase())
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

function renderCard(card) {
  document.querySelector("#provenance").textContent =
    `${card.provenance.provider} · ${card.provenance.freshness} · fetched ${shortDateTime(card.provenance.fetched_at)}`;
  text("#summary-ticker", `${card.ticker}${card.sector ? " · " + card.sector : ""}`);
  text("#summary-date", card.as_of);
  text("#summary-close", money(card.close));
  text("#summary-day", pct(card.day_return_pct));
  colorSigned(document.querySelector("#summary-day"), card.day_return_pct);
  text("#summary-classification", card.attribution.classification);
  renderVerdict(card);

  panel("panel-attribution", "今日归因", `${card.attribution.mode} · R2 ${value(card.attribution.r_squared, 2)}`, `
    <div class="component-list">
      ${component("市场", card.attribution.market_component, "beta " + value(card.attribution.beta_market, 2))}
      ${component("板块", card.attribution.sector_component, "beta " + value(card.attribution.beta_sector, 2))}
      ${component("残差", card.attribution.residual, "z " + value(card.attribution.residual_z, 1))}
    </div>
    <div class="metric-grid">
      ${metric("分类", card.attribution.classification, "优先级规则判定")}
      ${metric("特有风险", value(card.attribution.residual_vol_annualized, 1) + "%", "残差波动年化")}
      ${metric("5日残差z", value(card.judgement.attribution_diagnostics?.residual_5d_z, 2), "序列诊断")}
      ${metric("20日逆市/放大", `${value(card.judgement.attribution_diagnostics?.defiant_days_20d, 0)} / ${value(card.judgement.attribution_diagnostics?.amplifier_days_20d, 0)}`, "")}
    </div>
  `);

  panel("panel-volume", "量价状态", card.volume_price.state, `
    <div class="metric-grid">
      ${metric("量能分位", value(card.volume_price.volume_pct, 0), bar(card.volume_price.volume_pct))}
      ${metric("ATR/昨收", pctField(card.volume_price.atr_pct), "")}
      ${metric("OBV", `${value(card.volume_price.obv_norm_slope_20d, 2)} · ${card.volume_price.obv_trend || "N/A"}`, "")}
      ${metric("上下行量比", value(card.volume_price.updown_vol_ratio_10d, 2), "")}
      ${metric("成交额", compactMoney(card.volume_price.dollar_volume.value), "")}
      ${metric("3月动量", pctField(card.volume_price.momentum_3m), "")}
      ${metric("6月动量", pctField(card.volume_price.momentum_6m), "")}
      ${metric("12-1动量", pctField(card.volume_price.momentum_12_1), "")}
      ${metric("SMA50 / SMA200", `${moneyField(card.volume_price.sma50)} / ${moneyField(card.volume_price.sma200)}`, "")}
      ${metric("距52周高点", pctField(card.volume_price.pct_from_252d_high), "")}
      ${metric("低于SMA200天数", value(card.volume_price.days_below_sma200, 0), "")}
      ${metric("10日放量涨/跌", `${value(card.volume_price.hv_up_days_10d, 0)} / ${value(card.volume_price.hv_down_days_10d, 0)}`, "")}
    </div>
  `);

  panel("panel-crowding", "拥挤度", `${value(card.crowding.crowding_score, 0)}/100`, `
    <div class="metric-grid">
      ${metric("综合分", value(card.crowding.crowding_score, 0), `${bar(card.crowding.crowding_score, true)}等权未验证`)}
      ${metric("换手", value(card.crowding.turnover_pct, 0), bar(card.crowding.turnover_pct))}
      ${metric("波动", value(card.crowding.rvol_pct, 0), bar(card.crowding.rvol_pct, true))}
      ${metric("乖离", value(card.crowding.extension_pct, 0), bar(card.crowding.extension_pct, true))}
      ${metric("空头占比", value(card.crowding.short_percent_of_float, 1) + "%", "独立展示")}
    </div>
  `);

  panel("panel-valuation", "估值分位", "自身历史", `
    <div class="metric-grid">
      ${metric("PE 分位", value(card.valuation.pe_ttm_pct, 0), bar(card.valuation.pe_ttm_pct, true))}
      ${metric("PS 分位", value(card.valuation.ps_ttm_pct, 0), bar(card.valuation.ps_ttm_pct, true))}
      ${metric("当前 PE", value(card.valuation.pe_ttm_current, 1), "")}
      ${metric("当前 PS", value(card.valuation.ps_ttm_current, 1), "")}
      ${metric("历史深度", value(card.valuation.depth_years, 1) + "y", "")}
      ${metric("说明", escapeHtml(card.valuation.note), "", "wide")}
    </div>
  `);

  panel("panel-relative", "相对强弱", flags(card.relative.flags), `
    <div class="metric-grid">
      ${metric("vs QQQ 斜率", pctField(card.relative.rs_vs_qqq_slope_20d), "")}
      ${metric("vs QQQ 3月分位", value(card.relative.rs_vs_qqq_pct_3m, 0), bar(card.relative.rs_vs_qqq_pct_3m))}
      ${metric("vs 板块斜率", pctField(card.relative.rs_vs_sector_slope_20d), "")}
      ${metric("vs 板块3月分位", value(card.relative.rs_vs_sector_pct_3m, 0), bar(card.relative.rs_vs_sector_pct_3m))}
    </div>
  `);

  panel("panel-fundamentals", "基本面快照", compactMoney(card.fundamentals.market_cap.value), `
    <div class="metric-grid">
      ${metric("年营收YoY", pctField(card.fundamentals.revenue_yoy_annual), "")}
      ${metric("季营收YoY", pctField(card.fundamentals.revenue_yoy_quarter), "")}
      ${metric("EPS YoY", pctField(card.fundamentals.eps_yoy_annual), "")}
      ${metric("毛利率", pctField(card.fundamentals.gross_margin), "")}
      ${metric("毛利率趋势", value(card.fundamentals.gross_margin_trend, 1) + "pp", "")}
      ${metric("ROE", pctField(card.fundamentals.roe), "")}
      ${metric("D/E", value(card.fundamentals.debt_to_equity, 2), "")}
      ${metric("股息率", pctField(card.fundamentals.dividend_yield), "")}
    </div>
  `);

  panel("panel-analyst", "分析师面", `覆盖 ${value(card.analyst.n_analysts, 0)}`, `
    <div class="metric-grid">
      ${metric("覆盖", value(card.analyst.n_analysts, 0), ratingCounts(card.analyst.rating_counts))}
      ${metric("目标均价", moneyField(card.analyst.target_mean), "")}
      ${metric("目标空间", pctField(card.analyst.target_upside_pct), "")}
      ${metric("前瞻PE", value(card.analyst.forward_pe, 1), "")}
      ${metric("90日EPS修正", pctField(card.analyst.eps_revision_90d_pct), "")}
      ${metric("上/下调", `${value(card.analyst.eps_up_30d, 0)} / ${value(card.analyst.eps_down_30d, 0)}`, "")}
      ${metric("财报", `${value(card.days_to_next_earnings, 0)} days`, `surprise ${value(card.last_earnings_surprise_pct, 1)}%`)}
      ${metric("说明", escapeHtml(card.analyst.note), "", "wide")}
    </div>
  `);

  applyProfileTemplate(card);
  renderDebug(card);
}

function panel(id, title, meta, body) {
  document.querySelector(`#${id}`).innerHTML = `
    <div class="panel-header">
      <h2>${escapeHtml(title)}</h2>
      <span>${escapeHtml(meta)}</span>
    </div>
    ${body}
  `;
}

function renderVerdict(card) {
  const judgement = card.judgement;
  const headline = judgement.earnings_overlay
    ? `earnings_risk_event(${judgement.stance})`
    : judgement.stance;
  const stanceNode = document.querySelector("#verdict-stance");
  text("#verdict-stance", headline);
  text("#verdict-caveat", judgement.caveat);
  text("#verdict-confidence", `${judgement.confidence} · ${Number(judgement.confidence_score).toFixed(2)}`);
  text(
    "#verdict-contexts",
    `${judgement.profile_template || "default"} · ${judgement.trend_state} · ${judgement.tape_state} · ${judgement.rs_context} · ${judgement.attribution_context}`
  );
  const rulePath = document.querySelector("#rule-path");
  rulePath.hidden = true;
  rulePath.innerHTML = renderRulePath(judgement);
  stanceNode.onclick = () => {
    rulePath.hidden = !rulePath.hidden;
  };
  stanceNode.onkeydown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      rulePath.hidden = !rulePath.hidden;
    }
  };
  document.querySelector("#risk-flags").innerHTML =
    judgement.risk_flags.length
      ? judgement.risk_flags.map((item) => chip(item)).join("")
      : '<span class="chip muted-chip">none</span>';
  document.querySelector("#evidence-list").innerHTML =
    judgement.evidence.slice(0, 4).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function renderRulePath(judgement) {
  const diagnostics = judgement.attribution_diagnostics || {};
  const rows = [
    ["stance", judgement.stance],
    ["entry", judgement.entry_context],
    ["exit", judgement.exit_context],
    ["trend", judgement.trend_state],
    ["tape", judgement.tape_state],
    ["crowding", judgement.crowding_risk],
    ["valuation", judgement.valuation_context],
    ["RS", judgement.rs_context],
    ["attribution", judgement.attribution_context],
    ["residual_5d_z", value(diagnostics.residual_5d_z, 2)],
    ["amplifier/defiant", `${value(diagnostics.amplifier_days_20d, 0)} / ${value(diagnostics.defiant_days_20d, 0)}`],
  ];
  return `
    <dl>
      ${rows.map(([key, val]) => `<div><dt>${escapeHtml(key)}</dt><dd>${val}</dd></div>`).join("")}
    </dl>
    <ol>${judgement.evidence.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>
  `;
}

function applyProfileTemplate(card) {
  const profile = card.judgement.profile_template || profileTemplate(card);
  const orders = {
    default: ["panel-attribution", "panel-volume", "panel-crowding", "panel-valuation", "panel-relative", "panel-fundamentals", "panel-analyst"],
    momentum_leader: ["panel-volume", "panel-relative", "panel-crowding", "panel-attribution", "panel-fundamentals", "panel-analyst", "panel-valuation"],
    stable_compounder: ["panel-fundamentals", "panel-valuation", "panel-attribution", "panel-relative", "panel-volume", "panel-analyst", "panel-crowding"],
    pre_profit: ["panel-fundamentals", "panel-valuation", "panel-attribution", "panel-volume", "panel-relative", "panel-crowding", "panel-analyst"],
  };
  const order = orders[profile] || orders.default;
  document.querySelector(".dashboard").dataset.profile = profile;
  order.forEach((id, index) => {
    const node = document.querySelector(`#${id}`);
    if (node) node.style.order = index + 1;
  });
  document.querySelector("#panel-valuation").classList.toggle("lower-priority", profile === "momentum_leader");
  document.querySelector("#panel-volume").classList.toggle("lower-priority", profile === "stable_compounder");
  document.querySelector("#panel-analyst").classList.toggle("lower-priority", profile === "pre_profit");
}

function profileTemplate(card) {
  const rvol = card.crowding.rvol_pct.value;
  const mom6 = card.volume_price.momentum_6m.value;
  const beta = card.attribution.beta_market.value;
  const dividend = card.fundamentals.dividend_yield.value;
  const revenue = card.fundamentals.revenue_yoy_annual.value;
  if (rvol != null && mom6 != null && beta != null && rvol >= 70 && mom6 > 0.15 && beta > 1.2) return "momentum_leader";
  if (beta != null && dividend != null && beta < 0.9 && dividend > 0) return "stable_compounder";
  if (card.valuation.pe_ttm_current.value == null && revenue != null && revenue > 0) return "pre_profit";
  return "default";
}

function renderDebug(card) {
  const judgement = card.judgement;
  const diagnostics = judgement.attribution_diagnostics || {};
  const naRows = collectNaReasons(card).slice(0, 18);
  document.querySelector("#debug-content").innerHTML = `
    <section>
      <h2>Judgement Diagnostics</h2>
      <div class="debug-grid">
        ${debugRow("profile_template", judgement.profile_template || "default", "")}
        ${debugRow("residual_5d_z", value(diagnostics.residual_5d_z, 2), "5日累计残差")}
        ${debugRow("amplifier_days_20d", value(diagnostics.amplifier_days_20d, 0), "20日放大器天数")}
        ${debugRow("defiant_days_20d", value(diagnostics.defiant_days_20d, 0), "20日逆市强势天数")}
        ${debugRow("market_5d_return", pctField(diagnostics.market_5d_return), "市场5日回报")}
      </div>
    </section>
    <section>
      <h2>Explain-Layer Metrics</h2>
      <div class="debug-grid">
        ${debugRow("MFI", value(card.volume_price.mfi_14, 0), "量价辅助，首屏降级")}
        ${debugRow("EV/S percentile", value(card.valuation.ev_sales_pct, 0), "静态债务近似")}
        ${debugRow("recommendation_mean", value(card.analyst.recommendation_mean, 1), "低离散度")}
        ${debugRow("corr_uplift", value(card.crowding.corr_uplift, 2), "体制漂移风险")}
        ${debugRow("target_upside_pct", pctField(card.analyst.target_upside_pct), "价格滞后派生值")}
      </div>
    </section>
    <section>
      <h2>Rule Thresholds</h2>
      <ul class="threshold-list">
        <li>near_high: pct_from_252d_high >= -5%</li>
        <li>distribution_pressure: hv_down_days_10d >= 3</li>
        <li>too_hot: extension_pct >= 90 or hv_up_days_10d >= 4</li>
        <li>earnings_overlay: days_to_next_earnings <= 5</li>
        <li>confidence: 0.6 * coverage + 0.4 * consistency</li>
      </ul>
    </section>
    <section>
      <h2>NA Reasons</h2>
      ${
        naRows.length
          ? `<ul class="threshold-list">${naRows.map((row) => `<li>${escapeHtml(row.path)}: ${escapeHtml(row.reason)}</li>`).join("")}</ul>`
          : `<p class="debug-empty">none</p>`
      }
    </section>
  `;
}

function debugRow(label, value, note) {
  return `
    <div class="debug-row">
      <label>${escapeHtml(label)}</label>
      <strong>${value}</strong>
      ${note ? `<small>${escapeHtml(note)}</small>` : ""}
    </div>
  `;
}

function collectNaReasons(card) {
  const out = [];
  const families = ["volume_price", "crowding", "valuation", "relative", "attribution", "fundamentals", "analyst", "judgement"];
  families.forEach((family) => collectNa(`${family}`, card[family], out));
  collectNa("days_to_next_earnings", card.days_to_next_earnings, out);
  collectNa("last_earnings_surprise_pct", card.last_earnings_surprise_pct, out);
  return out;
}

function collectNa(path, value, out) {
  if (!value || typeof value !== "object") return;
  if ("value" in value && value.value == null && value.reason) {
    out.push({ path, reason: value.reason });
    return;
  }
  Object.entries(value).forEach(([key, child]) => collectNa(`${path}.${key}`, child, out));
}

function chip(item) {
  const hard = [
    "earnings_within_5d",
    "extreme_crowding",
    "extended_gt90",
    "negative_revisions",
    "amplifier_pattern",
    "idio_bleed",
    "valuation_very_rich",
  ].includes(item);
  return `<span class="chip ${hard ? "hard-chip" : ""}">${escapeHtml(item)}</span>`;
}

function component(label, field, note) {
  const raw = field.value;
  const signClass = raw == null ? "na" : raw >= 0 ? "positive" : "negative";
  return `
    <div class="component">
      <span class="eyebrow">${escapeHtml(label)}</span>
      <strong class="${signClass}">${pctField(field)}</strong>
      <small>${escapeHtml(note)}</small>
    </div>
  `;
}

function metric(label, main, sub, extraClass = "") {
  return `
    <div class="metric ${extraClass}">
      <label>${escapeHtml(label)}</label>
      <strong>${main}</strong>
      ${sub ? `<small>${sub}</small>` : ""}
    </div>
  `;
}

function bar(field, risk = false) {
  if (!field || field.value == null) return "N/A";
  const width = Math.max(0, Math.min(100, field.value));
  let tone = "";
  if (risk && width >= 80) tone = "bad";
  else if (risk && width >= 65) tone = "warn";
  return `<span class="bar ${tone}"><span style="width:${width}%"></span></span>`;
}

function value(field, digits = 1) {
  if (!field || field.value == null) return `<span class="na">N/A(${escapeHtml(field?.reason || "not available")})</span>`;
  return Number(field.value).toFixed(digits);
}

function pctField(field) {
  if (!field || field.value == null) return `<span class="na">N/A(${escapeHtml(field?.reason || "not available")})</span>`;
  return pct(field.value);
}

function pct(value) {
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

function money(value) {
  return `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;
}

function moneyField(field) {
  if (!field || field.value == null) return `<span class="na">N/A(${escapeHtml(field?.reason || "not available")})</span>`;
  return money(field.value);
}

function compactMoney(value) {
  if (value == null) return "N/A";
  const abs = Math.abs(value);
  if (abs >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  return money(value);
}

function flags(items) {
  return items && items.length ? items.join(", ") : "none";
}

function ratingCounts(counts) {
  if (!counts) return "N/A";
  return `SB ${counts.strongBuy || 0} · B ${counts.buy || 0} · H ${counts.hold || 0} · S ${counts.sell || 0}`;
}

function colorSigned(node, number) {
  node.classList.remove("positive", "negative");
  node.classList.add(number >= 0 ? "positive" : "negative");
}

function text(selector, content) {
  document.querySelector(selector).textContent = content;
}

function shortDateTime(raw) {
  if (!raw) return "-";
  return raw.replace("T", " ").replace("Z", "");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderMarkdown(markdown) {
  const html = escapeHtml(markdown || "")
    .split(/\n{2,}/)
    .map((block) => {
      if (block.startsWith("## ")) {
        return `<h2>${block.slice(3)}</h2>`;
      }
      if (block.startsWith("> ")) {
        return `<blockquote>${block.slice(2)}</blockquote>`;
      }
      const lines = block.split("\n").filter(Boolean);
      if (lines.every((line) => line.startsWith("- "))) {
        return `<ul>${lines.map((line) => `<li>${line.slice(2)}</li>`).join("")}</ul>`;
      }
      return `<p>${lines.join("<br />")}</p>`;
    })
    .join("");
  return html || "<p>-</p>";
}

loadTicker(input.value, false);
loadWatchlist(false);
