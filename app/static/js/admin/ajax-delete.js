(() => {
  const getCsrfToken = () => {
    const cookie = document.cookie || "";
    const names = ["csrftoken", "csrf_token", "csrf"];

    for (const name of names) {
      const match = cookie.match(new RegExp(`(?:^|; )${name}=([^;]+)`));
      if (match?.[1]) {
        return decodeURIComponent(match[1]);
      }
    }

    return "";
  };

  const showMessage = (text, type = "ok") => {
    const note = document.createElement("div");
    note.className = `admin-toast admin-toast--${type}`;
    note.textContent = text;
    note.style.cssText = [
      "position:fixed",
      "right:16px",
      "bottom:16px",
      "z-index:9999",
      "padding:10px 12px",
      "border-radius:10px",
      "border:1px solid var(--color-line)",
      "background:var(--color-surface)",
      "font-size:var(--fs-xs)",
      type === "error" ? "color:var(--color-danger, #b91c1c)" : "color:var(--color-text)",
    ].join(";");

    document.body.appendChild(note);
    window.setTimeout(() => note.remove(), 1800);
  };

  const readErrorText = async (res) => {
    const contentType = res.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
      const data = await res.json().catch(() => null);
      if (data?.detail) return String(data.detail);
      if (data?.message) return String(data.message);
      if (data?.error) return String(data.error);
    }

    const text = await res.text().catch(() => "");
    if (!text) return "";

    return text.length > 300 ? `${text.slice(0, 300)}…` : text;
  };

  document.addEventListener("submit", async (e) => {
    const form = e.target.closest("form[data-ajax-delete]");
    if (!form) return;

    const confirmText = form.dataset.confirm;
    if (confirmText && !window.confirm(confirmText)) {
      e.preventDefault();
      return;
    }

    if (!form.dataset.ajaxDeleteScope) {
      return;
    }

    e.preventDefault();

    const body = new URLSearchParams(new FormData(form));
    const headers = {
      Accept: "application/json",
      "X-Requested-With": "fetch",
    };

    const csrf = getCsrfToken();
    if (csrf) {
      headers["X-CSRFToken"] = csrf;
      headers["X-CSRF-Token"] = csrf;
    }

    let res;
    try {
      res = await fetch(form.action, {
        method: (form.method || "POST").toUpperCase(),
        credentials: "same-origin",
        headers,
        body,
      });
    } catch (_) {
      showMessage("Ошибка сети. Попробуйте ещё раз.", "error");
      return;
    }

    if (!res.ok) {
      const msg = (await readErrorText(res)) || "Не удалось удалить запись.";
      showMessage(msg, "error");
      return;
    }

    const row = form.closest("[data-delete-item]") || form.closest("tr, article, li, .card");
    if (row) row.remove();

    showMessage("Удалено", "ok");
  });
})();
