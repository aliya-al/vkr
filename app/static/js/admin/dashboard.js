(function () {
  const elSales = document.getElementById("chartSales");
  const elCum = document.getElementById("chartCumulative");
  const elCats = document.getElementById("chartCategories");

  const salesChart = elSales ? echarts.init(elSales) : null;
  const cumChart = elCum ? echarts.init(elCum) : null;
  const catChart = elCats ? echarts.init(elCats) : null;

  const groupSales = document.getElementById("groupSales");
  const groupCumulative = document.getElementById("groupCumulative");
  const groupCategories = document.getElementById("groupCategories");
  const groupTop = document.getElementById("groupTop");

  const scopeCategories = document.getElementById("scopeCategories");
  const scopeTop = document.getElementById("scopeTop");

  const legendEl = document.getElementById("categoriesLegend");
  const topListEl = document.getElementById("topProductsList");

  const kpiOrdersWeek = document.getElementById("kpiOrdersWeek");
  const kpiInProgress = document.getElementById("kpiInProgress");
  const kpiDone = document.getElementById("kpiDone");

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function pad2(n) {
  return String(n).padStart(2, "0");
}

  const moneyFmt = new Intl.NumberFormat("ru-RU");

  function fmtMoney(v) {
    const n = Number(v);
    if (!Number.isFinite(n)) return "0";
    return moneyFmt.format(Math.round(n));
  }


function formatPeriodLabel(raw) {
  if (raw == null) return "";
  const s = String(raw).trim();
  if (!s) return "";

  const isoOrDate = s.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s].*)?$/);
  if (isoOrDate) {
    const [, y, m, d] = isoOrDate;
    return `${d}.${m}.${y}`;
  }

  const ym = s.match(/^(\d{4})-(\d{2})$/);
  if (ym) {
    const [, y, m] = ym;
    return `${m}.${y}`;
  }

  const yw = s.match(/^(\d{4})-W(\d{1,2})$/i);
  if (yw) {
    const [, y, w] = yw;
    return `нед ${pad2(w)}, ${y}`;
  }

  const yOnly = s.match(/^\d{4}$/);
  if (yOnly) return s;

  return s;
}

function normalizeSeries(arr) {
  const x = [];
  const y = [];
  (arr || []).forEach((it) => {
    const label = it.label ?? it.period ?? it.x ?? it.name ?? "";
    const val = it.value ?? it.amount ?? it.total ?? it.sum ?? it.revenue ?? it.qty ?? 0;

    x.push(formatPeriodLabel(label));
    y.push(Number(val) || 0);
  });
  return { x, y };
}


  function normalizePie(arr) {
    return (arr || []).map((it) => {
      const name = it.name ?? it.category ?? it.label ?? "—";
      const value = it.value ?? it.amount ?? it.total ?? it.sum ?? it.revenue ?? it.qty ?? 0;
      return { name: String(name), value: Number(value) || 0 };
    });
  }

  function setKpis(k) {
    const ordersWeek = k.orders_week ?? k.ordersWeek ?? k.week_orders ?? k.week ?? 0;
    const inProg = k.in_progress ?? k.inProgress ?? k.requests_in_progress ?? k.inwork ?? 0;
    const done = k.done ?? k.done_total ?? k.completed ?? k.orders_done ?? 0;

    if (kpiOrdersWeek) kpiOrdersWeek.textContent = String(ordersWeek);
    if (kpiInProgress) kpiInProgress.textContent = String(inProg);
    if (kpiDone) kpiDone.textContent = String(done);
  }

  function renderSales(series) {
    if (!salesChart) return;
    const { x, y } = normalizeSeries(series);

    salesChart.setOption({
      grid: { left: 56, right: 16, top: 14, bottom: 30 },
      tooltip: {
        trigger: "axis",
        formatter: (params) => {
          const p = (params && params[0]) ? params[0] : null;
          if (!p) return "";
          return `${p.axisValue}<br/>${fmtMoney(p.data)} ₽`;
        },
      },
      xAxis: {
        type: "category",
        data: x,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: cssVar("--color-line") } },
        axisLabel: { color: cssVar("--color-muted"), fontSize: 11 },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: cssVar("--color-line") } },
        axisLabel: {
          color: cssVar("--color-muted"),
          fontSize: 11,
          formatter: (value) => fmtMoney(value),
        },
      },
      series: [
        { type: "bar", data: y, barWidth: 18, itemStyle: { borderRadius: [6, 6, 0, 0] } },
      ],
      animation: false,
    }, true);
  }

  function renderCumulative(series) {
    if (!cumChart) return;
    const { x, y } = normalizeSeries(series);

    cumChart.setOption({
      grid: { left: 56, right: 16, top: 14, bottom: 30 },
      tooltip: {
        trigger: "axis",
        formatter: (params) => {
          const p = (params && params[0]) ? params[0] : null;
          if (!p) return "";
          return `${p.axisValue}<br/>${fmtMoney(p.data)} ₽`;
        },
      },
      xAxis: {
        type: "category",
        data: x,
        axisTick: { show: false },
        axisLine: { lineStyle: { color: cssVar("--color-line") } },
        axisLabel: { color: cssVar("--color-muted"), fontSize: 11 },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: cssVar("--color-line") } },
        axisLabel: {
          color: cssVar("--color-muted"),
          fontSize: 11,
          formatter: (value) => fmtMoney(value),
        },
      },
      series: [
        { type: "line", data: y, smooth: true, symbol: "none", areaStyle: {}, lineStyle: { width: 2 } },
      ],
      animation: false,
    }, true);
  }

  function renderCategories(data) {
    if (!catChart) return;
    const pie = normalizePie(data).slice(0, 6);

    catChart.setOption({
      tooltip: { trigger: "item" },
      series: [{
        type: "pie",
        radius: ["62%", "82%"],
        center: ["50%", "46%"],
        label: { show: false },
        labelLine: { show: false },
        data: pie,
      }],
      animation: false,
    }, true);

    if (legendEl) {
      legendEl.innerHTML = "";
      pie.forEach((it) => {
        const row = document.createElement("div");
        row.className = "legend__row";
        const sw = document.createElement("span");
        sw.className = "legend__swatch";
        row.appendChild(sw);
        const tx = document.createElement("span");
        tx.textContent = it.name;
        row.appendChild(tx);
        legendEl.appendChild(row);
      });
    }
  }

  function renderTopProducts(arr) {
    if (!topListEl) return;
    topListEl.innerHTML = "";

    (arr || []).slice(0, 5).forEach((it) => {
      const name = it.name ?? it.product_name ?? it.title ?? "—";
      const uniq = it.unique_orders ?? it.unique ?? it.orders_unique ?? it.uniqueCount ?? 0;
      const total = it.total_qty ?? it.qty ?? it.total ?? it.orders_total ?? 0;

      const wrap = document.createElement("div");
      wrap.className = "topitem";

      const pid  = it.product_id ?? it.id ?? "";
      const slug = it.product_slug ?? it.slug ?? "";

      let productUrl = "";
      if (pid) productUrl = `/product/${slug}/`;

      const img = document.createElement("div");
      img.className = "topitem__img";

      let imgUrl = it.product_image ?? it.image ?? it.image_url ?? it.image_path ?? "";

      if (imgUrl) {
        if (imgUrl.startsWith("static/")) imgUrl = "/" + imgUrl;
        if (imgUrl.startsWith("uploads/")) imgUrl = "/static/" + imgUrl;
        if (!imgUrl.startsWith("/") && !imgUrl.startsWith("http")) imgUrl = "/" + imgUrl;

        img.style.backgroundImage = `url("${imgUrl}")`;
        img.style.backgroundSize = "cover";
        img.style.backgroundPosition = "center";
        img.style.backgroundRepeat = "no-repeat";
      }

      if (productUrl) {
        const link = document.createElement("a");
        link.className = "topitem__imgLink";
        link.href = productUrl;
        link.title = name;
        link.appendChild(img);
        wrap.appendChild(link);
      } else {
        wrap.appendChild(img);
      }



      const body = document.createElement("div");

      const nm = document.createElement("div");
      nm.className = "topitem__name";
      nm.textContent = name;
      body.appendChild(nm);

      const meta = document.createElement("div");
      meta.className = "topitem__meta";
      const a = document.createElement("div");
      a.textContent = `Уникальных заказов: ${uniq}`;
      const b = document.createElement("div");
      b.textContent = `Заказов всего: ${total}`;
      meta.appendChild(a);
      meta.appendChild(b);
      body.appendChild(meta);

      wrap.appendChild(body);
      topListEl.appendChild(wrap);
    });
  }

  async function getJSON(url) {
    const r = await fetch(url, { headers: { "Accept": "application/json" } });
    if (!r.ok) throw new Error(String(r.status));
    return await r.json();
  }

  async function loadKpis() {
  try {
    const data = await getJSON("/admin/api/analytics/kpis");
    setKpis(data);
  } catch (e) {
    console.error("KPI load failed:", e);
  }
}


  async function loadSales() {
    if (!salesChart) return;
    const g = groupSales ? groupSales.value : "month";
    const url = new URL("/admin/api/analytics/sales", window.location.origin);
    url.searchParams.set("group", g);
    url.searchParams.set("scope", "recent");
    try {
      const data = await getJSON(url.toString());
      renderSales(data.series || []);
    } catch (_) {}
  }

  async function loadCumulative() {
    if (!cumChart) return;
    const g = groupCumulative ? groupCumulative.value : "month";
    const url = new URL("/admin/api/analytics/cumulative", window.location.origin);
    url.searchParams.set("group", g);
    url.searchParams.set("scope", "recent");
    try {
      const data = await getJSON(url.toString());
      renderCumulative(data.series || []);
    } catch (_) {}
  }

  async function loadCategories() {
    if (!catChart) return;
    const g = groupCategories ? groupCategories.value : "month";
    const scope = scopeCategories ? scopeCategories.value : "recent";

    const url = new URL("/admin/api/analytics/categories", window.location.origin);
    url.searchParams.set("group", g);
    url.searchParams.set("scope", scope);

    try {
      const data = await getJSON(url.toString());
      renderCategories(data.data || []);
    } catch (_) {}
  }

  async function loadTopProducts() {
    if (!topListEl) return;
    const g = groupTop ? groupTop.value : "month";
    const scope = scopeTop ? scopeTop.value : "all";

    const url = new URL("/admin/api/analytics/top-products", window.location.origin);
    url.searchParams.set("group", g);
    url.searchParams.set("scope", scope);
    url.searchParams.set("limit", "5");

    try {
      const data = await getJSON(url.toString());
      renderTopProducts(data.data || []);
    } catch (_) {}
  }

  function wire() {
    if (groupSales) groupSales.addEventListener("change", loadSales);
    if (groupCumulative) groupCumulative.addEventListener("change", loadCumulative);

    if (groupCategories) groupCategories.addEventListener("change", loadCategories);
    if (scopeCategories) scopeCategories.addEventListener("change", loadCategories);

    if (groupTop) groupTop.addEventListener("change", loadTopProducts);
    if (scopeTop) scopeTop.addEventListener("change", loadTopProducts);

    window.addEventListener("resize", () => {
      if (salesChart) salesChart.resize();
      if (cumChart) cumChart.resize();
      if (catChart) catChart.resize();
    });
  }

  wire();
  loadKpis();
  loadSales();
  loadCumulative();
  loadCategories();
  loadTopProducts();
})();

document.addEventListener("DOMContentLoaded", () => {
  const sel = document.getElementById("manageSiteSelect");
  if (!sel) return;

  sel.addEventListener("change", () => {
    const url = sel.value;
    if (url) window.location.href = url;
  });
});


(function () {
  function postInline(orderId, payload) {
    return fetch(`/admin/requests/${orderId}/inline`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    }).then(async (r) => {
      const data = await r.json().catch(() => ({}));
      if (!r.ok || !data.ok) {
        const msg = data && data.error ? data.error : "Не удалось сохранить.";
        throw new Error(msg);
      }
      return data;
    });
  }

  function setStatusClass(selectEl, statusValue) {
    selectEl.classList.remove("badge--new", "badge--in_progress", "badge--done", "badge--canceled");
    selectEl.classList.add(`badge--${statusValue}`);
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".js-inline-status, .js-inline-manager").forEach((s) => {
      s.dataset.prevValue = s.value;
    });
  });

  document.addEventListener("change", async (e) => {
    const statusSel = e.target.closest(".js-inline-status");
    const managerSel = e.target.closest(".js-inline-manager");
    const sel = statusSel || managerSel;
    if (!sel) return;

    const orderId = sel.dataset.orderId;
    if (!orderId) return;

    const prev = sel.dataset.prevValue ?? "";
    const next = sel.value;

    sel.disabled = true;
    try {
      if (statusSel) {
        const data = await postInline(orderId, { status: next });
        setStatusClass(statusSel, data.status || next);
        sel.dataset.prevValue = next;
      } else {
        await postInline(orderId, { manager_id: next });
        sel.dataset.prevValue = next;
      }
    } catch (err) {
      sel.value = prev;
      sel.dataset.prevValue = prev;
      if (statusSel) setStatusClass(statusSel, prev || "new");
      alert(err.message || "Ошибка сохранения");
    } finally {
      sel.disabled = false;
    }
  });
})();
