from __future__ import annotations

import json
import re
import struct
import sys
import tempfile
import unittest
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
        self.assertTrue((self.output / "classement" / "index.html").is_file())
        self.assertTrue((self.output / "404.html").is_file())
        self.assertEqual(len(list((self.output / "biais").glob("*/index.html"))), 39)

    def test_pwa_manifest_and_icons_are_generated(self) -> None:
        manifest_path = self.output / "assets" / "manifest.webmanifest"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "Bien penser — Les biais cognitifs")
        self.assertEqual(manifest["short_name"], "Bien penser")
        self.assertEqual(manifest["lang"], "fr")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["start_url"], "../")
        self.assertEqual(manifest["scope"], "../")
        self.assertEqual((manifest_path.parent / manifest["start_url"]).resolve(), self.output.resolve())
        self.assertEqual((manifest_path.parent / manifest["scope"]).resolve(), self.output.resolve())
        self.assertEqual(manifest["theme_color"], "#15273f")
        self.assertEqual(manifest["background_color"], "#f3eee5")

        expected_sizes = {
            "icons/icon-192.png": (192, 192),
            "icons/icon-512.png": (512, 512),
            "icons/icon-maskable-512.png": (512, 512),
            "icons/apple-touch-icon.png": (180, 180),
            "icons/favicon-32.png": (32, 32),
        }
        purposes = {icon["purpose"] for icon in manifest["icons"]}
        self.assertEqual(purposes, {"any", "maskable"})
        for relative_path, dimensions in expected_sizes.items():
            image_path = manifest_path.parent / relative_path
            self.assertTrue(image_path.is_file(), relative_path)
            data = image_path.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", data[16:24]), dimensions)

    def test_every_page_has_installable_metadata_with_resolving_paths(self) -> None:
        pages = list(self.output.rglob("*.html"))
        self.assertEqual(len(pages), 43)
        for page in pages:
            content = page.read_text(encoding="utf-8")
            self.assertEqual(content.count('rel="manifest"'), 1, page)
            self.assertEqual(content.count('rel="apple-touch-icon"'), 1, page)
            self.assertIn("viewport-fit=cover", content, page)
            self.assertIn('name="apple-mobile-web-app-capable" content="yes"', content, page)
            self.assertIn('name="apple-mobile-web-app-title" content="Bien penser"', content, page)
            self.assertIn('id="install-dialog"', content, page)
            self.assertIn("Partager", content, page)
            self.assertIn("Sur l’écran d’accueil", content, page)
            self.assertIn('class="mobile-nav"', content, page)
            if page.name != "404.html":
                self.assertIn("data-install-open hidden", content, page)

        not_found = (self.output / "404.html").read_text(encoding="utf-8")
        self.assertIn(f'href="{build_site.PUBLIC_SITE_URL}assets/manifest.webmanifest"', not_found)
        self.assertIn(f'href="{build_site.PUBLIC_SITE_URL}"', not_found)
        self.assertNotIn('href="assets/manifest.webmanifest"', not_found)

    def test_home_contains_cards_and_controls(self) -> None:
        home = (self.output / "index.html").read_text(encoding="utf-8")
        self.assertEqual(home.count('data-bias-card'), 39)
        self.assertEqual(home.count('data-bias-card data-bias-id="'), 39)
        self.assertEqual(home.count('data-example-slot'), 39)
        self.assertEqual(home.count('data-example-text'), 39)
        self.assertIn('id="search"', home)
        self.assertIn('id="importance-filter"', home)
        self.assertIn('id="evidence-filter"', home)
        self.assertIn('id="review-filter"', home)
        self.assertIn('data-family-filter="all"', home)
        self.assertIn('href="classement/"', home)
        self.assertEqual(home.count('data-community-score="'), 39)
        self.assertIn('data-personal-scope="all" aria-pressed="true"', home)
        self.assertIn('data-personal-scope="mine" aria-pressed="false" disabled', home)
        self.assertIn('data-personal-scope="unrated" aria-pressed="false" disabled', home)
        self.assertIn('data-personal-filter-status aria-live="polite"', home)
        review_states = ("non_revue", "en_revue", "revue")
        self.assertEqual(sum(home.count(f'data-review="{state}"') for state in review_states), 39)
        self.assertEqual(sum(home.count(f'review-state--{state}">') for state in review_states), 39)

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
        bias = replace(self.biases[0], review_status="non_revue", reviewed_on=None)
        request = build_site.review_request_url(bias, "demarrer")
        query = parse_qs(urlsplit(request).query)
        self.assertEqual(query["title"], [f"REVUE | demarrer | {bias.slug}"])
        detail = build_site.render_detail(bias, None, None)
        self.assertIn("Passer en revue", detail)
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

    def test_github_request_applies_both_review_transitions(self) -> None:
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

    def test_review_workflow_is_restricted_to_the_repository_owner(self) -> None:
        workflow = (PROJECT_ROOT / ".github" / "workflows" / "review-state.yml").read_text(encoding="utf-8")
        self.assertIn("github.actor_id == '158738352'", workflow)
        self.assertNotIn("github.actor ==", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("issues: write", workflow)

    def test_detail_contains_authentication_and_rating_widget(self) -> None:
        detail = next((self.output / "biais").glob("*/index.html")).read_text(encoding="utf-8")
        self.assertIn('id="auth-dialog"', detail)
        self.assertIn('data-rating-widget="', detail)
        self.assertIn("Votre évaluation", detail)
        self.assertIn('type="range" min="1" max="100"', detail)
        self.assertIn('data-example-editor data-bias-id="', detail)
        self.assertIn('textarea id="personal-example-', detail)
        self.assertIn('minlength="10" maxlength="600"', detail)
        self.assertIn('data-example-gallery data-bias-id="', detail)
        self.assertIn('data-examples-list aria-busy="true"', detail)
        self.assertIn('data-example-slot data-bias-id="', detail)
        self.assertIn('type="module" src="../../assets/community.js"', detail)

    def test_every_detail_contains_the_personal_editor_and_public_gallery(self) -> None:
        pages = list((self.output / "biais").glob("*/index.html"))
        self.assertEqual(len(pages), 39)
        for page in pages:
            detail = page.read_text(encoding="utf-8")
            self.assertEqual(detail.count("data-example-editor"), 1, page)
            self.assertEqual(detail.count("data-example-gallery"), 1, page)
            self.assertEqual(detail.count("data-example-slot"), 1, page)
            self.assertIn("Cet exemple sera visible publiquement", detail, page)
            self.assertIn("data-example-signed-out", detail, page)
            self.assertIn("data-example-delete hidden", detail, page)
            self.assertIn('data-examples-status role="status" aria-live="polite"', detail, page)

    def test_leaderboard_contains_all_documented_biases(self) -> None:
        leaderboard = (self.output / "classement" / "index.html").read_text(encoding="utf-8")
        self.assertEqual(leaderboard.count("data-leaderboard-row"), 39)
        self.assertIn("Classement communautaire", leaderboard)
        self.assertIn("Score moyen", leaderboard)
        self.assertIn("Votre note", leaderboard)
        for label in ("Rang", "Biais", "Score moyen", "Médiane", "Notes", "Votre note"):
            self.assertEqual(leaderboard.count(f'data-label="{label}"'), 39)

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
        self.assertIn("au moins 10 caractères hors espaces", community)
        self.assertIn("L’exemple éditorial est de nouveau affiché", community)
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
            self.assertIn("node --check web/assets/app.js", workflow)
            self.assertIn("node --check web/assets/install.js", workflow)
            self.assertIn("node --check web/assets/community.js", workflow)

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
