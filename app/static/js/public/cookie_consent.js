(() => {
  const consentCookieName = "cookie_consent_accepted";
  const consentMaxAgeSeconds = 60 * 60 * 24 * 365;

  const banner = document.getElementById("cookieConsent");
  const toggleButton = document.getElementById("cookieConsentToggle");
  const details = document.getElementById("cookieConsentDetails");
  const acceptButton = document.getElementById("cookieConsentAccept");

  if (!banner || !toggleButton || !details || !acceptButton) {
    return;
  }

  const hasConsent = document.cookie
    .split(";")
    .map((entry) => entry.trim())
    .some((entry) => entry.startsWith(`${consentCookieName}=1`));

  if (!hasConsent) {
    banner.hidden = false;
  }

  toggleButton.addEventListener("click", () => {
    const isExpanded = banner.classList.toggle("cookie-consent--expanded");
    toggleButton.setAttribute("aria-expanded", String(isExpanded));
    details.setAttribute("aria-hidden", String(!isExpanded));
  });

  acceptButton.addEventListener("click", () => {
    const secureFlag = window.location.protocol === "https:" ? "; Secure" : "";
    document.cookie = `${consentCookieName}=1; Max-Age=${consentMaxAgeSeconds}; Path=/; SameSite=Lax${secureFlag}`;
    banner.hidden = true;
  });
})();
