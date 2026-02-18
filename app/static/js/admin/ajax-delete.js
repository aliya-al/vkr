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

  const readErrorText = async (res) => {
    const contentType = res.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
      const data = await res.json().catch(() => null);
      if (data?.detail) return String(data.detail);
      if (data?.message) return String(data.message);
    }

    const text = await res.text().catch(() => "");
    if (!text) return "";

    return text.length > 300 ? `${text.slice(0, 300)}…` : text;
  };

  document.addEventListener("submit", async (e) => {
    const form = e.target.closest("form[data-ajax-delete]");
    if (!form) return;

    e.preventDefault();

    const confirmText = form.dataset.confirm;
    if (confirmText && !window.confirm(confirmText)) {
      return;
    }

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
      alert("Ошибка сети. Попробуйте ещё раз.");
      return;
    }

    if (!res.ok) {
      const msg = (await readErrorText(res)) || "Не удалось удалить запись.";
      alert(msg);
      return;
    }

    const row = form.closest("[data-delete-item]") || form.closest("tr, article, li, .card");
    if (row) row.remove();

    alert("Удалено");
  });
})();
