(() => {
  const consentCookieName = "cookie_consent_accepted";
  const consentMaxAgeSeconds = 60 * 60 * 24 * 365;

  const banner = document.getElementById("cookieConsent");
  const text = document.getElementById("cookieConsentText");
  const toggleButton = document.getElementById("cookieConsentToggle");
  const acceptButton = document.getElementById("cookieConsentAccept");

  if (!banner || !text || !toggleButton || !acceptButton) {
    return;
  }

  const hasConsent = document.cookie
    .split(";")
    .map((entry) => entry.trim())
    .some((entry) => entry.startsWith(`${consentCookieName}=1`));

  if (!hasConsent) {
    banner.hidden = false;
  }

  const toggleDetails = () => {
    const isExpanded = banner.classList.toggle("cookie-consent--expanded");
    toggleButton.setAttribute("aria-expanded", String(isExpanded));
  };

  toggleButton.addEventListener("click", toggleDetails);

  text.addEventListener("click", (event) => {
    const clickedControl = event.target.closest("button");
    if (clickedControl && clickedControl !== toggleButton) {
      return;
    }

    if (event.target === text || event.target.closest(".cookie-consent__details")) {
      toggleDetails();
    }
  });

  acceptButton.addEventListener("click", () => {
    document.cookie = `${consentCookieName}=1; Max-Age=${consentMaxAgeSeconds}; Path=/; SameSite=Lax`;
    banner.hidden = true;
  });
})();
