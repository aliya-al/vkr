(function () {
  function qs(sel, root = document) { return root.querySelector(sel); }
  function qsa(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

  async function applyFilterFromForm(form) {
    const listEl = qs("#apProductsList");
    if (!form || !listEl) return;

    const url = new URL(window.location.href);
    url.search = "";

    const fd = new FormData(form);

    for (const [k, v] of fd.entries()) {
      if (v === "" || v == null) continue;
      url.searchParams.append(k, String(v));
    }

    const y = window.scrollY;

    const r = await fetch(url.toString(), { headers: { "X-Requested-With": "fetch" } });
    if (!r.ok) throw new Error(String(r.status));
    const html = await r.text();

    const doc = new DOMParser().parseFromString(html, "text/html");
    const nextList = doc.querySelector("#apProductsList");
    if (!nextList) return;

    listEl.innerHTML = nextList.innerHTML;

    history.replaceState({}, "", url.toString());

    window.scrollTo(0, y);
  }

  function wireFilter() {
    const form = qs("#apFilterForm");
    if (!form) return;

    const noneEl = qs("#apNone");

    form.addEventListener("change", (e) => {
      const el = e.target;
      if (!el) return;

      const isCategory = el.matches('input[type="checkbox"][name="cat"]');
      const isExtraFilter = el.matches('input[type="radio"][name="activity"], input[type="radio"][name="photos"]');
      if (!isCategory && !isExtraFilter) return;

      if (isCategory && noneEl) noneEl.value = "";
      applyFilterFromForm(form).catch(console.error);
    });

    const btnReset = qs("#apReset");
    const btnAll = qs("#apSelectAll");

    if (btnReset) {
      btnReset.addEventListener("click", () => {
        qsa('input[type="checkbox"][name="cat"]', form).forEach(cb => cb.checked = false);
        if (noneEl) noneEl.value = "1";
        applyFilterFromForm(form).catch(console.error);
      });
    }

    if (btnAll) {
      btnAll.addEventListener("click", () => {
        qsa('input[type="checkbox"][name="cat"]', form).forEach(cb => cb.checked = true);
        if (noneEl) noneEl.value = "";
        applyFilterFromForm(form).catch(console.error);
      });
    }
  }

  async function postInlineActive(productId, isActive) {
    const r = await fetch(`/admin/products/${productId}/inline`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ is_active: !!isActive }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || !data.ok) {
      throw new Error(data && data.error ? data.error : "Не удалось сохранить.");
    }
    return data;
  }

  function setActiveClass(selectEl, isActive) {
    selectEl.classList.remove("badge--active", "badge--inactive");
    selectEl.classList.add(isActive ? "badge--active" : "badge--inactive");
  }

  function wireInlineActive() {
    document.addEventListener("DOMContentLoaded", () => {
      qsa(".js-inline-active").forEach((s) => { s.dataset.prevValue = s.value; });
    });

    document.addEventListener("change", async (e) => {
      const sel = e.target.closest(".js-inline-active");
      if (!sel) return;

      const productId = sel.dataset.productId;
      if (!productId) return;

      const prev = sel.dataset.prevValue ?? "1";
      const next = sel.value;
      const nextBool = next === "1";

      sel.disabled = true;
      try {
        const data = await postInlineActive(productId, nextBool);
        const saved = !!(data.is_active ?? nextBool);
        setActiveClass(sel, saved);
        sel.value = saved ? "1" : "0";
        sel.dataset.prevValue = sel.value;
      } catch (err) {
        sel.value = prev;
        sel.dataset.prevValue = prev;
        setActiveClass(sel, prev === "1");
        alert(err.message || "Ошибка сохранения");
      } finally {
        sel.disabled = false;
      }
    });
  }

  wireFilter();
  wireInlineActive();
})();
