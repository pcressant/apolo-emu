# Architecture

## Modules

| Module | Rôle | Dépend de |
|---|---|---|
| `protocol.py` | Tables et fonctions pures : motifs de commandes, `hex_value`, réponses hexadécimales, découpage en propositions (`ClauseAccumulator`), analyse (`scan_clause`) | rien |
| `device.py` | **L'appareil** : étages communication et proposition, registres, chronologie de la parole, réponses | `protocol`, `speech` |
| `speech.py` | Interface du backend vocal (`SpeechBackend`, `Utterance`, `SpeechEvent`, `VoiceParams`) et backends sans son (`NullBackend`, `SimulatedBackend`) | rien |
| `mapping.py` | Traduction des réglages Apollo en réglages SSIP | `speech` |
| `ssip.py` | Backend Speech Dispatcher : client SSIP asynchrone, SSML, événements | `speech`, `mapping` |
| `transport.py` | Socket Unix (écoute ou connexion), sockets obsolètes, journal des octets | `device` |
| `app.py` | Assemblage d'un émulateur complet à partir des options ; mode autonome | tous |
| `launcher.py` | Lanceur QEMU : arguments, répertoire d'instance, signaux, nettoyage | `app` |
| `cli.py` | Ligne de commande | `app`, `launcher` |

Le cœur (`protocol`, `device`) ne fait aucune entrée-sortie et ne connaît ni QEMU, ni la socket, ni
Speech Dispatcher, ni le système invité. Il est synchrone et se teste octet par octet.

## Interfaces

```python
# Appareil
device = ApolloDevice(backend, reply=callable_bytes, config=DeviceConfig(...))
device.feed(data: bytes)                # octets reçus, en morceaux quelconques
device.on_speech_event(ev: SpeechEvent) # progression signalée par le backend
# réponses : reply(bytes) ; parole : backend.speak(Utterance), backend.cancel()

# Backend vocal (speech.SpeechBackend)
set_event_sink(sink)      # sink(SpeechEvent(uid, "begin" | "mark" | "end" | "cancel", mark))
speak(utt: Utterance)     # met en file, après les énoncés en cours
cancel()                  # silence immédiat, file vidée
async start(), async close()
```

Un `Utterance` est une suite de parties : du texte (`str`), des marques (`Mark(name)`) et des silences
(`Pause(ms)`). Il porte ses `VoiceParams`, exprimés en **valeurs Apollo** : la traduction appartient au
backend.

Un autre moteur se branche en écrivant une classe qui respecte ces cinq méthodes. Il doit signaler au minimum
`end` pour chaque énoncé ; `mark` et `begin` améliorent la précision.

## Modèle de l'appareil

Le firmware traite les données en deux étages (voir [protocole.md](protocole.md) §2) :

1. **Étage communication** (`_receive`), octet par octet :
   - Ctrl-A et Ctrl-X déclenchent `mute()` ;
   - `@` passe en mode commande immédiate : `@I?` répond tout de suite, `@I+` incrémente le compteur ;
   - le reste va dans le tampon d'entrée.
2. **Étage proposition** (`_clause`) :
   - `ClauseAccumulator` découpe le flux sur CR, sur la ponctuation et selon les longueurs limites ;
   - `scan_clause` retire les commandes reconnues ;
   - `_phrase_command` applique les commandes de l'étage proposition à l'**état projeté** ;
   - les commandes synchronisées (`@A`, `@B`, `@I+`, `@T`) deviennent des marques ou des silences à leur position.

### Deux états de registres

- `projected` : l'état après toutes les propositions déjà analysées. Il sert à fixer les réglages des énoncés
  au moment où on les construit.
- `live` : l'état atteint par la parole. Il est modifié par les actions quand la parole y arrive, et c'est lui
  que lisent les interrogations `@c?`.

Après un mute, `projected` redevient égal à `live`. Les réglages des propositions effacées n'ont donc jamais
pris effet, comme sur l'appareil.

### Chronologie

`timeline` est la file ordonnée de ce qui reste à « jouer ». Elle contient deux sortes d'éléments :
- **`_Spoken`** : un énoncé confié au backend. Il porte la liste de ses marques et, pour chacune, les actions à
  exécuter : échos, réponses, mises à jour de `live`, décompte d'index.
- **`_Immediate`** : les actions d'une proposition qui n'a rien à dire. Elles s'exécutent dès que tout ce qui
  précède est terminé.

Règles :
- **Début de proposition.** Chaque proposition qui a des effets reçoit une marque initiale. Les actions de
  l'étage proposition (échos `@E`, réponses `@c?` et `@L`, réglages) y sont rattachées. Elles s'exécutent quand
  la parole atteint la proposition, c'est-à-dire juste après la fin de la précédente, comme sur l'Apollo dont
  la lecture est séquentielle.
- **Fusion.** Les propositions reçues dans une même lecture et qui ont les mêmes réglages forment **un seul
  message**. Il n'y a jamais un message par mot.
  - Une proposition muette coincée entre deux textes devient une marque à la jonction.
  - En fin de lot, elle reste un élément `_Immediate`, exécuté à la fin effective de la parole (événement END).
- **Changement de réglages.** Un changement de volume au milieu d'une proposition, ou un changement de réglage
  d'une proposition à l'autre, ouvre un nouveau message : SSIP applique ses réglages message par message.
- **Ordre.** Un événement reçu pour l'énoncé N termine tous les énoncés précédents : le moteur parle dans
  l'ordre.
- **Annulation.** Un événement `cancel` abandonne les actions restantes de l'énoncé : ses échos sont perdus,
  comme ceux d'une proposition effacée par un mute.

### `T` ou `M` dans la réponse à `@I?`

`talking` est vrai s'il reste un énoncé parlé dans la chronologie ou dans le lot en cours.

Avec `--talking-rule rom`, il l'est aussi pendant qu'une proposition inachevée est en cours de réception. Voir
[protocole.md](protocole.md) §2.4.

## Concurrence

Tout tourne dans une seule boucle asyncio et un seul fil :
- le transport appelle `device.feed()` à chaque lecture de la socket ;
- le backend appelle `device.on_speech_event()` depuis sa tâche de lecture SSIP.

L'appareil n'est jamais appelé en parallèle. Un appel réentrant (un backend qui signale un événement pendant
`speak()`) est toléré.

## Journalisation

- Les journaux passent par le module `logging`, sur la sortie d'erreur, à quatre niveaux (`--log-level`).
- Les commandes inconnues, les valeurs rejetées et les fonctions non émulées sont signalées au niveau `info`.
- Le niveau `debug` détaille chaque lecture et chaque événement vocal.
- `--trace FICHIER` ajoute une ligne par lecture ou écriture sur le port série :
  `secondes RX|TX octets-hexadécimaux`, par exemple `   12.3456 RX 40 49 3f`.
  Le fichier est ouvert en ajout ; chaque démarrage écrit d'abord une ligne `# début AAAA-MM-JJ hh:mm:ss`,
  origine des secondes qui suivent.
  Ce format permet de rejouer ou d'analyser une session.
