#!/usr/bin/env python3
"""Extract Appendix B from Soprano et al. (2024) and create Markdown stubs.

The generated files preserve the source numbering. They deliberately do not
merge suspected duplicates: relations and review flags record those cases so
that later editorial work remains reversible and traceable.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path

import pdfplumber


SOURCE_DOI = "https://doi.org/10.1016/j.ipm.2024.103672"
SOURCE_TITLE = (
    "Cognitive Biases in Fact-Checking and Their Countermeasures: A Review"
)

FACT_CHECKING_BIASES = {
    "Affect Heuristic",
    "Anchoring Effect",
    "Attentional Bias",
    "Authority Bias",
    "Automation Bias",
    "Availability Cascade",
    "Availability Heuristic",
    "Backfire Effect",
    "Bandwagon Effect",
    "Barnum Effect",
    "Base Rate Fallacy",
    "Belief Bias",
    "Choice-supportive Bias",
    "Compassion Fade",
    "Confirmation Bias",
    "Conjunction Fallacy",
    "Conservatism Bias",
    "Consistency Bias",
    "Courtesy Bias",
    "Declinism",
    "Dunning-Kruger Effect",
    "Framing Effect",
    "Fundamental Attribution Error",
    "Google Effect",
    "Hindsight Bias",
    "Hostile Attribution Bias",
    "Illusion of Validity",
    "Illusory Correlation",
    "Illusory Truth Effect",
    "Ingroup Bias",
    "Just-world Hypothesis",
    "Optimism Bias",
    "Ostrich Effect",
    "Outcome Bias",
    "Overconfidence Effect",
    "Proportionality Bias",
    "Salience Bias",
    "Stereotypical Bias",
    "Telescoping Effect",
}

# These are review leads, not final scientific conclusions.
REVIEW_METADATA = {
    15: {
        "flags": ["broad_family_candidate"],
        "relations": [
            "soprano-2024-002",
            "soprano-2024-053",
            "soprano-2024-078",
            "soprano-2024-089",
            "soprano-2024-211",
        ],
    },
    18: {
        "flags": ["possible_terminology_overlap"],
        "relations": ["soprano-2024-020"],
    },
    34: {
        "flags": ["possible_parent_relation"],
        "relations": ["soprano-2024-060"],
    },
    67: {
        "flags": ["possible_alias_or_close_construct"],
        "relations": ["soprano-2024-136"],
    },
    77: {
        "flags": ["source_aliases_probably_incorrect"],
        "relations": ["soprano-2024-169"],
    },
    86: {
        "flags": ["source_internal_alias_conflict"],
        "relations": ["soprano-2024-016"],
    },
    105: {
        "flags": ["probable_alias_duplicate"],
        "relations": ["soprano-2024-212"],
    },
    112: {
        "flags": ["possible_family_relation"],
        "relations": ["soprano-2024-190", "soprano-2024-195"],
    },
    117: {"flags": ["broad_category_not_single_bias"], "relations": []},
    153: {
        "flags": ["source_alias_is_a_theory_not_a_synonym"],
        "relations": [],
    },
    156: {
        "flags": ["probable_child_relation"],
        "relations": ["soprano-2024-183"],
    },
    162: {"flags": ["theory_not_single_bias"], "relations": []},
    166: {"flags": ["theory_not_single_bias"], "relations": []},
    168: {
        "flags": ["probable_child_relation"],
        "relations": ["soprano-2024-183"],
    },
    179: {
        "flags": ["broad_methodological_category"],
        "relations": ["soprano-2024-027"],
    },
    183: {
        "flags": ["probable_parent_relation"],
        "relations": ["soprano-2024-156", "soprano-2024-168"],
    },
    190: {
        "flags": ["exact_duplicate_in_source"],
        "relations": ["soprano-2024-195"],
    },
    195: {
        "flags": ["exact_duplicate_in_source"],
        "relations": ["soprano-2024-190"],
    },
    201: {"flags": ["generic_category_not_single_bias"], "relations": []},
    212: {
        "flags": ["probable_alias_duplicate"],
        "relations": ["soprano-2024-105"],
    },
    216: {"flags": ["psychophysical_law_not_single_bias"], "relations": []},
}


def yaml_string(value: str) -> str:
    """Return a JSON-quoted string, which is valid YAML."""

    return json.dumps(value, ensure_ascii=False)


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")


def split_label(label: str) -> tuple[str, list[str]]:
    match = re.fullmatch(r"(.+?)\s+\(or\s+(.+)\)", label)
    if not match:
        return label, []
    primary, alias_text = match.groups()
    aliases = [part.strip() for part in re.split(r",\s+or\s+", alias_text)]
    return primary.strip(), aliases


def extract_text(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as document:
        return "\n\f\n".join(
            page.extract_text(x_tolerance=1, y_tolerance=3, layout=True) or ""
            for page in document.pages
        )


def parse_appendix(text: str) -> list[tuple[int, str]]:
    start = text.find("Appendix B. List of 221 cognitive biases")
    end = text.find("\n     References", start)
    if start < 0 or end < 0:
        raise ValueError("Appendix B boundaries were not found")

    entries: list[tuple[int, str]] = []
    for line in text[start:end].splitlines():
        match = re.match(r"^\s+(\d{1,3})\.\s+(.+?)\s*$", line)
        if match:
            entries.append((int(match.group(1)), match.group(2).strip()))

    numbers = [number for number, _ in entries]
    if numbers != list(range(1, 222)):
        raise ValueError(
            "Expected source numbers 1..221, got "
            f"{len(entries)} entries from {numbers[:3]} to {numbers[-3:]}"
        )
    return entries


def render_list(values: list[str], indent: int = 0) -> list[str]:
    prefix = " " * indent
    if not values:
        return [f"{prefix}[]"]
    return [f"{prefix}- {yaml_string(value)}" for value in values]


def card_content(number: int, original_label: str) -> str:
    name_en, aliases_en = split_label(original_label)
    metadata = REVIEW_METADATA.get(number, {"flags": [], "relations": []})
    fact_checking = name_en in FACT_CHECKING_BIASES
    source_id = f"soprano-2024-{number:03d}"

    lines = [
        "---",
        "schema_version: 1",
        f"id: {yaml_string(source_id)}",
        f"source_number: {number}",
        f"source_original_label: {yaml_string(original_label)}",
        f"name_en: {yaml_string(name_en)}",
        'name_fr: ""',
        "aliases_en:",
        *render_list(aliases_en, indent=2),
        "aliases_fr: []",
        'status: "candidat"',
        'type: "a_qualifier"',
        'family: "a_classer"',
        "parent_id: null",
        "importance: null",
        'evidence_level: "a_evaluer"',
        f"fact_checking_relevant: {'true' if fact_checking else 'false'}",
        "review_flags:",
        *render_list(metadata["flags"], indent=2),
        "relations:",
        *render_list(metadata["relations"], indent=2),
        "source:",
        '  key: "soprano-2024"',
        f"  title: {yaml_string(SOURCE_TITLE)}",
        f"  doi: {yaml_string(SOURCE_DOI)}",
        '  locator: "Appendix B"',
        f"  number: {number}",
        "---",
        "",
        f"# {name_en}",
        "",
        "> Fiche de travail importée automatiquement. Le nom et les alias sont",
        "> conservés tels qu'ils apparaissent dans la source ; le contenu reste à valider.",
        "",
        "## Carte",
        "",
        "- **Nom français :** à traduire",
        "- **Explication brève :** à rédiger",
        "- **Exemple :** à rédiger",
        "- **Importance :** à évaluer",
        "",
        "## Description détaillée",
        "",
        "À rédiger à partir de sources scientifiques propres à ce biais.",
        "",
        "## Validation et limites",
        "",
        "- Définition opérationnelle : à vérifier",
        "- Études primaires : à ajouter",
        "- Réplications ou revues : à ajouter",
        "- Controverses : à rechercher",
        "",
        "## Prévention",
        "",
        "À documenter.",
        "",
    ]
    return "\n".join(lines)


def index_content(entries: list[tuple[int, str]]) -> str:
    lines = [
        "# Index des 221 candidats de Soprano et al. (2024)",
        "",
        "Cet index reproduit l'ordre de l'annexe B. Il conserve les doublons et",
        "les alias de la source afin que chaque correction reste traçable.",
        "",
        f"Source : [{SOURCE_TITLE}]({SOURCE_DOI}), annexe B.",
        "",
        "| Nº | Nom original | Alias indiqués par la source | Fact-checking | Revue initiale |",
        "|---:|---|---|:---:|---|",
    ]
    for number, original_label in entries:
        name_en, aliases_en = split_label(original_label)
        filename = f"{number:03d}-{slugify(name_en)}.md"
        metadata = REVIEW_METADATA.get(number, {"flags": [], "relations": []})
        aliases = ", ".join(aliases_en) if aliases_en else "-"
        flags = ", ".join(f"`{flag}`" for flag in metadata["flags"]) or "-"
        fact_checking = "oui" if name_en in FACT_CHECKING_BIASES else "-"
        lines.append(
            f"| {number} | [{name_en}](biais/{filename}) | {aliases} | "
            f"{fact_checking} | {flags} |"
        )
    lines.extend(
        [
            "",
            "## Contrôles automatiques",
            "",
            f"- Entrées extraites : **{len(entries)}**",
            f"- Entrées marquées pertinentes au fact-checking : **{sum(split_label(label)[0] in FACT_CHECKING_BIASES for _, label in entries)}**",
            "- Numérotation vérifiée : **1 à 221 sans lacune**",
            "- Les drapeaux de revue sont des pistes éditoriales, pas des conclusions scientifiques.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path, help="Soprano et al. PDF file")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("catalogue/biais"),
        help="Directory for generated Markdown cards",
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=Path("catalogue/index-soprano-2024.md"),
        help="Generated Markdown index",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing cards (unsafe after manual editing)",
    )
    args = parser.parse_args()

    entries = parse_appendix(extract_text(args.pdf))
    args.output.mkdir(parents=True, exist_ok=True)

    created = 0
    skipped = 0
    for number, original_label in entries:
        name_en, _ = split_label(original_label)
        destination = args.output / f"{number:03d}-{slugify(name_en)}.md"
        if destination.exists() and not args.force:
            skipped += 1
            continue
        destination.write_text(card_content(number, original_label), encoding="utf-8")
        created += 1

    args.index.parent.mkdir(parents=True, exist_ok=True)
    args.index.write_text(index_content(entries), encoding="utf-8")
    print(
        f"Validated {len(entries)} entries; created {created} cards; "
        f"skipped {skipped}; wrote {args.index}"
    )


if __name__ == "__main__":
    main()
