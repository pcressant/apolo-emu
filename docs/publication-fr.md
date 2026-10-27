[English](publication.md) | Français

# Préparation à la publication

Vérification effectuée le 27 octobre 2026 sur l'historique accessible depuis les
références Git locales, jusqu'au commit `7c34e88`, et sur les changements de
préparation qui lui succèdent dans l'arbre de travail.

## Licence et périmètre

La licence choisie pour les contributions propres au projet est MIT, déclarée
dans `LICENSE`, les métadonnées Python et le paquet Nix. Elle permet la
réutilisation en conservant la notice de licence. Elle ne confère aucun droit
sur les sources externes citées, les marques ou les logiciels invités.

Voir [NOTICE-fr.md](../NOTICE-fr.md) pour le périmètre et les dépendances externes.

## Historique et données à publier

Les huit commits accessibles contiennent 61 versions de fichiers, représentant
404 134 octets au total, pour 45 chemins distincts. Toutes ces versions ont été
parcourues par une recherche de signatures de clés privées, jetons GitHub, clés
AWS, secrets affectés en clair et URL contenant des identifiants. Aucune
correspondance n'a été trouvée. Aucune version de fichier ne contient d'octet NUL
et aucune ne dépasse 100 Ko ; l'inventaire ne révèle ni ROM, ni manuel complet,
ni image de disque propriétaire.

Cette recherche par signatures n'est pas une garantie d'absence de secret et ne
couvre pas les objets inaccessibles, les fichiers non suivis ou les autres dépôts.
Les noms et adresses d'auteur des commits restent présents dans l'historique Git.
Les chemins locaux de projets voisins sont conservés dans les notes de recherche
comme indications de provenance ; le README propose des instructions autonomes.

Le verrou `.claude/scheduled_tasks.lock` était déjà supprimé dans l'arbre de
travail avant cette préparation. Sa version historique ne contient que des
identifiants de session et de processus ainsi qu'un horodatage local. Le dossier
`.claude/` est désormais ignoré. Aucun historique n'a été réécrit.

## Éléments issus de l'étude du firmware

La comparaison a porté sur `cmd_match.c`, `boot_input.c` et `data/cmd_data.c` du
projet Dolphin-Apollo-II-Reborn, au commit indiqué dans les
[références](references-fr.md).

Les motifs de commandes, leur priorité, les limites de propositions et les valeurs
de registres expriment des règles de compatibilité du protocole. Les tables
d'Apolo-emu associent les motifs à ses propres gestionnaires Python : elles
n'incluent ni adresses de ROM, ni tables de phonèmes, ni données acoustiques.
L'accumulateur de propositions travaille avec un tampon Python, sans reproduire
la machine et ses registres. La conversion ASCII remplace seulement les caractères
nécessaires à l'analyse ; elle n'embarque pas la table complète de la ROM.

En revanche, l'ancienne fonction `hex_value` suivait de très près les opérations
arithmétiques de `cmd_hex_value` dans la décompilation C. Elle a été reformulée
par intervalles de valeurs d'entrée, sans simulation des instructions du processeur.
Les 256 résultats ont été comparés à ceux de la version précédente pour préserver
le comportement, y compris hors des plages de commandes admises.

Cette reformulation ne change pas la provenance des connaissances et n'efface
pas la version antérieure de l'historique. Elle ne suffit pas à établir, à elle
seule, une absence de contrefaçon. La comparaison ciblée ne constitue pas un audit
exhaustif de similarité avec tous les logiciels consultés.

## Cadre et limites juridiques

L'article 1 de la [directive européenne 2009/24/CE](https://eur-lex.europa.eu/legal-content/FR/TXT/?uri=CELEX:32009L0024)
distingue l'expression protégée d'un programme des idées et principes de ses
interfaces. Ses articles 5 et 6 encadrent l'étude du fonctionnement et la
décompilation pour l'interopérabilité, sous conditions. Cette distinction motive
la séparation entre les règles du protocole et le code du firmware ; elle ne
constitue pas une autorisation générale de copier ou redistribuer celui-ci.

Ce compte rendu décrit des vérifications techniques, pas un avis juridique ni
une certification des conditions dans lesquelles les tiers ont obtenu ou
décompilé le firmware. Les points marqués `[ROM]` restent attribués à cette source
secondaire, et les incertitudes de fidélité restent dans la documentation.

## Validation technique

- Comparaison exhaustive de `hex_value` avant et après modification : 256 valeurs
  identiques.
- Suite `python3 -m unittest discover -s tests -t .` : 113 tests, succès, dont
  un ignoré par défaut (parole réelle). L'intégration QEMU est exécutée.
- Construction `nix-build --no-out-link` : paquet et wheel produits, suite réussie
  dans l'environnement Nix ; `LICENSE` et `NOTICE-fr.md` sont inclus dans la wheel.
- Aucun nouvel essai de parole réelle et aucun démarrage des VM des projets voisins.
