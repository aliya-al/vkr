(() => {
  const form = document.querySelector('[data-search-form]');
  if (!form) return;

  const input = form.querySelector('[data-search-input]');
  const container = form.querySelector('[data-search-suggestions]');
  const endpoint = form.getAttribute('data-suggest-url');

  if (!input || !container || !endpoint) return;

  let timer = null;

  const hide = () => {
    container.hidden = true;
    container.innerHTML = '';
  };

  const render = (items) => {
    if (!items.length) {
      hide();
      return;
    }

    const fragment = document.createDocumentFragment();

    items.slice(0, 6).forEach((item) => {
      const button = document.createElement('button');
      button.className = 'public-search__suggestion';
      button.type = 'button';
      button.dataset.url = item.url || '';

      const title = document.createElement('span');
      title.className = 'public-search__suggestion-title';
      title.textContent = item.title || '';

      const subtitle = document.createElement('span');
      subtitle.className = 'public-search__suggestion-subtitle';
      subtitle.textContent = item.subtitle || '';

      button.append(title, subtitle);
      fragment.append(button);
    });

    container.innerHTML = '';
    container.append(fragment);
    container.hidden = false;
  };

  const loadSuggestions = async () => {
    const q = input.value.trim();
    if (!q) {
      hide();
      return;
    }

    try {
      const res = await fetch(`${endpoint}?q=${encodeURIComponent(q)}`, {
        headers: { Accept: 'application/json' },
      });
      if (!res.ok) {
        hide();
        return;
      }

      const data = await res.json();
      render(Array.isArray(data.items) ? data.items : []);
    } catch {
      hide();
    }
  };

  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = window.setTimeout(loadSuggestions, 180);
  });

  container.addEventListener('click', (event) => {
    const button = event.target.closest('[data-url]');
    if (!button) return;
    const url = button.getAttribute('data-url');
    if (url) window.location.href = url;
  });

  document.addEventListener('click', (event) => {
    if (!form.contains(event.target)) hide();
  });

  input.addEventListener('focus', () => {
    if (input.value.trim()) loadSuggestions();
  });
})();
