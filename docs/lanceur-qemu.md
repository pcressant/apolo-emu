# Lanceur QEMU

```bash
apolo-emu run [options Apolo-emu] -- qemu-system-i386 [options QEMU]
```

## Déroulement

1. **Répertoire d'instance.**
   - Il est créé dans `$XDG_RUNTIME_DIR`, ou dans `--socket-dir` : `apolo-emu-XXXXXXXX/`, droits 0700, avec un
     fichier `pid` et la socket `com.sock`.
   - Avant de le créer, le lanceur supprime les répertoires `apolo-emu-*` **abandonnés**. Ce sont ceux qui
     appartiennent à l'utilisateur, dont le processus a disparu et qui ne contiennent que `pid` et `com.sock`.
   - Il ne touche à rien d'autre.
2. **L'émulateur démarre et écoute.** En cas d'échec, QEMU n'est pas lancé (code 2).
3. **La commande QEMU est complétée.** Les options de l'utilisateur ne sont pas modifiées ; on ajoute à la fin :
   ```text
   -chardev socket,id=apolo-emu-<pid>,path=<répertoire>/com.sock
   -device isa-serial,chardev=apolo-emu-<pid>,index=<N-1>
   ```
   `--com N` (1 à 4, par défaut 1) choisit le port ; `index` fixe l'adresse et l'IRQ standard de COMN.
4. **QEMU est lancé** dans le même groupe de processus. Il garde le terminal : console, moniteur et Ctrl-C se
   comportent comme d'habitude.
5. **À la sortie de QEMU**, le lanceur ferme l'émulateur et la connexion SSIP, supprime la socket et le
   répertoire, puis rend le code de retour de QEMU.

## Conflits de ports

Le lanceur lit la commande QEMU et refuse de démarrer (code 2) si le port demandé est déjà défini.

**Vérifié sur QEMU 10.2.4** : QEMU n'empêche pas de créer deux UART au même emplacement. Avec `-serial null` et
`-device isa-serial,index=0`, deux UART se retrouvent à l'adresse 0x3F8. Le lanceur fait donc la vérification
lui-même.

| Dans la commande | Effet |
|---|---|
| `-serial X` | occupe le port suivant : le premier `-serial` donne COM1, le deuxième COM2… |
| `-serial none` | consomme un numéro **sans** créer de port (vérifié : `-serial none -serial null` place `null` sur COM2) |
| `-device isa-serial,index=K` | occupe COM(K+1) |
| `-device isa-serial` sans `index` | QEMU choisit ; le lanceur avertit |
| `-chardev …,id=apolo-emu-<pid>` | refusé (identifiant déjà pris) |
| `-readconfig` | non analysé ; le lanceur avertit |
| `-nographic` sans `-serial` | avertissement : ajouter `-device isa-serial` empêche QEMU de créer sa console série par défaut sur COM1 ; ajouter `-serial mon:stdio` et utiliser `--com 2` |

## Signaux et arrêt

| Événement | Comportement |
|---|---|
| Ctrl-C au terminal | QEMU le reçoit directement, puisqu'il est dans le même groupe, et s'arrête comme d'habitude ; le lanceur attend sa fin, puis nettoie |
| SIGTERM, SIGHUP, SIGINT ou SIGQUIT envoyé au lanceur | transmis à QEMU, avec `--on-signal forward`, le défaut |
| idem, avec `--on-signal wait` | non transmis : le lanceur l'indique dans le journal et attend que QEMU s'arrête, après un arrêt propre du système invité |
| erreur de l'émulateur pendant l'exécution | journalisée ; **la VM continue**, sans parole, et n'est jamais arrêtée par le lanceur |

Le lanceur n'envoie jamais SIGKILL, et n'agit sur aucun autre processus que le QEMU qu'il a lancé.

Les systèmes de cette époque (DOS, Windows 3.11, OS/2 Warp 4) ne gèrent pas l'arrêt ACPI. `--on-signal wait`
évite qu'un signal reçu par erreur coupe la VM, et donc le disque, en pleine écriture.

## Codes de retour

| Code | Cas |
|---|---|
| code de QEMU | fin normale |
| 128 + n | QEMU tué par le signal n |
| 2 | erreur d'utilisation, conflit de port, émulateur impossible à démarrer |
| 126 / 127 | QEMU non exécutable / introuvable |

## Plusieurs instances

Chaque lancement a son propre répertoire, sa propre socket et son propre identifiant de chardev. Plusieurs VM
peuvent tourner en même temps, chacune avec son Apollo II virtuel (vérifié par `tests/test_launcher.py`). Elles
partagent le même Speech Dispatcher, et donc la même sortie audio.

## Intégrer Apolo-emu à une commande QEMU existante

### Sans le lanceur, Apolo-emu en écoute

```bash
apolo-emu --listen "$XDG_RUNTIME_DIR/apollo.sock" --language fr &
qemu-system-i386 … \
  -chardev socket,id=apollo,path="$XDG_RUNTIME_DIR/apollo.sock",reconnect-ms=1000 \
  -serial chardev:apollo
```

- Avec `reconnect-ms`, QEMU démarre même si l'émulateur n'est pas encore prêt, et se reconnecte si on le
  redémarre.
- `-serial chardev:apollo` prend le numéro suivant dans l'ordre des `-serial` : COM1 s'il est le premier. Pour
  un port précis, utiliser `-device isa-serial,chardev=apollo,index=0`.
- Comportement vérifié sur QEMU 10.2.4 : sans `reconnect-ms`, une socket absente fait échouer QEMU (code 1) ;
  avec, QEMU démarre et attend.

### QEMU déjà configuré en serveur

C'est le cas des projets `pc486` et `os2` :

```text
-chardev socket,id=com1,path=$RUN/com1.sock,server=on,wait=off -serial chardev:com1
```

Apolo-emu s'y connecte :

```bash
apolo-emu --connect /chemin/vers/run/com1.sock --language fr --codepage cp850 --extension epaulard-index
```

- Le chardev serveur de QEMU n'accepte qu'un client à la fois. Il faut donc que la passerelle du projet ne soit
  pas connectée à ce moment-là. Arrêter cette passerelle reste une décision de l'utilisateur.
- Avec `wait=off`, les octets que l'invité émet quand aucun client n'est connecté sont perdus.
- **Rien n'est à modifier dans ces projets** pour essayer Apolo-emu.

### Exemples complets

```bash
# DOS + Sonolect, COM1, français
apolo-emu run --language fr --codepage cp850 --extension burst-interrupt -- \
  qemu-system-i386 -machine pc -m 16 -hda dos.img

# OS/2 + Screen Reader/2 : console série du moniteur sur COM1, Apollo sur COM2
apolo-emu run --com 2 --language en --extension lenient-speed -- \
  qemu-system-i386 -m 64 -hda os2.img -serial mon:stdio
```

Avec le second exemple, Screen Reader/2 doit être configuré sur COM2. Le correctif QEMU du projet `os2` reste
nécessaire pour que COM.SYS détecte CTS et DSR (voir [transport-serie.md](transport-serie.md)).
