(() => {
  const qs = (s, r = document) => r.querySelector(s);
  const qsa = (s, r = document) => Array.from(r.querySelectorAll(s));

  const digitsOnly = (s) => (s || "").replace(/\D/g, "");

  const normalizeRu = (digits) => {
    if (!digits) return "";
    if (digits[0] === "9") digits = "7" + digits;
    if (digits[0] === "8") digits = "7" + digits.slice(1);
    if (digits[0] !== "7") return digits;
    return digits.slice(0, 11);
  };

  const formatRu = (digits11) => {
    if (!digits11) return "";
    const d = digits11;
    const a = d.slice(1, 4);
    const b = d.slice(4, 7);
    const c = d.slice(7, 9);
    const e = d.slice(9, 11);

    let out = "+7";
    if (a) out += ` (${a}`;
    if (a.length === 3) out += ")";
    if (b) out += ` ${b}`;
    if (c) out += `-${c}`;
    if (e) out += `-${e}`;
    return out;
  };

  const parseNum = (v, fallback = 0) => {
    const n = parseInt(String(v ?? "").replace(/[^\d-]/g, ""), 10);
    return Number.isFinite(n) ? n : fallback;
  };

  const parseFloatNum = (v, fallback = 0) => {
    const n = parseFloat(String(v ?? "").replace(",", "."));
    return Number.isFinite(n) ? n : fallback;
  };

  const formatMoney = (n) => `${parseNum(n)} ₽`;
  const cleanId = (v) => {
    const s = String(v ?? "").trim();
    if (!s || s === "None" || s === "null" || s === "undefined") return "";
    return s;
  };

  const getForm = () => qs("#reqNewForm");
  const getCartPrefix = () => getForm()?.dataset?.cartPrefix || "/admin/requests/new";

  const getDraft = () => {
    const form = getForm();
    if (!form) return {};
    const fd = new FormData(form);
    const out = {};
    [
      "customer_name",
      "customer_phone",
      "delivery_type",
      "pickup_address",
      "delivery_address",
      "comment",
      "created_at",
      "status",
      "manager_id",
    ].forEach((k) => (out[k] = String(fd.get(k) || "")));
    return out;
  };

  const postForm = async (url, data) => {
    const body = new URLSearchParams();
    Object.entries(data || {}).forEach(([k, v]) => body.set(k, String(v)));
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        Accept: "application/json",
        "X-Requested-With": "fetch",
      },
      credentials: "same-origin",
      body: body.toString(),
    });
    if (!res.ok) {
  const txt = await res.text().catch(() => "");
  console.warn("cart api error", res.status, url, txt);
  return null;
}

    return res.json().catch(() => ({}));
  };

  const syncInQtyInPicker = (productId, qty) => {
    const btn = qs(`[data-add][data-product-id="${productId}"]`);
    const card = btn?.closest(".reqn-prod");
    if (!card) return;
    const inQty = card.querySelector("[data-inqty]");
    const val = card.querySelector("[data-inqty-val]");
    if (!inQty || !val) return;

    const q = parseNum(qty, 0);
    if (q > 0) {
      val.textContent = String(q);
      inQty.hidden = false;
    } else {
      inQty.hidden = true;
    }
  };

  const updateTotals = () => {
    const sumEl = qs("[data-total-price]");
    const baseEl = qs("[data-total-base]");
    const wEl = qs("[data-total-weight]");
    const vEl = qs("[data-total-volume]");

    let total = 0;
    let base = 0;
    let weight = 0;
    let volume = 0;

    qsa("[data-cart-item]").forEach((it) => {
      const qty = Math.max(1, parseNum(it.querySelector("[data-input]")?.value, 1));
      const unit = parseNum(it.getAttribute("data-unit"), 0);
      const baseUnit = parseNum(it.getAttribute("data-base-unit"), unit);
      const w = parseFloatNum(it.getAttribute("data-weight"), 0);
      const vol = parseFloatNum(it.getAttribute("data-volume"), 0);

      total += unit * qty;
      base += baseUnit * qty;
      weight += w * qty;
      volume += vol * qty;
    });

    if (sumEl) sumEl.textContent = formatMoney(total);

    if (baseEl) {
      if (base > total) {
        baseEl.textContent = formatMoney(base);
        baseEl.hidden = false;
      } else {
        baseEl.hidden = true;
      }
    }

    if (wEl) wEl.textContent = `${weight.toFixed(1)} кг`;
    if (vEl) vEl.textContent = `${volume.toFixed(3)} м³`;
  };

  const ensureEmptyCartState = () => {
    const wrap = qs("#reqCartList");
    const card = wrap?.closest(".reqn-card");
    if (!card) return;

    const hasItems = qsa("[data-cart-item]", wrap).length > 0;
    const empty = card.querySelector(".reqn-empty");

    if (hasItems) {
      if (empty) empty.remove();
    } else {
      if (!empty) {
        const div = document.createElement("div");
        div.className = "reqn-empty";
        div.textContent = "Пока нет товаров. Добавь сверху.";
        card.appendChild(div);
      }
    }

    const clearBtn = card.querySelector('button[type="submit"]');
    if (clearBtn) clearBtn.disabled = !hasItems;

    updateTotals();
  };

  const buildCartItemFromPicker = (productId, qty) => {
    const prod = qs(`.reqn-prod[data-product-id="${productId}"]`);
    if (!prod) return null;

    const name = prod.querySelector(".reqn-pName")?.textContent?.trim() || "Товар";
    const img = prod.getAttribute("data-img") || "";
    const unit = parseNum(prod.getAttribute("data-unit"), 0);
    const baseUnit = parseNum(prod.getAttribute("data-base"), unit);
    const w = parseFloatNum(prod.getAttribute("data-weight"), 0);
    const vol = parseFloatNum(prod.getAttribute("data-volume"), 0);

    const item = document.createElement("article");
    item.className = "reqn-cartItem";
    item.setAttribute("data-cart-item", "");
    item.setAttribute("data-product-id", productId);
    item.setAttribute("data-unit", String(unit));
    item.setAttribute("data-base-unit", String(baseUnit));
    item.setAttribute("data-weight", String(w));
    item.setAttribute("data-volume", String(vol));

    item.innerHTML = `
      <div class="reqn-ciMedia">
        ${img ? `<img class="reqn-ciImg" src="${img}" alt="${name}">` : `<span class="reqn-ciPh" aria-hidden="true"></span>`}
      </div>
      <div class="reqn-ciBody">
        <div class="reqn-ciName" title="${name}">${name}</div>
        <div class="reqn-ciMeta">
          ${baseUnit > unit ? `<del class="reqn-ciOld">${formatMoney(baseUnit)}</del>` : ""}
          <span class="reqn-ciUnit">${formatMoney(unit)}/шт.</span>
        </div>
        <div class="reqn-ciControls">
          <div class="reqn-qty" data-qty>
            <button class="reqn-qtyBtn" type="button" data-minus>−</button>
            <input class="reqn-qtyInput" type="number" min="1" step="1" value="${qty}" data-input inputmode="numeric" pattern="[0-9]*">
            <button class="reqn-qtyBtn" type="button" data-plus>+</button>
          </div>
          <div class="reqn-ciLine" data-line-total>${formatMoney(unit * qty)}</div>
          <button class="reqn-iconBtn" type="button" data-remove title="Удалить" aria-label="Удалить">×</button>
        </div>
      </div>
    `;
    return item;
  };

  const initPhone = () => {
    const phoneEl = qs("#customerPhone");
    if (!phoneEl) return;

    const apply = () => {
      const raw = digitsOnly(phoneEl.value);
      const norm = normalizeRu(raw);
      phoneEl.value = formatRu(norm);
      const ok = norm.length === 11 && norm[0] === "7";
      phoneEl.setCustomValidity(ok || phoneEl.value === "" ? "" : "Введите телефон в формате +7 (999) 999-99-99");
    };

    phoneEl.addEventListener("input", apply);
    phoneEl.addEventListener("blur", apply);
    apply();

    const form = getForm();
    if (form) form.addEventListener("submit", () => apply());
  };

  const initDeliveryToggle = () => {
    const btns = qsa(".reqn-toggleBtn");
    const deliveryType = qs("#deliveryType");
    const panePickup = qs("#panePickup");
    const paneDelivery = qs("#paneDelivery");
    const pickupAddress = qs("#pickupAddress");
    const deliveryAddress = qs("#deliveryAddress");

    if (!deliveryType || btns.length === 0) return;

    const setMode = (mode) => {
      deliveryType.value = mode;

      const isPickup = mode === "pickup";
      panePickup?.classList.toggle("is-hidden", !isPickup);
      paneDelivery?.classList.toggle("is-hidden", isPickup);

      if (pickupAddress) pickupAddress.required = isPickup;
      if (deliveryAddress) deliveryAddress.required = !isPickup;

      btns.forEach((b) => {
        const active = b.dataset.value === mode;
        b.classList.toggle("is-active", active);
        b.setAttribute("aria-pressed", active ? "true" : "false");
      });
    };

    btns.forEach((b) =>
      b.addEventListener("click", (e) => {
        e.preventDefault();
        setMode(b.dataset.value);
      })
    );

    setMode(deliveryType.value || "pickup");
  };

  const initSearch = () => {
    const inp = qs("#prodSearch");
    const list = qs("#prodList");
    if (!inp || !list) return;

    inp.addEventListener("input", () => {
      const q = (inp.value || "").trim().toLowerCase();
      qsa(".reqn-prod", list).forEach((row) => {
        const name = row.getAttribute("data-name") || "";
        row.hidden = q ? !name.includes(q) : false;
      });
    });
  };

  const initAddButtons = () => {
    const list = qs("#prodList");
    if (!list) return;

    list.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-add]");
      if (!btn) return;

      e.preventDefault();

      const productId = btn.getAttribute("data-product-id");
      if (!productId) return;

      const prefix = getCartPrefix();

      btn.disabled = true;
      const r = await postForm(`${prefix}/cart/add`, { product_id: productId, qty: 1 });

      btn.disabled = false;

      if (!r || r.ok !== true) return;

      const newQty = parseNum(r.qty, 1);
      syncInQtyInPicker(productId, newQty);

      const wrap = qs("#reqCartList");
      if (!wrap) return;

      const existing = wrap.querySelector(`[data-cart-item][data-product-id="${productId}"]`);
      if (existing) {
        const input = existing.querySelector("[data-input]");
        if (input) input.value = String(newQty);

        const unit = parseNum(existing.getAttribute("data-unit"), 0);
        const lineEl = existing.querySelector("[data-line-total]");
        if (lineEl) lineEl.textContent = formatMoney(unit * newQty);

        ensureEmptyCartState();
        updateTotals();
        return;
      }

      const item = buildCartItemFromPicker(productId, newQty);
      if (!item) return;

      if (r.order_item_id) item.setAttribute("data-order-item-id", String(r.order_item_id));

      wrap.appendChild(item);
      ensureEmptyCartState();
      updateTotals();
    });
  };

  const initCartControls = () => {
    const wrap = qs("#reqCartList");
    if (!wrap) return;

    const commit = async (item, pid, orderItemId, nextQty) => {
      const input = item.querySelector("[data-input]");
      if (input) input.value = String(nextQty);

      const unit = parseNum(item.getAttribute("data-unit"), 0);
      const lineEl = item.querySelector("[data-line-total]");
      if (lineEl) lineEl.textContent = formatMoney(unit * nextQty);

      updateTotals();

      const prefix = getCartPrefix();
      const r = await postForm(`${prefix}/cart/update`, { product_id: pid || "", order_item_id: orderItemId || "", qty: nextQty });

      if (!r || r.ok !== true) return;

      if (pid) syncInQtyInPicker(pid, nextQty);
      updateTotals();
    };

    wrap.addEventListener("click", async (e) => {
      const item = e.target.closest("[data-cart-item]");
      if (!item) return;

      e.preventDefault();

      const pid = cleanId(item.getAttribute("data-product-id"));
      const orderItemId = cleanId(item.getAttribute("data-order-item-id"));
      if (!pid && !orderItemId) return;

      const input = item.querySelector("[data-input]");
      const cur = input ? Math.max(1, parseNum(input.value, 1)) : 1;

      if (e.target.closest("[data-minus]")) {
        const next = Math.max(1, cur - 1);
        await commit(item, pid, orderItemId, next);
        return;
      }

      if (e.target.closest("[data-plus]")) {
        const next = cur + 1;
        await commit(item, pid, orderItemId, next);
        return;
      }

      if (e.target.closest("[data-remove]")) {
        const prefix = getCartPrefix();
        const r = await postForm(`${prefix}/cart/remove`, { product_id: pid || "", order_item_id: orderItemId || "" });
        if (!r || r.ok !== true) return;

        item.remove();
        if (pid) syncInQtyInPicker(pid, 0);
        ensureEmptyCartState();
      }
    });

    wrap.addEventListener("change", async (e) => {
      const input = e.target.closest("[data-input]");
      if (!input) return;

      const item = input.closest("[data-cart-item]");
      const pid = cleanId(item?.getAttribute("data-product-id"));
      const orderItemId = cleanId(item?.getAttribute("data-order-item-id"));
      if (!pid && !orderItemId) return;

      const next = Math.max(1, parseNum(input.value, 1));
      input.value = String(next);

      const unit = parseNum(item.getAttribute("data-unit"), 0);
      const lineEl = item.querySelector("[data-line-total]");
      if (lineEl) lineEl.textContent = formatMoney(unit * next);

      const prefix = getCartPrefix();
      const r = await postForm(`${prefix}/cart/update`, { product_id: pid || "", order_item_id: orderItemId || "", qty: next });
      if (!r || r.ok !== true) return;

      if (pid) syncInQtyInPicker(pid, next);
      updateTotals();
    });
  };

  const initClearCart = () => {
    const form = qs(".reqn-clearForm");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();

      const prefix = getCartPrefix();
      const r = await postForm(`${prefix}/cart/clear`, {});
      if (!r || r.ok !== true) return;

      qsa("[data-cart-item]").forEach((el) => el.remove());
      qsa(".reqn-prod [data-inqty]").forEach((el) => (el.hidden = true));
      ensureEmptyCartState();
    });
  };

  initPhone();
  initDeliveryToggle();
  initSearch();
  initAddButtons();
  initCartControls();
  initClearCart();
  ensureEmptyCartState();
})();
