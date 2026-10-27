[English](README.md) | Français

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

Projet indépendant, sans affiliation à Dolphin ou IBM. Le code et la documentation
propres au projet sont sous [licence MIT](LICENSE) ; voir les
[informations de provenance](NOTICE-fr.md). Aucune ROM ni aucun logiciel invité propriétaire
n'est fourni.

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

### Arch Linux

Depuis le répertoire complet du projet :

```bash
sudo pacman -S --needed base-devel
makepkg -si
# Pour la parole (dépendances optionnelles du paquet) :
sudo pacman -S --needed speech-dispatcher espeak-ng
```

Le [PKGBUILD](PKGBUILD) construit la copie locale actuelle, y compris les changements
non commités ; il ne télécharge aucune source et ne convient ni seul ni à un dépôt AUR.
`makepkg -s` installe les dépendances de construction et de test, dont `qemu-system-x86`
pour la VM de test indépendante. Les tests ne produisent pas de parole et n'utilisent
pas vos VM existantes. QEMU est optionnel à l'exécution pour une connexion à une socket
série déjà configurée. Les deux langues de documentation sont installées dans
`/usr/share/doc/apolo-emu/`.

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
[docs/lanceur-qemu-fr.md](docs/lanceur-qemu-fr.md).

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
| Sonolect 7.11 (DOS) | `--language fr --codepage cp850 --extension burst-interrupt` (interruption de la parole à la frappe) |
| Épaulard (Windows 3.11) | `--language fr --codepage cp850` avec une version envoyant l'écho authentique `@E` ; voir ci-dessous |
| IBM Screen Reader/2 (OS/2) | `--language en --extension lenient-speed` (le profil IBM envoie `@wb` et `@wf`) ; intégration décrite dans [le guide du lanceur](docs/lanceur-qemu-fr.md) |
| Speakup (Linux) | aucune |

Les extensions sont désactivées par défaut. Elles sont décrites dans [docs/extensions-fr.md](docs/extensions-fr.md) et
listées par `apolo-emu --list-extensions`.

L'essai d'Épaulard mentionné dans le bilan utilisait une version modifiée pour envoyer
`texte<CR>@E<c><CR>`. Une version utilisant l'ancien `@I<c>` nécessite l'extension
`epaulard-index` ; consulter [sa description](docs/extensions-fr.md) avant de l'activer.

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
| [docs/protocole-fr.md](docs/protocole-fr.md) | protocole Apollo II, avec la source et le degré de certitude de chaque point |
| [docs/compatibilite-fr.md](docs/compatibilite-fr.md) | matrice de compatibilité des commandes |
| [docs/architecture-fr.md](docs/architecture-fr.md) | modules, interfaces, modèle de synchronisation |
| [docs/transport-serie-fr.md](docs/transport-serie-fr.md) | ce qui relève de QEMU, de la socket et de l'Apollo ; contrôle de flux |
| [docs/backend-vocal-fr.md](docs/backend-vocal-fr.md) | traduction des réglages, marques SSML, Speech Dispatcher |
| [docs/lanceur-qemu-fr.md](docs/lanceur-qemu-fr.md) | lanceur, et intégration à des commandes QEMU existantes |
| [docs/extensions-fr.md](docs/extensions-fr.md) | extensions non authentiques, désactivées par défaut |
| [docs/limitations-fr.md](docs/limitations-fr.md) | limitations connues |
| [docs/references-fr.md](docs/references-fr.md) | sources consultées |
| [docs/publication-fr.md](docs/publication-fr.md) | vérifications de provenance et de l'historique avant publication |
| [docs/bilan-fr.md](docs/bilan-fr.md) | compte rendu du développement |

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
