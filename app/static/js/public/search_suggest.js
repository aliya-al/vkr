(() => {
  const form = document.querySelector('[data-search-form]');
  const input = document.querySelector('[data-search-input]');
  const box = document.querySelector('[data-search-suggestions]');

  if (!form || !input || !box) return;

  let timer = null;

  const hide = () => {
    box.hidden = true;
    box.innerHTML = '';
  };

  const render = (items) => {
    if (!items.length) {
      hide();
      return;
    }

    box.innerHTML = '';
    items.slice(0, 6).forEach((item) => {
      const link = document.createElement('a');
      link.className = 'public-search__suggestion';
      link.href = item.url;
      link.textContent = item.name || '';

      const type = document.createElement('small');
      type.textContent = item.type === 'category' ? 'категория' : 'товар';
      link.appendChild(type);

      box.appendChild(link);
    });
    box.hidden = false;
  };

  const load = async (query) => {
    try {
      const resp = await fetch(`/search/suggest?q=${encodeURIComponent(query)}`);
      if (!resp.ok) {
        hide();
        return;
      }
      const data = await resp.json();
      render(Array.isArray(data.items) ? data.items : []);
    } catch {
      hide();
    }
  };

  input.addEventListener('input', () => {
    const q = input.value.trim();
    if (timer) clearTimeout(timer);
    if (!q) {
      hide();
      return;
    }

    timer = setTimeout(() => {
      load(q);
    }, 180);
  });

  document.addEventListener('click', (evt) => {
    if (!form.contains(evt.target)) hide();
  });

  input.addEventListener('keydown', (evt) => {
    if (evt.key === 'Escape') hide();
  });
})();
