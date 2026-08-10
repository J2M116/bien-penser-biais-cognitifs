#!/usr/bin/env python3
"""Change the editorial review status of one cognitive-bias Markdown card."""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "catalogue" / "biais"
REVIEW_STATUSES = ("non_revue", "en_revue", "revue")


def scalar(front: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}:\s*(.*?)\s*$", front, flags=re.MULTILINE)
    if not match or match.group(1) == "null":
        return None
    return match.group(1).strip().strip('"')


def upsert(front: str, key: str, rendered_value: str, *, after: str) -> str:
    rendered = f"{key}: {rendered_value}"
    if re.search(rf"^{re.escape(key)}:", front, flags=re.MULTILINE):
        return re.sub(rf"^{re.escape(key)}:.*$", rendered, front, count=1, flags=re.MULTILINE)
    updated, count = re.subn(
        rf"^({re.escape(after)}:.*)$",
        lambda match: f"{match.group(1)}\n{rendered}",
        front,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise ValueError(f"Champ d'ancrage absent : {after}")
    return updated


def update_review(path: Path, status: str, reviewed_on: str | None = None) -> str | None:
    text = path.read_text(encoding="utf-8")
    pieces = text.split("---", 2)
    if len(pieces) != 3:
        raise ValueError(f"En-tête YAML invalide : {path}")
    front, body = pieces[1], pieces[2]
    previous_date = scalar(front, "reviewed_on")

    if status == "revue":
        final_date = reviewed_on or date.today().isoformat()
        date.fromisoformat(final_date)
    elif status == "non_revue":
        final_date = None
    else:
        final_date = previous_date

    front = upsert(front, "review_status", f'"{status}"', after="evidence_level")
    rendered_date = f'"{final_date}"' if final_date else "null"
    front = upsert(front, "reviewed_on", rendered_date, after="review_status")
    path.write_text(f"---{front}---{body}", encoding="utf-8")
    return final_date


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="Fichier Markdown de la fiche")
    parser.add_argument("status", choices=REVIEW_STATUSES, help="Nouvel état de revue")
    parser.add_argument("--date", help="Date ISO de la revue achevée (AAAA-MM-JJ)")
    args = parser.parse_args()

    path = args.file if args.file.is_absolute() else PROJECT_ROOT / args.file
    path = path.resolve()
    if path.parent != CONTENT_DIR.resolve() or path.suffix != ".md" or not path.is_file():
        parser.error("le fichier doit être une fiche Markdown existante de catalogue/biais/")
    if args.date and args.status != "revue":
        parser.error("--date s'utilise uniquement avec le statut revue")

    final_date = update_review(path, args.status, args.date)
    suffix = f" (dernière revue : {final_date})" if final_date else ""
    print(f"{path.name}: {args.status}{suffix}")


if __name__ == "__main__":
    main()
