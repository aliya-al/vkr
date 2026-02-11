// app/static/js/admin/products_create.js
(function () {
  const MAX_PREVIEWS = 3;

  function renderPreviews(previewsEl, files) {
    if (!previewsEl) return;
    previewsEl.innerHTML = "";

    if (!files || !files.length) return;

    const count = Math.min(files.length, MAX_PREVIEWS);

    for (let i = 0; i < count; i++) {
      const f = files[i];
      if (!f || !f.type || !f.type.startsWith("image/")) continue;

      const wrap = document.createElement("span");
      wrap.className = "pc-preview";

      const img = document.createElement("img");
      img.alt = "";
      wrap.appendChild(img);
      previewsEl.appendChild(wrap);

      const reader = new FileReader();
      reader.onload = function (e) {
        img.src = e.target && e.target.result ? e.target.result : "";
      };
      reader.readAsDataURL(f);
    }

    if (files.length > MAX_PREVIEWS) {
      const more = document.createElement("span");
      more.className = "pc-previewMore";
      more.textContent = `+${files.length - MAX_PREVIEWS}`;
      previewsEl.appendChild(more);
    }
  }

  function updateBox(box) {
    const input = box.querySelector(".pc-file__input");
    const title = box.querySelector("[data-title]");
    const hint  = box.querySelector("[data-hint]");
    const clear = box.querySelector("[data-clear]");
    const previewsEl = box.querySelector("[data-previews]");

    if (!input || !title || !hint) return;

    const files = input.files;

    if (files && files.length) {
      box.classList.add("is-picked");

      if (files.length === 1) {
        title.textContent = files[0].name || "Файл выбран";
        hint.textContent = "Готово";
      } else {
        title.textContent = `Выбрано файлов: ${files.length}`;
        hint.textContent = "Готово";
      }

      if (clear) clear.disabled = false;
      renderPreviews(previewsEl, files);
    } else {
      box.classList.remove("is-picked");

      title.textContent = title.getAttribute("data-default") || "Выбрать файл";
      hint.textContent  = hint.getAttribute("data-default")  || "";

      if (clear) clear.disabled = true;
      if (previewsEl) previewsEl.innerHTML = "";
    }
  }

  function initBox(box) {
    const title = box.querySelector("[data-title]");
    const hint  = box.querySelector("[data-hint]");
    const input = box.querySelector(".pc-file__input");
    const clear = box.querySelector("[data-clear]");

    if (title && !title.getAttribute("data-default")) {
      title.setAttribute("data-default", title.textContent);
    }
    if (hint && !hint.getAttribute("data-default")) {
      hint.setAttribute("data-default", hint.textContent);
    }

    if (input) {
      input.addEventListener("change", function () {
        updateBox(box);
      });
    }

    if (clear) {
      clear.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (input) input.value = "";
        updateBox(box);
      });
    }

    updateBox(box);
  }

  document.querySelectorAll("[data-file]").forEach(initBox);
})();
