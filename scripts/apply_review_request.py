#!/usr/bin/env python3
"""Apply a validated review-state request created from the public catalogue."""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from set_review_status import CONTENT_DIR, scalar, update_review


REQUEST_PATTERN = re.compile(r"^REVUE \| (demarrer|terminer) \| ([0-9]{3}-[a-z0-9-]+)$")


def apply_request(
    title: str,
    *,
    content_dir: Path = CONTENT_DIR,
    review_date: date | None = None,
) -> tuple[Path, str, bool]:
    match = REQUEST_PATTERN.fullmatch(title)
    if not match:
        raise ValueError("Titre de demande de revue invalide")
    action, slug = match.groups()
    path = (content_dir / f"{slug}.md").resolve()
    if path.parent != content_dir.resolve() or not path.is_file():
        raise ValueError(f"Fiche inconnue : {slug}")

    text = path.read_text(encoding="utf-8")
    pieces = text.split("---", 2)
    if len(pieces) != 3:
        raise ValueError(f"En-tête YAML invalide : {path}")
    front = pieces[1]
    if scalar(front, "status") != "documente":
        raise ValueError("Seules les fiches documentées peuvent entrer en revue")
    current_status = scalar(front, "review_status") or "non_revue"

    if action == "demarrer":
        if current_status == "en_revue":
            return path, current_status, False
        update_review(path, "en_revue")
        return path, "en_revue", True

    if current_status == "revue":
        return path, current_status, False
    if current_status != "en_revue":
        raise ValueError("La fiche doit être en revue avant d'être marquée comme revue")
    final_date = (review_date or date.today()).isoformat()
    update_review(path, "revue", final_date)
    return path, "revue", True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("title", help="Titre exact de la demande GitHub")
    args = parser.parse_args()
    path, status, changed = apply_request(args.title)
    result = "modifiée" if changed else "déjà à jour"
    print(f"{path.name}: {status} ({result})")


if __name__ == "__main__":
    main()
