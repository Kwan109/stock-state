const form = document.querySelector("#ticker-form");
const input = document.querySelector("#ticker-input");
const runButton = document.querySelector("#run-button");
const refreshButton = document.querySelector("#refresh-button");
const statusNode = document.querySelector("#status");

form.addEventListener("submit", (event) => {
  event.preventDefault();
  loadTicker(input.value, false);
});

refreshButton.addEventListener("click", () => {
  loadTicker(input.value, true);
});

function setBusy(isBusy) {
  runButton.disabled = isBusy;
  refreshButton.disabled = isBusy;
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
    statusNode.textContent = payload.card.provenance.stale ? "STALE cache data" : "";
  } catch (error) {
    statusNode.className = "status error";
    statusNode.textContent = error.message;
  } finally {
    setBusy(false);
  }
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

  panel("panel-attribution", "今日归因", `${card.attribution.mode} · R2 ${value(card.attribution.r_squared, 2)}`, `
    <div class="component-list">
      ${component("市场", card.attribution.market_component, "beta " + value(card.attribution.beta_market, 2))}
      ${component("板块", card.attribution.sector_component, "beta " + value(card.attribution.beta_sector, 2))}
      ${component("残差", card.attribution.residual, "z " + value(card.attribution.residual_z, 1))}
    </div>
    <div class="metric-grid">
      ${metric("分类", card.attribution.classification, "优先级规则判定")}
      ${metric("特有风险", value(card.attribution.residual_vol_annualized, 1) + "%", "残差波动年化")}
    </div>
  `);

  panel("panel-volume", "量价状态", card.volume_price.state, `
    <div class="metric-grid">
      ${metric("量能分位", value(card.volume_price.volume_pct, 0), bar(card.volume_price.volume_pct))}
      ${metric("ATR/昨收", pctField(card.volume_price.atr_pct), "")}
      ${metric("OBV", `${value(card.volume_price.obv_norm_slope_20d, 2)} · ${card.volume_price.obv_trend || "N/A"}`, "")}
      ${metric("上下行量比", value(card.volume_price.updown_vol_ratio_10d, 2), "")}
      ${metric("MFI", value(card.volume_price.mfi_14, 0), bar(card.volume_price.mfi_14))}
      ${metric("成交额", compactMoney(card.volume_price.dollar_volume.value), "")}
      ${metric("3月动量", pctField(card.volume_price.momentum_3m), "")}
      ${metric("6月动量", pctField(card.volume_price.momentum_6m), "")}
      ${metric("12-1动量", pctField(card.volume_price.momentum_12_1), "")}
    </div>
  `);

  panel("panel-crowding", "拥挤度", `${value(card.crowding.crowding_score, 0)}/100`, `
    <div class="metric-grid">
      ${metric("综合分", value(card.crowding.crowding_score, 0), bar(card.crowding.crowding_score, true))}
      ${metric("换手", value(card.crowding.turnover_pct, 0), bar(card.crowding.turnover_pct))}
      ${metric("波动", value(card.crowding.rvol_pct, 0), bar(card.crowding.rvol_pct, true))}
      ${metric("乖离", value(card.crowding.extension_pct, 0), bar(card.crowding.extension_pct, true))}
      ${metric("相关抬升", value(card.crowding.corr_uplift, 2), "")}
      ${metric("空头占比", value(card.crowding.short_percent_of_float, 1) + "%", "独立展示")}
    </div>
  `);

  panel("panel-valuation", "估值分位", "自身历史", `
    <div class="metric-grid">
      ${metric("PE 分位", value(card.valuation.pe_ttm_pct, 0), bar(card.valuation.pe_ttm_pct, true))}
      ${metric("PS 分位", value(card.valuation.ps_ttm_pct, 0), bar(card.valuation.ps_ttm_pct, true))}
      ${metric("EV/S 分位", value(card.valuation.ev_sales_pct, 0), bar(card.valuation.ev_sales_pct, true))}
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
      ${metric("评级均值", value(card.analyst.recommendation_mean, 1), ratingCounts(card.analyst.rating_counts))}
      ${metric("目标均价", moneyField(card.analyst.target_mean), "")}
      ${metric("目标空间", pctField(card.analyst.target_upside_pct), "")}
      ${metric("前瞻PE", value(card.analyst.forward_pe, 1), "")}
      ${metric("90日EPS修正", pctField(card.analyst.eps_revision_90d_pct), "")}
      ${metric("上/下调", `${value(card.analyst.eps_up_30d, 0)} / ${value(card.analyst.eps_down_30d, 0)}`, "")}
      ${metric("财报", `${value(card.days_to_next_earnings, 0)} days`, `surprise ${value(card.last_earnings_surprise_pct, 1)}%`)}
      ${metric("说明", escapeHtml(card.analyst.note), "", "wide")}
    </div>
  `);
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

loadTicker(input.value, false);

