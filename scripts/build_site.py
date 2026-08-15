#!/usr/bin/env python3
"""Build the multilingual static cognitive-bias catalogue without dependencies."""

from __future__ import annotations

import argparse
import html
import json
import posixpath
import re
import shutil
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from urllib.parse import urlencode


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "catalogue" / "biais"
I18N_DIR = PROJECT_ROOT / "catalogue" / "i18n"
WEB_DIR = PROJECT_ROOT / "web"
BUILD_MARKER = ".bien-penser-build"
SUPPORTED_LOCALES = ("fr", "en")

ROUTES = {
    "fr": {
        "home": "",
        "about": "a-propos/",
        "leaderboard": "classement/",
        "bias": "biais/{slug}/",
    },
    "en": {
        "home": "en/",
        "about": "en/about/",
        "leaderboard": "en/ranking/",
        "bias": "en/biases/{slug}/",
    },
}

EVIDENCE_ORDER = {"forte": 0, "moderee": 1, "limitee": 2, "contestee": 3, "a_evaluer": 4}
REVIEW_STATUSES = ("non_revue", "en_revue", "revue")

GITHUB_REPOSITORY = "https://github.com/J2M116/bien-penser-biais-cognitifs"
GITHUB_EDIT_ROOT = f"{GITHUB_REPOSITORY}/edit/main"
GITHUB_NEW_ISSUE = f"{GITHUB_REPOSITORY}/issues/new"
PUBLIC_SITE_URL = "https://j2m116.github.io/bien-penser-biais-cognitifs/"


def load_ui_catalog(locale: str) -> dict[str, object]:
    if locale not in SUPPORTED_LOCALES:
        raise ValueError(f"Unsupported locale: {locale}")
    path = I18N_DIR / locale / "ui.json"
    return json.loads(path.read_text(encoding="utf-8"))


UI = {locale: load_ui_catalog(locale) for locale in SUPPORTED_LOCALES}


def catalog_value(locale: str, key: str) -> object:
    value: object = UI[locale]
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(f"Missing UI key {key!r} for {locale}")
        value = value[part]
    return value


def t(locale: str, key: str, **params: object) -> str:
    value = catalog_value(locale, key)
    if not isinstance(value, str):
        raise TypeError(f"UI key {key!r} is not a string")
    return value.format(**params)


def tp(locale: str, key: str, count: int, **params: object) -> str:
    value = catalog_value(locale, key)
    if not isinstance(value, dict):
        raise TypeError(f"Plural UI key {key!r} is not an object")
    form = "one" if count == 1 else "other"
    rendered = value.get(form)
    if not isinstance(rendered, str):
        raise KeyError(f"Missing plural form {key}.{form} for {locale}")
    return rendered.format(count=count, **params)


@dataclass(frozen=True)
class Bias:
    bias_id: str
    number: int
    slug: str
    locale: str
    name: str
    name_fr: str
    name_en: str
    aliases: tuple[str, ...]
    aliases_fr: tuple[str, ...]
    aliases_en: tuple[str, ...]
    family: str
    importance: int
    evidence: str
    short: str
    example: str
    detail: str
    why: str
    limits: str
    prevention: tuple[str, ...]
    sources: tuple[tuple[str, str], ...]
    review_status: str
    reviewed_on: str | None
    source_path: Path
    canonical_source_path: Path


def parse_scalar(front: str, key: str, default: object = None) -> object:
    match = re.search(rf"^{re.escape(key)}:\s*(.*?)\s*$", front, flags=re.MULTILINE)
    if not match:
        return default
    raw = match.group(1)
    if raw == "null":
        return None
    if raw in {"true", "false"}:
        return raw == "true"
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if raw.startswith('"'):
        return json.loads(raw)
    return raw


def parse_list(front: str, key: str) -> tuple[str, ...]:
    match = re.search(
        rf"^{re.escape(key)}:(?:\s*\[\])?(?P<items>(?:\n  - .*)*)",
        front,
        flags=re.MULTILINE,
    )
    if not match:
        return ()
    values = []
    for raw in re.findall(r"^  - (.*)$", match.group("items"), flags=re.MULTILINE):
        values.append(json.loads(raw) if raw.startswith('"') else raw)
    return tuple(values)


def section(body: str, title: str) -> str:
    match = re.search(
        rf"^## {re.escape(title)}\s*$\n(?P<content>.*?)(?=^## |\Z)",
        body,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group("content").strip() if match else ""


def card_value(body: str, label: str) -> str:
    content = section(body, "Carte")
    match = re.search(rf"^- \*\*{re.escape(label)}\s*:\*\*\s*(.+)$", content, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"Card field not found: {label}")
    return match.group(1).strip()


def paragraphs(raw: str) -> str:
    return "\n\n".join(
        " ".join(line.strip() for line in block.splitlines())
        for block in re.split(r"\n\s*\n", raw.strip())
        if block.strip() and not block.lstrip().startswith("-")
    )


def bullet_values(raw: str) -> tuple[str, ...]:
    return tuple(match.group(1).strip() for match in re.finditer(r"^-\s+(.+)$", raw, flags=re.MULTILINE))


def source_values(raw: str) -> tuple[tuple[str, str], ...]:
    return tuple(
        (match.group(1).strip(), match.group(2).strip())
        for match in re.finditer(r"^- \[(.+?)\]\((https://.+?)\)$", raw, flags=re.MULTILINE)
    )


def parse_review(front: str, path: Path) -> tuple[str, str | None]:
    review_status = str(parse_scalar(front, "review_status", "non_revue"))
    if review_status not in REVIEW_STATUSES:
        raise ValueError(f"Invalid review status {review_status!r}: {path}")
    reviewed_on = parse_scalar(front, "reviewed_on")
    if reviewed_on is not None:
        reviewed_on = str(reviewed_on)
        try:
            date.fromisoformat(reviewed_on)
        except ValueError as error:
            raise ValueError(f"Invalid review date {reviewed_on!r}: {path}") from error
    if review_status == "revue" and reviewed_on is None:
        raise ValueError(f"A reviewed card must have a review date: {path}")
    return review_status, reviewed_on


def read_bias(path: Path) -> Bias | None:
    text = path.read_text(encoding="utf-8")
    pieces = text.split("---", 2)
    if len(pieces) != 3:
        raise ValueError(f"Invalid front matter: {path}")
    front, body = pieces[1], pieces[2].strip()
    if parse_scalar(front, "status") != "documente":
        return None
    importance = parse_scalar(front, "importance")
    if not isinstance(importance, int):
        raise ValueError(f"Missing importance: {path}")
    review_status, reviewed_on = parse_review(front, path)
    name_fr = str(parse_scalar(front, "name_fr"))
    name_en = str(parse_scalar(front, "name_en"))
    aliases_fr = parse_list(front, "aliases_fr")
    aliases_en = parse_list(front, "aliases_en")
    return Bias(
        bias_id=str(parse_scalar(front, "id")),
        number=int(parse_scalar(front, "source_number")),
        slug=path.stem,
        locale="fr",
        name=name_fr,
        name_fr=name_fr,
        name_en=name_en,
        aliases=aliases_fr,
        aliases_fr=aliases_fr,
        aliases_en=aliases_en,
        family=str(parse_scalar(front, "family")),
        importance=importance,
        evidence=str(parse_scalar(front, "evidence_level")),
        short=card_value(body, "En bref"),
        example=card_value(body, "Exemple"),
        detail=paragraphs(section(body, "Description détaillée")),
        why=paragraphs(section(body, "Pourquoi c'est important")),
        limits=paragraphs(section(body, "Limites et nuances")),
        prevention=bullet_values(section(body, "Prévention")),
        sources=source_values(section(body, "Sources de départ")),
        review_status=review_status,
        reviewed_on=reviewed_on,
        source_path=path,
        canonical_source_path=path,
    )


def read_translation(base: Bias, locale: str) -> Bias | None:
    path = I18N_DIR / locale / "biais" / f"{base.slug}.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    pieces = text.split("---", 2)
    if len(pieces) != 3:
        raise ValueError(f"Invalid translation front matter: {path}")
    front, body = pieces[1], pieces[2].strip()
    if parse_scalar(front, "translation_status") != "published":
        return None
    if parse_scalar(front, "locale") != locale:
        raise ValueError(f"Translation locale mismatch: {path}")
    if parse_scalar(front, "translation_of") != base.bias_id:
        raise ValueError(f"Translation source mismatch: {path}")
    heading = re.search(r"^#\s+(.+?)\s*$", body, flags=re.MULTILINE)
    if not heading:
        raise ValueError(f"Missing translation heading: {path}")
    name = heading.group(1).strip()
    expected_name = base.name_en if locale == "en" else name
    if name != expected_name:
        raise ValueError(f"Translation heading must equal name_en for {base.slug}")
    localized_sections = {
        key: section(body, title)
        for key, title in {
            "short": "Short",
            "example": "Example",
            "detail": "Detailed description",
            "why": "Why it matters",
            "limits": "Limits and nuances",
            "prevention": "Prevention",
            "sources": "Sources",
        }.items()
    }
    if any(not value for value in localized_sections.values()):
        raise ValueError(f"Incomplete published translation: {path}")
    sources = source_values(localized_sections["sources"])
    if {url for _, url in sources} != {url for _, url in base.sources}:
        raise ValueError(f"Translation source URLs differ from canonical card: {path}")
    review_status, reviewed_on = parse_review(front, path)
    aliases = base.aliases_en if locale == "en" else ()
    return replace(
        base,
        locale=locale,
        name=name,
        aliases=aliases,
        short=paragraphs(localized_sections["short"]),
        example=paragraphs(localized_sections["example"]),
        detail=paragraphs(localized_sections["detail"]),
        why=paragraphs(localized_sections["why"]),
        limits=paragraphs(localized_sections["limits"]),
        prevention=bullet_values(localized_sections["prevention"]),
        sources=sources,
        review_status=review_status,
        reviewed_on=reviewed_on,
        source_path=path,
    )


def inline_markdown(value: str) -> str:
    escaped = html.escape(value, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    return escaped


def render_paragraphs(value: str) -> str:
    return "\n".join(f"<p>{inline_markdown(block)}</p>" for block in value.split("\n\n") if block)


def route_path(locale: str, route: str, slug: str | None = None) -> str:
    template = ROUTES[locale][route]
    if "{slug}" in template:
        if not slug:
            raise ValueError(f"Route {route} requires a slug")
        return template.format(slug=slug)
    if slug is not None:
        raise ValueError(f"Route {route} does not accept a slug")
    return template


def relative_href(current_path: str, target_path: str) -> str:
    current = current_path.rstrip("/") or "."
    target = target_path.rstrip("/") or "."
    relative = posixpath.relpath(target, current)
    return "./" if relative == "." else f"{relative}/"


def route_href(current_path: str, locale: str, route: str, slug: str | None = None) -> str:
    return relative_href(current_path, route_path(locale, route, slug))


def public_url(path: str) -> str:
    if path.startswith("/") or "://" in path:
        raise ValueError(f"Public path must be project-relative: {path}")
    return f"{PUBLIC_SITE_URL}{path}"


def format_review_date(value: str, locale: str = "fr") -> str:
    parsed = date.fromisoformat(value)
    months = catalog_value(locale, "dates.months")
    if not isinstance(months, list):
        raise TypeError("dates.months must be a list")
    return t(locale, "dates.long", day=parsed.day, month=months[parsed.month - 1], year=parsed.year)


def family_label(locale: str, family: str) -> str:
    labels = catalog_value(locale, "families")
    return str(labels.get(family, family)) if isinstance(labels, dict) else family


def evidence_label(locale: str, evidence: str) -> str:
    labels = catalog_value(locale, "evidence")
    return str(labels.get(evidence, evidence)) if isinstance(labels, dict) else evidence


def review_label(locale: str, status: str) -> str:
    return t(locale, f"review.{status}")


def review_description(locale: str, status: str) -> str:
    return t(locale, f"review.{status}_description")


def importance_marks(level: int, *, label: bool = True, locale: str = "fr") -> str:
    marks = "".join(
        f'<span class="importance-mark{" is-active" if point <= level else ""}" aria-hidden="true"></span>'
        for point in range(1, 6)
    )
    aria = f' aria-label="{html.escape(t(locale, "card.importance_aria", level=level), quote=True)}"' if label else ""
    return f'<span class="importance"{aria}>{marks}<span class="importance-value">{level}/5</span></span>'


def evidence_badge(bias: Bias) -> str:
    return (
        f'<span class="evidence evidence--{html.escape(bias.evidence)}">'
        f'{html.escape(evidence_label(bias.locale, bias.evidence))}</span>'
    )


def family_badge(bias: Bias) -> str:
    return f'<span class="family-tag">{html.escape(family_label(bias.locale, bias.family))}</span>'


def review_badge(bias: Bias) -> str:
    return (
        f'<span class="review-state review-state--{html.escape(bias.review_status)}">'
        f'{html.escape(review_label(bias.locale, bias.review_status))}</span>'
    )


def review_metadata(bias: Bias) -> str:
    reviewed_date = ""
    if bias.reviewed_on:
        label = t(
            bias.locale,
            "review.last_reviewed",
            date=format_review_date(bias.reviewed_on, bias.locale),
        )
        reviewed_date = f'<time datetime="{bias.reviewed_on}">{html.escape(label)}</time>'
    return f'<div class="review-meta">{review_badge(bias)}{reviewed_date}</div>'


def edit_url(bias: Bias) -> str:
    relative_path = bias.source_path.relative_to(PROJECT_ROOT).as_posix()
    return f"{GITHUB_EDIT_ROOT}/{relative_path}"


def review_request_url(bias: Bias, action: str) -> str:
    if action not in {"demarrer", "terminer"}:
        raise ValueError(f"Unknown review action: {action}")
    action_key = "review.issue_start" if action == "demarrer" else "review.issue_finish"
    title = f"REVUE | {action} | {bias.locale} | {bias.slug}"
    body = t(
        bias.locale,
        "review.issue_body",
        name=bias.name,
        language=t(bias.locale, "locale.label"),
        action=t(bias.locale, action_key),
    )
    return f"{GITHUB_NEW_ISSUE}?{urlencode({'title': title, 'body': body})}"


def language_switcher(
    locale: str,
    current_path: str,
    route: str,
    slug: str | None,
    available_locales: tuple[str, ...],
) -> str:
    links = []
    for candidate in available_locales:
        current = ' aria-current="page"' if candidate == locale else ""
        href = route_href(current_path, candidate, route, slug)
        links.append(
            f'<a href="{html.escape(href, quote=True)}" hreflang="{candidate}" lang="{candidate}" '
            f'data-language-choice="{candidate}"{current}>{html.escape(t(candidate, "locale.short"))}</a>'
        )
    return (
        f'<div class="language-switch language-switcher" role="group" data-language-switch '
        f'aria-label="{html.escape(t(locale, "nav.language"), quote=True)}">'
        f'{"".join(links)}</div>'
    )


def account_button(locale: str) -> str:
    return (
        '<button class="account-button" type="button" data-auth-open aria-haspopup="dialog">'
        '<span class="account-dot" aria-hidden="true"></span>'
        f'<span data-account-label>{html.escape(t(locale, "auth.sign_in"))}</span></button>'
    )


def install_button(locale: str) -> str:
    return (
        '<button class="install-button" type="button" data-install-open hidden>'
        f'{html.escape(t(locale, "install.button"))}</button>'
    )


def site_header(
    locale: str,
    current_path: str,
    route: str,
    slug: str | None,
    links: tuple[tuple[str, str, str], ...],
    available_locales: tuple[str, ...],
    *,
    detail: bool = False,
) -> str:
    navigation = "\n      ".join(
        f'<a class="{css_class}" href="{html.escape(href, quote=True)}">{label}</a>'
        for css_class, href, label in links
    )
    home_href = route_href(current_path, locale, "home")
    detail_class = " detail-header" if detail else ""
    return f"""<header class="site-header{detail_class}">
  <div class="header-inner">
    <a class="wordmark" href="{home_href}" aria-label="{html.escape(t(locale, 'nav.home_aria'), quote=True)}">
      <span class="wordmark-mark" aria-hidden="true">P</span>
      <span><strong>{html.escape(t(locale, 'brand.name'))}</strong><small>{html.escape(t(locale, 'brand.subtitle'))}</small></span>
    </a>
    <nav class="header-actions" aria-label="{html.escape(t(locale, 'nav.primary'), quote=True)}">
      {navigation}
      {language_switcher(locale, current_path, route, slug, available_locales)}
      {install_button(locale)}
      {account_button(locale)}
    </nav>
  </div>
</header>"""


def mobile_navigation(
    locale: str,
    current_path: str,
    route: str,
    slug: str | None,
    available_locales: tuple[str, ...],
) -> str:
    home_current = ' aria-current="page"' if route == "home" else ""
    leaderboard_current = ' aria-current="page"' if route == "leaderboard" else ""
    about_current = ' aria-current="page"' if route == "about" else ""
    other_locales = [candidate for candidate in available_locales if candidate != locale]
    language_link = ""
    if other_locales:
        other = other_locales[0]
        language_link = (
            f'<a href="{route_href(current_path, other, route, slug)}" hreflang="{other}" lang="{other}" '
            f'data-language-choice="{other}"><span aria-hidden="true">文</span>{html.escape(t(other, "locale.short"))}</a>'
        )
    modifier = " mobile-nav--4" if language_link else ""
    return f"""<nav class="mobile-nav{modifier}" aria-label="{html.escape(t(locale, 'nav.mobile'), quote=True)}">
  <a href="{html.escape(route_href(current_path, locale, 'home'), quote=True)}"{home_current}><span aria-hidden="true">⌂</span>{html.escape(t(locale, 'nav.catalogue'))}</a>
  <a href="{html.escape(route_href(current_path, locale, 'leaderboard'), quote=True)}"{leaderboard_current}><span aria-hidden="true">↗</span>{html.escape(t(locale, 'nav.leaderboard'))}</a>
  <a href="{html.escape(route_href(current_path, locale, 'about'), quote=True)}"{about_current}><span aria-hidden="true">i</span>{html.escape(t(locale, 'nav.method'))}</a>
  {language_link}
</nav>"""


def auth_dialog(locale: str) -> str:
    return f"""<dialog id="auth-dialog" class="auth-dialog" aria-labelledby="auth-title">
  <div class="auth-dialog-inner">
    <form method="dialog" class="dialog-close-form"><button class="dialog-close" aria-label="{html.escape(t(locale, 'auth.close'), quote=True)}">×</button></form>
    <div data-auth-anonymous>
      <p class="eyebrow">{html.escape(t(locale, 'auth.eyebrow'))}</p>
      <h2 id="auth-title">{html.escape(t(locale, 'auth.title'))}</h2>
      <p class="auth-intro">{html.escape(t(locale, 'auth.intro'))}</p>
      <div class="auth-tabs" role="tablist" aria-label="{html.escape(t(locale, 'auth.tabs_aria'), quote=True)}">
        <button class="is-active" type="button" role="tab" aria-selected="true" data-auth-tab="login">{html.escape(t(locale, 'auth.login_tab'))}</button>
        <button type="button" role="tab" aria-selected="false" data-auth-tab="register">{html.escape(t(locale, 'auth.register_tab'))}</button>
      </div>
      <form class="auth-form" data-auth-form="login">
        <label><span>{html.escape(t(locale, 'auth.email'))}</span><input name="email" type="email" autocomplete="email" required></label>
        <label><span>{html.escape(t(locale, 'auth.password'))}</span><input name="password" type="password" autocomplete="current-password" minlength="6" required></label>
        <button class="auth-submit" type="submit">{html.escape(t(locale, 'auth.login_submit'))}</button>
      </form>
      <form class="auth-form" data-auth-form="register" hidden>
        <label><span>{html.escape(t(locale, 'auth.display_name'))}</span><input name="display_name" type="text" autocomplete="nickname" minlength="2" maxlength="40" required></label>
        <label><span>{html.escape(t(locale, 'auth.email'))}</span><input name="email" type="email" autocomplete="email" required></label>
        <label><span>{html.escape(t(locale, 'auth.password'))}</span><input name="password" type="password" autocomplete="new-password" minlength="6" required></label>
        <button class="auth-submit" type="submit">{html.escape(t(locale, 'auth.register_submit'))}</button>
      </form>
      <p class="auth-message" data-auth-message aria-live="polite"></p>
    </div>
    <div class="auth-profile" data-auth-profile hidden>
      <p class="eyebrow">{html.escape(t(locale, 'auth.profile_eyebrow'))}</p>
      <h2>{html.escape(t(locale, 'auth.hello'))} <span data-profile-name>{html.escape(t(locale, 'auth.member'))}</span>.</h2>
      <p>{html.escape(t(locale, 'auth.profile_intro'))}</p>
      <p class="reviewer-badge" data-reviewer-badge hidden>{html.escape(t(locale, 'auth.reviewer_badge'))}</p>
      <button class="auth-signout" type="button" data-sign-out>{html.escape(t(locale, 'auth.sign_out'))}</button>
    </div>
  </div>
</dialog>"""


def install_dialog(locale: str) -> str:
    return f"""<dialog id="install-dialog" class="install-dialog" aria-labelledby="install-title">
  <div class="install-dialog-inner">
    <form method="dialog" class="dialog-close-form"><button class="dialog-close" aria-label="{html.escape(t(locale, 'install.close'), quote=True)}">×</button></form>
    <p class="eyebrow">{html.escape(t(locale, 'install.eyebrow'))}</p>
    <h2 id="install-title">{html.escape(t(locale, 'install.title'))}</h2>
    <div data-install-ios-instructions hidden><p>{html.escape(t(locale, 'install.ios'))}</p></div>
    <div data-install-browser-instructions hidden>
      <p>{html.escape(t(locale, 'install.browser'))}</p>
      <button class="install-confirm" type="button" data-install-confirm>{html.escape(t(locale, 'install.confirm'))}</button>
    </div>
  </div>
</dialog>"""


def language_suggestion(
    locale: str,
    current_path: str,
    route: str,
    slug: str | None,
    available_locales: tuple[str, ...],
) -> str:
    others = [candidate for candidate in available_locales if candidate != locale]
    if route != "home" or not others:
        return ""
    other = others[0]
    return f"""<aside class="language-suggestion" data-language-suggestion data-suggestion-locale="{other}" hidden>
  <p>{html.escape(t(locale, 'language_suggestion.text'))}</p>
  <div class="language-suggestion-actions">
    <a href="{route_href(current_path, other, route, slug)}" hreflang="{other}" lang="{other}" data-language-choice="{other}">{html.escape(t(locale, 'language_suggestion.action'))}</a>
    <button type="button" data-language-suggestion-dismiss>{html.escape(t(locale, 'language_suggestion.dismiss'))}</button>
  </div>
</aside>"""


def flatten_runtime_strings(value: object, prefix: str = "") -> dict[str, object]:
    flattened: dict[str, object] = {}
    if isinstance(value, dict):
        plural_forms = {"zero", "one", "two", "few", "many", "other"}
        if prefix and set(value).issubset(plural_forms) and all(isinstance(item, str) for item in value.values()):
            flattened[prefix] = value
            return flattened
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else key
            flattened.update(flatten_runtime_strings(item, child))
    elif isinstance(value, str) and prefix:
        flattened[prefix] = value
    return flattened


def runtime_payload(locale: str) -> str:
    payload = {
        "locale": locale,
        "localeTag": t(locale, "locale.tag"),
        "strings": flatten_runtime_strings(UI[locale]),
    }
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def page_shell(
    *,
    locale: str,
    route: str,
    slug: str | None,
    title: str,
    description: str,
    body: str,
    page_class: str,
    available_locales: tuple[str, ...] = SUPPORTED_LOCALES,
) -> str:
    current_path = route_path(locale, route, slug)
    relative_root = relative_href(current_path, "")
    canonical = public_url(current_path)
    alternate_tags = []
    for candidate in available_locales:
        alternate = public_url(route_path(candidate, route, slug))
        alternate_tags.append(
            f'  <link rel="alternate" hreflang="{candidate}" href="{html.escape(alternate, quote=True)}">'
        )
    if "fr" in available_locales:
        alternate_tags.append(
            f'  <link rel="alternate" hreflang="x-default" href="{html.escape(public_url(route_path("fr", route, slug)), quote=True)}">'
        )
    manifest = "manifest.en.webmanifest" if locale == "en" else "manifest.webmanifest"
    return f"""<!doctype html>
<html lang="{locale}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="description" content="{html.escape(description, quote=True)}">
  <meta name="theme-color" content="#15273f">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="{html.escape(t(locale, 'brand.name'), quote=True)}">
  <title>{html.escape(title)}</title>
  <link rel="canonical" href="{html.escape(canonical, quote=True)}">
{chr(10).join(alternate_tags)}
  <link rel="manifest" href="{relative_root}assets/{manifest}">
  <link rel="apple-touch-icon" sizes="180x180" href="{relative_root}assets/icons/apple-touch-icon.png">
  <link rel="icon" type="image/png" sizes="32x32" href="{relative_root}assets/icons/favicon-32.png">
  <link rel="stylesheet" href="{relative_root}assets/styles.css">
  <script id="app-translations" type="application/json">{runtime_payload(locale)}</script>
  <script src="{relative_root}assets/i18n.js"></script>
  <script src="{relative_root}assets/language.js" defer></script>
  <script src="{relative_root}assets/app.js" defer></script>
  <script src="{relative_root}assets/install.js" defer></script>
  <script type="module" src="{relative_root}assets/community.js"></script>
</head>
<body class="{page_class}" data-locale="{locale}" data-page-kind="{route}">
  <a class="skip-link" href="#contenu">{html.escape(t(locale, 'nav.skip'))}</a>
  {mobile_navigation(locale, current_path, route, slug, available_locales)}
  {language_suggestion(locale, current_path, route, slug, available_locales)}
  {body}
  {auth_dialog(locale)}
  {install_dialog(locale)}
</body>
</html>
"""


def community_score(bias: Bias, *, compact: bool = False) -> str:
    modifier = " community-score--compact" if compact else ""
    return f"""<div class="community-score{modifier}" data-community-score="{html.escape(bias.slug)}">
  <span class="community-score-label">{html.escape(t(bias.locale, 'score.label'))}</span>
  <strong><span data-score-value>—</span><small>/100</small></strong>
  <span data-score-count>{html.escape(t(bias.locale, 'score.none'))}</span>
</div>"""


def rating_widget(bias: Bias) -> str:
    slug = html.escape(bias.slug)
    return f"""<section class="rating-panel" data-rating-widget="{slug}" aria-labelledby="rating-title">
  <div class="rating-summary">
    <p class="section-kicker">{html.escape(t(bias.locale, 'rating.eyebrow'))}</p>
    <h2 id="rating-title">{html.escape(t(bias.locale, 'rating.title'))}</h2>
    <p>{html.escape(t(bias.locale, 'rating.intro'))}</p>
    {community_score(bias)}
  </div>
  <div class="rating-personal">
    <div data-rating-signed-out>
      <p><strong>{html.escape(t(bias.locale, 'rating.signed_out'))}</strong></p>
      <button class="rating-login" type="button" data-auth-open>{html.escape(t(bias.locale, 'rating.login'))}</button>
    </div>
    <form data-rating-form hidden>
      <label for="rating-{slug}">{html.escape(t(bias.locale, 'rating.your_rating'))}</label>
      <div class="rating-value"><output for="rating-{slug}" data-rating-output>50</output><span>/100</span></div>
      <input id="rating-{slug}" name="score" type="range" min="1" max="100" value="50" step="1">
      <div class="rating-scale"><span>{html.escape(t(bias.locale, 'rating.low'))}</span><span>{html.escape(t(bias.locale, 'rating.high'))}</span></div>
      <div class="rating-actions">
        <button class="rating-save" type="submit">{html.escape(t(bias.locale, 'rating.save'))}</button>
        <button class="rating-delete" type="button" data-rating-delete hidden>{html.escape(t(bias.locale, 'rating.delete'))}</button>
      </div>
      <p class="rating-message" data-rating-message aria-live="polite"></p>
    </form>
  </div>
</section>"""


def personal_example_editor(bias: Bias) -> str:
    slug = html.escape(bias.slug)
    return f"""<section class="personal-example-panel" data-example-editor data-bias-id="{slug}" aria-labelledby="personal-example-title">
  <div class="personal-example-copy">
    <p class="section-kicker">{html.escape(t(bias.locale, 'examples.personal_eyebrow'))}</p>
    <h2 id="personal-example-title">{html.escape(t(bias.locale, 'examples.personal_title'))}</h2>
    <p>{html.escape(t(bias.locale, 'examples.personal_intro'))}</p>
  </div>
  <div class="personal-example-editor">
    <div data-example-signed-out>
      <p><strong>{html.escape(t(bias.locale, 'examples.signed_out'))}</strong></p>
      <button class="example-login" type="button" data-auth-open>{html.escape(t(bias.locale, 'examples.login'))}</button>
    </div>
    <p class="example-loading" data-example-loading hidden>{html.escape(t(bias.locale, 'examples.loading'))}</p>
    <form data-example-form hidden>
      <label for="personal-example-{slug}">{html.escape(t(bias.locale, 'examples.label'))}</label>
      <textarea id="personal-example-{slug}" name="example_text" minlength="10" maxlength="600" rows="5" required aria-describedby="example-public-note-{slug} example-counter-{slug}"></textarea>
      <div class="example-form-meta">
        <p id="example-public-note-{slug}">{html.escape(t(bias.locale, 'examples.public_note'))}</p>
        <span id="example-counter-{slug}" data-example-counter>0/600</span>
      </div>
      <div class="example-actions">
        <button class="example-save" type="submit" data-example-save>{html.escape(t(bias.locale, 'examples.save_new'))}</button>
        <button class="example-delete" type="button" data-example-delete hidden>{html.escape(t(bias.locale, 'examples.delete'))}</button>
      </div>
      <p class="example-message" data-example-message role="status" aria-live="polite"></p>
    </form>
  </div>
</section>"""


def community_examples_gallery(bias: Bias) -> str:
    slug = html.escape(bias.slug)
    return f"""<section class="community-examples" data-example-gallery data-bias-id="{slug}" aria-labelledby="community-examples-title">
  <div class="community-examples-heading">
    <div>
      <p class="section-kicker">{html.escape(t(bias.locale, 'examples.gallery_eyebrow'))}</p>
      <h2 id="community-examples-title">{html.escape(t(bias.locale, 'examples.gallery_title'))}</h2>
      <p class="community-examples-language-note">{html.escape(t(bias.locale, 'examples.gallery_language_note'))}</p>
    </div>
    <p><strong data-examples-total>0</strong> <span data-examples-total-label>{html.escape(tp(bias.locale, 'examples.shared_count', 1))}</span></p>
  </div>
  <div class="examples-feedback">
    <p data-examples-status role="status" aria-live="polite">{html.escape(t(bias.locale, 'examples.loading_shared'))}</p>
    <button type="button" data-examples-retry hidden>{html.escape(t(bias.locale, 'examples.retry'))}</button>
  </div>
  <div class="community-examples-list" data-examples-list aria-busy="true"></div>
  <button class="examples-more" type="button" data-examples-more hidden>{html.escape(t(bias.locale, 'examples.more'))}</button>
</section>"""


def render_card(bias: Bias, current_path: str | None = None) -> str:
    if current_path is None:
        current_path = route_path(bias.locale, "home")
    search_text = " ".join(
        [
            bias.name_fr,
            bias.name_en,
            *bias.aliases_fr,
            *bias.aliases_en,
            family_label(bias.locale, bias.family),
            bias.short,
            bias.example,
        ]
    ).casefold()
    public_url_value = route_href(current_path, bias.locale, "bias", bias.slug)
    public_aria_label = t(bias.locale, "card.open_aria", name=bias.name)
    reviewing = bias.review_status == "en_revue"
    reviewer_card_attribute = " data-reviewer-card" if reviewing else ""
    reviewer_link_attributes = ""
    if reviewing:
        reviewer_link_attributes = (
            f' data-reviewer-href="{html.escape(edit_url(bias), quote=True)}"'
            f' data-reviewer-aria-label="{html.escape(t(bias.locale, "card.review_aria", name=bias.name), quote=True)}"'
        )
    secondary_name = bias.name_en if bias.locale == "fr" else bias.name_fr
    secondary_locale = "en" if bias.locale == "fr" else "fr"
    return f"""<article class="bias-card" data-bias-card data-bias-id="{html.escape(bias.slug)}"
    data-user-rated="unknown"{reviewer_card_attribute} data-family="{html.escape(bias.family)}"
    data-importance="{bias.importance}" data-evidence="{html.escape(bias.evidence)}"
    data-review="{html.escape(bias.review_status)}"
    data-name="{html.escape(bias.name.casefold(), quote=True)}"
    data-search="{html.escape(search_text, quote=True)}">
  <a class="card-link" href="{html.escape(public_url_value, quote=True)}"
     aria-label="{html.escape(public_aria_label, quote=True)}" data-card-primary-action
     data-public-href="{html.escape(public_url_value, quote=True)}"
     data-public-aria-label="{html.escape(public_aria_label, quote=True)}"{reviewer_link_attributes}>
    <div class="card-topline">
      {family_badge(bias)}
      <span class="card-number">{html.escape(t(bias.locale, 'card.number', number=bias.number))}</span>
    </div>
    {review_metadata(bias)}
    <h2>{html.escape(bias.name)}</h2>
    <p class="english-name" lang="{secondary_locale}">{html.escape(secondary_name)}</p>
    <p class="card-summary">{inline_markdown(bias.short)}</p>
    <div class="card-example" data-example-slot data-bias-id="{html.escape(bias.slug)}">
      <span data-example-label>{html.escape(t(bias.locale, 'card.example'))}</span><p data-example-text>{inline_markdown(bias.example)}</p>
    </div>
    <div class="card-footer">
      {importance_marks(bias.importance, locale=bias.locale)}
      {evidence_badge(bias)}
    </div>
    {community_score(bias, compact=True)}
    <span class="card-open" aria-hidden="true"><span data-card-action-label>{html.escape(t(bias.locale, 'card.read'))}</span> <span>→</span></span>
  </a>
</article>"""


def render_home(biases: list[Bias]) -> str:
    locale = biases[0].locale
    current_path = route_path(locale, "home")
    families = Counter(bias.family for bias in biases)
    reviews = Counter(bias.review_status for bias in biases)
    family_buttons = "\n".join(
        f'<button class="filter-chip" type="button" data-family-filter="{html.escape(key)}" aria-pressed="false">'
        f'{html.escape(family_label(locale, key))}<span>{count}</span></button>'
        for key, count in sorted(families.items(), key=lambda item: family_label(locale, item[0]))
    )
    cards = "\n".join(render_card(bias, current_path) for bias in biases)
    header = site_header(
        locale,
        current_path,
        "home",
        None,
        (
            ("about-link", route_href(current_path, locale, "leaderboard"), html.escape(t(locale, "nav.leaderboard"))),
            ("about-link", route_href(current_path, locale, "about"), html.escape(t(locale, "nav.about"))),
        ),
        SUPPORTED_LOCALES,
    )
    body = f"""{header}
<main id="contenu">
  <section class="hero" aria-labelledby="hero-title">
    <div class="hero-copy">
      <p class="eyebrow">{html.escape(t(locale, 'home.eyebrow'))}</p>
      <h1 id="hero-title">{html.escape(t(locale, 'home.title_line_1'))}<br>{html.escape(t(locale, 'home.title_line_2'))}</h1>
      <p class="hero-intro">{html.escape(t(locale, 'home.intro'))}</p>
      <a class="leaderboard-cta" href="{route_href(current_path, locale, 'leaderboard')}">{html.escape(t(locale, 'home.leaderboard_cta'))} <span aria-hidden="true">→</span></a>
      <div class="hero-stats" aria-label="{html.escape(t(locale, 'home.stats_aria'), quote=True)}">
        <span><strong>{len(biases)}</strong> {html.escape(t(locale, 'home.documented'))}</span>
        <span><strong>{reviews['revue']}</strong> {html.escape(t(locale, 'home.reviewed'))}</span>
        <span><strong>{reviews['en_revue']}</strong> {html.escape(t(locale, 'home.reviewing'))}</span>
        <span><strong>{len(families)}</strong> {html.escape(t(locale, 'home.families'))}</span>
      </div>
    </div>
    <blockquote><p>{html.escape(t(locale, 'home.quote'))}</p><footer>{html.escape(t(locale, 'home.quote_author'))}</footer></blockquote>
  </section>

  <section class="catalogue" aria-labelledby="catalogue-title">
    <div class="catalogue-heading">
      <div><p class="eyebrow">{html.escape(t(locale, 'home.explore'))}</p><h2 id="catalogue-title">{html.escape(t(locale, 'home.catalogue_title'))}</h2></div>
      <p><span id="result-count">{len(biases)}</span> {html.escape(t(locale, 'home.displayed'))}</p>
    </div>
    <div class="controls" aria-label="{html.escape(t(locale, 'home.controls_aria'), quote=True)}">
      <label class="search-field"><span>{html.escape(t(locale, 'home.search'))}</span><input id="search" type="search" placeholder="{html.escape(t(locale, 'home.search_placeholder'), quote=True)}" autocomplete="off"></label>
      <label><span>{html.escape(t(locale, 'home.importance_min'))}</span><select id="importance-filter">
        <option value="0">{html.escape(t(locale, 'home.all_feminine'))}</option><option value="5">{html.escape(t(locale, 'home.critical'))}</option><option value="4">{html.escape(t(locale, 'home.high'))}</option><option value="3">{html.escape(t(locale, 'home.moderate'))}</option>
      </select></label>
      <label><span>{html.escape(t(locale, 'home.evidence'))}</span><select id="evidence-filter">
        <option value="all">{html.escape(t(locale, 'home.all_feminine'))}</option><option value="forte">{html.escape(t(locale, 'home.strong'))}</option><option value="moderee">{html.escape(t(locale, 'home.moderate_evidence'))}</option><option value="limitee">{html.escape(t(locale, 'home.limited'))}</option><option value="contestee">{html.escape(t(locale, 'home.disputed'))}</option>
      </select></label>
      <label><span>{html.escape(t(locale, 'home.review_state'))}</span><select id="review-filter">
        <option value="all">{html.escape(t(locale, 'home.all_masculine'))}</option><option value="non_revue">{html.escape(t(locale, 'home.not_reviewed'))}</option><option value="en_revue">{html.escape(t(locale, 'home.in_review'))}</option><option value="revue">{html.escape(t(locale, 'home.reviewed_option'))}</option>
      </select></label>
      <label><span>{html.escape(t(locale, 'home.sort'))}</span><select id="sort-order">
        <option value="importance">{html.escape(t(locale, 'home.sort_importance'))}</option><option value="alphabetical">{html.escape(t(locale, 'home.sort_alpha'))}</option><option value="evidence">{html.escape(t(locale, 'home.sort_evidence'))}</option><option value="review">{html.escape(t(locale, 'home.sort_review'))}</option>
      </select></label>
      <button id="reset-filters" class="reset-button" type="button">{html.escape(t(locale, 'home.reset'))}</button>
    </div>
    <div class="personal-filter-panel">
      <div class="personal-rating-filters" aria-label="{html.escape(t(locale, 'home.personal_aria'), quote=True)}">
        <span class="personal-filter-label">{html.escape(t(locale, 'home.personal_label'))}</span>
        <button class="filter-chip is-active" type="button" data-personal-scope="all" aria-pressed="true">{html.escape(t(locale, 'home.personal_all'))}</button>
        <button class="filter-chip" type="button" data-personal-scope="mine" aria-pressed="false" disabled>{html.escape(t(locale, 'home.personal_mine'))}</button>
        <button class="filter-chip" type="button" data-personal-scope="unrated" aria-pressed="false" disabled>{html.escape(t(locale, 'home.personal_unrated'))}</button>
      </div>
      <p class="personal-filter-status" data-personal-filter-status aria-live="polite">{html.escape(t(locale, 'home.personal_signed_out'))}</p>
    </div>
    <div class="family-filters" aria-label="{html.escape(t(locale, 'home.family_aria'), quote=True)}">
      <button class="filter-chip is-active" type="button" data-family-filter="all" aria-pressed="true">{html.escape(t(locale, 'home.all_feminine'))}<span>{len(biases)}</span></button>
      {family_buttons}
    </div>
    <div id="bias-grid" class="bias-grid">{cards}</div>
    <div id="empty-state" class="empty-state" hidden><strong>{html.escape(t(locale, 'home.empty_title'))}</strong><p>{html.escape(t(locale, 'home.empty_help'))}</p></div>
  </section>
</main>
<footer class="site-footer">
  <p>{html.escape(t(locale, 'home.footer'))}</p>
  <div class="site-footer-links"><a href="{route_href(current_path, locale, 'leaderboard')}">{html.escape(t(locale, 'nav.leaderboard'))}</a><a href="{route_href(current_path, locale, 'about')}">{html.escape(t(locale, 'home.footer_method'))}</a></div>
</footer>"""
    return page_shell(
        locale=locale,
        route="home",
        slug=None,
        title=t(locale, "meta.home_title"),
        description=t(locale, "meta.home_description"),
        body=body,
        page_class="home-page",
    )


def render_detail(bias: Bias, previous: Bias | None, following: Bias | None) -> str:
    locale = bias.locale
    current_path = route_path(locale, "bias", bias.slug)
    aliases = ""
    if bias.aliases:
        aliases = f'<p class="aliases"><span>{html.escape(t(locale, "detail.also_called"))}</span> {html.escape(", ".join(bias.aliases))}</p>'
    prevention = "\n".join(f"<li>{inline_markdown(item)}</li>" for item in bias.prevention)
    sources = "\n".join(
        f'<li><a href="{html.escape(url, quote=True)}" rel="noreferrer">{html.escape(label)}</a></li>'
        for label, url in bias.sources
    )
    previous_link = (
        f'<a href="{route_href(current_path, locale, "bias", previous.slug)}"><span>← {html.escape(t(locale, "detail.previous"))}</span><strong>{html.escape(previous.name)}</strong></a>'
        if previous else "<span></span>"
    )
    next_link = (
        f'<a class="next" href="{route_href(current_path, locale, "bias", following.slug)}"><span>{html.escape(t(locale, "detail.next"))} →</span><strong>{html.escape(following.name)}</strong></a>'
        if following else "<span></span>"
    )
    if bias.review_status == "non_revue":
        review_controls = f'<a class="review-action" href="{html.escape(review_request_url(bias, "demarrer"), quote=True)}" target="_blank" rel="noreferrer">{html.escape(t(locale, "review.start"))} <span aria-hidden="true">→</span></a><p>{html.escape(t(locale, "review.start_help"))}</p>'
    elif bias.review_status == "en_revue":
        review_controls = f'<div class="review-button-group"><a class="review-action" href="{html.escape(edit_url(bias), quote=True)}" target="_blank" rel="noreferrer">{html.escape(t(locale, "review.edit"))} <span aria-hidden="true">↗</span></a><a class="review-transition" href="{html.escape(review_request_url(bias, "terminer"), quote=True)}" target="_blank" rel="noreferrer">{html.escape(t(locale, "review.finish"))}</a></div><p>{html.escape(t(locale, "review.edit_help"))}</p>'
    else:
        review_controls = f'<a class="review-action" href="{html.escape(review_request_url(bias, "demarrer"), quote=True)}" target="_blank" rel="noreferrer">{html.escape(t(locale, "review.restart"))} <span aria-hidden="true">→</span></a><p>{html.escape(t(locale, "review.restart_help"))}</p>'
    review_date = ""
    if bias.reviewed_on:
        review_date = f'<p class="review-panel-date">{html.escape(t(locale, "review.last_reviewed_completed", date=format_review_date(bias.reviewed_on, locale)))}</p>'
    header = site_header(
        locale,
        current_path,
        "bias",
        bias.slug,
        (
            ("back-link", route_href(current_path, locale, "home"), f'← {html.escape(t(locale, "nav.all_cards"))}'),
            ("about-link", route_href(current_path, locale, "leaderboard"), html.escape(t(locale, "nav.leaderboard"))),
        ),
        SUPPORTED_LOCALES,
        detail=True,
    )
    secondary_name = bias.name_en if locale == "fr" else bias.name_fr
    secondary_locale = "en" if locale == "fr" else "fr"
    body = f"""{header}
<main id="contenu" class="detail-main">
  <article>
    <header class="bias-hero">
      <div class="detail-badges">{family_badge(bias)} {evidence_badge(bias)} {review_badge(bias)}</div>
      <p class="detail-number">{html.escape(t(locale, 'detail.number', number=bias.number))}</p>
      <h1>{html.escape(bias.name)}</h1>
      <p class="detail-english" lang="{secondary_locale}">{html.escape(secondary_name)}</p>
      {aliases}
      <p class="detail-lead">{inline_markdown(bias.short)}</p>
      <div class="detail-importance"><span>{html.escape(t(locale, 'detail.importance'))}</span>{importance_marks(bias.importance, locale=locale)}</div>
    </header>
    <section class="review-panel" aria-labelledby="review-panel-title">
      <div><p class="section-kicker">{html.escape(t(locale, 'review.panel_eyebrow'))}</p><h2 id="review-panel-title">{html.escape(review_label(locale, bias.review_status))}</h2><p>{html.escape(review_description(locale, bias.review_status))}</p>{review_date}</div>
      <div class="review-panel-control"><div class="review-panel-actions" data-reviewer-only hidden>{review_controls}</div><div class="review-panel-locked" data-reviewer-locked><p>{html.escape(t(locale, 'review.locked'))}</p></div></div>
    </section>
    {rating_widget(bias)}
    {personal_example_editor(bias)}
    {community_examples_gallery(bias)}
    <div class="article-layout">
      <aside class="example-panel" data-example-slot data-bias-id="{html.escape(bias.slug)}"><span class="section-index" data-example-label>{html.escape(t(locale, 'card.example'))}</span><p data-example-text>{inline_markdown(bias.example)}</p></aside>
      <div class="article-content">
        <section><p class="section-kicker">{html.escape(t(locale, 'detail.understand'))}</p><h2>{html.escape(t(locale, 'detail.detailed_description'))}</h2>{render_paragraphs(bias.detail)}</section>
        <section><p class="section-kicker">{html.escape(t(locale, 'detail.issue'))}</p><h2>{html.escape(t(locale, 'detail.why'))}</h2>{render_paragraphs(bias.why)}</section>
        <section class="limits-section"><p class="section-kicker">{html.escape(t(locale, 'detail.critical_thinking'))}</p><h2>{html.escape(t(locale, 'detail.limits'))}</h2>{render_paragraphs(bias.limits)}</section>
        <section><p class="section-kicker">{html.escape(t(locale, 'detail.act'))}</p><h2>{html.escape(t(locale, 'detail.prevention'))}</h2><ol class="prevention-list">{prevention}</ol></section>
        <section class="sources-section"><p class="section-kicker">{html.escape(t(locale, 'detail.learn_more'))}</p><h2>{html.escape(t(locale, 'detail.sources'))}</h2><ul>{sources}</ul><p class="source-note">{html.escape(t(locale, 'detail.source_note'))}</p></section>
      </div>
    </div>
  </article>
  <nav class="bias-navigation" aria-label="{html.escape(t(locale, 'nav.catalogue'), quote=True)}">{previous_link}{next_link}</nav>
</main>
<footer class="site-footer detail-footer"><p>{html.escape(t(locale, 'detail.footer_quote'))}</p><div class="site-footer-links"><a href="{route_href(current_path, locale, 'leaderboard')}">{html.escape(t(locale, 'nav.leaderboard'))}</a><a href="{route_href(current_path, locale, 'about')}">{html.escape(t(locale, 'home.footer_method'))}</a></div></footer>"""
    return page_shell(
        locale=locale,
        route="bias",
        slug=bias.slug,
        title=t(locale, "meta.detail_title", name=bias.name),
        description=bias.short,
        body=body,
        page_class="detail-page",
    )


def render_about(biases: list[Bias]) -> str:
    locale = biases[0].locale
    current_path = route_path(locale, "about")
    review_counts = Counter(bias.review_status for bias in biases)
    header = site_header(
        locale,
        current_path,
        "about",
        None,
        (
            ("back-link", route_href(current_path, locale, "home"), f'← {html.escape(t(locale, "nav.all_cards"))}'),
            ("about-link", route_href(current_path, locale, "leaderboard"), html.escape(t(locale, "nav.leaderboard"))),
        ),
        SUPPORTED_LOCALES,
        detail=True,
    )
    evolving = t(
        locale,
        "about.evolving_text",
        count=len(biases),
        reviewed=review_counts["revue"],
        reviewing=review_counts["en_revue"],
        not_reviewed=review_counts["non_revue"],
    )
    body = f"""{header}
<main id="contenu" class="about-main">
  <header class="about-hero"><p class="eyebrow">{html.escape(t(locale, 'about.eyebrow'))}</p><h1>{html.escape(t(locale, 'about.title'))}</h1><p>{html.escape(t(locale, 'about.intro'))}</p></header>
  <div class="about-grid">
    <section><span class="about-number">01</span><h2>{html.escape(t(locale, 'about.level_title'))}</h2><p>{html.escape(t(locale, 'about.level_text'))}</p></section>
    <section><span class="about-number">02</span><h2>{html.escape(t(locale, 'about.evidence_title'))}</h2><p>{html.escape(t(locale, 'about.evidence_text'))}</p></section>
    <section><span class="about-number">03</span><h2>{html.escape(t(locale, 'about.evolving_title'))}</h2><p>{html.escape(evolving)}</p></section>
  </div>
  <section class="pascal-panel"><blockquote>{html.escape(t(locale, 'about.quote'))}</blockquote><p>{html.escape(t(locale, 'about.quote_source'))}</p><a href="https://www.penseesdepascal.fr/Transition/P-R-Transition6.php">{html.escape(t(locale, 'about.quote_link'))}</a></section>
  <section class="method-section">
    <p class="section-kicker">{html.escape(t(locale, 'about.corpus'))}</p><h2>{html.escape(t(locale, 'about.sources_title'))}</h2>
    <ul>
      <li><a href="https://doi.org/10.1016/j.ipm.2024.103672">Soprano et al. (2024)</a> — {html.escape(t(locale, 'about.source_soprano'))}</li>
      <li><a href="https://doi.org/10.1109/TVCG.2018.2872577">Dimara et al. (2020)</a> — {html.escape(t(locale, 'about.source_dimara'))}</li>
      <li><a href="https://foundation.wikimedia.org/wiki/File:Cognitive_bias_codex_en.svg">Cognitive Bias Codex</a> — {html.escape(t(locale, 'about.source_codex'))}</li>
    </ul>
    <p>{html.escape(t(locale, 'about.method_note'))}</p>
  </section>
</main>
<footer class="site-footer detail-footer"><p>{html.escape(t(locale, 'about.footer'))}</p><div class="site-footer-links"><a href="{route_href(current_path, locale, 'leaderboard')}">{html.escape(t(locale, 'nav.leaderboard'))}</a><a href="{route_href(current_path, locale, 'home')}">{html.escape(t(locale, 'about.explore'))}</a></div></footer>"""
    return page_shell(
        locale=locale,
        route="about",
        slug=None,
        title=t(locale, "meta.about_title"),
        description=t(locale, "meta.about_description"),
        body=body,
        page_class="about-page",
    )


def render_leaderboard(biases: list[Bias]) -> str:
    locale = biases[0].locale
    current_path = route_path(locale, "leaderboard")
    rows = "\n".join(
        f"""<tr data-leaderboard-row data-bias-id="{html.escape(bias.slug)}" data-name="{html.escape(bias.name.casefold(), quote=True)}" data-family="{html.escape(bias.family)}">
  <td class="leaderboard-rank" data-label="{html.escape(t(locale, 'leaderboard.rank'), quote=True)}" data-rank>—</td>
  <th scope="row" data-label="{html.escape(t(locale, 'leaderboard.bias'), quote=True)}"><a href="{route_href(current_path, locale, 'bias', bias.slug)}">{html.escape(bias.name)}</a><span>{html.escape(family_label(locale, bias.family))}</span></th>
  <td class="leaderboard-score" data-provisional-label="{html.escape(t(locale, 'score.provisional'), quote=True)}" data-label="{html.escape(t(locale, 'leaderboard.average'), quote=True)}"><strong data-score>—</strong><span>/100</span></td>
  <td data-label="{html.escape(t(locale, 'leaderboard.median'), quote=True)}" data-median>—</td>
  <td data-label="{html.escape(t(locale, 'leaderboard.ratings'), quote=True)}" data-count>0</td>
  <td class="leaderboard-personal" data-label="{html.escape(t(locale, 'leaderboard.your_rating'), quote=True)}" data-personal>—</td>
</tr>"""
        for bias in biases
    )
    family_options = "\n".join(
        f'<option value="{html.escape(key)}">{html.escape(family_label(locale, key))}</option>'
        for key in sorted(catalog_value(locale, "families"), key=lambda item: family_label(locale, item))
    )
    header = site_header(
        locale,
        current_path,
        "leaderboard",
        None,
        (
            ("back-link", route_href(current_path, locale, "home"), f'← {html.escape(t(locale, "nav.all_cards"))}'),
            ("about-link", route_href(current_path, locale, "about"), html.escape(t(locale, "nav.about"))),
        ),
        SUPPORTED_LOCALES,
        detail=True,
    )
    headers = ["rank", "bias", "average", "median", "ratings", "your_rating"]
    head_cells = "".join(
        f'<th scope="col">{html.escape(t(locale, f"leaderboard.{key}"))}</th>'
        for key in headers
    )
    body = f"""{header}
<main id="contenu" class="leaderboard-main" data-leaderboard>
  <header class="leaderboard-hero"><p class="eyebrow">{html.escape(t(locale, 'leaderboard.eyebrow'))}</p><h1>{html.escape(t(locale, 'leaderboard.title_line_1'))}<br>{html.escape(t(locale, 'leaderboard.title_line_2'))}</h1><p>{html.escape(t(locale, 'leaderboard.intro'))}</p></header>
  <section class="leaderboard-section" aria-labelledby="leaderboard-title">
    <div class="leaderboard-heading"><div><p class="section-kicker">{html.escape(t(locale, 'leaderboard.section_eyebrow'))}</p><h2 id="leaderboard-title">{html.escape(t(locale, 'leaderboard.title'))}</h2></div><p><span data-ratings-total>0</span> {html.escape(t(locale, 'leaderboard.ratings_registered'))}</p></div>
    <div class="leaderboard-controls">
      <label><span>{html.escape(t(locale, 'leaderboard.search'))}</span><input type="search" data-leaderboard-search placeholder="{html.escape(t(locale, 'leaderboard.search_placeholder'), quote=True)}"></label>
      <label><span>{html.escape(t(locale, 'leaderboard.family'))}</span><select data-leaderboard-family><option value="all">{html.escape(t(locale, 'leaderboard.all_families'))}</option>{family_options}</select></label>
      <label><span>{html.escape(t(locale, 'leaderboard.display'))}</span><select data-leaderboard-scope><option value="all">{html.escape(t(locale, 'leaderboard.all_biases'))}</option><option value="rated">{html.escape(t(locale, 'leaderboard.with_ratings'))}</option><option value="mine">{html.escape(t(locale, 'leaderboard.my_ratings'))}</option></select></label>
    </div>
    <div class="leaderboard-table-wrap"><table class="leaderboard-table" aria-labelledby="leaderboard-title"><thead><tr>{head_cells}</tr></thead><tbody>{rows}</tbody></table></div>
    <p class="leaderboard-note">{html.escape(t(locale, 'leaderboard.note'))}</p>
  </section>
</main>
<footer class="site-footer detail-footer"><p>{html.escape(t(locale, 'leaderboard.footer'))}</p><a href="{route_href(current_path, locale, 'home')}">{html.escape(t(locale, 'leaderboard.explore'))}</a></footer>"""
    return page_shell(
        locale=locale,
        route="leaderboard",
        slug=None,
        title=t(locale, "meta.leaderboard_title"),
        description=t(locale, "meta.leaderboard_description"),
        body=body,
        page_class="leaderboard-page",
    )


def render_not_found() -> str:
    blocks = []
    for locale in SUPPORTED_LOCALES:
        blocks.append(
            f"""<section class="not-found-locale" data-not-found-locale="{locale}" data-not-found-title="{html.escape(t(locale, 'meta.not_found_title'), quote=True)}" lang="{locale}">
  <p class="eyebrow">{html.escape(t(locale, 'not_found.eyebrow'))}</p>
  <h1>{html.escape(t(locale, 'not_found.title'))}</h1>
  <p>{html.escape(t(locale, 'not_found.text'))}</p>
  <a class="primary-link" href="{public_url(route_path(locale, 'home'))}">{html.escape(t(locale, 'not_found.action'))}</a>
</section>"""
        )
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="robots" content="noindex">
  <meta name="theme-color" content="#15273f">
  <title>{html.escape(t('fr', 'meta.not_found_title'))}</title>
  <link rel="apple-touch-icon" sizes="180x180" href="{PUBLIC_SITE_URL}assets/icons/apple-touch-icon.png">
  <link rel="icon" type="image/png" sizes="32x32" href="{PUBLIC_SITE_URL}assets/icons/favicon-32.png">
  <link rel="stylesheet" href="{PUBLIC_SITE_URL}assets/styles.css">
  <script src="{PUBLIC_SITE_URL}assets/not-found.js" defer></script>
</head>
<body class="error-page">
  <main id="contenu" class="error-main error-main--bilingual">{''.join(blocks)}</main>
</body>
</html>
"""


def render_sitemap(biases_by_locale: dict[str, list[Bias]]) -> str:
    entries: list[tuple[str, str | None, str | None]] = []
    for route in ("home", "about", "leaderboard"):
        entries.append((route, None, None))
    french_slugs = {bias.slug for bias in biases_by_locale["fr"]}
    english_slugs = {bias.slug for bias in biases_by_locale["en"]}
    for slug in sorted(french_slugs | english_slugs):
        entries.append(("bias", slug, None))
    urls = []
    for route, slug, _unused in entries:
        available = tuple(
            locale
            for locale in SUPPORTED_LOCALES
            if route != "bias" or slug in {bias.slug for bias in biases_by_locale[locale]}
        )
        for locale in available:
            path = route_path(locale, route, slug)
            alternates = "".join(
                f'<xhtml:link rel="alternate" hreflang="{candidate}" href="{html.escape(public_url(route_path(candidate, route, slug)), quote=True)}"/>'
                for candidate in available
            )
            if "fr" in available:
                alternates += f'<xhtml:link rel="alternate" hreflang="x-default" href="{html.escape(public_url(route_path("fr", route, slug)), quote=True)}"/>'
            urls.append(f'<url><loc>{html.escape(public_url(path))}</loc>{alternates}</url>')
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">' + "".join(urls) + "</urlset>\n"


def write_page(output: Path, path: str, content: str) -> None:
    destination = output / path
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "index.html").write_text(content, encoding="utf-8")


def build(output: Path) -> list[Bias]:
    french_biases = [bias for path in sorted(CONTENT_DIR.glob("*.md")) if (bias := read_bias(path))]
    if not french_biases:
        raise ValueError("No documented biases found")
    english_biases = [translated for base in french_biases if (translated := read_translation(base, "en"))]
    biases_by_locale = {"fr": french_biases, "en": english_biases}
    for locale, biases in biases_by_locale.items():
        biases.sort(key=lambda bias: (-bias.importance, EVIDENCE_ORDER.get(bias.evidence, 99), bias.name.casefold()))

    forbidden_outputs = {
        Path("/").resolve(),
        Path.home().resolve(),
        PROJECT_ROOT.resolve(),
        CONTENT_DIR.resolve(),
        WEB_DIR.resolve(),
        (PROJECT_ROOT / "catalogue").resolve(),
    }
    if output.resolve() in forbidden_outputs:
        raise ValueError(f"Unsafe output directory: {output}")
    if output.exists():
        if not (output / BUILD_MARKER).is_file():
            raise ValueError(f"Refusing to replace an unmarked directory: {output}. Expected {BUILD_MARKER}.")
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / BUILD_MARKER).write_text("Generated by scripts/build_site.py\n", encoding="utf-8")
    shutil.copytree(WEB_DIR / "assets", output / "assets")
    (output / ".nojekyll").write_text("", encoding="utf-8")

    for locale, biases in biases_by_locale.items():
        if not biases:
            continue
        write_page(output, route_path(locale, "home"), render_home(biases))
        write_page(output, route_path(locale, "about"), render_about(biases))
        write_page(output, route_path(locale, "leaderboard"), render_leaderboard(biases))
        for index, bias in enumerate(biases):
            previous = biases[index - 1] if index else None
            following = biases[index + 1] if index + 1 < len(biases) else None
            write_page(output, route_path(locale, "bias", bias.slug), render_detail(bias, previous, following))

    (output / "404.html").write_text(render_not_found(), encoding="utf-8")
    (output / "sitemap.xml").write_text(render_sitemap(biases_by_locale), encoding="utf-8")
    (output / "robots.txt").write_text(f"Sitemap: {PUBLIC_SITE_URL}sitemap.xml\n", encoding="utf-8")
    return french_biases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "_site")
    args = parser.parse_args()
    output = args.output.resolve()
    biases = build(output)
    print(f"Built {len(biases)} bias pages in {len(SUPPORTED_LOCALES)} languages in {output}")


if __name__ == "__main__":
    main()
