(() => {
  const source = document.querySelector("#app-translations");
  let payload = {};

  try {
    payload = source?.textContent ? JSON.parse(source.textContent) : {};
  } catch (error) {
    console.warn("Unable to read application translations.", error);
  }

  const locale = typeof payload.locale === "string" && payload.locale
    ? payload.locale
    : document.documentElement.lang || "fr";
  const localeTag = typeof payload.localeTag === "string" && payload.localeTag
    ? payload.localeTag
    : locale;
  const strings = payload.strings && typeof payload.strings === "object"
    ? payload.strings
    : {};
  const missing = (key) => `[${key}]`;

  const lookup = (key) => {
    if (Object.prototype.hasOwnProperty.call(strings, key)) return strings[key];
    return String(key).split(".").reduce(
      (value, part) => value && typeof value === "object" ? value[part] : undefined,
      strings,
    );
  };

  const interpolate = (template, params = {}) => String(template).replace(
    /\{([a-zA-Z0-9_]+)\}/g,
    (match, name) => Object.prototype.hasOwnProperty.call(params, name)
      ? String(params[name])
      : match,
  );

  const t = (key, params = {}) => {
    const value = lookup(key);
    return typeof value === "string" ? interpolate(value, params) : missing(key);
  };

  const numberFormatter = (options = {}) => new Intl.NumberFormat(localeTag, options);
  const dateFormatter = (options = {}) => new Intl.DateTimeFormat(localeTag, options);
  const pluralRules = new Intl.PluralRules(localeTag);
  const collator = new Intl.Collator(localeTag, { numeric: true, sensitivity: "base" });

  const formatNumber = (value, options = {}) => {
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value ?? "");
    return numberFormatter(options).format(number);
  };

  const toDate = (value) => {
    if (value instanceof Date) return value;
    if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
      const [year, month, day] = value.split("-").map(Number);
      return new Date(year, month - 1, day);
    }
    return new Date(value);
  };

  const formatDate = (value, options = { day: "numeric", month: "long", year: "numeric" }) => {
    const date = toDate(value);
    if (Number.isNaN(date.getTime())) return String(value ?? "");
    return dateFormatter(options).format(date);
  };

  const tp = (key, count, params = {}) => {
    const number = Number(count);
    const category = Number.isFinite(number) ? pluralRules.select(number) : "other";
    const direct = lookup(key);
    let template = null;

    if (direct && typeof direct === "object") {
      if (number === 0 && typeof direct.zero === "string") template = direct.zero;
      if (template === null && typeof direct[category] === "string") template = direct[category];
      if (template === null && typeof direct.other === "string") template = direct.other;
    }

    if (template === null && number === 0 && typeof lookup(`${key}.zero`) === "string") {
      template = lookup(`${key}.zero`);
    }
    if (template === null && typeof lookup(`${key}.${category}`) === "string") {
      template = lookup(`${key}.${category}`);
    }
    if (template === null && typeof lookup(`${key}.other`) === "string") {
      template = lookup(`${key}.other`);
    }
    if (template === null && typeof direct === "string") template = direct;
    if (template === null) return missing(key);

    return interpolate(template, {
      ...params,
      count: formatNumber(number),
    });
  };

  window.BienPenserI18n = Object.freeze({
    locale,
    localeTag,
    t,
    tp,
    formatDate,
    formatNumber,
    collator,
  });
})();
