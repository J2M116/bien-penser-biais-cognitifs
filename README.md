# Bien penser - Catalogue des biais cognitifs

Ce projet place un catalogue critique des biais cognitifs sous cette invitation de Blaise Pascal :

> « Travaillons donc à bien penser : voilà le principe de la morale. »

Le contenu est écrit en Markdown pour rester facile à modifier par une personne ou une IA. Un générateur produira ensuite un site HTML statique publiable gratuitement avec GitHub Pages.

## État actuel

- corpus bibliographique qualifié dans [`sources-biais-cognitifs.md`](sources-biais-cognitifs.md) ;
- 221 candidats extraits de Soprano et al. (2024) dans [`catalogue/biais/`](catalogue/biais/) ;
- index de contrôle dans [`catalogue/index-soprano-2024.md`](catalogue/index-soprano-2024.md) ;
- première version française des 39 biais prioritaires dans [`catalogue/lot-prioritaire-39.md`](catalogue/lot-prioritaire-39.md) ;
- premières anomalies et relations dans [`catalogue/revue-initiale.md`](catalogue/revue-initiale.md).

## Principe éditorial

La liste brute n'est pas traitée comme une vérité définitive. Chaque entrée commence au statut `candidat`, puis doit être traduite, définie, reliée à ses sources propres et évaluée. Les doublons sont signalés avant toute fusion afin de préserver la traçabilité.

## Structure

```text
catalogue/
  biais/                    # une fiche Markdown modifiable par candidat
  index-soprano-2024.md     # index des 221 entrées
  revue-initiale.md         # doublons et anomalies à examiner
scripts/
  import_soprano_2024.py    # import reproductible depuis l'article PDF
sources-biais-cognitifs.md  # corpus bibliographique général
```

Le dossier `tmp/` contient les documents de travail locaux et n'est pas destiné à être publié.

## Site HTML

Le script [`scripts/build_site.py`](scripts/build_site.py) transforme les fiches documentées en site statique :

- une page d'accueil avec cartes, recherche, filtres et tri ;
- une page détaillée par biais ;
- une page présentant la méthode et les sources ;
- une mise en page adaptée aux ordinateurs et téléphones.

Il utilise uniquement la bibliothèque standard de Python : aucun service d'IA, token ou dépendance payante n'intervient dans la génération.

Le workflow [`.github/workflows/pages.yml`](.github/workflows/pages.yml) reconstruit et publie automatiquement le site avec GitHub Pages après chaque modification envoyée sur la branche `main`.
