from __future__ import annotations

import json
import re
import struct
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import build_site  # noqa: E402
import apply_review_request  # noqa: E402
import set_review_status  # noqa: E402


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "a" and attr_map.get("href"):
            self.links.append(attr_map["href"] or "")
        if tag in {"link", "script"}:
            candidate = attr_map.get("href") or attr_map.get("src")
            if candidate:
                self.links.append(candidate)


class PageMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.html_lang: str | None = None
        self.canonicals: list[str] = []
        self.alternates: dict[str, str] = {}
        self.manifests: list[str] = []
        self.language_choices: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "html":
            self.html_lang = attr_map.get("lang")
        elif tag == "link":
            rel = attr_map.get("rel")
            href = attr_map.get("href")
            if rel == "canonical" and href:
                self.canonicals.append(href)
            elif rel == "alternate" and href and attr_map.get("hreflang"):
                self.alternates[attr_map["hreflang"] or ""] = href
            elif rel == "manifest" and href:
                self.manifests.append(href)
        elif tag == "a" and attr_map.get("data-language-choice"):
            self.language_choices.append(attr_map)


def dictionary_shape(value: object, prefix: str = "") -> dict[str, tuple[str, int | None]]:
    shape: dict[str, tuple[str, int | None]] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            shape.update(dictionary_shape(child, child_prefix))
    elif isinstance(value, list):
        shape[prefix] = ("list", len(value))
    else:
        shape[prefix] = (type(value).__name__, None)
    return shape


class SiteBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp_dir.name) / "site"
        cls.biases = build_site.build(cls.output)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def test_expected_pages_are_generated(self) -> None:
        self.assertEqual(len(self.biases), 39)
        self.assertEqual(len(list(self.output.rglob("*.html"))), 85)
        for page in ("index.html", "a-propos/index.html", "classement/index.html"):
            self.assertTrue((self.output / page).is_file(), page)
        for page in ("en/index.html", "en/about/index.html", "en/ranking/index.html"):
            self.assertTrue((self.output / page).is_file(), page)
        self.assertTrue((self.output / "404.html").is_file())
        french_pages = list((self.output / "biais").glob("*/index.html"))
        english_pages = list((self.output / "en" / "biases").glob("*/index.html"))
        self.assertEqual(len(french_pages), 39)
        self.assertEqual(len(english_pages), 39)
        self.assertEqual(
            {page.parent.name for page in french_pages},
            {page.parent.name for page in english_pages},
        )

    def test_ui_dictionaries_have_identical_complete_shapes(self) -> None:
        french = json.loads((build_site.I18N_DIR / "fr" / "ui.json").read_text(encoding="utf-8"))
        english = json.loads((build_site.I18N_DIR / "en" / "ui.json").read_text(encoding="utf-8"))
        french_shape = dictionary_shape(french)
        english_shape = dictionary_shape(english)
        self.assertEqual(french_shape, english_shape)
        self.assertGreaterEqual(len(french_shape), 250)

        for locale, catalogue in (("fr", french), ("en", english)):
            for key, value in build_site.flatten_runtime_strings(catalogue).items():
                if isinstance(value, str):
                    self.assertTrue(value.strip(), f"{locale}: {key}")
                else:
                    self.assertIsInstance(value, dict, f"{locale}: {key}")
                    self.assertEqual(set(value), {"one", "other"}, f"{locale}: {key}")
                    self.assertTrue(all(str(item).strip() for item in value.values()), f"{locale}: {key}")

    def test_i18n_runtime_formats_text_plurals_numbers_and_dates_in_both_locales(self) -> None:
        i18n_path = PROJECT_ROOT / "web" / "assets" / "i18n.js"
        script = """
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(__I18N_PATH__, "utf8");

const evaluate = (locale, localeTag, greeting, one, other) => {
  const payload = {
    locale,
    localeTag,
    strings: {
      greeting,
      "items.count": { one, other },
    },
  };
  const window = {};
  const document = {
    documentElement: { lang: locale },
    querySelector: (selector) => selector === "#app-translations"
      ? { textContent: JSON.stringify(payload) }
      : null,
  };
  vm.runInNewContext(source, { window, document, console, Intl, Date, JSON, Object, Number, String });
  const api = window.BienPenserI18n;
  return {
    text: api.t("greeting", { name: "Ada" }),
    one: api.tp("items.count", 1),
    other: api.tp("items.count", 2),
    number: api.formatNumber(1234.5),
    date: api.formatDate("2026-08-15"),
  };
};

const result = {
  fr: evaluate("fr", "fr-FR", "Bonjour {name}", "{count} élément", "{count} éléments"),
  en: evaluate("en", "en-GB", "Hello {name}", "{count} item", "{count} items"),
};
process.stdout.write(JSON.stringify(result));
""".replace("__I18N_PATH__", json.dumps(str(i18n_path)))
        completed = subprocess.run(
            ["node", "-e", script],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=True,
            timeout=10,
        )
        result = json.loads(completed.stdout)
        self.assertEqual(
            result["fr"],
            {
                "text": "Bonjour Ada",
                "one": "1 élément",
                "other": "2 éléments",
                "number": "1\u202f234,5",
                "date": "15 août 2026",
            },
        )
        self.assertEqual(
            result["en"],
            {
                "text": "Hello Ada",
                "one": "1 item",
                "other": "2 items",
                "number": "1,234.5",
                "date": "15 August 2026",
            },
        )

    def test_all_english_translations_are_published_and_complete(self) -> None:
        translation_dir = build_site.I18N_DIR / "en" / "biais"
        translations = {path.stem: path for path in translation_dir.glob("*.md")}
        canonical = {bias.slug: bias for bias in self.biases}
        self.assertEqual(set(translations), set(canonical))
        self.assertEqual(len(translations), 39)

        required_sections = [
            "Short",
            "Example",
            "Detailed description",
            "Why it matters",
            "Limits and nuances",
            "Prevention",
            "Sources",
        ]
        forbidden_shared_metadata = {
            "source_number",
            "name_en",
            "name_fr",
            "aliases_en",
            "aliases_fr",
            "family",
            "importance",
            "importance_status",
            "evidence_level",
            "fact_checking_relevant",
            "source",
        }
        forbidden_placeholders = ("to be written", "to be translated", "todo", "placeholder")

        for slug, base in canonical.items():
            path = translations[slug]
            pieces = path.read_text(encoding="utf-8").split("---", 2)
            self.assertEqual(len(pieces), 3, path)
            front, body = pieces[1], pieces[2].strip()
            self.assertEqual(build_site.parse_scalar(front, "schema_version"), 1, path)
            self.assertEqual(build_site.parse_scalar(front, "locale"), "en", path)
            self.assertEqual(build_site.parse_scalar(front, "translation_of"), base.bias_id, path)
            self.assertEqual(build_site.parse_scalar(front, "translation_status"), "published", path)
            self.assertIn(build_site.parse_scalar(front, "review_status"), build_site.REVIEW_STATUSES, path)
            reviewed_on = build_site.parse_scalar(front, "reviewed_on")
            if reviewed_on is not None:
                date.fromisoformat(str(reviewed_on))
            self.assertEqual(build_site.parse_scalar(front, "translated_on"), "2026-08-15", path)
            for key in forbidden_shared_metadata:
                self.assertIsNone(build_site.parse_scalar(front, key), f"{path}: {key}")

            heading = re.search(r"^# (.+)$", body, flags=re.MULTILINE)
            self.assertIsNotNone(heading, path)
            self.assertEqual(heading.group(1), base.name_en, path)
            self.assertEqual(re.findall(r"^## (.+)$", body, flags=re.MULTILINE), required_sections, path)
            for section_title in required_sections:
                self.assertTrue(build_site.section(body, section_title).strip(), f"{path}: {section_title}")
            self.assertEqual(
                len(build_site.bullet_values(build_site.section(body, "Prevention"))),
                2,
                path,
            )
            translated_sources = build_site.source_values(build_site.section(body, "Sources"))
            self.assertEqual(
                [url for _label, url in translated_sources],
                [url for _label, url in base.sources],
                path,
            )
            self.assertFalse(any(token in body.casefold() for token in forbidden_placeholders), path)
            translated = build_site.read_translation(base, "en")
            self.assertIsNotNone(translated, path)
            self.assertEqual(translated.locale, "en", path)

    def test_pwa_manifest_and_icons_are_generated(self) -> None:
        assets = self.output / "assets"
        manifests = {
            "fr": (assets / "manifest.webmanifest", "../", "Bien penser — Les biais cognitifs"),
            "en": (assets / "manifest.en.webmanifest", "../en/", "Bien penser — Cognitive Biases"),
        }
        parsed: dict[str, dict[str, object]] = {}
        for locale, (manifest_path, start_url, name) in manifests.items():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            parsed[locale] = manifest
            self.assertEqual(manifest["name"], name)
            self.assertEqual(manifest["short_name"], "Bien penser")
            self.assertEqual(manifest["lang"], locale)
            self.assertEqual(manifest["id"], "../")
            self.assertEqual(manifest["display"], "standalone")
            self.assertEqual(manifest["start_url"], start_url)
            self.assertEqual(manifest["scope"], "../")
            self.assertEqual((manifest_path.parent / manifest["scope"]).resolve(), self.output.resolve())
            self.assertTrue((manifest_path.parent / manifest["start_url"]).resolve().is_dir())
            self.assertEqual(manifest["theme_color"], "#15273f")
            self.assertEqual(manifest["background_color"], "#f3eee5")
        self.assertEqual(parsed["fr"]["icons"], parsed["en"]["icons"])

        expected_sizes = {
            "icons/icon-192.png": (192, 192),
            "icons/icon-512.png": (512, 512),
            "icons/icon-maskable-512.png": (512, 512),
            "icons/apple-touch-icon.png": (180, 180),
            "icons/favicon-32.png": (32, 32),
        }
        purposes = {icon["purpose"] for icon in parsed["fr"]["icons"]}
        self.assertEqual(purposes, {"any", "maskable"})
        for relative_path, dimensions in expected_sizes.items():
            image_path = assets / relative_path
            self.assertTrue(image_path.is_file(), relative_path)
            data = image_path.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", data[16:24]), dimensions)

    def test_every_page_has_installable_metadata_with_resolving_paths(self) -> None:
        pages = [page for page in self.output.rglob("*.html") if page.name != "404.html"]
        self.assertEqual(len(pages), 84)
        for page in pages:
            content = page.read_text(encoding="utf-8")
            self.assertEqual(content.count('rel="manifest"'), 1, page)
            self.assertEqual(content.count('rel="apple-touch-icon"'), 1, page)
            self.assertIn("viewport-fit=cover", content, page)
            self.assertIn('name="apple-mobile-web-app-capable" content="yes"', content, page)
            self.assertIn('name="apple-mobile-web-app-title" content="Bien penser"', content, page)
            self.assertIn('id="install-dialog"', content, page)
            self.assertIn('class="mobile-nav', content, page)
            self.assertIn("data-install-open hidden", content, page)

            parser = PageMetadataParser()
            parser.feed(content)
            relative_parts = page.relative_to(self.output).parts
            locale = "en" if relative_parts[0] == "en" else "fr"
            expected_manifest = "manifest.en.webmanifest" if locale == "en" else "manifest.webmanifest"
            self.assertEqual(len(parser.manifests), 1, page)
            manifest_target = (page.parent / parser.manifests[0]).resolve()
            self.assertEqual(manifest_target, (self.output / "assets" / expected_manifest).resolve(), page)
            self.assertIn(build_site.t(locale, "install.button"), content, page)
            self.assertIn(build_site.t(locale, "install.title"), content, page)

    def test_home_contains_cards_and_controls(self) -> None:
        homes = {
            "fr": (self.output / "index.html", 'href="classement/"'),
            "en": (self.output / "en" / "index.html", 'href="ranking/"'),
        }
        for locale, (path, leaderboard_href) in homes.items():
            home = path.read_text(encoding="utf-8")
            self.assertEqual(home.count('data-bias-card'), 39, path)
            self.assertEqual(home.count('data-bias-card data-bias-id="'), 39, path)
            self.assertEqual(home.count('data-example-slot'), 39, path)
            self.assertEqual(home.count('data-example-text'), 39, path)
            self.assertIn('id="search"', home, path)
            self.assertIn('id="importance-filter"', home, path)
            self.assertIn('id="evidence-filter"', home, path)
            self.assertIn('id="review-filter"', home, path)
            self.assertIn('data-family-filter="all"', home, path)
            self.assertIn(leaderboard_href, home, path)
            self.assertEqual(home.count('data-community-score="'), 39, path)
            self.assertIn('data-personal-scope="all" aria-pressed="true"', home, path)
            self.assertIn('data-personal-scope="mine" aria-pressed="false" disabled', home, path)
            self.assertIn('data-personal-scope="unrated" aria-pressed="false" disabled', home, path)
            self.assertIn('data-personal-filter-status aria-live="polite"', home, path)
            self.assertIn(build_site.t(locale, "home.title_line_1"), home, path)
            review_states = ("non_revue", "en_revue", "revue")
            self.assertEqual(sum(home.count(f'data-review="{state}"') for state in review_states), 39, path)
            self.assertEqual(sum(home.count(f'review-state--{state}">') for state in review_states), 39, path)

    def test_routes_canonical_hreflang_and_language_switcher_are_paired(self) -> None:
        routes: list[tuple[str, str | None]] = [
            ("home", None),
            ("about", None),
            ("leaderboard", None),
        ]
        routes.extend(("bias", bias.slug) for bias in self.biases)

        for route, slug in routes:
            localized_paths = {
                locale: build_site.route_path(locale, route, slug)
                for locale in build_site.SUPPORTED_LOCALES
            }
            expected_alternates = {
                "fr": build_site.public_url(localized_paths["fr"]),
                "en": build_site.public_url(localized_paths["en"]),
                "x-default": build_site.public_url(localized_paths["fr"]),
            }
            for locale, current_path in localized_paths.items():
                page = self.output / current_path / "index.html" if current_path else self.output / "index.html"
                parser = PageMetadataParser()
                parser.feed(page.read_text(encoding="utf-8"))
                self.assertEqual(parser.html_lang, locale, page)
                self.assertEqual(parser.canonicals, [build_site.public_url(current_path)], page)
                self.assertEqual(parser.alternates, expected_alternates, page)

                for candidate, candidate_path in localized_paths.items():
                    expected_href = build_site.relative_href(current_path, candidate_path)
                    matching = [
                        choice
                        for choice in parser.language_choices
                        if choice.get("data-language-choice") == candidate
                        and choice.get("href") == expected_href
                    ]
                    self.assertTrue(matching, f"{page}: missing {candidate} selector to {expected_href}")
                    if candidate == locale:
                        self.assertTrue(
                            any(choice.get("aria-current") == "page" for choice in matching),
                            f"{page}: current language is not exposed",
                        )

    def test_language_preference_is_remembered_and_suggested_without_redirect(self) -> None:
        language = (PROJECT_ROOT / "web" / "assets" / "language.js").read_text(encoding="utf-8")
        self.assertIn('const LOCALE_KEY = "bienpenser.locale"', language)
        self.assertIn('writeStorage("localStorage", LOCALE_KEY, locale)', language)
        self.assertIn('readStorage("localStorage", LOCALE_KEY)', language)
        self.assertIn("window.navigator.languages", language)
        self.assertIn('document.body.classList.contains("home-page")', language)
        self.assertIn("suggestion.hidden = false", language)
        self.assertNotIn("window.location.replace", language)
        self.assertNotIn("window.location.assign", language)

        for locale, page in (
            ("fr", self.output / "index.html"),
            ("en", self.output / "en" / "index.html"),
        ):
            content = page.read_text(encoding="utf-8")
            other = "en" if locale == "fr" else "fr"
            self.assertIn(
                f'data-language-suggestion data-suggestion-locale="{other}" hidden',
                content,
                page,
            )

    def test_bilingual_404_is_noindex_and_uses_absolute_project_urls(self) -> None:
        page = (self.output / "404.html").read_text(encoding="utf-8")
        self.assertIn('<meta name="robots" content="noindex">', page)
        self.assertEqual(page.count('data-not-found-locale="fr"'), 1)
        self.assertEqual(page.count('data-not-found-locale="en"'), 1)
        self.assertIn(build_site.t("fr", "not_found.title"), page)
        self.assertIn(build_site.t("en", "not_found.title"), page)
        self.assertIn(f'href="{build_site.PUBLIC_SITE_URL}"', page)
        self.assertIn(f'href="{build_site.PUBLIC_SITE_URL}en/"', page)
        for asset in (
            "assets/styles.css",
            "assets/not-found.js",
            "assets/icons/apple-touch-icon.png",
            "assets/icons/favicon-32.png",
        ):
            self.assertIn(f'"{build_site.PUBLIC_SITE_URL}{asset}"', page)
        self.assertNotIn('rel="canonical"', page)
        self.assertNotIn('rel="manifest"', page)

        script = (self.output / "assets" / "not-found.js").read_text(encoding="utf-8")
        self.assertIn('const EN_PATH_PREFIX = "/bien-penser-biais-cognitifs/en/"', script)
        self.assertIn('window.localStorage.getItem("bienpenser.locale")', script)
        self.assertIn("window.navigator.languages", script)
        self.assertIn("document.documentElement.lang = locale", script)

    def test_sitemap_contains_every_localized_canonical_and_alternate(self) -> None:
        root = ET.fromstring((self.output / "sitemap.xml").read_text(encoding="utf-8"))
        sitemap_ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        xhtml_ns = "{http://www.w3.org/1999/xhtml}"
        entries = root.findall(f"{sitemap_ns}url")
        self.assertEqual(len(entries), 84)

        route_pairs: list[tuple[str, str | None]] = [
            ("home", None),
            ("about", None),
            ("leaderboard", None),
        ]
        route_pairs.extend(("bias", bias.slug) for bias in self.biases)
        expected_by_url: dict[str, dict[str, str]] = {}
        for route, slug in route_pairs:
            french = build_site.public_url(build_site.route_path("fr", route, slug))
            english = build_site.public_url(build_site.route_path("en", route, slug))
            alternates = {"fr": french, "en": english, "x-default": french}
            expected_by_url[french] = alternates
            expected_by_url[english] = alternates

        actual_by_url: dict[str, dict[str, str]] = {}
        for entry in entries:
            location = entry.findtext(f"{sitemap_ns}loc")
            self.assertIsNotNone(location)
            actual_by_url[str(location)] = {
                str(link.attrib.get("hreflang")): str(link.attrib.get("href"))
                for link in entry.findall(f"{xhtml_ns}link")
            }
        self.assertEqual(actual_by_url, expected_by_url)
        self.assertNotIn(f"{build_site.PUBLIC_SITE_URL}404.html", actual_by_url)
        self.assertEqual(
            (self.output / "robots.txt").read_text(encoding="utf-8"),
            f"Sitemap: {build_site.PUBLIC_SITE_URL}sitemap.xml\n",
        )

    def test_every_source_card_has_review_metadata(self) -> None:
        for source in build_site.CONTENT_DIR.glob("*.md"):
            content = source.read_text(encoding="utf-8")
            self.assertRegex(content, r'(?m)^review_status: "(?:non_revue|en_revue|revue)"$', source)
            self.assertRegex(content, r'(?m)^reviewed_on: (?:null|"\d{4}-\d{2}-\d{2}")$', source)

    def test_in_review_card_defaults_to_detail_until_reviewer_is_authorized(self) -> None:
        bias = replace(self.biases[0], review_status="en_revue")
        card = build_site.render_card(bias)
        detail = build_site.render_detail(bias, None, None)
        self.assertIn(f'href="biais/{bias.slug}/"', card)
        self.assertIn("data-reviewer-card", card)
        self.assertIn('data-reviewer-href="https://github.com/J2M116/bien-penser-biais-cognitifs/edit/main/', card)
        self.assertIn("<span data-card-action-label>Lire la fiche</span>", card)
        self.assertNotIn('target="_blank"', card)
        self.assertIn("Faire évoluer la fiche", detail)
        self.assertIn("Marquer comme revue", detail)
        self.assertIn('class="review-panel-actions" data-reviewer-only hidden', detail)
        self.assertIn('class="review-panel-locked" data-reviewer-locked', detail)

    def test_review_transition_link_prepares_a_github_request(self) -> None:
        french = replace(self.biases[0], review_status="non_revue", reviewed_on=None)
        english_translation = build_site.read_translation(self.biases[0], "en")
        self.assertIsNotNone(english_translation)
        english = replace(english_translation, review_status="non_revue", reviewed_on=None)
        for bias in (french, english):
            request = build_site.review_request_url(bias, "demarrer")
            query = parse_qs(urlsplit(request).query)
            self.assertEqual(
                query["title"],
                [f"REVUE | demarrer | {bias.locale} | {bias.slug}"],
            )
            detail = build_site.render_detail(bias, None, None)
            self.assertIn(build_site.t(bias.locale, "review.start"), detail)
            self.assertIn("issues/new?", detail)

    def test_reviewed_card_displays_its_date_in_french(self) -> None:
        bias = replace(self.biases[0], review_status="revue", reviewed_on="2026-08-10")
        card = build_site.render_card(bias)
        self.assertIn("Revue", card)
        self.assertIn("Dernière revue : 10 août 2026", card)

    def test_review_status_helper_preserves_the_previous_review_date(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            card = Path(temporary) / "card.md"
            card.write_text(self.biases[0].source_path.read_text(encoding="utf-8"), encoding="utf-8")
            set_review_status.update_review(card, "revue", "2026-08-10")
            set_review_status.update_review(card, "en_revue")
            content = card.read_text(encoding="utf-8")
            self.assertIn('review_status: "en_revue"', content)
            self.assertIn('reviewed_on: "2026-08-10"', content)

    def test_review_status_helper_inserts_fields_after_the_locale_specific_anchor(self) -> None:
        fixtures = {
            "fr": '---\nstatus: "documente"\nevidence_level: "forte"\n---\n\n# Carte\n',
            "en": '---\nlocale: "en"\ntranslation_status: "published"\n---\n\n# Card\n',
        }
        anchors = {"fr": "evidence_level", "en": "translation_status"}
        with tempfile.TemporaryDirectory() as temporary:
            for locale, fixture in fixtures.items():
                card = Path(temporary) / f"{locale}.md"
                card.write_text(fixture, encoding="utf-8")
                set_review_status.update_review(card, "en_revue")
                front = card.read_text(encoding="utf-8").split("---", 2)[1]
                lines = [line for line in front.splitlines() if line]
                anchor_index = next(i for i, line in enumerate(lines) if line.startswith(f"{anchors[locale]}:"))
                self.assertEqual(lines[anchor_index + 1], 'review_status: "en_revue"')
                self.assertEqual(lines[anchor_index + 2], "reviewed_on: null")

    def test_legacy_github_request_applies_both_french_review_transitions(self) -> None:
        bias = self.biases[0]
        with tempfile.TemporaryDirectory() as temporary:
            content_dir = Path(temporary)
            card = content_dir / bias.source_path.name
            card.write_text(bias.source_path.read_text(encoding="utf-8"), encoding="utf-8")
            start = f"REVUE | demarrer | {bias.slug}"
            finish = f"REVUE | terminer | {bias.slug}"
            apply_review_request.apply_request(start, content_dir=content_dir)
            apply_review_request.apply_request(
                finish,
                content_dir=content_dir,
                review_date=date(2026, 8, 10),
            )
            content = card.read_text(encoding="utf-8")
            self.assertIn('review_status: "revue"', content)
            self.assertIn('reviewed_on: "2026-08-10"', content)

    def test_localized_github_requests_apply_french_and_english_review_transitions(self) -> None:
        base = self.biases[0]
        english = build_site.read_translation(base, "en")
        self.assertIsNotNone(english)

        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            french_dir = temporary_root / "fr"
            english_dir = temporary_root / "en"
            french_dir.mkdir()
            english_dir.mkdir()
            french_card = french_dir / f"{base.slug}.md"
            english_card = english_dir / f"{base.slug}.md"
            french_card.write_text(base.canonical_source_path.read_text(encoding="utf-8"), encoding="utf-8")
            english_card.write_text(english.source_path.read_text(encoding="utf-8"), encoding="utf-8")

            previous_english_dir = apply_review_request.LOCALE_CONTENT_DIRS["en"]
            apply_review_request.LOCALE_CONTENT_DIRS["en"] = english_dir
            try:
                for locale, content_dir in (("fr", french_dir), ("en", english_dir)):
                    start = f"REVUE | demarrer | {locale} | {base.slug}"
                    finish = f"REVUE | terminer | {locale} | {base.slug}"
                    apply_review_request.apply_request(start, content_dir=content_dir)
                    apply_review_request.apply_request(
                        finish,
                        content_dir=content_dir,
                        review_date=date(2026, 8, 15),
                    )
                    card = french_card if locale == "fr" else english_card
                    content = card.read_text(encoding="utf-8")
                    self.assertIn('review_status: "revue"', content)
                    self.assertIn('reviewed_on: "2026-08-15"', content)
            finally:
                apply_review_request.LOCALE_CONTENT_DIRS["en"] = previous_english_dir

    def test_review_request_format_rejects_unknown_locales_and_path_traversal(self) -> None:
        slug = self.biases[0].slug
        self.assertEqual(
            apply_review_request.parse_request(f"REVUE | demarrer | fr | {slug}"),
            ("demarrer", "fr", slug),
        )
        self.assertEqual(
            apply_review_request.parse_request(f"REVUE | terminer | en | {slug}"),
            ("terminer", "en", slug),
        )
        self.assertEqual(
            apply_review_request.parse_request(f"REVUE | demarrer | {slug}"),
            ("demarrer", "fr", slug),
        )
        for invalid in (
            f"REVUE | demarrer | de | {slug}",
            "REVUE | demarrer | en | ../../secret",
            f"REVUE | publier | en | {slug}",
            f"REVUE | demarrer | en | {slug} | extra",
        ):
            with self.assertRaises(ValueError, msg=invalid):
                apply_review_request.parse_request(invalid)

    def test_review_requests_reject_unpublished_french_and_english_cards(self) -> None:
        base = self.biases[0]
        english = build_site.read_translation(base, "en")
        self.assertIsNotNone(english)
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            french_dir = temporary_root / "fr"
            english_dir = temporary_root / "en"
            french_dir.mkdir()
            english_dir.mkdir()
            (french_dir / f"{base.slug}.md").write_text(
                base.source_path.read_text(encoding="utf-8").replace(
                    'status: "documente"',
                    'status: "brouillon"',
                    1,
                ),
                encoding="utf-8",
            )
            (english_dir / f"{base.slug}.md").write_text(
                english.source_path.read_text(encoding="utf-8").replace(
                    'translation_status: "published"',
                    'translation_status: "draft"',
                    1,
                ),
                encoding="utf-8",
            )
            previous_english_dir = apply_review_request.LOCALE_CONTENT_DIRS["en"]
            apply_review_request.LOCALE_CONTENT_DIRS["en"] = english_dir
            try:
                with self.assertRaises(ValueError):
                    apply_review_request.apply_request(
                        f"REVUE | demarrer | fr | {base.slug}",
                        content_dir=french_dir,
                    )
                with self.assertRaises(ValueError):
                    apply_review_request.apply_request(
                        f"REVUE | demarrer | en | {base.slug}",
                        content_dir=french_dir,
                    )
            finally:
                apply_review_request.LOCALE_CONTENT_DIRS["en"] = previous_english_dir

    def test_review_workflow_is_restricted_to_the_repository_owner(self) -> None:
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "review-state.yml").read_text(encoding="utf-8")
        self.assertIn("github.actor_id == '158738352'", workflow)
        self.assertNotIn("github.actor ==", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("issues: write", workflow)
        self.assertIn("git add catalogue/biais catalogue/i18n", workflow)

    def test_detail_contains_authentication_and_rating_widget(self) -> None:
        details = {
            "fr": (next((self.output / "biais").glob("*/index.html")), "../../assets/community.js"),
            "en": (next((self.output / "en" / "biases").glob("*/index.html")), "../../../assets/community.js"),
        }
        for locale, (path, community_src) in details.items():
            detail = path.read_text(encoding="utf-8")
            self.assertIn('id="auth-dialog"', detail, path)
            self.assertIn('data-rating-widget="', detail, path)
            self.assertIn(build_site.t(locale, "rating.your_rating"), detail, path)
            self.assertIn('type="range" min="1" max="100"', detail, path)
            self.assertIn('data-example-editor data-bias-id="', detail, path)
            self.assertIn('textarea id="personal-example-', detail, path)
            self.assertIn('minlength="10" maxlength="600"', detail, path)
            self.assertIn('data-example-gallery data-bias-id="', detail, path)
            self.assertIn('data-examples-list aria-busy="true"', detail, path)
            self.assertIn('data-example-slot data-bias-id="', detail, path)
            self.assertIn(f'type="module" src="{community_src}"', detail, path)

    def test_every_detail_contains_the_personal_editor_and_public_gallery(self) -> None:
        localized_pages = {
            "fr": list((self.output / "biais").glob("*/index.html")),
            "en": list((self.output / "en" / "biases").glob("*/index.html")),
        }
        for locale, pages in localized_pages.items():
            self.assertEqual(len(pages), 39)
            for page in pages:
                detail = page.read_text(encoding="utf-8")
                self.assertEqual(detail.count("data-example-editor"), 1, page)
                self.assertEqual(detail.count("data-example-gallery"), 1, page)
                self.assertEqual(detail.count("data-example-slot"), 1, page)
                self.assertIn(build_site.t(locale, "examples.public_note"), detail, page)
                self.assertIn("data-example-signed-out", detail, page)
                self.assertIn("data-example-delete hidden", detail, page)
                self.assertIn('data-examples-status role="status" aria-live="polite"', detail, page)

    def test_leaderboard_contains_all_documented_biases(self) -> None:
        leaderboards = {
            "fr": self.output / "classement" / "index.html",
            "en": self.output / "en" / "ranking" / "index.html",
        }
        keys = ("rank", "bias", "average", "median", "ratings", "your_rating")
        for locale, path in leaderboards.items():
            leaderboard = path.read_text(encoding="utf-8")
            self.assertEqual(leaderboard.count("data-leaderboard-row"), 39, path)
            self.assertIn(build_site.t(locale, "leaderboard.title"), leaderboard, path)
            for key in keys:
                label = build_site.t(locale, f"leaderboard.{key}")
                self.assertEqual(leaderboard.count(f'data-label="{label}"'), 39, path)

    def test_supabase_schema_enforces_private_single_rating(self) -> None:
        schema = (PROJECT_ROOT / "supabase" / "migrations" / "20260813061613_community_ratings.sql").read_text(encoding="utf-8")
        self.assertIn("primary key (user_id, bias_id)", schema)
        self.assertIn("score between 1 and 100", schema)
        self.assertIn("alter table public.ratings enable row level security", schema)
        self.assertIn('create policy "ratings_update_own"', schema)
        summary_schema = (PROJECT_ROOT / "supabase" / "migrations" / "20260813061857_public_score_summaries.sql").read_text(encoding="utf-8")
        self.assertIn('create policy "bias_score_summaries_public_read"', summary_schema)
        self.assertIn("grant select on table public.bias_score_summaries to anon, authenticated", summary_schema)
        self.assertIn("drop function public.get_bias_scores()", summary_schema)

    def test_reviewer_access_cannot_be_self_assigned(self) -> None:
        schema = (PROJECT_ROOT / "supabase" / "migrations" / "20260813183024_reviewer_access.sql").read_text(
            encoding="utf-8"
        )
        normalized = schema.lower()
        self.assertIn("alter table public.reviewer_access enable row level security", normalized)
        self.assertIn('create policy "reviewer_access_select_own"', normalized)
        self.assertIn("using ((select auth.uid()) = user_id)", normalized)
        self.assertIn("revoke all on table public.reviewer_access from public, anon, authenticated", normalized)
        self.assertIn("grant select on table public.reviewer_access to authenticated", normalized)
        self.assertNotIn("grant insert", normalized)
        self.assertNotIn("grant update", normalized)
        self.assertNotIn("grant delete", normalized)

        community = (PROJECT_ROOT / "web" / "assets" / "community.js").read_text(encoding="utf-8")
        self.assertIn('.from("reviewer_access")', community)
        self.assertIn('.eq("user_id", state.user.id)', community)
        self.assertIn("state.canReview = false", community)
        self.assertNotRegex(schema + community, r"[\w.+-]+@gmail\.com")

    def test_community_examples_schema_protects_owners_and_votes(self) -> None:
        schema = (PROJECT_ROOT / "supabase" / "migrations" / "20260813203521_community_examples.sql").read_text(
            encoding="utf-8"
        )
        normalized = schema.lower()
        self.assertIn("unique (user_id, bias_id)", normalized)
        self.assertIn("primary key (user_id, example_id)", normalized)
        self.assertIn("example_text = btrim(example_text)", normalized)
        self.assertIn("char_length(example_text) between 10 and 600", normalized)
        self.assertIn("references auth.users(id) on delete cascade", normalized)
        self.assertIn("references public.bias_examples(id) on delete cascade", normalized)
        for table in ("bias_examples", "bias_example_hearts", "bias_example_summaries"):
            self.assertIn(f"alter table public.{table} enable row level security", normalized)
        self.assertIn('create policy "bias_examples_update_own"', normalized)
        self.assertIn("with check ((select auth.uid()) = user_id)", normalized)
        self.assertIn('create policy "bias_example_summaries_public_read"', normalized)
        self.assertIn("grant select\n  on table public.bias_example_summaries to anon, authenticated", normalized)
        self.assertNotIn("grant insert\n  on table public.bias_example_summaries", normalized)
        self.assertIn("grant insert (user_id, bias_id, example_text)", normalized)
        self.assertIn("grant update (example_text)", normalized)
        self.assertIn("grant insert (user_id, example_id)", normalized)
        self.assertIn("revoke all on function private.sync_bias_example_summary()", normalized)
        self.assertIn("revoke all on function private.sync_bias_example_heart_count()", normalized)
        self.assertIn("set search_path = pg_catalog, public", normalized)

        summary_block = normalized.split("create table public.bias_example_summaries", 1)[1].split(");", 1)[0]
        self.assertNotIn("user_id", summary_block)
        self.assertNotIn("email", summary_block)

        catalog_block = normalized.split("insert into private.bias_catalog", 1)[1].split(
            "create table public.bias_examples", 1
        )[0]
        registered = set(re.findall(r"\('([0-9]{3}-[a-z0-9-]+)'\)", catalog_block))
        self.assertEqual(registered, {bias.slug for bias in self.biases})

    def test_personal_examples_and_hearts_use_safe_client_contracts(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
        community = (PROJECT_ROOT / "web" / "assets" / "community.js").read_text(encoding="utf-8")
        self.assertIn('.from("bias_examples")', community)
        self.assertIn('.from("bias_example_summaries")', community)
        self.assertIn('.from("bias_example_hearts")', community)
        self.assertIn('.eq("user_id", state.user.id)', community)
        self.assertIn('.eq("bias_id", biasId)', community)
        self.assertIn('.eq("example_id", exampleId)', community)
        self.assertIn("text.textContent = personal.example_text", community)
        self.assertIn("text.textContent = example.example_text", community)
        self.assertIn("text.replaceChildren", community)
        self.assertIn("exampleText.length < 10", community)
        self.assertIn('t("examples.minimum")', community)
        self.assertIn('t(current ? "examples.updated" : "examples.added")', community)
        self.assertIn('t("examples.deleted")', community)
        self.assertEqual(
            build_site.t("fr", "examples.minimum"),
            "Votre exemple doit contenir au moins 10 caractères hors espaces.",
        )
        self.assertEqual(
            build_site.t("en", "examples.minimum"),
            "Your example must contain at least 10 non-space characters.",
        )
        self.assertIn("isCurrentSyncContext", community)
        self.assertIn("syncEpoch += 1", community)
        self.assertIn("personalHeartsError", community)
        self.assertIn("?.focus()", community)
        self.assertIn("submitButton.disabled = false", community)
        self.assertNotIn("innerHTML", community)
        self.assertNotIn("insertAdjacentHTML", community)
        self.assertIn('heart.setAttribute("aria-pressed", String(liked))', community)
        self.assertIn("bienpenser:personal-examples-changed", community)
        self.assertIn("bienpenser:personal-examples-changed", app)

    def test_publication_workflows_run_tests_before_building(self) -> None:
        for workflow_path in (
            PROJECT_ROOT / ".github" / "workflows" / "pages.yml",
            PROJECT_ROOT / ".github" / "workflows" / "review-state.yml",
        ):
            workflow = workflow_path.read_text(encoding="utf-8")
            tests_position = workflow.rfind("python -m unittest discover -s tests -v")
            build_position = workflow.rfind("python scripts/build_site.py --output _site")
            self.assertGreaterEqual(tests_position, 0, workflow_path)
            self.assertGreater(build_position, tests_position, workflow_path)
            for script in (
                "app.js",
                "install.js",
                "community.js",
                "i18n.js",
                "language.js",
                "not-found.js",
            ):
                self.assertIn(f"node --check web/assets/{script}", workflow, workflow_path)

        review_workflow = (PROJECT_ROOT / ".github" / "workflows" / "review-state.yml").read_text(
            encoding="utf-8"
        )
        apply_position = review_workflow.find('python scripts/apply_review_request.py "$REVIEW_REQUEST_TITLE"')
        precommit_tests_position = review_workflow.find(
            "python -m unittest discover -s tests -v",
            apply_position,
        )
        commit_position = review_workflow.find("git commit -m", precommit_tests_position)
        self.assertGreater(precommit_tests_position, apply_position)
        self.assertGreater(commit_position, precommit_tests_position)

    def test_mobile_contract_preserves_desktop_layout(self) -> None:
        styles = (PROJECT_ROOT / "web" / "assets" / "styles.css").read_text(encoding="utf-8")
        install = (PROJECT_ROOT / "web" / "assets" / "install.js").read_text(encoding="utf-8")
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", styles)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", styles)
        self.assertIn("min-width: 760px", styles)
        responsive = styles.split('@media (max-width: 800px), (max-height: 500px) and (pointer: coarse)', 1)[1]
        touch = styles.split('@media (max-width: 620px), (max-height: 500px) and (pointer: coarse)', 1)[1]
        self.assertIn("font-size: 16px", touch)
        self.assertIn("min-height: 44px", touch)
        self.assertIn("100dvh", touch)
        self.assertIn("env(safe-area-inset-bottom)", responsive)
        self.assertIn(".leaderboard-table tr", responsive)
        self.assertIn(".leaderboard-table tr[hidden]", responsive)
        self.assertIn("grid-row: 1 / span 2", responsive)
        self.assertIn('content: attr(data-label)', responsive)
        self.assertIn('(display-mode: standalone)', install)
        self.assertIn("window.navigator.standalone", install)
        self.assertIn('window.navigator.platform === "MacIntel"', install)
        self.assertIn('window.addEventListener("beforeinstallprompt"', install)
        self.assertIn('window.addEventListener("appinstalled"', install)

    def test_personal_rating_filters_share_a_single_visibility_controller(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
        community = (PROJECT_ROOT / "web" / "assets" / "community.js").read_text(encoding="utf-8")
        event_name = "bienpenser:personal-ratings-changed"
        self.assertIn(event_name, app)
        self.assertIn(event_name, community)
        self.assertIn("state.personal.has(card.dataset.biasId)", community)
        self.assertIn('card.dataset.userRated === "true"', app)
        self.assertIn('card.dataset.userRated === "false"', app)
        self.assertNotIn("card.hidden", community)

    def test_only_publishable_supabase_key_is_shipped(self) -> None:
        config = (PROJECT_ROOT / "web" / "assets" / "supabase-config.js").read_text(encoding="utf-8")
        self.assertIn("sb_publishable_", config)
        self.assertNotIn("service_role", config)
        self.assertNotIn("sb_secret_", config)

    def test_signup_redirects_to_the_github_pages_project_path(self) -> None:
        config = (PROJECT_ROOT / "web" / "assets" / "supabase-config.js").read_text(encoding="utf-8")
        community = (PROJECT_ROOT / "web" / "assets" / "community.js").read_text(encoding="utf-8")
        site_url = "https://j2m116.github.io/bien-penser-biais-cognitifs/"
        self.assertIn(f'export const SITE_URL = "{site_url}";', config)
        self.assertIn("emailRedirectTo: SITE_URL", community)
        self.assertIn("import { SITE_URL,", community)

    def test_documented_content_has_no_placeholders(self) -> None:
        localized = {
            "fr": (
                (self.output / "biais").glob("*/index.html"),
                ("à rédiger", "à traduire", "à ajouter", "à documenter"),
            ),
            "en": (
                (self.output / "en" / "biases").glob("*/index.html"),
                ("to be written", "to be translated", "to be added", "todo", "placeholder"),
            ),
        }
        for locale, (pages, forbidden) in localized.items():
            for page in pages:
                content = page.read_text(encoding="utf-8")
                visible_markup = re.sub(
                    r"<script\b[^>]*>.*?</script>",
                    "",
                    content,
                    flags=re.IGNORECASE | re.DOTALL,
                ).casefold()
                self.assertFalse(any(term in visible_markup for term in forbidden), page)
                self.assertIn(
                    build_site.t(locale, "detail.detailed_description").casefold(),
                    visible_markup,
                    page,
                )
                self.assertIn(build_site.t(locale, "detail.limits").casefold(), visible_markup, page)
                self.assertIn(build_site.t(locale, "detail.prevention").casefold(), visible_markup, page)

    def test_all_local_links_resolve(self) -> None:
        missing: list[tuple[Path, str]] = []
        for page in self.output.rglob("*.html"):
            parser = LinkParser()
            parser.feed(page.read_text(encoding="utf-8"))
            for href in parser.links:
                split = urlsplit(href)
                if split.scheme or split.netloc or href.startswith(("#", "mailto:")):
                    continue
                target = (page.parent / unquote(split.path)).resolve()
                if split.path.endswith("/") or target.is_dir():
                    target /= "index.html"
                if not target.exists():
                    missing.append((page.relative_to(self.output), href))
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
