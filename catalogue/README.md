# Guide d'édition du catalogue

Chaque biais candidat possède son propre fichier Markdown. Ce choix permet :

- une modification simple depuis GitHub, un éditeur de texte ou une IA ;
- un historique Git précis pour chaque fiche ;
- la génération automatique d'une carte courte et d'une page détaillée ;
- la conservation des sources et des controverses avec le contenu.

## Anatomie d'une fiche

La partie située entre les deux marqueurs `---` est un en-tête YAML lisible par le futur générateur HTML.

| Champ | Rôle | Valeurs attendues |
|---|---|---|
| `schema_version` | Version de la structure | `1` |
| `id` | Identifiant stable importé | Ne pas modifier |
| `source_number` | Numéro dans l'annexe B | 1 à 221 |
| `source_original_label` | Libellé exact de la source | Ne pas traduire ni corriger |
| `name_en`, `name_fr` | Noms d'affichage | Texte |
| `aliases_en`, `aliases_fr` | Synonymes vérifiés ou à vérifier | Listes YAML |
| `status` | Avancement scientifique | `candidat`, `documente`, `confirme`, `debattu`, `a_fusionner`, `hors_perimetre` |
| `type` | Nature du concept | `biais`, `heuristique`, `effet`, `famille`, `theorie`, `loi`, `a_qualifier` |
| `family` | Famille éditoriale | Identifiant à définir |
| `parent_id` | Concept parent éventuel | Identifiant d'une autre fiche ou `null` |
| `importance` | Importance pratique | Entier de 1 à 5 ou `null` |
| `importance_status` | Maturité du score | `provisoire` tant que les quatre axes ne sont pas documentés |
| `evidence_level` | Solidité des preuves | `a_evaluer`, `limitee`, `moderee`, `forte`, `contestee` |
| `documented_on` | Date de la première rédaction documentée | Date ISO `AAAA-MM-JJ` ou champ absent |
| `review_status` | État de la revue individuelle | `non_revue`, `en_revue`, `revue` |
| `reviewed_on` | Date de la dernière revue individuelle achevée | Date ISO `AAAA-MM-JJ` ou `null` |
| `fact_checking_relevant` | Sélection de l'article source | `true` ou `false` |
| `review_flags` | Points à contrôler | Liste de codes explicites |
| `relations` | Entrées proches | Liste d'identifiants |

## Règles de modification

1. Ne jamais changer `id`, `source_number` ou `source_original_label` : ils assurent la traçabilité.
2. Corriger les erreurs de la source dans les champs éditoriaux, sans effacer le libellé original.
3. Ne pas fusionner deux fiches tant que la relation n'est pas soutenue par une source scientifique.
4. Ne pas confondre importance pratique et solidité des preuves.
5. Paraphraser les définitions ; ne pas recopier de longs passages protégés.

## Parcours de revue individuelle

Ce parcours est proposé uniquement au responsable éditorial après connexion avec son compte autorisé.

1. Ouvrir la fiche sur le site, puis cliquer sur **Passer en revue**.
2. GitHub présente une demande préremplie. Après confirmation, l'automatisation passe la fiche à `en_revue` et republie le site.
3. La carte affiche alors **En revue** et son bouton devient **Revoir la fiche**. La page détaillée propose aussi **Faire évoluer la fiche**, qui ouvre le Markdown dans l'éditeur GitHub.
4. À la fin du travail, cliquer sur **Marquer comme revue**. L'automatisation passe la fiche à `revue`, inscrit la date du jour dans `reviewed_on` et republie le site.
5. Une fiche déjà revue peut repartir en revue ; la date précédente reste visible jusqu'à l'achèvement de la nouvelle passe.

La confirmation GitHub est volontaire : elle authentifie l'auteur sans placer de jeton secret dans le site public. L'automatisation refuse toute demande qui ne provient pas du compte propriétaire `J2M116`.

En local, la même transition peut être effectuée sans modifier l'en-tête à la main :

```sh
python3 scripts/set_review_status.py catalogue/biais/037-confirmation-bias.md en_revue
python3 scripts/set_review_status.py catalogue/biais/037-confirmation-bias.md revue
```

## Import reproductible

Le script [`../scripts/import_soprano_2024.py`](../scripts/import_soprano_2024.py) reconstruit les fiches depuis le PDF. Par sécurité, il n'écrase pas les fiches existantes sauf avec l'option `--force`. Cette option ne devra plus être utilisée après le début des modifications manuelles.

Le script [`../scripts/enrich_factchecking_39.py`](../scripts/enrich_factchecking_39.py) documente la première passe française appliquée aux 39 biais prioritaires. Après cette étape, les fiches deviennent la source éditoriale principale : le script ne doit pas servir à écraser des corrections manuelles ultérieures.
