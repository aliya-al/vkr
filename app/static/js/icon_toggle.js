(() => {
  const forms = document.querySelectorAll("form.js-icon-toggle");
  if (!forms.length) return;

  const postForm = async (form) => {
    const action = form.getAttribute("action");
    const data = new URLSearchParams(new FormData(form));

    const btn = form.querySelector("button.icon-btn");
    const card = form.closest("article.p-card");

    if (btn) btn.classList.toggle("is-active");

    try {
      const res = await fetch(action, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
        body: data.toString(),
        credentials: "same-origin",
        redirect: "follow",
      });

      if (!res.ok) {
        if (btn) btn.classList.toggle("is-active");
        return;
      }

      // на странице /favorites при снятии лайка — убираем карточку
      if (action === "/favorites/toggle" && btn && !btn.classList.contains("is-active") && card) {
        // удаляем только если мы реально на странице избранного
        if (document.body && document.body.querySelector(".fav")) {
          card.remove();
          if (document.querySelectorAll("article.p-card").length === 0) window.location.reload();
        }
      }
    } catch (_) {
      if (btn) btn.classList.toggle("is-active");
    }
  };

  forms.forEach((form) => {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      postForm(form);
    });
  });
})();
