from __future__ import annotations

import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import build_site  # noqa: E402


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
        self.assertIn('data-family-filter="all"', home)

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
