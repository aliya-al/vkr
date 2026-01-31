(() => {
  const parseIntSafe = (v, fallback = 0) => {
    const n = parseInt(String(v).replace(/[^\d]/g, ""), 10);
    return Number.isFinite(n) ? n : fallback;
  };

  const postQty = async (productId, qty) => {
    const data = new URLSearchParams();
    data.set("product_id", productId);
    data.set("qty", String(qty));

    try {
      const res = await fetch("/cart/update", {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          "Accept": "application/json",
          "X-Requested-With": "fetch",
        },
        body: data.toString(),
        credentials: "same-origin",
      });
      return res.ok;
    } catch (_) {
      return false;
    }
  };

  const postAdd = async (form) => {
    const action = form.getAttribute("action") || "/cart/add";
    const data = new URLSearchParams(new FormData(form));

    try {
      const res = await fetch(action, {
        method: "POST",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          "Accept": "application/json",
          "X-Requested-With": "fetch",
        },
        body: data.toString(),
        credentials: "same-origin",
        redirect: "follow",
      });

      if (!res.ok) return { ok: false };

      const json = await res.json().catch(() => null);
      if (json && typeof json === "object") {
        // если бэкенд возвращает qty — используем
        if (json.ok === false) return { ok: false };
        if (Number.isFinite(Number(json.qty))) return { ok: true, qty: Number(json.qty) };
      }

      // если JSON нет/другой — считаем, что добавили 1
      return { ok: true, qty: 1 };
    } catch (_) {
      return { ok: false };
    }
  };

  const initCartWidget = (root) => {
    const productId = root.getAttribute("data-product-id");
    if (!productId) return;

    const addForm = root.querySelector("form.js-cart-add");
    const step = root.querySelector(".js-cart-step");
    const qtyInput = root.querySelector(".js-step-qty");
    const plusBtn = root.querySelector(".js-step-plus");
    const minusBtn = root.querySelector(".js-step-minus");

    let qty = parseIntSafe(root.getAttribute("data-initial-qty"), 0);
    if (!Number.isFinite(qty) || qty < 0) qty = 0;

    const setUI = () => {
      if (!addForm || !step || !qtyInput) return;
      if (qty <= 0) {
        step.hidden = true;
        addForm.hidden = false;
      } else {
        qtyInput.value = String(qty);
        addForm.hidden = true;
        step.hidden = false;
      }
    };

    const commitQty = async (nextQty) => {
      const prev = qty;
      qty = nextQty;
      setUI();

      const ok = await postQty(productId, nextQty);
      if (!ok) {
        qty = prev;
        setUI();
      }
    };

    // ADD -> показывает степпер
    if (addForm) {
      addForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        const prev = qty;
        qty = Math.max(1, prev || 1);
        setUI();

        const r = await postAdd(addForm);
        if (!r.ok) {
          // fallback: обычный сабмит (перезагрузка)
          try { addForm.submit(); } catch (_) {}
          qty = prev;
          setUI();
          return;
        }

        qty = Math.max(1, parseIntSafe(r.qty, 1));
        setUI();
      });
    }

    // PLUS / MINUS
    if (plusBtn) {
      plusBtn.addEventListener("click", () => {
        const next = qty + 1;
        commitQty(next);
      });
    }

    if (minusBtn) {
      minusBtn.addEventListener("click", () => {
        const next = Math.max(0, qty - 1);
        commitQty(next);
      });
    }

    // MANUAL INPUT (как в PDP)
    const parseQty = (v) => {
      if (v === "" || v == null) return null; // временно пусто — ок
      const n = Number(v);
      if (!Number.isFinite(n)) return null;
      return Math.max(0, Math.floor(n));
    };

    let t = null;

    if (qtyInput) {
      qtyInput.addEventListener("input", () => {
        const next = parseQty(qtyInput.value);
        if (next === null) return;

        qty = next;
        setUI();

        if (t) clearTimeout(t);
        t = setTimeout(() => commitQty(next), 350);
      });

      qtyInput.addEventListener("blur", () => {
        if (t) clearTimeout(t);

        const next = parseQty(qtyInput.value);
        const finalNext = (next === null) ? 0 : next;

        qty = finalNext;
        setUI();
        commitQty(finalNext);
      });

      qtyInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          qtyInput.blur();
        }
      });
    }

    setUI();
  };

  // init all widgets on page
  document.querySelectorAll("[data-cart-widget]").forEach(initCartWidget);
})();
