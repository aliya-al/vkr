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

  function normalizeSeries(arr) {
    const x = [];
    const y = [];
    (arr || []).forEach((it) => {
      const label = it.label ?? it.period ?? it.x ?? it.name ?? "";
      const val = it.value ?? it.amount ?? it.total ?? it.sum ?? it.revenue ?? it.qty ?? 0;
      x.push(String(label));
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
      grid: { left: 38, right: 16, top: 14, bottom: 30 },
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
        axisLabel: { color: cssVar("--color-muted"), fontSize: 11 },
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
      grid: { left: 38, right: 16, top: 14, bottom: 30 },
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
        axisLabel: { color: cssVar("--color-muted"), fontSize: 11 },
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
        center: ["50%", "42%"],
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

    (arr || []).slice(0, 4).forEach((it) => {
      const name = it.name ?? it.product_name ?? it.title ?? "—";
      const uniq = it.unique_orders ?? it.unique ?? it.orders_unique ?? it.uniqueCount ?? 0;
      const total = it.total_qty ?? it.qty ?? it.total ?? it.orders_total ?? 0;

      const wrap = document.createElement("div");
      wrap.className = "topitem";

      const img = document.createElement("div");
      img.className = "topitem__img";
      wrap.appendChild(img);

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
    } catch (_) {}
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
    url.searchParams.set("limit", "4");

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
