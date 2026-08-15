(() => {
  const EN_PATH_PREFIX = "/bien-penser-biais-cognitifs/en/";
  const panels = Array.from(document.querySelectorAll("[data-not-found-locale]"));
  if (!panels.length) return;

  const normalizeLocale = (value) => {
    const locale = String(value || "").toLocaleLowerCase().split("-")[0];
    return locale === "en" || locale === "fr" ? locale : null;
  };

  const readPreference = () => {
    try {
      return normalizeLocale(window.localStorage.getItem("bienpenser.locale"));
    } catch {
      return null;
    }
  };

  const path = window.location.pathname;
  const pathRequestsEnglish = path === EN_PATH_PREFIX.slice(0, -1)
    || path.startsWith(EN_PATH_PREFIX)
    || /^\/en(?:\/|$)/.test(path);
  const preference = readPreference();
  const browserLocale = (window.navigator.languages || [window.navigator.language])
    .map(normalizeLocale)
    .find(Boolean) || null;
  const locale = pathRequestsEnglish || preference === "en"
    ? "en"
    : preference || browserLocale || "fr";
  const selected = panels.find((panel) => panel.dataset.notFoundLocale === locale);

  if (!selected) return;
  document.documentElement.lang = locale;
  document.body.dataset.activeLocale = locale;
  panels.forEach((panel) => {
    panel.hidden = panel !== selected;
  });

  if (selected.dataset.notFoundTitle) document.title = selected.dataset.notFoundTitle;
})();
