#!/usr/bin/env python3
"""Apply the first French editorial pass to the 39 fact-checking biases.

This is a one-time, curated enrichment. It only updates cards still marked as
fact-checking-relevant and keeps every original source field untouched.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


SOURCE_URL = "https://doi.org/10.1016/j.ipm.2024.103672"
DOCUMENTATION_DATE = "2026-08-10"


@dataclass(frozen=True)
class Entry:
    name_fr: str
    aliases_fr: tuple[str, ...]
    kind: str
    family: str
    importance: int
    evidence: str
    short: str
    example: str
    detail: str
    importance_reason: str
    limits: str
    prevention: tuple[str, str]
    reference_label: str
    reference_url: str


E = Entry

ENTRIES: dict[int, Entry] = {
    5: E(
        "Heuristique de l'affect", ("heuristique affective",), "heuristique", "affect_emotion", 4, "forte",
        "Nos émotions immédiates orientent l'évaluation d'un risque ou d'un bénéfice avant l'examen complet des faits.",
        "Une affirmation portée par une personne sympathique paraît plus crédible, même si les preuves présentées sont faibles.",
        "L'affect sert de raccourci : une impression positive tend à réduire le risque perçu et à augmenter le bénéfice perçu, et inversement. Ce mécanisme peut être utile pour décider vite, mais il devient trompeur lorsque l'émotion n'est pas pertinente pour la question.",
        "Elle agit dans la santé, la finance, la politique, la communication et l'évaluation des risques.",
        "Une émotion n'est pas en soi une erreur ; le biais apparaît lorsqu'elle remplace des informations pertinentes.",
        ("Nommer l'émotion ressentie avant de conclure.", "Évaluer séparément les preuves, les probabilités et les conséquences."),
        "Slovic et al. (2007), The Affect Heuristic", "https://doi.org/10.1016/j.ejor.2005.04.006"),
    7: E(
        "Effet d'ancrage", ("biais d'ancrage",), "effet", "probabilite_estimation", 5, "forte",
        "Une valeur ou information initiale influence excessivement une estimation ultérieure.",
        "Après avoir entendu qu'un projet coûtera un million d'euros, les estimations suivantes restent proches de ce montant, même si l'estimation initiale était arbitraire.",
        "L'ancre fournit un point de départ dont l'ajustement reste souvent insuffisant. L'effet apparaît même lorsque la valeur initiale est peu informative et peut persister chez des personnes expérimentées.",
        "Il affecte négociations, prix, prévisions, diagnostics, délais et interprétation de nombres erronés.",
        "La taille de l'effet dépend de la tâche, de la connaissance disponible et de la pertinence apparente de l'ancre.",
        ("Produire une estimation indépendante avant de voir celle d'autrui.", "Chercher activement des raisons pour lesquelles l'ancre pourrait être trop haute ou trop basse."),
        "Furnham & Boo (2011), revue de l'effet d'ancrage", "https://doi.org/10.1016/j.socec.2010.10.008"),
    13: E(
        "Biais attentionnel", (), "biais", "attention_perception", 4, "forte",
        "L'attention est attirée de façon disproportionnée par certains signaux, au détriment d'informations également pertinentes.",
        "Après une succession de nouvelles anxiogènes, une personne repère surtout les indices de danger dans un dossier pourtant équilibré.",
        "Les préoccupations, objectifs, émotions et expériences antérieures orientent ce qui est remarqué et ce qui est ignoré. Le contenu non sélectionné par l'attention peut ne jamais participer au jugement final.",
        "Ce mécanisme intervient très tôt dans le raisonnement et peut donc contaminer toutes les étapes suivantes.",
        "Il existe plusieurs biais attentionnels ; les résultats observés pour les menaces et l'anxiété ne se généralisent pas automatiquement à tout sujet.",
        ("Utiliser une grille obligeant à examiner des catégories d'informations prédéfinies.", "Faire une seconde lecture consacrée aux éléments initialement peu saillants."),
        "Bar-Haim et al. (2007), méta-analyse", "https://doi.org/10.1037/0033-2909.133.1.1"),
    16: E(
        "Biais d'autorité", (), "biais", "influence_sociale", 5, "moderee",
        "Nous accordons trop de poids à une affirmation parce qu'elle vient d'une figure d'autorité ou de prestige.",
        "Un chiffre non sourcé paraît fiable parce qu'il est cité par un professeur célèbre hors de son domaine d'expertise.",
        "Le statut peut être utilisé comme indice de compétence lorsque nous manquons de temps ou de connaissances. Le biais survient lorsque ce statut remplace l'examen de l'expertise pertinente, de la méthode et des preuves.",
        "L'autorité influence fortement santé, travail, politique, médias et usages de systèmes experts ou d'IA.",
        "Le libellé recouvre plusieurs mécanismes d'obéissance, de prestige et de crédibilité ; il ne doit pas être traité comme un synonyme exact de l'effet de halo.",
        ("Vérifier l'expertise précise et les conflits d'intérêts de la source.", "Évaluer l'argument sans le nom de son auteur, lorsque c'est possible."),
        "Milgram (1963), Behavioral Study of Obedience", "https://doi.org/10.1037/h0040525"),
    17: E(
        "Biais d'automatisation", ("biais d'automation",), "biais", "decision_action", 5, "forte",
        "Nous suivons trop facilement la recommandation d'un système automatisé, même lorsqu'elle contredit des indices fiables.",
        "Un analyste valide une alerte générée par une IA malgré une incohérence visible dans les données sources.",
        "L'automatisation peut provoquer des erreurs de commission, lorsque l'humain suit une mauvaise recommandation, et d'omission, lorsqu'il ne détecte pas ce que le système n'a pas signalé. La confiance, la charge de travail et la présentation de la recommandation modulent l'effet.",
        "Avec la généralisation des outils algorithmiques et de l'IA, son champ pratique est très large et parfois critique.",
        "Une recommandation automatisée exacte améliore souvent la décision ; le problème est la confiance mal calibrée, pas l'automatisation elle-même.",
        ("Exiger l'affichage des données et incertitudes qui soutiennent la recommandation.", "Prévoir des cas où l'utilisateur doit former un jugement avant de voir la sortie du système."),
        "Goddard et al. (2012), revue systématique", "https://doi.org/10.1136/amiajnl-2011-000089"),
    19: E(
        "Cascade de disponibilité", (), "effet", "influence_sociale", 4, "moderee",
        "Une idée paraît de plus en plus plausible parce qu'elle est répétée publiquement et devient facile à évoquer.",
        "Une rumeur souvent reprise dans les médias finit par sembler établie alors que toutes les reprises remontent à la même source.",
        "La répétition sociale augmente la disponibilité mentale d'une croyance ; les réactions qu'elle suscite produisent ensuite de nouvelles répétitions. Cette boucle peut donner l'apparence d'un consensus ou d'une preuve indépendante.",
        "Elle aide à comprendre l'amplification des risques, rumeurs et paniques morales dans les environnements médiatiques.",
        "Le concept décrit un processus collectif autant qu'un biais individuel ; son importance dépend fortement de l'écosystème d'information.",
        ("Remonter à la première source plutôt que compter les reprises.", "Distinguer nombre de publications, nombre de sources indépendantes et qualité des preuves."),
        "Kuran & Sunstein (1998), Availability Cascades and Risk Regulation", "https://ssrn.com/abstract=138144"),
    20: E(
        "Heuristique de disponibilité", (), "heuristique", "probabilite_estimation", 5, "forte",
        "Nous estimons plus probable ou fréquent ce qui nous vient facilement à l'esprit.",
        "Après avoir vu plusieurs reportages sur des accidents aériens, une personne surestime leur fréquence par rapport aux accidents routiers.",
        "La facilité de rappel dépend de la récence, de l'émotion, de la couverture médiatique et de l'expérience personnelle. Elle constitue parfois un indice utile, mais ne remplace pas un taux de base représentatif.",
        "Elle intervient dans presque toute estimation intuitive de fréquence ou de risque.",
        "Ce n'est pas exactement la même chose qu'une cascade de disponibilité, qui ajoute une dynamique sociale d'amplification.",
        ("Chercher des données de fréquence provenant d'un échantillon représentatif.", "Demander quels exemples seraient disponibles si l'on avait été exposé à d'autres informations."),
        "Tversky & Kahneman (1973), Availability: A Heuristic for Judging Frequency and Probability", "https://doi.org/10.1016/0010-0285%2873%2990033-9"),
    21: E(
        "Effet boomerang", ("effet retour de flamme",), "effet", "croyances_preuves", 3, "contestee",
        "Une correction pourrait, dans certaines conditions, renforcer la croyance erronée qu'elle cherche à réduire.",
        "Une personne très engagée politiquement rejette une réfutation menaçante et affirme ensuite sa position avec davantage de force.",
        "L'hypothèse propose qu'une correction incompatible avec l'identité ou les convictions déclenche une réaction défensive. Toutefois, les études récentes trouvent généralement que les corrections améliorent l'exactitude et que les véritables retours de flamme sont rares et dépendants du contexte.",
        "Le sujet est important pour la communication corrective, mais son importance pratique est souvent exagérée.",
        "Ne jamais affirmer que corriger une erreur la renforce normalement : c'est précisément le point controversé.",
        ("Corriger clairement avec une explication alternative et une source crédible.", "Mesurer l'effet réel de la correction au lieu de supposer une réaction défensive."),
        "Wood & Porter (2019), The Elusive Backfire Effect", "https://doi.org/10.1007/s11109-018-9443-y"),
    22: E(
        "Effet de suivisme", ("effet de mode", "effet bandwagon"), "effet", "influence_sociale", 4, "moderee",
        "La popularité apparente d'une idée ou d'un choix augmente notre tendance à l'adopter.",
        "Un avis reçoit davantage d'approbation après l'affichage d'un grand nombre de votes positifs.",
        "Le comportement d'autrui peut être interprété comme une information sur la qualité ou comme une norme sociale à suivre. Les classements, compteurs et sondages rendent ce signal particulièrement visible.",
        "Il influence consommation, élections, marchés, réseaux sociaux et diffusion des croyances.",
        "Suivre le groupe peut être rationnel lorsque les autres disposent réellement d'informations indépendantes ; le biais apparaît quand la popularité est confondue avec la vérité.",
        ("Former et consigner son jugement avant de voir les votes ou classements.", "Vérifier si les choix observés sont indépendants ou copiés les uns sur les autres."),
        "Kiss & Simonovits (2014), Identifying the Bandwagon Effect", "https://doi.org/10.1007/s11127-013-0146-y"),
    23: E(
        "Effet Barnum", ("effet Forer",), "effet", "croyances_preuves", 3, "moderee",
        "Nous jugeons personnellement exactes des descriptions vagues et très générales.",
        "Un horoscope affirmant que vous appréciez les autres mais avez parfois besoin de solitude semble décrire précisément votre personnalité.",
        "Les formulations positives, souples et applicables à beaucoup de personnes favorisent l'appropriation personnelle. Le lecteur complète mentalement les ambiguïtés avec ses propres souvenirs.",
        "Il est particulièrement pertinent pour tests de personnalité non validés, astrologie, mentalisme et messages personnalisés automatiquement.",
        "La sensibilité varie avec la formulation, la crédibilité attribuée à la source et la croyance préalable dans la procédure.",
        ("Demander quelle proportion de personnes accepterait la même description.", "Tester la description en aveugle face à plusieurs profils possibles."),
        "Forer (1949), The Fallacy of Personal Validation", "https://doi.org/10.1037/h0059240"),
    24: E(
        "Négligence du taux de base", ("sophisme du taux de base",), "biais", "probabilite_estimation", 5, "forte",
        "Nous sous-utilisons la fréquence générale d'un événement au profit d'un cas particulier frappant.",
        "Un test médical très précis paraît presque certain, sans tenir compte du fait que la maladie est extrêmement rare.",
        "Un jugement probabiliste correct combine le taux de base avec la valeur diagnostique de l'information particulière. Les descriptions ressemblantes ou émotionnelles peuvent faire oublier cette fréquence préalable.",
        "Les conséquences sont majeures en médecine, justice, sécurité, recrutement et interprétation des tests.",
        "Les performances changent fortement selon la présentation en probabilités ou en fréquences naturelles.",
        ("Écrire explicitement le taux de base avant d'examiner le cas individuel.", "Transformer les pourcentages en fréquences naturelles, par exemple sur 1 000 cas."),
        "Welsh & Navarro (2012), Seeing Is Believing", "https://doi.org/10.1016/j.obhdp.2012.04.001"),
    25: E(
        "Biais de croyance", (), "biais", "croyances_preuves", 5, "forte",
        "La plausibilité d'une conclusion influence notre jugement sur la validité logique du raisonnement.",
        "Un syllogisme invalide est accepté parce que sa conclusion correspond à une conviction vraie ou familière.",
        "Nous pouvons confondre deux questions : la conclusion est-elle crédible, et découle-t-elle réellement des prémisses ? Le biais devient visible lorsque logique et croyance conduisent à des réponses opposées.",
        "Il touche directement l'argumentation, la vérification des faits et les débats où la conclusion nous convient déjà.",
        "Il est principalement étudié avec des tâches de raisonnement formel ; son ampleur dans une conversation ordinaire varie avec la tâche.",
        ("Évaluer d'abord la structure de l'argument en remplaçant son contenu par des termes neutres.", "Séparer explicitement vérité des prémisses, validité du raisonnement et vérité de la conclusion."),
        "Evans, Barston & Pollard (1983), On the Conflict Between Logic and Belief", "https://doi.org/10.3758/BF03196976"),
    33: E(
        "Biais de soutien au choix", ("rationalisation postérieure au choix",), "biais", "memoire_temps", 3, "moderee",
        "Après une décision, nous reconstruisons plus favorablement l'option choisie et moins favorablement les alternatives.",
        "Après l'achat d'un téléphone, son propriétaire se rappelle surtout ses qualités et exagère les défauts du modèle écarté.",
        "La mémoire des caractéristiques peut être déformée de manière à soutenir l'identité du décideur et réduire le regret. Des qualités peuvent même être attribuées à tort à l'option retenue.",
        "Ce biais complique les retours d'expérience, comparaisons de produits et révisions de décisions antérieures.",
        "Il ne signifie pas que toute satisfaction après un choix est irrationnelle ; il faut démontrer une distorsion par rapport aux informations disponibles au départ.",
        ("Conserver les critères et informations utilisés avant la décision.", "Lors du bilan, évaluer symétriquement les avantages et défauts de toutes les options."),
        "Mather, Shafir & Johnson (2000), Misremembrance of Options Past", "https://doi.org/10.1111/1467-9280.00228"),
    36: E(
        "Effacement de la compassion", ("érosion de la compassion",), "effet", "affect_emotion", 4, "moderee",
        "Notre réaction émotionnelle n'augmente pas proportionnellement au nombre de personnes en détresse et peut même diminuer.",
        "L'histoire d'une victime identifiée suscite davantage de dons qu'une présentation abstraite de milliers de victimes.",
        "L'émotion est plus facilement mobilisée par une personne identifiable que par une statistique ou un groupe. L'augmentation de l'échelle peut provoquer engourdissement, sentiment d'impuissance ou moindre représentation affective.",
        "Elle influence dons, politiques humanitaires, santé publique et traitement médiatique des catastrophes.",
        "Les résultats dépendent de la manière dont les personnes et le groupe sont présentés ; l'effet n'est pas une incapacité morale fixe.",
        ("Associer les statistiques à des histoires représentatives sans les substituer aux données.", "Présenter l'action concrète possible et l'impact marginal d'une aide."),
        "Västfjäll et al. (2014), Compassion Fade", "https://doi.org/10.1371/journal.pone.0100115"),
    37: E(
        "Biais de confirmation", (), "biais", "croyances_preuves", 5, "forte",
        "Nous recherchons, interprétons ou mémorisons préférentiellement ce qui confirme nos croyances existantes.",
        "Pour évaluer un complément alimentaire, une personne ne consulte que des témoignages favorables et explique les résultats négatifs comme des exceptions.",
        "Le biais peut intervenir dans la recherche d'information, l'interprétation ambiguë, la pondération des preuves et la mémoire. Il protège des croyances déjà établies et peut se combiner à la sélection des sources et à l'identité sociale.",
        "Sa portée est transversale : science, médecine, management, relations, politique et usage des moteurs de recherche.",
        "Le terme couvre plusieurs processus ; une préférence pour une hypothèse n'est pas toujours biaisée si les probabilités antérieures la justifient.",
        ("Formuler à l'avance ce qui réfuterait l'hypothèse.", "Chercher la meilleure preuve contradictoire et comparer des sources indépendantes."),
        "Nickerson (1998), Confirmation Bias: A Ubiquitous Phenomenon", "https://doi.org/10.1037/1089-2680.2.2.175"),
    40: E(
        "Erreur de conjonction", ("sophisme de conjonction", "problème de Linda"), "effet", "probabilite_estimation", 4, "forte",
        "Une combinaison de deux événements paraît parfois plus probable que l'un de ces événements pris seul.",
        "Un profil détaillé rend « employée de banque et militante » plus plausible que « employée de banque », alors que le premier ensemble est inclus dans le second.",
        "La représentativité d'un scénario cohérent peut l'emporter sur la règle selon laquelle une intersection ne peut pas être plus probable que l'un de ses composants. Les détails ajoutés rendent l'histoire plus convaincante tout en réduisant mathématiquement sa probabilité.",
        "Elle est importante pour les diagnostics, scénarios causaux, prévisions et récits complotistes complexes.",
        "La fréquence de l'erreur dépend fortement de la formulation et de la représentation du problème.",
        ("Dessiner les ensembles ou reformuler le problème avec des fréquences.", "Comparer explicitement l'événement simple et le même événement avec une condition supplémentaire."),
        "Tversky & Kahneman (1983), The Conjunction Fallacy", "https://doi.org/10.1037/0033-295X.90.4.293"),
    41: E(
        "Biais de conservatisme", ("sous-révision des croyances",), "biais", "croyances_preuves", 4, "moderee",
        "Nous révisons insuffisamment une croyance lorsque de nouvelles preuves devraient modifier davantage notre jugement.",
        "Après plusieurs indicateurs économiques contraires à sa prévision, un analyste ne réduit que très légèrement sa confiance initiale.",
        "Le biais concerne la mise à jour d'une croyance déjà formée : l'information nouvelle est prise en compte, mais avec un poids trop faible. Il se distingue du biais de confirmation, qui peut aussi déterminer quelles informations sont cherchées ou acceptées.",
        "Il peut prolonger de mauvaises stratégies, diagnostics et prévisions malgré l'accumulation d'indices contraires.",
        "La mise à jour normative dépend de la fiabilité des nouvelles preuves ; une révision prudente n'est donc pas automatiquement biaisée.",
        ("Attribuer à l'avance un poids attendu à différents résultats possibles.", "Réestimer périodiquement la situation comme si l'on héritait aujourd'hui du dossier."),
        "Oeberst & Imhoff (2023), cadre de traitement cohérent avec les croyances", "https://doi.org/10.1177/17456916221148147"),
    42: E(
        "Biais de cohérence rétrospective", ("biais de cohérence",), "biais", "memoire_temps", 3, "moderee",
        "Nous reconstruisons nos attitudes ou comportements passés comme plus proches de notre état présent qu'ils ne l'étaient réellement.",
        "Après avoir changé d'opinion sur un parti, une personne affirme avoir toujours eu des réserves qu'elle n'exprimait pas auparavant.",
        "La mémoire autobiographique n'est pas un enregistrement exact ; elle est reconstruite à partir de l'identité et des croyances actuelles. Cette reconstruction crée une continuité subjective parfois supérieure à la continuité réelle.",
        "Il réduit la qualité des témoignages rétrospectifs et des bilans d'évolution personnelle ou organisationnelle.",
        "Le terme est employé de plusieurs manières et peut chevaucher le biais rétrospectif ; la définition de la fiche doit rester centrée sur la reconstruction du passé à partir du présent.",
        ("Conserver des traces datées des opinions, prévisions et décisions.", "Comparer le souvenir aux documents de l'époque avant d'interpréter une évolution."),
        "Clark & Kashima (2007), Stereotype Consistency Bias in Communication", "https://doi.org/10.1037/0022-3514.93.6.1028"),
    46: E(
        "Biais de courtoisie", (), "biais", "influence_sociale", 3, "limitee",
        "Nous donnons une réponse plus positive ou socialement acceptable pour ne pas offenser notre interlocuteur.",
        "Un patient déclare être très satisfait lorsque le soignant qui l'a pris en charge lui pose directement la question.",
        "La présence, l'identité ou les attentes perçues de l'enquêteur peuvent modifier une réponse. Le mécanisme est proche du biais de désirabilité sociale, mais met particulièrement l'accent sur la politesse et la relation avec l'interlocuteur.",
        "Il peut fausser enquêtes de satisfaction, entretiens, évaluations hiérarchiques et collecte de retours.",
        "Les preuves sont contextuelles et parfois mixtes ; il s'agit aussi d'un biais de mesure produit par la situation d'enquête.",
        ("Recueillir les réponses de façon anonyme et hors de la présence de la personne évaluée.", "Employer des formulations neutres qui rendent la critique explicitement acceptable."),
        "Hameed et al. (2018), étude du courtesy bias", "https://doi.org/10.2147/OAJC.S153443"),
    50: E(
        "Déclinisme", ("illusion du déclin",), "biais", "memoire_temps", 4, "moderee",
        "Nous avons tendance à idéaliser le passé et à percevoir le présent ou l'avenir comme un déclin général.",
        "Chaque génération affirme que les jeunes sont moins respectueux et que la société était plus sûre autrefois, malgré des données plus nuancées.",
        "L'exposition disproportionnée aux mauvaises nouvelles présentes et la disparition plus rapide de certains souvenirs négatifs peuvent créer une comparaison asymétrique. Le déclin peut bien sûr être réel dans un domaine précis ; le biais consiste à le conclure sans indicateurs comparables.",
        "Il influence diagnostics sociaux, nostalgie politique, allocation de ressources et perception du risque.",
        "L'entrée est large et longtemps peu standardisée ; des travaux récents portent plus précisément sur l'illusion du déclin moral.",
        ("Comparer des indicateurs définis de la même manière sur plusieurs périodes.", "Distinguer l'évolution d'un domaine précis d'un jugement global sur la société."),
        "Mastroianni & Gilbert (2023), The Illusion of Moral Decline", "https://doi.org/10.1038/s41586-023-06137-x"),
    58: E(
        "Effet Dunning-Kruger", (), "effet", "metacognition_confiance", 4, "contestee",
        "Une faible compétence peut s'accompagner d'une mauvaise capacité à reconnaître ses propres erreurs.",
        "Un débutant surestime la qualité de son analyse parce qu'il ne maîtrise pas encore les critères permettant d'en voir les défauts.",
        "Les compétences nécessaires pour réussir une tâche peuvent aussi aider à évaluer sa performance. Cependant, la version populaire selon laquelle les moins compétents seraient toujours les plus confiants simplifie excessivement les résultats et peut être amplifiée par des effets statistiques.",
        "La calibration de la confiance est importante en apprentissage, recrutement, expertise et communication publique.",
        "L'interprétation, l'ampleur et une partie des méthodes de démonstration sont débattues ; cette fiche ne doit pas servir à étiqueter ou ridiculiser autrui.",
        ("Demander des prédictions chiffrées et fournir un retour objectif répété.", "Faire évaluer le travail à l'aide de critères externes et d'exemples de référence."),
        "Dunning (2011), revue de l'effet", "https://doi.org/10.1016/B978-0-12-385522-0.00005-6"),
    77: E(
        "Effet de cadrage", (), "effet", "attention_perception", 5, "forte",
        "Des formulations logiquement équivalentes conduisent à des jugements ou choix différents.",
        "Un traitement accepté par 90 % des patients paraît préférable au même traitement présenté comme échouant dans 10 % des cas.",
        "Le cadrage sélectionne un point de référence, un gain, une perte ou un aspect particulier de la situation. La décision peut alors changer alors que les conséquences objectives décrites sont identiques.",
        "Il affecte santé, politique publique, assurance, négociation, marketing et présentation des statistiques.",
        "Les alias « Frequency Illusion » et « Baader-Meinhof Phenomenon » donnés dans l'annexe source sont erronés et ne sont pas repris comme synonymes français.",
        ("Reformuler la même information en gains, en pertes et en valeurs absolues.", "Présenter simultanément les deux cadrages équivalents."),
        "Tversky & Kahneman (1981), The Framing of Decisions", "https://doi.org/10.1126/science.7455683"),
    78: E(
        "Erreur fondamentale d'attribution", (), "biais", "attribution_groupes", 5, "moderee",
        "Nous expliquons trop le comportement d'autrui par sa personnalité et pas assez par sa situation.",
        "Un retard est attribué à la négligence d'une personne sans considérer les transports interrompus ou des instructions contradictoires.",
        "L'observateur voit facilement l'acteur et moins bien les contraintes qui l'entourent. Il peut donc surestimer les dispositions stables et sous-estimer les rôles, pressions et occasions.",
        "Elle influence management, justice, relations, évaluation des performances et interprétation des comportements politiques.",
        "La force du phénomène dépend de la culture, de l'information disponible et du point de vue ; le nom « fondamentale » ne signifie pas universelle.",
        ("Lister au moins trois explications situationnelles avant de conclure sur la personnalité.", "Comparer le comportement de plusieurs personnes placées dans la même situation."),
        "Harvey, Town & Yarkin (1981), critique et étude du concept", "https://doi.org/10.1037/0022-3514.40.2.346"),
    82: E(
        "Effet Google", ("amnésie numérique",), "effet", "memoire_temps", 4, "moderee",
        "Lorsque nous savons qu'une information restera accessible en ligne, nous mémorisons davantage où la retrouver que son contenu.",
        "Une personne oublie un chiffre lu quelques minutes plus tôt mais se rappelle précisément la requête permettant de le retrouver.",
        "Les ressources externes peuvent devenir une forme de mémoire transactive. Cela modifie l'effort d'encodage et le type d'information conservée, sans signifier simplement que l'Internet détruit la mémoire.",
        "Le phénomène concerne apprentissage, recherche d'information, travail numérique et dépendance aux outils accessibles.",
        "Les effets varient selon les tâches et les réplications ; se souvenir du chemin d'accès peut être une stratégie adaptative.",
        ("Décider quelles informations doivent être comprises et mémorisées avant de lancer la recherche.", "Pratiquer le rappel sans accès au moteur pour les connaissances essentielles."),
        "Sparrow, Liu & Wegner (2011), Google Effects on Memory", "https://doi.org/10.1126/science.1207745"),
    88: E(
        "Biais rétrospectif", ("effet je-le-savais",), "biais", "memoire_temps", 5, "forte",
        "Après avoir connu un résultat, nous le jugeons plus prévisible qu'il ne l'était auparavant.",
        "Après l'échec d'un projet, chacun affirme que les signes annonciateurs étaient évidents dès le début.",
        "La connaissance du résultat modifie le souvenir des prévisions initiales, renforce la cohérence apparente des causes et réduit les alternatives imaginées. Cela peut produire une illusion de prévisibilité.",
        "Il déforme apprentissage, audit, médecine, justice, histoire et évaluation des décideurs.",
        "Un événement pouvait être objectivement prévisible ; le biais se démontre par l'écart entre les jugements avant et après le résultat, pas par la seule affirmation rétrospective.",
        ("Consigner prévisions, probabilités et raisons avant de connaître le résultat.", "Reconstituer les scénarios alternatifs plausibles avec les seules informations disponibles à l'époque."),
        "Roese & Vohs (2012), Hindsight Bias", "https://doi.org/10.1177/1745691612454303"),
    89: E(
        "Biais d'attribution hostile", (), "biais", "attribution_groupes", 4, "moderee",
        "Nous interprétons une action ambiguë comme délibérément hostile.",
        "Un message bref et maladroit est lu comme une attaque personnelle plutôt que comme une réponse écrite dans l'urgence.",
        "Lorsque l'intention est incertaine, les attentes de menace peuvent orienter l'interprétation vers l'hostilité. Cette lecture peut ensuite provoquer une réaction agressive qui confirme en apparence l'attente initiale.",
        "Il compte dans conflits interpersonnels, harcèlement, polarisation et modération de contenus ambigus.",
        "Une grande partie de la littérature concerne l'agression et certaines populations ; il ne faut pas diagnostiquer un individu sur un exemple isolé.",
        ("Générer plusieurs intentions possibles avant de répondre.", "Demander une clarification factuelle lorsque le coût relationnel le permet."),
        "Pornari & Wood (2010), hostile attribution bias and aggression", "https://doi.org/10.1002/ab.20336"),
    100: E(
        "Illusion de validité", (), "effet", "metacognition_confiance", 4, "moderee",
        "La cohérence apparente des informations augmente excessivement notre confiance dans un jugement ou une prévision.",
        "Un recruteur devient très sûr de son évaluation parce que le récit d'un candidat est fluide et cohérent, malgré peu de données prédictives.",
        "Un ensemble d'indices concordants produit une histoire convaincante, même lorsque les indices sont redondants, sélectionnés ou faiblement liés au résultat. La confiance subjective dépasse alors la validité réelle de la méthode.",
        "Ce mécanisme touche entretiens, prévisions, diagnostics, analyse de renseignement et récits explicatifs.",
        "La cohérence constitue parfois une preuve légitime ; il faut la comparer à la précision prédictive observée et à l'indépendance des indices.",
        ("Mesurer la précision passée de la méthode plutôt que sa seule plausibilité.", "Vérifier l'indépendance des indices et rechercher des données qui produiraient un récit concurrent."),
        "Einhorn & Hogarth (1978), Persistence of the Illusion of Validity", "https://doi.org/10.1037/0033-295X.85.5.395"),
    101: E(
        "Corrélation illusoire", (), "effet", "probabilite_estimation", 5, "forte",
        "Nous percevons une relation entre deux variables alors qu'elle est absente ou beaucoup plus faible.",
        "Quelques incidents mémorables suffisent à associer un groupe minoritaire à un comportement négatif pourtant aussi fréquent ailleurs.",
        "La cooccurrence d'événements rares ou saillants attire l'attention et se mémorise mieux que les nombreux cas ordinaires. Sans tableau complet des quatre combinaisons possibles, une association paraît plus forte qu'elle ne l'est.",
        "Elle alimente stéréotypes, pseudo-sciences, erreurs médicales et fausses explications causales.",
        "Une corrélation réelle peut exister ; le contrôle exige des données comparatives, un dénominateur et une mesure d'incertitude.",
        ("Construire un tableau incluant présence et absence de chaque variable.", "Calculer l'association sur l'ensemble des observations plutôt que sur les cas mémorables."),
        "Hamilton & Gifford (1976), Illusory Correlation", "https://doi.org/10.1016/S0022-1031%2876%2980006-6"),
    103: E(
        "Effet de vérité illusoire", ("effet de répétition de la vérité",), "effet", "croyances_preuves", 5, "forte",
        "La répétition d'une affirmation augmente son impression de vérité, même sans nouvelle preuve.",
        "Un slogan faux paraît plus crédible après avoir été vu plusieurs fois dans différents fils d'actualité.",
        "La répétition augmente la familiarité et la fluidité de traitement ; cette facilité peut être interprétée à tort comme un signe de vérité. L'effet peut toucher des affirmations plausibles comme des affirmations connues comme douteuses.",
        "Il est central pour publicité, propagande, rumeurs, désinformation et mémorisation des rectifications.",
        "L'effet moyen est robuste, mais sa taille dépend du délai, des connaissances, du contexte et de la formulation.",
        ("Éviter de répéter inutilement la formulation exacte d'une fausse affirmation.", "Mettre l'accent sur le fait correct et rappeler la qualité de sa source."),
        "Dechêne et al. (2010), méta-analyse de l'effet de vérité", "https://doi.org/10.1177/1088868309352251"),
    107: E(
        "Biais d'endogroupe", ("favoritisme intragroupe",), "biais", "attribution_groupes", 5, "forte",
        "Nous évaluons ou favorisons plus positivement les membres du groupe auquel nous nous identifions.",
        "La même erreur est excusée chez un collègue de son équipe et jugée révélatrice d'incompétence dans l'équipe rivale.",
        "Une simple catégorisation peut suffire à modifier allocation, confiance et jugement. Le biais peut se manifester comme favoritisme envers les siens sans nécessairement produire une hostilité explicite envers les autres.",
        "Il affecte politique, recrutement, coopération, justice, sport et circulation partisane de l'information.",
        "L'intensité dépend de la saillance, du statut et de la pertinence du groupe ; toutes les préférences pour un proche ne sont pas injustifiées.",
        ("Utiliser des critères identiques définis avant de connaître l'appartenance au groupe.", "Faire relire les décisions par des personnes ayant des appartenances ou perspectives différentes."),
        "Mullen, Brown & Smith (1992), méta-analyse", "https://doi.org/10.1002/ejsp.2420220202"),
    111: E(
        "Croyance en un monde juste", ("hypothèse du monde juste",), "biais", "attribution_groupes", 4, "moderee",
        "Nous tendons à croire que les personnes reçoivent ce qu'elles méritent, même lorsque le hasard ou les structures comptent fortement.",
        "Une victime d'escroquerie est blâmée pour sa naïveté afin de préserver l'idée que les personnes prudentes sont à l'abri.",
        "La croyance en un ordre juste peut donner un sentiment de contrôle et de prévisibilité. Face à une injustice difficile à réparer, elle peut conduire à réinterpréter la victime ou le résultat comme mérité.",
        "Elle influence jugement moral, pauvreté, santé, justice, victimes et légitimation des institutions.",
        "Le concept peut aussi être mesuré comme une croyance stable ; ses effets dépendent du contexte et ne sont pas toujours identiques à la culpabilisation de la victime.",
        ("Séparer responsabilité causale, responsabilité morale et possibilité de prévention.", "Examiner explicitement le rôle du hasard, des contraintes et des inégalités de départ."),
        "Lerner & Miller (1978), revue du just-world research", "https://doi.org/10.1037/0033-2909.85.5.1030"),
    138: E(
        "Biais d'optimisme", ("optimisme irréaliste",), "biais", "probabilite_estimation", 4, "moderee",
        "Nous sous-estimons nos risques futurs et surestimons la probabilité d'issues favorables.",
        "Un conducteur pense que l'accident concerne surtout les autres et néglige une mesure de sécurité.",
        "L'optimisme peut concerner le résultat attendu ou la comparaison avec autrui. Il soutient parfois motivation et persévérance, mais fausse préparation, prévention et allocation des ressources lorsque les risques sont objectivement sous-évalués.",
        "Il intervient en santé, sécurité, planification, entrepreneuriat et changement climatique.",
        "L'optimisme n'est pas toujours une erreur et peut être adaptatif ; il faut comparer la prévision à un risque de référence pertinent.",
        ("Utiliser des taux de base pour des personnes ou projets comparables.", "Préparer un plan d'échec et identifier des indicateurs précoces de dérive."),
        "Sharot (2011), The Optimism Bias", "https://doi.org/10.1016/j.cub.2011.10.030"),
    139: E(
        "Effet autruche", ("problème de l'autruche",), "effet", "decision_action", 5, "moderee",
        "Nous évitons une information utile lorsqu'elle risque d'être désagréable ou menaçante.",
        "Un investisseur consulte moins souvent son portefeuille pendant une baisse et retarde ainsi une décision nécessaire.",
        "L'évitement réduit l'inconfort à court terme mais peut augmenter le coût futur. Il porte sur l'acquisition de l'information, ce qui le distingue d'un simple rejet après lecture.",
        "Il est important en santé, finances, sécurité, gestion de projet et suivi de performances.",
        "Ne pas consulter une information peut être rationnel si elle est coûteuse ou non actionnable ; il faut montrer que l'évitement est motivé par sa valence négative.",
        ("Planifier à l'avance des moments obligatoires de consultation des indicateurs.", "Associer l'information négative à une action précise et réalisable."),
        "Karlsson, Loewenstein & Seppi (2009), The Ostrich Effect", "https://doi.org/10.1007/s11166-009-9060-6"),
    140: E(
        "Biais de résultat", (), "biais", "decision_action", 5, "forte",
        "Nous jugeons la qualité d'une décision à partir de son résultat plutôt qu'à partir des informations disponibles au moment du choix.",
        "Une décision médicale prudente est qualifiée de mauvaise parce qu'une complication rare s'est produite.",
        "Une bonne procédure peut conduire à un mauvais résultat par hasard, et une mauvaise procédure réussir par chance. Confondre décision et résultat empêche d'apprendre correctement et récompense parfois la prise de risque injustifiée.",
        "Il affecte médecine, investissement, management, justice, sport et évaluation des politiques.",
        "Le résultat peut fournir une information pertinente sur la qualité d'une règle ; le biais consiste à lui attribuer un poids injustifié dans l'évaluation d'une décision passée unique.",
        ("Évaluer séparément processus, informations, probabilités prévues et résultat.", "Faire juger la décision en masquant d'abord son résultat."),
        "Baron & Hershey (1988), Outcome Bias in Decision Evaluation", "https://doi.org/10.1037/0022-3514.54.4.569"),
    142: E(
        "Excès de confiance", ("biais de surconfiance",), "biais", "metacognition_confiance", 5, "forte",
        "Notre confiance subjective dépasse la précision réelle de nos connaissances, estimations ou prévisions.",
        "Un expert donne une fourchette très étroite pour une prévision économique qui dépend de nombreux facteurs incertains.",
        "L'excès de confiance recouvre au moins la surestimation de sa performance, le surclassement par rapport aux autres et une précision excessive des intervalles. Ces formes ne se comportent pas toujours de la même façon.",
        "Il amplifie risques, erreurs de planification, mauvaises prévisions et résistance aux avis contraires.",
        "Le niveau dépend de la difficulté de la tâche et de la définition utilisée ; il faut éviter de fusionner excès de confiance et effet Dunning-Kruger.",
        ("Exprimer la confiance en probabilités et vérifier régulièrement la calibration.", "Utiliser des intervalles plus larges, des taux de base et un retour sur les prévisions passées."),
        "Moore & Healy (2008), The Trouble With Overconfidence", "https://doi.org/10.1037/0033-295X.115.2.502"),
    161: E(
        "Biais de proportionnalité", ("heuristique grande cause-grand événement",), "biais", "probabilite_estimation", 4, "moderee",
        "Nous supposons qu'un événement de grande ampleur doit avoir une cause de taille comparable.",
        "Une catastrophe majeure paraît nécessiter un vaste complot, tandis qu'une chaîne de petites erreurs semble psychologiquement insuffisante.",
        "La correspondance intuitive entre grandeur de l'effet et grandeur de la cause rend certaines explications plus satisfaisantes. Elle peut faire négliger les systèmes complexes, effets cumulatifs, seuils et événements rares.",
        "Elle joue dans raisonnement causal, accidents, histoire, santé et adhésion aux théories du complot.",
        "La littérature est plus limitée que pour l'ancrage ou le cadrage, et une cause majeure peut évidemment produire un événement majeur.",
        ("Construire une chaîne causale détaillée incluant petites causes, interactions et probabilités.", "Comparer le récit proportionnel à des mécanismes connus dans des événements similaires."),
        "Leman & Cinnirella (2007), A Major Event Has a Major Cause", "https://doi.org/10.1002/acp.1349"),
    176: E(
        "Biais de saillance", (), "biais", "attention_perception", 5, "moderee",
        "Les éléments voyants, émotionnels ou inhabituels pèsent davantage dans le jugement que des informations moins visibles mais pertinentes.",
        "Un accident spectaculaire influence davantage une politique de sécurité que des milliers d'incidents ordinaires totalisant plus de victimes.",
        "La saillance dirige l'attention et facilite le rappel ; elle peut ainsi être confondue avec la fréquence, l'importance ou la causalité. Les interfaces et médias déterminent en partie ce qui devient saillant.",
        "Elle intervient dans presque toute présentation d'information et interagit avec disponibilité, affect et attention.",
        "La saillance est un mécanisme général plutôt qu'un test unique ; son effet dépend de la tâche et de ce qui est rendu visible.",
        ("Définir les critères avant de voir les cas les plus frappants.", "Présenter aussi dénominateurs, distributions et informations peu visibles."),
        "Taylor & Fiske (1978), Salience, Attention, and Attribution", "https://doi.org/10.1016/S0065-2601%2808%2960009-X"),
    193: E(
        "Biais stéréotypique", ("biais de stéréotype",), "biais", "attribution_groupes", 5, "forte",
        "Nous attribuons à une personne des caractéristiques attendues de son groupe plutôt que de nous appuyer sur les informations individuelles pertinentes.",
        "Deux candidatures identiques sont évaluées différemment parce que le genre suggéré ne correspond pas au métier concerné.",
        "Les stéréotypes sont des associations ou attentes concernant des groupes. Ils orientent attention, interprétation, mémoire et décision, parfois sans intention consciente, et peuvent produire des discriminations cumulatives.",
        "Leur impact est majeur dans recrutement, santé, justice, éducation, médias et conception de systèmes automatisés.",
        "« Biais stéréotypique » est une famille très large ; chaque fiche d'application devra préciser le groupe, le domaine, la mesure et les conséquences étudiées.",
        ("Structurer les critères et, lorsque possible, masquer les caractéristiques non pertinentes.", "Comparer les décisions entre groupes et auditer les écarts avec des données appropriées."),
        "Heilman (2012), Gender Stereotypes and Workplace Bias", "https://doi.org/10.1016/j.riob.2012.11.003"),
    203: E(
        "Effet de télescopage temporel", ("télescopage temporel",), "effet", "memoire_temps", 3, "moderee",
        "Nous datons les événements récents comme plus anciens ou les événements lointains comme plus récents qu'ils ne le sont.",
        "Une personne affirme qu'un incident a eu lieu le mois dernier alors qu'il remonte en réalité à trois mois.",
        "La localisation temporelle d'un souvenir est reconstruite à partir d'indices imparfaits. Le télescopage vers l'avant rapproche les événements anciens ; le télescopage vers l'arrière éloigne certains événements récents.",
        "Il compte dans enquêtes rétrospectives, témoignages, historique médical et mesure de comportements passés.",
        "L'effet concerne surtout la datation et dépend de la période de rappel, de la saillance et des repères disponibles.",
        ("Utiliser des repères calendaires et documents datés.", "Demander une plage de dates et le degré de confiance plutôt qu'une date forcée."),
        "Thompson, Skowronski & Lee (1988), Telescoping in Dating Events", "https://doi.org/10.3758/BF03214227"),
}

FAMILY_LABELS = {
    "affect_emotion": "Émotions et évaluation affective",
    "attention_perception": "Attention, perception et présentation",
    "croyances_preuves": "Croyances, arguments et traitement des preuves",
    "probabilite_estimation": "Probabilité, quantité, causalité et estimation",
    "memoire_temps": "Mémoire, reconstruction du passé et perception du temps",
    "decision_action": "Choix, action, évitement et évaluation des décisions",
    "influence_sociale": "Conformité, autorité et influence sociale",
    "attribution_groupes": "Attribution, stéréotypes et relations entre groupes",
    "metacognition_confiance": "Métacognition et confiance",
}

EVIDENCE_LABELS = {
    "forte": "forte",
    "moderee": "modérée",
    "limitee": "limitée",
    "contestee": "contestée",
}


def quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def replace_scalar(text: str, key: str, value: str | int) -> str:
    rendered = str(value) if isinstance(value, int) else quoted(value)
    updated, count = re.subn(
        rf"^{re.escape(key)}:.*$", f"{key}: {rendered}", text, count=1, flags=re.MULTILINE
    )
    if count != 1:
        raise ValueError(f"Could not replace {key}")
    return updated


def replace_aliases(text: str, aliases: tuple[str, ...]) -> str:
    block = "aliases_fr: []"
    if aliases:
        block = "aliases_fr:\n" + "\n".join(f"  - {quoted(alias)}" for alias in aliases)
    updated, count = re.subn(
        r"^aliases_fr:(?: \[\])?(?:\n  - .*)*", block, text, count=1, flags=re.MULTILINE
    )
    if count != 1:
        raise ValueError("Could not replace aliases_fr")
    return updated


def upsert_after(text: str, after_key: str, key: str, value: str) -> str:
    rendered = f"{key}: {quoted(value)}"
    if re.search(rf"^{re.escape(key)}:", text, flags=re.MULTILINE):
        return replace_scalar(text, key, value)
    return re.sub(
        rf"^({re.escape(after_key)}:.*)$", rf"\1\n{rendered}", text, count=1, flags=re.MULTILINE
    )


def upsert_null_after(text: str, after_key: str, key: str) -> str:
    rendered = f"{key}: null"
    if re.search(rf"^{re.escape(key)}:", text, flags=re.MULTILINE):
        return re.sub(rf"^{re.escape(key)}:.*$", rendered, text, count=1, flags=re.MULTILINE)
    return re.sub(
        rf"^({re.escape(after_key)}:.*)$", rf"\1\n{rendered}", text, count=1, flags=re.MULTILINE
    )


def render_body(name_en: str, item: Entry) -> str:
    evidence_label = EVIDENCE_LABELS[item.evidence]
    prevention = "\n".join(f"- {action}" for action in item.prevention)
    return f"""# {item.name_fr}

*Nom anglais : {name_en}*

## Carte

- **En bref :** {item.short}
- **Exemple :** {item.example}
- **Importance :** {item.importance}/5 - provisoire
- **Solidité des preuves :** {evidence_label}

## Description détaillée

{item.detail}

## Pourquoi c'est important

{item.importance_reason}

## Limites et nuances

{item.limits}

## Prévention

{prevention}

## Sources de départ

- [Soprano et al. (2024), revue et sélection fact-checking]({SOURCE_URL})
- [{item.reference_label}]({item.reference_url})
"""


def enrich(path: Path, item: Entry) -> None:
    text = path.read_text(encoding="utf-8")
    if "fact_checking_relevant: true" not in text:
        raise ValueError(f"{path} is not marked fact-checking-relevant")
    name_match = re.search(r'^name_en: "(.+)"$', text, flags=re.MULTILINE)
    if not name_match:
        raise ValueError(f"English name not found in {path}")
    name_en = name_match.group(1)

    front, _, _old_body = text.partition("\n---\n")
    if not _:
        raise ValueError(f"Front matter boundary not found in {path}")
    front += "\n---"
    front = replace_scalar(front, "name_fr", item.name_fr)
    front = replace_aliases(front, item.aliases_fr)
    front = replace_scalar(front, "status", "documente")
    front = replace_scalar(front, "type", item.kind)
    front = replace_scalar(front, "family", item.family)
    front = replace_scalar(front, "importance", item.importance)
    front = upsert_after(front, "importance", "importance_status", "provisoire")
    front = replace_scalar(front, "evidence_level", item.evidence)
    front = upsert_after(front, "evidence_level", "documented_on", DOCUMENTATION_DATE)
    front = upsert_after(front, "documented_on", "review_status", "non_revue")
    front = upsert_null_after(front, "review_status", "reviewed_on")
    path.write_text(front + "\n\n" + render_body(name_en, item), encoding="utf-8")


def summary_content(files: dict[int, Path]) -> str:
    lines = [
        "# Lot prioritaire : 39 biais liés au fact-checking",
        "",
        "Ces fiches ont reçu une première traduction, une définition courte, un exemple,",
        "une famille éditoriale, un score d'importance provisoire et un niveau de preuve.",
        "Les scores servent à organiser le travail ; ils ne constituent pas encore un",
        "classement scientifique définitif.",
        "",
        "Voir la [grille d'importance et de preuve](grille-importance.md).",
        "",
        "## Vue d'ensemble",
        "",
        f"- Fiches documentées : **{len(ENTRIES)}**",
        f"- Importance critique (5/5) : **{sum(item.importance == 5 for item in ENTRIES.values())}**",
        f"- Preuves fortes : **{sum(item.evidence == 'forte' for item in ENTRIES.values())}**",
        f"- Preuves contestées : **{sum(item.evidence == 'contestee' for item in ENTRIES.values())}**",
        "",
    ]
    for family, label in FAMILY_LABELS.items():
        members = [
            (number, item) for number, item in ENTRIES.items() if item.family == family
        ]
        if not members:
            continue
        members.sort(key=lambda pair: (-pair[1].importance, pair[0]))
        lines.extend(
            [
                f"## {label}",
                "",
                "| Fiche | En bref | Importance | Preuves |",
                "|---|---|:---:|:---:|",
            ]
        )
        for number, item in members:
            path = files[number]
            short = item.short.replace("|", "\\|")
            lines.append(
                f"| [{item.name_fr}](biais/{path.name}) | {short} | "
                f"{item.importance}/5 | {EVIDENCE_LABELS[item.evidence]} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Étape de validation suivante",
            "",
            "Pour chaque fiche, il reste à rechercher une revue récente propre au biais,",
            "à contrôler les réplications et à justifier séparément les quatre axes du",
            "score d'importance : fréquence, gravité, diversité des domaines et actionnabilité.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    directory = Path("catalogue/biais")
    files = {int(path.name[:3]): path for path in directory.glob("*.md")}
    expected = {number for number, path in files.items() if "fact_checking_relevant: true" in path.read_text(encoding="utf-8")}
    if expected != set(ENTRIES):
        raise ValueError(
            f"Curated entries do not match source flags; missing={sorted(expected - set(ENTRIES))}, "
            f"extra={sorted(set(ENTRIES) - expected)}"
        )
    for number, item in ENTRIES.items():
        enrich(files[number], item)
    summary_path = Path("catalogue/lot-prioritaire-39.md")
    summary_path.write_text(summary_content(files), encoding="utf-8")
    print(
        f"Enriched {len(ENTRIES)} fact-checking cards in French; "
        f"wrote {summary_path}"
    )


if __name__ == "__main__":
    main()
