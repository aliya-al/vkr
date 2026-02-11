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
