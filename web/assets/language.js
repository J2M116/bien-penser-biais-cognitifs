(() => {
  const LOCALE_KEY = "bienpenser.locale";
  const DISMISS_KEY = "bienpenser.languageSuggestion.dismissed";
  const supportedLocales = new Set(["fr", "en"]);
  const choices = Array.from(document.querySelectorAll("[data-language-choice]"));

  const normalizeLocale = (value) => {
    const locale = String(value || "").toLocaleLowerCase().split("-")[0];
    return supportedLocales.has(locale) ? locale : null;
  };

  const readStorage = (storageName, key) => {
    try {
      return window[storageName].getItem(key);
    } catch {
      return null;
    }
  };

  const writeStorage = (storageName, key, value) => {
    try {
      window[storageName].setItem(key, value);
    } catch {
      // Browsing can continue when storage is unavailable or blocked.
    }
  };

  choices.forEach((choice) => {
    choice.addEventListener("click", () => {
      const locale = normalizeLocale(choice.dataset.languageChoice);
      if (locale) writeStorage("localStorage", LOCALE_KEY, locale);
    });
  });

  const storedLocale = normalizeLocale(readStorage("localStorage", LOCALE_KEY));
  const browserLocale = (window.navigator.languages || [window.navigator.language])
    .map(normalizeLocale)
    .find(Boolean) || null;
  const preferredLocale = storedLocale || browserLocale;
  const currentLocale = normalizeLocale(document.documentElement.lang) || "fr";

  if (!document.body.classList.contains("home-page") || !preferredLocale) return;

  document.querySelectorAll("[data-language-suggestion][data-suggestion-locale]").forEach((suggestion) => {
    const suggestedLocale = normalizeLocale(suggestion.dataset.suggestionLocale);
    const dismissed = readStorage(
      "sessionStorage",
      `${DISMISS_KEY}.${suggestedLocale || "unknown"}`,
    ) === "true";
    const shouldReveal = suggestedLocale === preferredLocale
      && suggestedLocale !== currentLocale
      && !dismissed;

    if (!shouldReveal) return;
    suggestion.hidden = false;

    const dismiss = suggestion.querySelector("[data-language-suggestion-dismiss]");
    dismiss?.addEventListener("click", () => {
      writeStorage("sessionStorage", `${DISMISS_KEY}.${suggestedLocale}`, "true");
      suggestion.hidden = true;

      const matchingChoices = choices.filter(
        (choice) => !choice.closest("[data-language-suggestion]")
          && normalizeLocale(choice.dataset.languageChoice) === suggestedLocale,
      );
      const languageChoice = matchingChoices.find((choice) => choice.getClientRects().length > 0)
        || matchingChoices[0];
      const main = document.querySelector("main");
      const focusTarget = languageChoice || main;
      if (focusTarget === main && !main?.hasAttribute("tabindex")) main?.setAttribute("tabindex", "-1");
      focusTarget?.focus({ preventScroll: true });
    });
  });
})();
