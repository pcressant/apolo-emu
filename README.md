# Apolo-emu

Apolo-emu émule un synthétiseur vocal **Dolphin Apollo II** relié à un port série. Il est conçu pour faire parler
les lecteurs d'écran DOS, Windows et OS/2 des années 1990 qui tournent dans QEMU : Sonolect, Épaulard,
IBM Screen Reader/2, etc. La voix vient d'un moteur moderne, eSpeak NG via Speech Dispatcher.

L'objectif est la **fidélité au protocole** de l'appareil, et non la reproduction de son timbre. Cela couvre :
- les commandes `@` et leurs plages ;
- le découpage en propositions ;
- le moment où chaque commande agit ;
- les échos `@E` et l'index `@I+` / `@I?`, synchronisés avec la parole réelle ;
- les interrogations `@c?` et `@L` ;
- le mute (Ctrl-X).

Ce qui n'est pas connu, approximé ou impossible est dit explicitement dans la documentation.

```text
VM DOS / Windows / OS/2 → pilote Apollo II → COM1 → UART QEMU → socket Unix
  → Apolo-emu (transport → appareil Apollo II → backend vocal) → Speech Dispatcher → eSpeak NG
```

## Installation

Il faut Linux, Python 3.10 ou plus récent, et aucune autre dépendance Python. Pour la parole, il faut
Speech Dispatcher et eSpeak NG ; pour le lanceur, QEMU.

```bash
# Sans installation, depuis le dépôt
python3 -m apolo_emu --help

# Installation pour l'utilisateur (crée la commande apolo-emu)
pip install --user .
```

Debian ou Ubuntu : `apt install speech-dispatcher espeak-ng qemu-system-x86`.

NixOS : ces paquets suffisent, avec `python3`.

Apolo-emu fonctionne sans privilèges root.

## Utilisation

### Mode lanceur : Apolo-emu et QEMU ensemble

```bash
apolo-emu run --language fr -- qemu-system-i386 -m 64 -hda dos.img
```

Le lanceur :
1. crée une socket propre à l'instance ;
2. démarre l'émulateur ;
3. ajoute COM1 à la commande QEMU ;
4. lance QEMU, puis nettoie tout à la sortie.

Les autres options de QEMU sont conservées telles quelles. Le port est choisi avec `--com 2`. Le lanceur refuse
de démarrer si le port est déjà défini dans la commande. Tous les détails sont dans
[docs/lanceur-qemu.md](docs/lanceur-qemu.md).

### Mode autonome : l'émulateur seul

```bash
apolo-emu --listen /run/user/$UID/apollo.sock
qemu-system-i386 … -chardev socket,id=apollo,path=/run/user/$UID/apollo.sock,reconnect-ms=1000 \
                   -serial chardev:apollo
```

Si QEMU est déjà configuré en serveur (`server=on`), on utilise la connexion inverse :

```bash
apolo-emu --connect /chemin/vers/com1.sock
```

### Réglages selon le logiciel invité

| Invité | Options suggérées |
|---|---|
| Sonolect 7.11 (DOS) | `--language fr --codepage cp850` ; ajouter `--extension burst-interrupt` pour retrouver l'interruption à la frappe de la passerelle `pc486` |
| Épaulard (Windows 3.11) | `--language fr --codepage cp850 --extension epaulard-index` |
| IBM Screen Reader/2 (OS/2) | `--language en --extension lenient-speed` (le profil IBM envoie `@wb` et `@wf`) |
| Speakup (Linux) | aucune |

Les extensions sont désactivées par défaut. Elles sont décrites dans [docs/extensions.md](docs/extensions.md) et
listées par `apolo-emu --list-extensions`.

### Options utiles

| Option | Rôle |
|---|---|
| `--backend simulated` | sans son : la durée de parole est simulée, ce qui permet d'essayer sans Speech Dispatcher |
| `--backend null` | sans son : chaque énoncé est déclaré fini aussitôt |
| `--module espeak-ng`, `--voice NOM` | choix du module et de la voix de Speech Dispatcher |
| `--rate-offset`, `--pitch-offset`, `--volume-offset`, `--no-volume` | ajustement de la correspondance des réglages |
| `--trace FICHIER` | journal horodaté de chaque octet reçu (RX) et émis (TX) |
| `--log-level debug` | détail de l'analyse et des événements vocaux |

## Documentation

| Document | Contenu |
|---|---|
| [docs/protocole.md](docs/protocole.md) | protocole Apollo II, avec la source et le degré de certitude de chaque point |
| [docs/compatibilite.md](docs/compatibilite.md) | matrice de compatibilité des commandes |
| [docs/architecture.md](docs/architecture.md) | modules, interfaces, modèle de synchronisation |
| [docs/transport-serie.md](docs/transport-serie.md) | ce qui relève de QEMU, de la socket et de l'Apollo ; contrôle de flux |
| [docs/backend-vocal.md](docs/backend-vocal.md) | traduction des réglages, marques SSML, Speech Dispatcher |
| [docs/lanceur-qemu.md](docs/lanceur-qemu.md) | lanceur, et intégration à des commandes QEMU existantes |
| [docs/extensions.md](docs/extensions.md) | extensions non authentiques, désactivées par défaut |
| [docs/limitations.md](docs/limitations.md) | limitations connues |
| [docs/references.md](docs/references.md) | sources consultées |
| [docs/bilan.md](docs/bilan.md) | compte rendu du développement |

## Tests

```bash
python3 -m unittest discover -s tests -t .                       # suite complète (QEMU inclus s'il est présent)
APOLO_EMU_SKIP_QEMU=1 python3 -m unittest discover -s tests -t .  # sans QEMU
APOLO_EMU_SPEECHD=1 python3 -m unittest tests.test_speechd_integration   # parole réelle, volume très bas
```

La suite n'a besoin ni d'OS/2 ni de Windows :
- un faux backend vocal pilote la progression de la parole ;
- un faux QEMU teste le lanceur ;
- un secteur d'amorçage de 512 octets, assemblé par les tests, sert de VM de test sous un vrai QEMU.
