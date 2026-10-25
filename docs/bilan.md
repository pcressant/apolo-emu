# Bilan du développement (25 octobre 2026)

## Fonctionnalités implémentées

- **Appareil Apollo II** (`device.py`, `protocol.py`) : un modèle à deux étages, fidèle à la ROM 2.01 et à la
  documentation Dolphin.
  - Étage communication : mute par Ctrl-A ou Ctrl-X, commandes immédiates `@I+` et `@I?`.
  - Propositions terminées par CR ou par la ponctuation ; table des commandes différées dans l'ordre de la ROM.
  - Commandes non reconnues laissées dans le texte.
  - Distinction entre les commandes appliquées à la proposition et celles synchronisées avec la parole.
  - Registres interrogeables (`@c?`), liste des langues (`@L`), échos `@E`, index.
- **Synchronisation** :
  - une marque SSML au début de chaque proposition qui a des effets, et à chaque `@I+` ;
  - les effets se produisent quand Speech Dispatcher signale que la parole les atteint ;
  - les propositions d'une même lecture forment un seul message : jamais un message par mot.
- **Backend Speech Dispatcher** (`ssip.py`) :
  - client SSIP sans dépendance, réglages traduits par `mapping.py` ;
  - reconnexion ; repli qui ne bloque pas l'invité ;
  - lancement automatique de Speech Dispatcher s'il est absent.
- **Backends sans son** : `simulated` (durée simulée) et `null`.
- **Transport** (`transport.py`) : socket Unix en écoute ou en connexion, une connexion à la fois, détection des
  sockets obsolètes, journal des octets.
- **Lanceur QEMU** (`launcher.py`) :
  - répertoire d'instance et socket propres à chaque lancement ;
  - ajout du port par `-device isa-serial,index=N` ;
  - détection des conflits de ports, transmission des signaux, codes de retour conservés ;
  - nettoyage des instances abandonnées ; plusieurs instances simultanées.
- **Quatre extensions isolées**, désactivées par défaut : `epaulard-index`, `word-echo`, `lenient-speed`,
  `burst-interrupt`.
- **Intégration Nix facultative** (`default.nix`). Le programme fonctionne aussi hors de NixOS, avec Python ≥ 3.10.

## Sources consultées

Voir [references.md](references.md) :
- documentation Dolphin : APOLLO.TXT, Technical Bulletin 25, manuel Series 2 de 1998 ;
- décompilation de la ROM 2.01 ;
- Speakup ;
- emacspeak-ss ;
- profils de Screen Reader/2 ;
- Sonolect et Épaulard, d'après les projets voisins.

## Résultats des tests

`python3 -m unittest discover -s tests -t .` donne **112 tests, tous réussis**. Un test est ignoré par défaut :
celui de la parole réelle, qui s'active avec `APOLO_EMU_SPEECHD=1`. Lancé séparément, ce test réussit aussi.

| Fichier | Contenu |
|---|---|
| `test_protocol.py` | `hex_value`, réponses hexadécimales, motifs, analyse des propositions, découpage, limites de longueur |
| `test_device.py` | fragments octet par octet, blocs multiples, réglages, mute (y compris au milieu d'une commande), échos, index, interrogations, `@J`, volume synchronisé, effets, langues, encodages, commandes inconnues, débordement, extensions |
| `test_mapping.py` | correspondance des réglages |
| `test_ssip.py` | faux serveur SSIP : initialisation, SSML, réglages envoyés une seule fois, événements, annulation, perte et rétablissement de la connexion, refus, moteur injoignable |
| `test_transport.py` | requêtes sur la socket, fragments, droits, seconde connexion refusée, reconnexion avec état conservé, réponses perdues hors connexion, sockets obsolètes, mode connexion avec reconnexion |
| `test_launcher.py` | construction de la commande QEMU et conflits ; code de retour ; QEMU absent ; nettoyage ; trois instances simultanées ; SIGTERM transmis ; politique `wait` ; répertoires abandonnés |
| `test_qemu_integration.py` | **vrai QEMU 10.2.4** avec une VM de test indépendante (secteur d'amorçage) : UART à 9600 bauds 8N1, MSR = 0xB0, `@I?` → `I10T` pendant la parole, écho `@E` après la fin, COM2 à côté d'un COM1 existant |
| `test_speechd_integration.py` | **vrai Speech Dispatcher et eSpeak NG** : ordre et temporisation des échos et des index |

`nix-build` relance toute la suite dans le bac à sable de Nix, avec le même résultat.

**Non fait, faute d'autorisation** : aucun essai avec Sonolect, Épaulard ou Screen Reader/2 sur les VM des
projets voisins. Ces VM n'ont été ni lancées ni modifiées ; une VM OS/2 tournait pendant le développement et n'a
pas été touchée.

## Limites de fidélité

Voir [limitations.md](limitations.md). Les principales :
- voix, prosodie et effets sonores ne sont pas ceux de l'appareil ;
- aucun contrôle de flux matériel n'est possible au travers d'une socket ;
- une seule ROM sert de référence pour le détail de l'analyse ;
- le sens de `T`/`M` dans la réponse à `@I?` est incertain ;
- le moment de l'écho `@E` est déduit, non mesuré.

## Commandes encore manquantes ou approximées

- **Non implémentées** : `@Y` (série), le NAK de lecture à vide, la poignée de main RTS/CTS, les phonèmes `_XX`
  et le mode `@X`, l'hypermode `@H`.
- **Mémorisées sans effet audible** : `@Q`, `@D`, `@R`, `@B`, `@M`, `@$`, `@u`.
- **Approximées** : `@T` (silences), `@?` (texte réglable), contenu de `@L`.

## Incompatibilités découvertes dans les passerelles existantes

Elles concernent `../pc486/gateway/apollo2spd.py` et sa copie dans `../os2/gateway/`.

1. **`@I<c>` (Épaulard)** n'est pas une commande Apollo II : un vrai appareil prononcerait « I A ». Le vrai
   `@I+` / `@I?` n'est pas géré. L'extension `epaulard-index` reproduit le comportement. L'idiome authentique
   `texte<CR>@Ec<CR>` le remplacerait sans extension.
2. **La ponctuation ne termine pas la proposition** dans les prototypes. Or Sonolect termine ses réglages par
   `.` (`@W4@A3@F9.`), et la ROM s'appuie sur ce point.
3. **Le prototype `os2` découpe la parole mot par mot** pour suivre `@e<TAB>`. Un vrai Apollo II renvoie ces
   échos ensemble, au début de la phrase : Apolo-emu fait de même, en un seul message.
4. **Analyse incorrecte** :
   - `@@` donne `@` ;
   - argument toujours d'un caractère : `@M**` et `@u…` ne sont pas reconnus ;
   - Ctrl-X ou Ctrl-A avalé après `@` : la chaîne de silence `@^A^X` du profil IBM perdrait son Ctrl-X ;
   - LF équivaut à CR ;
   - le texte est prononcé après 0,3 s sans CR ;
   - espaces normalisées.
5. **Aucune réponse** à `@I?`, `@c?` ou `@L`. Seul `@E` renvoie un octet.
6. **Le profil Screen Reader/2** envoie `@w0`, `@wb` et `@wf`, rejetés par la ROM 2.01. Les prototypes les
   acceptaient (option `lenient-speed` ici).
7. **Divergences mineures** de la passerelle `os2` :
   - langue `en` par défaut, alors que le commentaire dit « français » ;
   - le README annonce `@r0..@r7` dans APOLLO2.TTS, qui ne contient que `@r6` et `@r7` ;
   - restes de l'extension `@I` (code mort).

## Prochaines améliorations pertinentes

1. **Validation avec les logiciels d'époque**, sur autorisation : Sonolect et Épaulard (`pc486`), Screen
   Reader/2 (`os2`), avec `--trace` pour comparer les séquences réelles aux hypothèses. Il faut vérifier en
   particulier :
   - si Screen Reader/2 attend les échos `@e` avant de continuer ;
   - si le suivi par proposition lui convient, ou s'il faut `word-echo`.
2. **Côté Épaulard** : fait le 25 octobre 2026, Épaulard envoie `texte CR @E<c> CR` et n'a plus besoin
   d'extension. `pc486` et `os2` lancent désormais Apolo-emu à la place de leurs passerelles.
3. **Pauses `@D` et `@Q`** : les rendre par des `<break>` SSML, après étalonnage.
4. **Effets sonores `@T`** : courts fichiers audio (SSML `<audio>` ou icônes sonores de Speech Dispatcher), si le
   module les gère.
5. **Profils de ROM** : sélectionner une variante (2A, ROM US) si de la documentation ou une autre ROM le
   justifie.
6. **Analyse de `-readconfig`** dans le lanceur.
