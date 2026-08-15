# Bien penser - Catalogue des biais cognitifs

Ce projet place un catalogue critique des biais cognitifs sous cette invitation de Blaise Pascal :

> « Travaillons donc à bien penser : voilà le principe de la morale. »

Le contenu est écrit en Markdown pour rester facile à modifier par une personne ou une IA. Un générateur produira ensuite un site HTML statique publiable gratuitement avec GitHub Pages.

## État actuel

- corpus bibliographique qualifié dans [`sources-biais-cognitifs.md`](sources-biais-cognitifs.md) ;
- 221 candidats extraits de Soprano et al. (2024) dans [`catalogue/biais/`](catalogue/biais/) ;
- index de contrôle dans [`catalogue/index-soprano-2024.md`](catalogue/index-soprano-2024.md) ;
- première version française des 39 biais prioritaires dans [`catalogue/lot-prioritaire-39.md`](catalogue/lot-prioritaire-39.md) ;
- traduction anglaise publiée des 39 fiches prioritaires dans [`catalogue/i18n/en/biais/`](catalogue/i18n/en/biais/) ;
- premières anomalies et relations dans [`catalogue/revue-initiale.md`](catalogue/revue-initiale.md).

## Principe éditorial

La liste brute n'est pas traitée comme une vérité définitive. Chaque entrée commence au statut `candidat`, puis doit être traduite, définie, reliée à ses sources propres et évaluée. Les doublons sont signalés avant toute fusion afin de préserver la traçabilité.

## Structure

```text
catalogue/
  biais/                    # fiches canoniques françaises et métadonnées communes
  i18n/
    fr/ui.json              # textes de l'interface française
    en/ui.json              # textes de l'interface anglaise
    en/biais/               # contenu anglais, une traduction Markdown par fiche
  index-soprano-2024.md     # index des 221 entrées
  revue-initiale.md         # doublons et anomalies à examiner
scripts/
  import_soprano_2024.py    # import reproductible depuis l'article PDF
sources-biais-cognitifs.md  # corpus bibliographique général
```

Le dossier `tmp/` contient les documents de travail locaux et n'est pas destiné à être publié.

Les fiches françaises de [`catalogue/biais/`](catalogue/biais/) restent la source canonique : elles portent l'identifiant, la famille, l'importance et le niveau de preuve partagés par les deux langues. Une traduction anglaise reprend le même nom de fichier dans [`catalogue/i18n/en/biais/`](catalogue/i18n/en/biais/) et contient ses textes localisés ainsi que son propre état de revue. Cette séparation permet de traduire, corriger et revoir progressivement chaque version sans dupliquer les métadonnées communes.

Les adresses françaises existantes restent inchangées. Les pages anglaises vivent sous `/en/`, puis `/en/about/`, `/en/ranking/` et `/en/biases/<slug>/`. Pour ajouter plus tard une langue comme l'allemand ou l'espagnol, il faudra créer son dictionnaire d'interface, son dossier de traductions et déclarer ses routes dans le générateur ; aucune donnée Supabase ne sera dupliquée, car toutes les langues conservent le même identifiant technique pour un biais.

## Site HTML

Le script [`scripts/build_site.py`](scripts/build_site.py) transforme les fiches documentées en site statique :

- une page d'accueil avec cartes, recherche, filtres et tri ;
- une page détaillée par biais ;
- un suivi individuel `non revue` / `en revue` / `revue`, avec date de dernière revue ;
- un accès éditorial privé, accordé en base, pour faire évoluer chaque fichier Markdown ;
- des boutons d'état dans l'interface, confirmés par GitHub puis appliqués et publiés automatiquement ;
- des comptes par e-mail et mot de passe avec pseudonyme public ;
- une évaluation personnelle de l'importance de chaque biais, de 1 à 100 ;
- des filtres personnels pour retrouver les fiches déjà notées ou restant à noter ;
- un exemple personnel par biais, qui remplace l'exemple éditorial pour son auteur après connexion ;
- une galerie publique des exemples partagés, avec un cœur au maximum par compte et par exemple ;
- un classement communautaire présentant moyenne, médiane et nombre d'évaluations ;
- une page présentant la méthode et les sources ;
- un site intégralement disponible en français à la racine et en anglais sous `/en/`, avec liens de langue correspondants sur chaque page ;
- une préférence de langue enregistrée seulement après le choix de la personne, sans redirection automatique ;
- une mise en page adaptée aux ordinateurs et téléphones ;
- une installation sur l'écran d'accueil de l'iPhone grâce au manifeste web et à une aide intégrée ;
- une navigation et des contrôles tactiles adaptés aux petits écrans, sans modifier la présentation de bureau.

Il utilise uniquement la bibliothèque standard de Python : aucun service d'IA, token ou dépendance payante n'intervient dans la génération.

Sur iPhone, ouvrir le site dans Safari, toucher **Partager**, puis **Sur l'écran d'accueil**. Si l'option est proposée, activer **Ouvrir comme app web**, puis toucher **Ajouter**. Le bouton **Installer** présent dans le site rappelle ces étapes lorsqu'elles sont utiles.

Les comptes, évaluations, exemples personnels et cœurs sont conservés dans Supabase. La page publique ne contient qu'une clé publiable à droits limités ; les politiques de sécurité de la base garantissent qu'une personne ne peut modifier que ses propres notes, exemples et cœurs. La galerie publique est alimentée par une projection séparée qui contient uniquement le texte, les dates et le total des cœurs : elle n'expose ni e-mail, ni identifiant d'auteur, ni vote individuel. Le droit éditorial est conservé séparément : un compte peut uniquement vérifier son propre droit, sans pouvoir se l'accorder. GitHub vérifie indépendamment l'identifiant immuable du propriétaire avant toute modification automatisée du catalogue.

Dans **Supabase → Authentication → URL Configuration**, l'adresse du site et l'adresse de redirection autorisée doivent toutes deux être exactement `https://j2m116.github.io/bien-penser-biais-cognitifs/`. L'inscription transmet également cette adresse explicitement à Supabase afin que le lien de confirmation conserve le sous-chemin GitHub Pages.

Le workflow [`.github/workflows/pages.yml`](.github/workflows/pages.yml) reconstruit et publie automatiquement le site avec GitHub Pages après chaque modification envoyée sur la branche `main`.

Avant chaque publication, les tests valident notamment les 39 paires de fiches, les chemins et liens français/anglais, les balises `lang` et `hreflang`, les manifestes web ainsi que la syntaxe des scripts JavaScript multilingues.

Le schéma versionné se trouve dans [`supabase/migrations/20260813061613_community_ratings.sql`](supabase/migrations/20260813061613_community_ratings.sql), complété par les migrations suivantes du même dossier.
