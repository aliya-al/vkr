(() => {
  const input = document.getElementById("searchInput");
  const box = document.getElementById("searchSuggest");

  if (!input || !box) return;

  const suggestUrl = input.dataset.suggestUrl;
  if (!suggestUrl) return;

  let timer = null;

  const hide = () => {
    box.hidden = true;
    box.innerHTML = "";
  };

  const renderItems = (items) => {
    if (!items.length) {
      hide();
      return;
    }

    box.innerHTML = items
      .slice(0, 6)
      .map((item) => {
        const typeLabel = item.type === "category" ? "Категория" : "Товар";
        return `
          <a class="search-suggest__item" href="${item.url}">
            <span class="search-suggest__type">${typeLabel}</span>
            <span>${item.label}</span>
          </a>
        `;
      })
      .join("");

    box.hidden = false;
  };

  const load = async () => {
    const value = input.value.trim();
    if (value.length < 2) {
      hide();
      return;
    }

    try {
      const res = await fetch(`${suggestUrl}?q=${encodeURIComponent(value)}`, {
        credentials: "same-origin",
      });
      if (!res.ok) {
        hide();
        return;
      }
      const data = await res.json();
      renderItems(Array.isArray(data.items) ? data.items : []);
    } catch (_) {
      hide();
    }
  };

  input.addEventListener("input", () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(load, 180);
  });

  input.addEventListener("blur", () => {
    setTimeout(hide, 120);
  });

  input.addEventListener("focus", () => {
    if (input.value.trim().length >= 2) {
      load();
    }
  });
})();
