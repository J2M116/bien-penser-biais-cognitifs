from __future__ import annotations

import sys
import tempfile
import unittest
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import build_site  # noqa: E402
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
        self.assertTrue((self.output / "index.html").is_file())
        self.assertTrue((self.output / "a-propos" / "index.html").is_file())
        self.assertTrue((self.output / "404.html").is_file())
        self.assertEqual(len(list((self.output / "biais").glob("*/index.html"))), 39)

    def test_home_contains_cards_and_controls(self) -> None:
        home = (self.output / "index.html").read_text(encoding="utf-8")
        self.assertEqual(home.count('data-bias-card'), 39)
        self.assertIn('id="search"', home)
        self.assertIn('id="importance-filter"', home)
        self.assertIn('id="evidence-filter"', home)
        self.assertIn('id="review-filter"', home)
        self.assertIn('data-family-filter="all"', home)
        review_states = ("non_revue", "en_revue", "revue")
        self.assertEqual(sum(home.count(f'data-review="{state}"') for state in review_states), 39)
        self.assertEqual(sum(home.count(f'review-state--{state}">') for state in review_states), 39)

    def test_every_source_card_has_review_metadata(self) -> None:
        for source in build_site.CONTENT_DIR.glob("*.md"):
            content = source.read_text(encoding="utf-8")
            self.assertRegex(content, r'(?m)^review_status: "(?:non_revue|en_revue|revue)"$', source)
            self.assertRegex(content, r'(?m)^reviewed_on: (?:null|"\d{4}-\d{2}-\d{2}")$', source)

    def test_in_review_card_opens_the_github_editor(self) -> None:
        bias = replace(self.biases[0], review_status="en_revue")
        card = build_site.render_card(bias)
        detail = build_site.render_detail(bias, None, None)
        self.assertIn("Revoir la fiche", card)
        self.assertIn("github.com/J2M116/bien-penser-biais-cognitifs/edit/main/", card)
        self.assertIn('target="_blank"', card)
        self.assertIn("Revoir la fiche", detail)

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

    def test_documented_content_has_no_placeholders(self) -> None:
        forbidden = ("à rédiger", "à traduire", "à ajouter", "à documenter")
        for page in (self.output / "biais").glob("*/index.html"):
            content = page.read_text(encoding="utf-8").lower()
            self.assertFalse(any(term in content for term in forbidden), page)
            self.assertIn("description détaillée", content)
            self.assertIn("limites et nuances", content)
            self.assertIn("deux réflexes utiles", content)

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
