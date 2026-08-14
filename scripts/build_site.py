#!/usr/bin/env python3
"""Build the static cognitive-bias catalogue without third-party packages."""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlencode


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "catalogue" / "biais"
WEB_DIR = PROJECT_ROOT / "web"
BUILD_MARKER = ".bien-penser-build"

FAMILY_LABELS = {
    "affect_emotion": "Émotions",
    "attention_perception": "Attention et perception",
    "croyances_preuves": "Croyances et preuves",
    "probabilite_estimation": "Probabilité et estimation",
    "memoire_temps": "Mémoire et temps",
    "decision_action": "Décision et action",
    "influence_sociale": "Influence sociale",
    "attribution_groupes": "Attribution et groupes",
    "metacognition_confiance": "Confiance et métacognition",
}

EVIDENCE_LABELS = {
    "forte": "Preuves fortes",
    "moderee": "Preuves modérées",
    "limitee": "Preuves limitées",
    "contestee": "Preuves contestées",
    "a_evaluer": "Preuves à évaluer",
}

EVIDENCE_ORDER = {"forte": 0, "moderee": 1, "limitee": 2, "contestee": 3, "a_evaluer": 4}

REVIEW_LABELS = {
    "non_revue": "Non revue",
    "en_revue": "En revue",
    "revue": "Revue",
}

REVIEW_DESCRIPTIONS = {
    "non_revue": "Cette fiche n'a pas encore fait l'objet d'une revue individuelle.",
    "en_revue": "La revue individuelle de cette fiche est en cours.",
    "revue": "Cette fiche a fait l'objet d'une revue individuelle achevée.",
}

FRENCH_MONTHS = (
    "",
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)

GITHUB_REPOSITORY = "https://github.com/J2M116/bien-penser-biais-cognitifs"
GITHUB_EDIT_ROOT = f"{GITHUB_REPOSITORY}/edit/main"
GITHUB_NEW_ISSUE = f"{GITHUB_REPOSITORY}/issues/new"
PUBLIC_SITE_URL = "https://j2m116.github.io/bien-penser-biais-cognitifs/"


@dataclass(frozen=True)
class Bias:
    number: int
    slug: str
    name_fr: str
    name_en: str
    aliases_fr: tuple[str, ...]
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
    review_status = str(parse_scalar(front, "review_status", "non_revue"))
    if review_status not in REVIEW_LABELS:
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
    return Bias(
        number=int(parse_scalar(front, "source_number")),
        slug=path.stem,
        name_fr=str(parse_scalar(front, "name_fr")),
        name_en=str(parse_scalar(front, "name_en")),
        aliases_fr=parse_list(front, "aliases_fr"),
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
    )


def inline_markdown(value: str) -> str:
    escaped = html.escape(value, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    return escaped


def render_paragraphs(value: str) -> str:
    return "\n".join(f"<p>{inline_markdown(block)}</p>" for block in value.split("\n\n") if block)


def importance_marks(level: int, *, label: bool = True) -> str:
    marks = "".join(
        f'<span class="importance-mark{" is-active" if point <= level else ""}" aria-hidden="true"></span>'
        for point in range(1, 6)
    )
    aria = f' aria-label="Importance {level} sur 5"' if label else ""
    return f'<span class="importance"{aria}>{marks}<span class="importance-value">{level}/5</span></span>'


def evidence_badge(evidence: str) -> str:
    return (
        f'<span class="evidence evidence--{html.escape(evidence)}">'
        f'{html.escape(EVIDENCE_LABELS.get(evidence, evidence))}</span>'
    )


def family_badge(family: str) -> str:
    return f'<span class="family-tag">{html.escape(FAMILY_LABELS.get(family, family))}</span>'


def format_review_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    return f"{parsed.day} {FRENCH_MONTHS[parsed.month]} {parsed.year}"


def review_badge(bias: Bias) -> str:
    label = REVIEW_LABELS[bias.review_status]
    return (
        f'<span class="review-state review-state--{html.escape(bias.review_status)}">'
        f'{html.escape(label)}</span>'
    )


def review_metadata(bias: Bias) -> str:
    reviewed_date = ""
    if bias.reviewed_on:
        reviewed_date = f'<time datetime="{bias.reviewed_on}">Dernière revue : {format_review_date(bias.reviewed_on)}</time>'
    return f'<div class="review-meta">{review_badge(bias)}{reviewed_date}</div>'


def edit_url(bias: Bias) -> str:
    relative_path = bias.source_path.relative_to(PROJECT_ROOT).as_posix()
    return f"{GITHUB_EDIT_ROOT}/{relative_path}"


def account_button() -> str:
    return (
        '<button class="account-button" type="button" data-auth-open '
        'aria-haspopup="dialog"><span class="account-dot" aria-hidden="true"></span>'
        '<span data-account-label>Se connecter</span></button>'
    )


def install_button() -> str:
    return '<button class="install-button" type="button" data-install-open hidden>Installer</button>'


def install_dialog() -> str:
    return """<dialog id="install-dialog" class="install-dialog" aria-labelledby="install-title">
  <div class="install-dialog-inner">
    <form method="dialog" class="dialog-close-form"><button class="dialog-close" aria-label="Fermer">×</button></form>
    <p class="eyebrow">Bien penser sur votre appareil</p>
    <h2 id="install-title">Installer l’application</h2>
    <div data-install-ios-instructions hidden>
      <p>Dans Safari, touchez <strong>Partager</strong>, puis <strong>Sur l’écran d’accueil</strong>. Si l’option est proposée, activez «&nbsp;Ouvrir comme app web&nbsp;», puis touchez <strong>Ajouter</strong>.</p>
    </div>
    <div data-install-browser-instructions hidden>
      <p>Installez Bien penser pour l’ouvrir directement depuis votre écran d’accueil ou votre bureau.</p>
      <button class="install-confirm" type="button" data-install-confirm>Installer l’application</button>
    </div>
  </div>
</dialog>"""


def mobile_navigation(relative_root: str) -> str:
    root = relative_root or "./"
    return f"""<nav class="mobile-nav" aria-label="Navigation mobile">
  <a href="{root}"><span aria-hidden="true">⌂</span>Catalogue</a>
  <a href="{root}classement/"><span aria-hidden="true">↗</span>Classement</a>
  <a href="{root}a-propos/"><span aria-hidden="true">i</span>Méthode</a>
</nav>"""


def auth_dialog() -> str:
    return """<dialog id="auth-dialog" class="auth-dialog" aria-labelledby="auth-title">
  <div class="auth-dialog-inner">
    <form method="dialog" class="dialog-close-form"><button class="dialog-close" aria-label="Fermer">×</button></form>
    <div data-auth-anonymous>
      <p class="eyebrow">Espace personnel</p>
      <h2 id="auth-title">Votre regard compte.</h2>
      <p class="auth-intro">Connectez-vous pour évaluer l'importance des biais de 1 à 100. Chaque note reste modifiable.</p>
      <div class="auth-tabs" role="tablist" aria-label="Connexion ou inscription">
        <button class="is-active" type="button" role="tab" aria-selected="true" data-auth-tab="login">Connexion</button>
        <button type="button" role="tab" aria-selected="false" data-auth-tab="register">Créer un compte</button>
      </div>
      <form class="auth-form" data-auth-form="login">
        <label><span>Adresse e-mail</span><input name="email" type="email" autocomplete="email" required></label>
        <label><span>Mot de passe</span><input name="password" type="password" autocomplete="current-password" minlength="6" required></label>
        <button class="auth-submit" type="submit">Se connecter</button>
      </form>
      <form class="auth-form" data-auth-form="register" hidden>
        <label><span>Pseudonyme public</span><input name="display_name" type="text" autocomplete="nickname" minlength="2" maxlength="40" required></label>
        <label><span>Adresse e-mail</span><input name="email" type="email" autocomplete="email" required></label>
        <label><span>Mot de passe</span><input name="password" type="password" autocomplete="new-password" minlength="6" required></label>
        <button class="auth-submit" type="submit">Créer mon compte</button>
      </form>
      <p class="auth-message" data-auth-message aria-live="polite"></p>
    </div>
    <div class="auth-profile" data-auth-profile hidden>
      <p class="eyebrow">Compte connecté</p>
      <h2>Bonjour, <span data-profile-name>membre</span>.</h2>
      <p>Vos évaluations sont enregistrées et vous pouvez les modifier à tout moment.</p>
      <p class="reviewer-badge" data-reviewer-badge hidden>Accès éditorial activé : vous pouvez faire évoluer les fiches.</p>
      <button class="auth-signout" type="button" data-sign-out>Se déconnecter</button>
    </div>
  </div>
</dialog>"""


def community_score(bias: Bias, *, compact: bool = False) -> str:
    modifier = " community-score--compact" if compact else ""
    return f"""<div class="community-score{modifier}" data-community-score="{html.escape(bias.slug)}">
  <span class="community-score-label">Score communautaire</span>
  <strong><span data-score-value>—</span><small>/100</small></strong>
  <span data-score-count>Aucune évaluation</span>
</div>"""


def rating_widget(bias: Bias) -> str:
    return f"""<section class="rating-panel" data-rating-widget="{html.escape(bias.slug)}" aria-labelledby="rating-title">
  <div class="rating-summary">
    <p class="section-kicker">Importance perçue</p>
    <h2 id="rating-title">À quel point faut-il y faire attention ?</h2>
    <p>Donnez votre appréciation personnelle de 1 à 100. Elle n'altère pas le score éditorial de la fiche.</p>
    {community_score(bias)}
  </div>
  <div class="rating-personal">
    <div data-rating-signed-out>
      <p><strong>Connectez-vous pour noter ce biais.</strong></p>
      <button class="rating-login" type="button" data-auth-open>Se connecter ou créer un compte</button>
    </div>
    <form data-rating-form hidden>
      <label for="rating-{html.escape(bias.slug)}">Votre évaluation</label>
      <div class="rating-value"><output for="rating-{html.escape(bias.slug)}" data-rating-output>50</output><span>/100</span></div>
      <input id="rating-{html.escape(bias.slug)}" name="score" type="range" min="1" max="100" value="50" step="1">
      <div class="rating-scale"><span>Peu important</span><span>Très important</span></div>
      <div class="rating-actions">
        <button class="rating-save" type="submit">Enregistrer ma note</button>
        <button class="rating-delete" type="button" data-rating-delete hidden>Supprimer</button>
      </div>
      <p class="rating-message" data-rating-message aria-live="polite"></p>
    </form>
  </div>
</section>"""


def personal_example_editor(bias: Bias) -> str:
    slug = html.escape(bias.slug)
    return f"""<section class="personal-example-panel" data-example-editor data-bias-id="{slug}"
  aria-labelledby="personal-example-title">
  <div class="personal-example-copy">
    <p class="section-kicker">Votre situation</p>
    <h2 id="personal-example-title">Quel exemple vous parle vraiment&nbsp;?</h2>
    <p>Ajoutez une situation concrète pour retrouver ce biais plus facilement. Après connexion, elle remplacera l'exemple éditorial dans votre catalogue.</p>
  </div>
  <div class="personal-example-editor">
    <div data-example-signed-out>
      <p><strong>Connectez-vous pour ajouter votre exemple.</strong></p>
      <button class="example-login" type="button" data-auth-open>Se connecter ou créer un compte</button>
    </div>
    <p class="example-loading" data-example-loading hidden>Chargement de votre exemple…</p>
    <form data-example-form hidden>
      <label for="personal-example-{slug}">Votre exemple personnel</label>
      <textarea id="personal-example-{slug}" name="example_text" minlength="10" maxlength="600"
        rows="5" required aria-describedby="example-public-note-{slug} example-counter-{slug}"></textarea>
      <div class="example-form-meta">
        <p id="example-public-note-{slug}">Cet exemple sera visible publiquement et pourra recevoir des cœurs. Votre adresse e-mail ne sera jamais affichée.</p>
        <span id="example-counter-{slug}" data-example-counter>0/600</span>
      </div>
      <div class="example-actions">
        <button class="example-save" type="submit" data-example-save>Ajouter mon exemple</button>
        <button class="example-delete" type="button" data-example-delete hidden>Supprimer</button>
      </div>
      <p class="example-message" data-example-message role="status" aria-live="polite"></p>
    </form>
  </div>
</section>"""


def community_examples_gallery(bias: Bias) -> str:
    slug = html.escape(bias.slug)
    return f"""<section class="community-examples" data-example-gallery data-bias-id="{slug}"
  aria-labelledby="community-examples-title">
  <div class="community-examples-heading">
    <div>
      <p class="section-kicker">Situations vécues</p>
      <h2 id="community-examples-title">Les exemples de la communauté</h2>
    </div>
    <p><strong data-examples-total>0</strong> <span data-examples-total-label>exemple partagé</span></p>
  </div>
  <div class="examples-feedback">
    <p data-examples-status role="status" aria-live="polite">Chargement des exemples partagés…</p>
    <button type="button" data-examples-retry hidden>Réessayer</button>
  </div>
  <div class="community-examples-list" data-examples-list aria-busy="true"></div>
  <button class="examples-more" type="button" data-examples-more hidden>Afficher davantage d'exemples</button>
</section>"""


def review_request_url(bias: Bias, action: str) -> str:
    action_labels = {
        "demarrer": "passer la fiche en revue",
        "terminer": "marquer la fiche comme revue",
    }
    if action not in action_labels:
        raise ValueError(f"Unknown review action: {action}")
    title = f"REVUE | {action} | {bias.slug}"
    body = (
        "Cette demande a été préparée par le catalogue Bien penser.\n\n"
        f"- Fiche : **{bias.name_fr}**\n"
        f"- Action : **{action_labels[action]}**\n\n"
        "Pour confirmer, créez cette demande sans modifier son titre. "
        "Elle sera traitée automatiquement puis fermée après la mise à jour du site."
    )
    return f"{GITHUB_NEW_ISSUE}?{urlencode({'title': title, 'body': body})}"


def page_shell(*, title: str, description: str, relative_root: str, body: str, page_class: str) -> str:
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="description" content="{html.escape(description, quote=True)}">
  <meta name="theme-color" content="#15273f">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="Bien penser">
  <title>{html.escape(title)}</title>
  <link rel="manifest" href="{relative_root}assets/manifest.webmanifest">
  <link rel="apple-touch-icon" sizes="180x180" href="{relative_root}assets/icons/apple-touch-icon.png">
  <link rel="icon" type="image/png" sizes="32x32" href="{relative_root}assets/icons/favicon-32.png">
  <link rel="stylesheet" href="{relative_root}assets/styles.css">
  <script src="{relative_root}assets/app.js" defer></script>
  <script src="{relative_root}assets/install.js" defer></script>
  <script type="module" src="{relative_root}assets/community.js"></script>
</head>
<body class="{page_class}">
  <a class="skip-link" href="#contenu">Aller au contenu</a>
  {mobile_navigation(relative_root)}
  {body}
  {auth_dialog()}
  {install_dialog()}
</body>
</html>
"""


def render_card(bias: Bias) -> str:
    search_text = " ".join(
        [
            bias.name_fr,
            bias.name_en,
            *bias.aliases_fr,
            FAMILY_LABELS.get(bias.family, bias.family),
            bias.short,
            bias.example,
        ]
    ).casefold()
    public_url = f"biais/{bias.slug}/"
    public_aria_label = f"Ouvrir la fiche {bias.name_fr}"
    reviewing = bias.review_status == "en_revue"
    reviewer_card_attribute = " data-reviewer-card" if reviewing else ""
    reviewer_link_attributes = ""
    if reviewing:
        reviewer_link_attributes = (
            f' data-reviewer-href="{html.escape(edit_url(bias), quote=True)}"'
            f' data-reviewer-aria-label="{html.escape(f"Revoir la fiche {bias.name_fr} dans l\'éditeur GitHub", quote=True)}"'
        )
    return f"""<article class="bias-card" data-bias-card data-bias-id="{html.escape(bias.slug)}"
    data-user-rated="unknown"{reviewer_card_attribute} data-family="{html.escape(bias.family)}"
    data-importance="{bias.importance}" data-evidence="{html.escape(bias.evidence)}"
    data-review="{html.escape(bias.review_status)}"
    data-name="{html.escape(bias.name_fr.casefold(), quote=True)}"
    data-search="{html.escape(search_text, quote=True)}">
  <a class="card-link" href="{html.escape(public_url, quote=True)}"
     aria-label="{html.escape(public_aria_label, quote=True)}" data-card-primary-action
     data-public-href="{html.escape(public_url, quote=True)}"
     data-public-aria-label="{html.escape(public_aria_label, quote=True)}"{reviewer_link_attributes}>
    <div class="card-topline">
      {family_badge(bias.family)}
      <span class="card-number">Nº {bias.number}</span>
    </div>
    {review_metadata(bias)}
    <h2>{html.escape(bias.name_fr)}</h2>
    <p class="english-name" lang="en">{html.escape(bias.name_en)}</p>
    <p class="card-summary">{inline_markdown(bias.short)}</p>
    <div class="card-example" data-example-slot data-bias-id="{html.escape(bias.slug)}">
      <span data-example-label>Exemple</span><p data-example-text>{inline_markdown(bias.example)}</p>
    </div>
    <div class="card-footer">
      {importance_marks(bias.importance)}
      {evidence_badge(bias.evidence)}
    </div>
    {community_score(bias, compact=True)}
    <span class="card-open" aria-hidden="true"><span data-card-action-label>Lire la fiche</span> <span>→</span></span>
  </a>
</article>"""


def render_home(biases: list[Bias]) -> str:
    families = Counter(bias.family for bias in biases)
    reviews = Counter(bias.review_status for bias in biases)
    family_buttons = "\n".join(
        f'<button class="filter-chip" type="button" data-family-filter="{html.escape(key)}" aria-pressed="false">'
        f'{html.escape(FAMILY_LABELS[key])}<span>{count}</span></button>'
        for key, count in sorted(families.items(), key=lambda item: FAMILY_LABELS[item[0]])
    )
    cards = "\n".join(render_card(bias) for bias in biases)
    body = f"""<header class="site-header">
  <div class="header-inner">
    <a class="wordmark" href="./" aria-label="Bien penser, accueil">
      <span class="wordmark-mark" aria-hidden="true">P</span>
      <span><strong>Bien penser</strong><small>Les biais cognitifs</small></span>
    </a>
    <nav class="header-actions" aria-label="Navigation principale">
      <a class="about-link" href="classement/">Classement</a>
      <a class="about-link" href="a-propos/">À propos</a>
      {install_button()}
      {account_button()}
    </nav>
  </div>
</header>

<main id="contenu">
  <section class="hero" aria-labelledby="hero-title">
    <div class="hero-copy">
      <p class="eyebrow">Un catalogue critique et évolutif</p>
      <h1 id="hero-title">Voir les raccourcis<br>qui orientent nos jugements.</h1>
      <p class="hero-intro">Une carte pour comprendre l'essentiel. Une fiche pour examiner les preuves, les limites et les moyens d'agir.</p>
      <a class="leaderboard-cta" href="classement/">Voir le classement communautaire <span aria-hidden="true">→</span></a>
      <div class="hero-stats" aria-label="Contenu du catalogue">
        <span><strong>{len(biases)}</strong> fiches documentées</span>
        <span><strong>{reviews['revue']}</strong> fiches revues</span>
        <span><strong>{reviews['en_revue']}</strong> en cours de revue</span>
        <span><strong>{len(families)}</strong> familles</span>
      </div>
    </div>
    <blockquote>
      <p>« Travaillons donc à bien penser : voilà le principe de la morale. »</p>
      <footer>Blaise Pascal, <cite>Pensées</cite></footer>
    </blockquote>
  </section>

  <section class="catalogue" aria-labelledby="catalogue-title">
    <div class="catalogue-heading">
      <div>
        <p class="eyebrow">Explorer</p>
        <h2 id="catalogue-title">Les biais prioritaires</h2>
      </div>
      <p><span id="result-count">{len(biases)}</span> fiches affichées</p>
    </div>

    <div class="controls" aria-label="Recherche et filtres">
      <label class="search-field">
        <span>Rechercher</span>
        <input id="search" type="search" placeholder="Un biais, un exemple, un mot…" autocomplete="off">
      </label>
      <label>
        <span>Importance minimale</span>
        <select id="importance-filter">
          <option value="0">Toutes</option>
          <option value="5">5 — critique</option>
          <option value="4">4 — élevée</option>
          <option value="3">3 — modérée</option>
        </select>
      </label>
      <label>
        <span>Solidité des preuves</span>
        <select id="evidence-filter">
          <option value="all">Toutes</option>
          <option value="forte">Fortes</option>
          <option value="moderee">Modérées</option>
          <option value="limitee">Limitées</option>
          <option value="contestee">Contestées</option>
        </select>
      </label>
      <label>
        <span>État de la revue</span>
        <select id="review-filter">
          <option value="all">Tous</option>
          <option value="non_revue">Non revues</option>
          <option value="en_revue">En revue</option>
          <option value="revue">Revues</option>
        </select>
      </label>
      <label>
        <span>Trier par</span>
        <select id="sort-order">
          <option value="importance">Importance</option>
          <option value="alphabetical">Ordre alphabétique</option>
          <option value="evidence">Solidité des preuves</option>
          <option value="review">État de la revue</option>
        </select>
      </label>
      <button id="reset-filters" class="reset-button" type="button">Réinitialiser</button>
    </div>

    <div class="personal-filter-panel">
      <div class="personal-rating-filters" aria-label="Filtrer selon vos évaluations">
        <span class="personal-filter-label">Vos évaluations</span>
        <button class="filter-chip is-active" type="button" data-personal-scope="all" aria-pressed="true">Toutes les fiches</button>
        <button class="filter-chip" type="button" data-personal-scope="mine" aria-pressed="false" disabled>Notées par moi</button>
        <button class="filter-chip" type="button" data-personal-scope="unrated" aria-pressed="false" disabled>Non notées par moi</button>
      </div>
      <p class="personal-filter-status" data-personal-filter-status aria-live="polite">Connectez-vous pour filtrer le catalogue selon vos notes.</p>
    </div>

    <div class="family-filters" aria-label="Filtrer par famille">
      <button class="filter-chip is-active" type="button" data-family-filter="all" aria-pressed="true">Toutes<span>{len(biases)}</span></button>
      {family_buttons}
    </div>

    <div id="bias-grid" class="bias-grid">
      {cards}
    </div>
    <div id="empty-state" class="empty-state" hidden>
      <strong>Aucune fiche ne correspond.</strong>
      <p>Essayez un autre mot ou réinitialisez les filtres.</p>
    </div>
  </section>
</main>

<footer class="site-footer">
  <p>Contenu ouvert à la révision — les scores d'importance restent provisoires.</p>
  <div class="site-footer-links"><a href="classement/">Classement</a><a href="a-propos/">Méthode et sources</a></div>
</footer>"""
    return page_shell(
        title="Bien penser — Les biais cognitifs",
        description="Un catalogue visuel et documenté des biais cognitifs : cartes synthétiques, preuves, limites et prévention.",
        relative_root="",
        body=body,
        page_class="home-page",
    )


def render_detail(bias: Bias, previous: Bias | None, following: Bias | None) -> str:
    aliases = ""
    if bias.aliases_fr:
        aliases = f'<p class="aliases"><span>Aussi appelé</span> {html.escape(", ".join(bias.aliases_fr))}</p>'
    prevention = "\n".join(f"<li>{inline_markdown(item)}</li>" for item in bias.prevention)
    sources = "\n".join(
        f'<li><a href="{html.escape(url, quote=True)}" rel="noreferrer">{html.escape(label)}</a></li>'
        for label, url in bias.sources
    )
    previous_link = (
        f'<a href="../{html.escape(previous.slug)}/"><span>← Fiche précédente</span><strong>{html.escape(previous.name_fr)}</strong></a>'
        if previous else "<span></span>"
    )
    next_link = (
        f'<a class="next" href="../{html.escape(following.slug)}/"><span>Fiche suivante →</span><strong>{html.escape(following.name_fr)}</strong></a>'
        if following else "<span></span>"
    )
    if bias.review_status == "non_revue":
        review_controls = f"""<a class="review-action" href="{html.escape(review_request_url(bias, 'demarrer'), quote=True)}" target="_blank" rel="noreferrer">Passer en revue <span aria-hidden="true">→</span></a>
        <p>GitHub vous demandera de confirmer cette transition. L'état de la fiche sera ensuite mis à jour et republié automatiquement.</p>"""
    elif bias.review_status == "en_revue":
        review_controls = f"""<div class="review-button-group">
          <a class="review-action" href="{html.escape(edit_url(bias), quote=True)}" target="_blank" rel="noreferrer">Faire évoluer la fiche <span aria-hidden="true">↗</span></a>
          <a class="review-transition" href="{html.escape(review_request_url(bias, 'terminer'), quote=True)}" target="_blank" rel="noreferrer">Marquer comme revue</a>
        </div>
        <p>Modifiez le contenu dans GitHub autant de fois que nécessaire. Lorsque la revue est terminée, sa date sera inscrite automatiquement.</p>"""
    else:
        review_controls = f"""<a class="review-action" href="{html.escape(review_request_url(bias, 'demarrer'), quote=True)}" target="_blank" rel="noreferrer">Relancer une revue <span aria-hidden="true">→</span></a>
        <p>Une nouvelle passe conservera la date de la dernière revue achevée jusqu'à la prochaine validation.</p>"""
    review_date = ""
    if bias.reviewed_on:
        review_date = (
            f'<p class="review-panel-date">Dernière revue achevée le '
            f'<time datetime="{bias.reviewed_on}">{format_review_date(bias.reviewed_on)}</time>.</p>'
        )
    body = f"""<header class="site-header detail-header">
  <div class="header-inner">
    <a class="wordmark" href="../../" aria-label="Bien penser, retour au catalogue">
      <span class="wordmark-mark" aria-hidden="true">P</span>
      <span><strong>Bien penser</strong><small>Les biais cognitifs</small></span>
    </a>
    <nav class="header-actions" aria-label="Navigation principale">
      <a class="back-link" href="../../">← Toutes les cartes</a>
      <a class="about-link" href="../../classement/">Classement</a>
      {install_button()}
      {account_button()}
    </nav>
  </div>
</header>

<main id="contenu" class="detail-main">
  <article>
    <header class="bias-hero">
      <div class="detail-badges">{family_badge(bias.family)} {evidence_badge(bias.evidence)} {review_badge(bias)}</div>
      <p class="detail-number">Fiche nº {bias.number}</p>
      <h1>{html.escape(bias.name_fr)}</h1>
      <p class="detail-english" lang="en">{html.escape(bias.name_en)}</p>
      {aliases}
      <p class="detail-lead">{inline_markdown(bias.short)}</p>
      <div class="detail-importance">
        <span>Importance provisoire</span>
        {importance_marks(bias.importance)}
      </div>
    </header>

    <section class="review-panel" aria-labelledby="review-panel-title">
      <div>
        <p class="section-kicker">Suivi éditorial</p>
        <h2 id="review-panel-title">{REVIEW_LABELS[bias.review_status]}</h2>
        <p>{REVIEW_DESCRIPTIONS[bias.review_status]}</p>
        {review_date}
      </div>
      <div class="review-panel-control">
        <div class="review-panel-actions" data-reviewer-only hidden>
          {review_controls}
        </div>
        <div class="review-panel-locked" data-reviewer-locked>
          <p>Les commandes de revue sont réservées au responsable éditorial connecté.</p>
        </div>
      </div>
    </section>

    {rating_widget(bias)}

    {personal_example_editor(bias)}

    {community_examples_gallery(bias)}

    <div class="article-layout">
      <aside class="example-panel" data-example-slot data-bias-id="{html.escape(bias.slug)}">
        <span class="section-index" data-example-label>Exemple</span>
        <p data-example-text>{inline_markdown(bias.example)}</p>
      </aside>
      <div class="article-content">
        <section>
          <p class="section-kicker">Comprendre</p>
          <h2>Description détaillée</h2>
          {render_paragraphs(bias.detail)}
        </section>
        <section>
          <p class="section-kicker">Enjeu</p>
          <h2>Pourquoi c'est important</h2>
          {render_paragraphs(bias.why)}
        </section>
        <section class="limits-section">
          <p class="section-kicker">Esprit critique</p>
          <h2>Limites et nuances</h2>
          {render_paragraphs(bias.limits)}
        </section>
        <section>
          <p class="section-kicker">Agir</p>
          <h2>Deux réflexes utiles</h2>
          <ol class="prevention-list">{prevention}</ol>
        </section>
        <section class="sources-section">
          <p class="section-kicker">Approfondir</p>
          <h2>Sources de départ</h2>
          <ul>{sources}</ul>
          <p class="source-note">Cette première fiche reste évolutive. Le niveau de preuve et l'importance seront affinés à mesure de la revue bibliographique.</p>
        </section>
      </div>
    </div>
  </article>

  <nav class="bias-navigation" aria-label="Navigation entre les fiches">
    {previous_link}
    {next_link}
  </nav>
</main>

<footer class="site-footer detail-footer">
  <p>« Travaillons donc à bien penser. » — Blaise Pascal</p>
  <div class="site-footer-links"><a href="../../classement/">Classement</a><a href="../../a-propos/">Méthode et sources</a></div>
</footer>"""
    return page_shell(
        title=f"{bias.name_fr} — Bien penser",
        description=bias.short,
        relative_root="../../",
        body=body,
        page_class="detail-page",
    )


def render_about(biases: list[Bias]) -> str:
    evidence_counts = Counter(bias.evidence for bias in biases)
    review_counts = Counter(bias.review_status for bias in biases)
    body = f"""<header class="site-header detail-header">
  <div class="header-inner">
    <a class="wordmark" href="../" aria-label="Bien penser, retour au catalogue">
      <span class="wordmark-mark" aria-hidden="true">P</span>
      <span><strong>Bien penser</strong><small>Les biais cognitifs</small></span>
    </a>
    <nav class="header-actions" aria-label="Navigation principale">
      <a class="back-link" href="../">← Toutes les cartes</a>
      <a class="about-link" href="../classement/">Classement</a>
      {install_button()}
      {account_button()}
    </nav>
  </div>
</header>
<main id="contenu" class="about-main">
  <header class="about-hero">
    <p class="eyebrow">Méthode et sources</p>
    <h1>Un catalogue qui distingue les noms, les preuves et l'importance.</h1>
    <p>Les biais cognitifs ne forment pas une liste scientifique parfaitement délimitée. Ce site conserve les désaccords, les chevauchements et les limites au lieu de les masquer.</p>
  </header>
  <div class="about-grid">
    <section>
      <span class="about-number">01</span>
      <h2>Deux niveaux de lecture</h2>
      <p>Chaque carte donne le nom, une explication, un exemple et l'importance provisoire. La fiche détaillée ajoute les mécanismes, les nuances, la prévention et les sources.</p>
    </section>
    <section>
      <span class="about-number">02</span>
      <h2>Importance ≠ preuve</h2>
      <p>L'importance pratique mesure la portée potentielle du biais. La solidité scientifique indique la qualité et la convergence des recherches disponibles. Les deux dimensions restent séparées.</p>
    </section>
    <section>
      <span class="about-number">03</span>
      <h2>Un contenu évolutif</h2>
      <p>Cette version publie {len(biases)} fiches : {review_counts['revue']} revues, {review_counts['en_revue']} en revue et {review_counts['non_revue']} non revues. Chaque statut et chaque date de revue proviennent du fichier Markdown de la fiche.</p>
    </section>
  </div>
  <section class="pascal-panel">
    <blockquote>« Travaillons donc à bien penser : voilà le principe de la morale. »</blockquote>
    <p>Blaise Pascal, <cite>Pensées</cite>, fragment Transition 6 — Lafuma 200, Sellier 232, Brunschvicg 347.</p>
    <a href="https://www.penseesdepascal.fr/Transition/P-R-Transition6.php">Consulter le texte et la concordance des éditions</a>
  </section>
  <section class="method-section">
    <p class="section-kicker">Corpus</p>
    <h2>Sources structurantes</h2>
    <ul>
      <li><a href="https://doi.org/10.1016/j.ipm.2024.103672">Soprano et al. (2024)</a> — inventaire de 221 candidats et sélection de 39 biais liés au fact-checking.</li>
      <li><a href="https://doi.org/10.1109/TVCG.2018.2872577">Dimara et al. (2020)</a> — taxonomie de 154 biais en sept catégories de tâches.</li>
      <li><a href="https://foundation.wikimedia.org/wiki/File:Cognitive_bias_codex_en.svg">Cognitive Bias Codex</a> — représentation visuelle historique de 188 entrées, utilisée pour la découverte et non comme preuve scientifique.</li>
    </ul>
    <p>Chaque fiche renvoie en outre vers une publication scientifique propre au phénomène. Les scores sont provisoires et seront révisés à partir de la fréquence, de la gravité, de la diversité des domaines et de l'actionnabilité.</p>
  </section>
</main>
<footer class="site-footer detail-footer"><p>Bien penser — catalogue critique des biais cognitifs</p><div class="site-footer-links"><a href="../classement/">Classement</a><a href="../">Explorer les cartes</a></div></footer>"""
    return page_shell(
        title="Méthode et sources — Bien penser",
        description="Méthode, niveaux de preuve et sources du catalogue Bien penser.",
        relative_root="../",
        body=body,
        page_class="about-page",
    )


def render_leaderboard(biases: list[Bias]) -> str:
    rows = "\n".join(
        f"""<tr data-leaderboard-row data-bias-id="{html.escape(bias.slug)}" data-name="{html.escape(bias.name_fr.casefold(), quote=True)}" data-family="{html.escape(bias.family)}">
  <td class="leaderboard-rank" data-label="Rang" data-rank>—</td>
  <th scope="row" data-label="Biais"><a href="../biais/{html.escape(bias.slug)}/">{html.escape(bias.name_fr)}</a><span>{html.escape(FAMILY_LABELS.get(bias.family, bias.family))}</span></th>
  <td class="leaderboard-score" data-label="Score moyen"><strong data-score>—</strong><span>/100</span></td>
  <td data-label="Médiane" data-median>—</td>
  <td data-label="Notes" data-count>0</td>
  <td class="leaderboard-personal" data-label="Votre note" data-personal>—</td>
</tr>"""
        for bias in biases
    )
    family_options = "\n".join(
        f'<option value="{html.escape(key)}">{html.escape(label)}</option>'
        for key, label in sorted(FAMILY_LABELS.items(), key=lambda item: item[1])
    )
    body = f"""<header class="site-header detail-header">
  <div class="header-inner">
    <a class="wordmark" href="../" aria-label="Bien penser, retour au catalogue">
      <span class="wordmark-mark" aria-hidden="true">P</span>
      <span><strong>Bien penser</strong><small>Les biais cognitifs</small></span>
    </a>
    <nav class="header-actions" aria-label="Navigation principale">
      <a class="back-link" href="../">← Toutes les cartes</a>
      <a class="about-link" href="../a-propos/">À propos</a>
      {install_button()}
      {account_button()}
    </nav>
  </div>
</header>
<main id="contenu" class="leaderboard-main" data-leaderboard>
  <header class="leaderboard-hero">
    <p class="eyebrow">Classement communautaire</p>
    <h1>Les biais auxquels<br>nous devrions prêter attention.</h1>
    <p>Ce classement rassemble les évaluations personnelles de 1 à 100. Il ne remplace ni le niveau de preuve scientifique ni l'importance éditoriale.</p>
  </header>
  <section class="leaderboard-section" aria-labelledby="leaderboard-title">
    <div class="leaderboard-heading">
      <div><p class="section-kicker">Tableau des scores</p><h2 id="leaderboard-title">Classement des biais</h2></div>
      <p><span data-ratings-total>0</span> évaluations enregistrées</p>
    </div>
    <div class="leaderboard-controls">
      <label><span>Rechercher</span><input type="search" data-leaderboard-search placeholder="Un biais…"></label>
      <label><span>Famille</span><select data-leaderboard-family><option value="all">Toutes</option>{family_options}</select></label>
      <label><span>Afficher</span><select data-leaderboard-scope><option value="all">Tous les biais</option><option value="rated">Avec évaluations</option><option value="mine">Mes évaluations</option></select></label>
    </div>
    <div class="leaderboard-table-wrap">
      <table class="leaderboard-table">
        <thead><tr><th>Rang</th><th>Biais</th><th>Score moyen</th><th>Médiane</th><th>Notes</th><th>Votre note</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
    <p class="leaderboard-note">Un score est signalé comme provisoire lorsqu'il repose sur moins de trois évaluations. À égalité, le nombre de votants départage les biais.</p>
  </section>
</main>
<footer class="site-footer detail-footer"><p>Bien penser — classement communautaire</p><a href="../">Explorer les cartes</a></footer>"""
    return page_shell(
        title="Classement communautaire — Bien penser",
        description="Classement des biais cognitifs selon les évaluations d'importance de la communauté.",
        relative_root="../",
        body=body,
        page_class="leaderboard-page",
    )


def build(output: Path) -> list[Bias]:
    biases = [bias for path in sorted(CONTENT_DIR.glob("*.md")) if (bias := read_bias(path))]
    if not biases:
        raise ValueError("No documented biases found")
    biases.sort(key=lambda bias: (-bias.importance, EVIDENCE_ORDER.get(bias.evidence, 99), bias.name_fr.casefold()))

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
            raise ValueError(
                f"Refusing to replace an unmarked directory: {output}. "
                f"Expected {BUILD_MARKER}."
            )
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / BUILD_MARKER).write_text("Generated by scripts/build_site.py\n", encoding="utf-8")
    shutil.copytree(WEB_DIR / "assets", output / "assets")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    (output / "index.html").write_text(render_home(biases), encoding="utf-8")

    about_dir = output / "a-propos"
    about_dir.mkdir()
    (about_dir / "index.html").write_text(render_about(biases), encoding="utf-8")

    leaderboard_dir = output / "classement"
    leaderboard_dir.mkdir()
    (leaderboard_dir / "index.html").write_text(render_leaderboard(biases), encoding="utf-8")

    bias_root = output / "biais"
    for index, bias in enumerate(biases):
        destination = bias_root / bias.slug
        destination.mkdir(parents=True)
        previous = biases[index - 1] if index else None
        following = biases[index + 1] if index + 1 < len(biases) else None
        (destination / "index.html").write_text(
            render_detail(bias, previous, following), encoding="utf-8"
        )

    not_found_body = f"""<main id="contenu" class="error-main">
  <p class="eyebrow">Erreur 404</p>
  <h1>Cette page s’est égarée.</h1>
  <p>Le catalogue, lui, est toujours là.</p>
  <a class="primary-link" href="{PUBLIC_SITE_URL}">Retour aux cartes</a>
</main>"""
    (output / "404.html").write_text(
        page_shell(
            title="Page introuvable — Bien penser",
            description="Cette page n'existe pas.",
            relative_root=PUBLIC_SITE_URL,
            page_class="error-page",
            body=not_found_body,
        ),
        encoding="utf-8",
    )
    return biases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "_site")
    args = parser.parse_args()
    output = args.output.resolve()
    biases = build(output)
    print(f"Built {len(biases)} bias pages in {output}")


if __name__ == "__main__":
    main()
