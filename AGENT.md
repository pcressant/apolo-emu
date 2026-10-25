# Guide de reprise — Apolo-emu

Ce fichier est la référence commune pour les agents qui travaillent sur ce dépôt.
`AGENTS.md` (Codex) et `CLAUDE.md` (Claude Code) sont des liens vers ce fichier :
modifier uniquement `AGENT.md` pour conserver une seule version des consignes.
Communiquer, commenter et rédiger la documentation en français.

Le cahier des charges complet est dans `docs/cahier-des-charges.md`. Ce guide en
résume les règles durables ; en cas de doute, le cahier des charges fait foi.

## But

Apolo-emu émule un **synthétiseur vocal matériel Apollo II** branché sur un port
série, tel qu'utilisé dans les années 1990 par les lecteurs d'écran DOS, Windows et
OS/2. L'objectif est la fidélité **protocolaire et comportementale** (commandes,
réponses, synchronisation, contrôle de flux, particularités), pas le timbre exact.
Le moteur vocal est eSpeak NG via Speech Dispatcher, derrière une interface
remplaçable.

Ce n'est pas un framework générique de synthèse vocale : on émule un appareil précis.

Priorités, dans l'ordre :

1. Fidélité au protocole Apollo II historique.
2. Compatibilité avec les lecteurs d'écran d'époque.
3. Fiabilité des échanges série.
4. Synchronisation correcte de la parole.
5. Indépendance vis-à-vis de QEMU et des systèmes invités.
6. Simplicité d'utilisation du lanceur intégré.
7. Qualité et maintenabilité du code.

## Reprendre rapidement

1. Lire ce guide, puis `git status --short` et `git log -6 --oneline` ; préserver
   les modifications existantes.
2. Consulter `docs/` (protocole, architecture, matrice de compatibilité,
   limitations) avant de modifier un comportement.
3. Faire une modification ciblée, exécuter les tests adaptés et indiquer clairement
   ce qui a été testé automatiquement, testé avec Speech Dispatcher, ou essayé dans
   une VM.
4. Mettre à jour la documentation et la matrice de compatibilité si le comportement
   change. Ajouter ici les pièges durables, pas un journal de session.

## Carte du dépôt

| Chemin | Rôle |
|---|---|
| `apolo_emu/protocol.py` | tables et fonctions pures : motifs, `hex_value`, propositions |
| `apolo_emu/device.py` | l'appareil : deux étages, registres, chronologie, extensions |
| `apolo_emu/speech.py`, `mapping.py`, `ssip.py` | interface vocale, correspondance SSIP, client SSIP |
| `apolo_emu/transport.py` | socket Unix (écoute ou connexion), trace des octets |
| `apolo_emu/app.py`, `launcher.py`, `cli.py` | assemblage, lanceur QEMU, ligne de commande |
| `tests/` | unittest ; `fakes.py` (faux backend), `fake_qemu.py`, `guest.py` (secteur d'amorçage) |
| `docs/protocole.md` | référence du protocole, avec la source de chaque point |
| `docs/compatibilite.md`, `limitations.md`, `bilan.md` | état, limites, compte rendu |

Tests : `python3 -m unittest discover -s tests -t .` (environ 4 s ; QEMU utilisé s'il
est présent). Parole réelle : `APOLO_EMU_SPEECHD=1 python3 -m unittest
tests.test_speechd_integration`. `nix-build` relance la suite.

## Projets voisins : lecture seule

- `../pc486` : DOS / Windows 3.11, Sonolect 7.11 et Épaulard
  (passerelle `gateway/apollo2spd.py`).
- `../os2` : OS/2 Warp 4, IBM Screen Reader/2 2.01 ; documentation historique dans
  `../os2/media/screen-reader/apollo-source/` (`APOLLO.TXT`, `APOLLO2.TXT`),
  investigation et correctif QEMU sur le port série.

Règles strictes :

- Les lire librement ; **ne jamais** modifier leurs fichiers, leurs VM, leurs
  configurations QEMU, ni interrompre leurs processus.
- Ne pas lancer leurs machines virtuelles sans nécessité **et** autorisation
  explicite de l'utilisateur.
- Leurs passerelles sont des prototypes : identifier ce qui est correct, approximatif
  ou erroné ; ne pas les traiter comme des références incontestables.
- Ne pas copier leur code aveuglément : comprendre, valider, vérifier licence et
  provenance.

## Sources et traçabilité

Sources à confronter : `APOLLO.TXT`, `APOLLO2.TXT`, archives et pilotes Apollo
d'IBM Screen Reader/2, notes des deux projets, pilotes Speakup du noyau Linux
(`drivers/accessibility/speakup/`, vérifier les pilotes réellement présents et le
modèle qu'ils visent), autres documentations publiques.

- Ne jamais déduire une commande de son seul nom ; confronter les sources.
- Attention aux commandes homonymes dont le sens diffère entre Apollo et Apollo II.
- Chaque comportement documenté doit être classé :
  1. confirmé par la documentation historique ;
  2. observé dans les pilotes existants ;
  3. déduit par analyse ;
  4. approximation nécessaire ;
  5. inconnu.
- La matrice de compatibilité distingue : implémentée et vérifiée, implémentée non
  vérifiée sur un véritable Apollo II, partiellement émulée, non implémentée,
  inconnue ou insuffisamment documentée.
- Préférer une émulation honnêtement documentée à une compatibilité prétendue.

## Architecture

```text
VM (DOS / Windows / OS/2) → pilote Apollo II → COM1 → UART émulée QEMU
  → socket Unix → Apolo-emu (transport → protocole → backend vocal)
  → Speech Dispatcher → eSpeak NG
```

- Pas de périphérique QEMU interne, **aucune modification de QEMU**.
- Cœur de l'émulation indépendant du transport, de QEMU, du backend vocal, du
  système invité et du lecteur d'écran. Responsabilités clairement séparées.
- Linux, Python, peu de dépendances, sans privilèges root, utilisable hors NixOS
  (une intégration Nix peut s'ajouter). Pas de réécriture en C.

## Règles du protocole

- Analyseur à **état explicite** traitant un **flux d'octets** : une lecture sur la
  socket ne correspond jamais à une commande complète ; gérer fragments, séquences
  incomplètes, commandes successives dans un même bloc et caractères de contrôle.
- Paramètres persistants, réinitialisations, interruptions et réponses à l'invité
  modélisés explicitement.
- Commandes inconnues : journalisées proprement, sans comportement arbitraire.
- Pas de conversion d'encodage implicite ni de transformation destructrice du texte.
- Synchronisation (notamment `@e` d'IBM Screen Reader/2) : distinguer réception,
  analyse, mise en attente, début de synthèse, progression, fin et interruption.
  Les réponses doivent suivre autant que possible la progression réelle (étudier
  SSML et `INDEX_MARKS` de Speech Dispatcher, vérifier leur prise en charge
  effective). Sinon, comportement déterministe et limite documentée.
- Éviter le découpage systématique en un message par mot.
- Extensions non authentiques (p. ex. variantes de `@I` utilisées par Épaulard) :
  isolées, documentées, **désactivées par défaut**, sans jamais modifier le sens
  d'une commande Apollo II authentique.

## Transport série et contrôle de flux

- Socket Unix bidirectionnelle vers QEMU.
- Une socket ne transporte que des octets : RTS/CTS/DTR/DSR ne la traversent pas.
  Distinguer ce que fait l'UART de QEMU, ce que permet le transport et ce qui
  relève de l'Apollo II. Ne pas prétendre à un contrôle de flux matériel complet
  si l'interface ne le permet pas.

## Backend vocal

Interface remplaçable : envoi de texte, arrêt immédiat, débit, hauteur, volume,
progression, fin de lecture. La traduction des paramètres Apollo II vers le moteur
est documentée et testée.

## Lanceur QEMU

- Mode autonome (p. ex. `apolo-emu --socket PATH`) et mode lanceur
  (p. ex. `apolo-emu run -- qemu-system-i386 …`) ; interface ajustable si plus robuste.
- Socket propre à chaque instance, ordre de démarrage correct, ajout du port série
  sans conflit avec les options existantes, erreurs de démarrage gérées, signaux
  propagés, codes de retour préservés, nettoyage de ses seules ressources, pas de
  socket obsolète, plusieurs instances indépendantes.
- Ne jamais tuer un processus QEMU qu'il n'a pas lancé ; ne pas arrêter brutalement
  une VM quand un arrêt propre de l'invité est nécessaire.
- N'imposer aucune configuration de disque, mémoire, processeur ou invité.

## Tests

- Faux backend vocal pour tester le protocole sans parole ; progression de lecture
  simulable précisément.
- Couvrir : analyse, fragments, blocs multiples, paramètres, interruptions,
  réinitialisations, acquittements, réponses, encodages, commandes inconnues,
  erreurs de transport, reconnexions, instances multiples, nettoyage des processus
  et sockets.
- Tests d'intégration Speech Dispatcher et QEMU quand c'est possible, sur une VM de
  test indépendante. Les tests automatisés ne dépendent pas du démarrage d'OS/2 ou
  de Windows 3.11.

## Documentation attendue

README, protocole Apollo II, architecture, lanceur QEMU (y compris intégration à des
commandes QEMU existantes), matrice de compatibilité, limitations connues,
installation, exemples, références documentaires.

## Méthode

Travail autonome par phases : investigation → architecture → implémentation →
tests → intégration QEMU → bilan (fonctionnalités, sources, résultats de tests,
limites de fidélité, commandes manquantes, incompatibilités trouvées dans les
passerelles existantes, prochaines améliorations). Pas besoin de validation entre
les étapes, mais respect strict de l'intégrité des projets voisins.

## Pièges connus

- La ponctuation `. , : ; ! ?` termine une proposition, comme CR : `?` dans `@W?`
  ferme la proposition. Beaucoup d'attentes de tests fausses venaient de là.
- `*` dans un motif accepte n'importe quel caractère, y compris `@` : `@Mz@M2A`
  consomme le second `@` (comportement de la ROM, voulu).
- Les effets d'une proposition (échos, réponses `@c?`) attendent que la parole
  l'atteigne : un test doit faire avancer le faux backend (`begin`, `reach`, `finish`).
- `@I?` répond immédiatement, avant les échos des propositions encore en attente.
- eSpeak signale une marque finale un peu avant END : les actions d'une proposition
  muette en fin de lot sont exécutées à END, pas sur une marque.
- QEMU 10.2 accepte deux UART au même emplacement sans erreur, et `-serial none`
  consomme un numéro de port : le lanceur doit compter lui-même.
- Avec un chardev socket, l'invité voit MSR = 0xB0 (CTS, DSR, DCD actifs) : aucun
  contrôle de flux n'est possible.
- Une VM du projet `os2` peut tourner : ne jamais la toucher. Pour les essais réels,
  utiliser la priorité SSIP `notification` et un volume bas.
