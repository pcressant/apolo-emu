# Transport série et contrôle de flux

Trois couches sont en jeu. Elles ne doivent pas être confondues.

| Couche | Qui | Ce qu'elle fait |
|---|---|---|
| UART 16550 vue par l'invité | QEMU (`hw/char/serial.c`) | registres, FIFO, interruptions, lignes modem (MCR, MSR) |
| Lien entre QEMU et l'émulateur | chardev `socket` de QEMU et socket Unix | un flux d'octets dans chaque sens, **et rien d'autre** |
| Périphérique | Apolo-emu | le protocole Apollo II |

## Ce qu'une socket ne transporte pas

- **De l'invité vers l'émulateur.** RTS et DTR, positionnés par l'invité dans le MCR, ne sortent pas de QEMU :
  le chardev socket ne connaît pas les lignes modem.
- **De l'émulateur vers l'invité.** L'émulateur ne peut pas agir sur CTS, DSR, DCD ou RI. QEMU interroge le
  chardev (`CHR_IOCTL_SERIAL_GET_TIOCM`) ; une socket ne répond pas ; l'UART garde alors le MSR de sa
  réinitialisation, avec **DCD, DSR et CTS actifs en permanence**.
  - **Mesuré** : le secteur d'amorçage de test lit **MSR = 0xB0** sur COM1 sous QEMU 10.2.4 avec
    `-chardev socket` (`tests/test_qemu_integration.py`).
- **Pas de cadence.** QEMU n'impose pas le débit en bauds aux octets émis par l'invité. Il ne lit la socket que
  lorsqu'il reste de la place dans la FIFO de réception.

## Conséquences pour l'émulation

L'Apollo II utilise une poignée de main RTS/CTS à l'alternat (TB25 §5.1, manuel de 1998, annexe 6) :
- l'appareil baisse CTS pendant le traitement de chaque octet ;
- le PC baisse RTS pour lire ;
- l'appareil répond NAK s'il n'a rien à envoyer.

**Rien de cela n'est émulé, et rien ne peut l'être au travers d'une socket :**

- L'invité voit CTS actif : il émet sans jamais attendre. Le pilote de COM d'OS/2, qui exige CTS et DSR, est
  satisfait.
- Apolo-emu accepte tous les octets. Il ne peut pas freiner l'invité.
  - Un véritable Apollo II perdrait des données si l'invité envoyait plus vite que la parole ne consomme : il
    n'a pas de signal « tampon plein ».
  - Apolo-emu signale ce cas dans le journal (environ 6 Ko en attente, l'anneau d'entrée de la ROM 2.01), mais
    ne jette rien.
- Les réponses (échos, index, interrogations) sont écrites sur la socket dès qu'elles sont produites. Elles
  arrivent dans la FIFO de réception de l'invité, quel que soit l'état de RTS.
- Le NAK renvoyé lors d'une lecture à vide suppose de connaître RTS : il n'est pas émulé.
- Speakup envoie une impulsion RTS quand le tty est plein : elle n'a aucun effet ici, et n'en a pas besoin.

## Le correctif QEMU du projet `os2`

`../os2/tools/qemu-serial-loopback-msr.patch` corrige un défaut de **l'UART émulée**, indépendant de tout
périphérique :
- QEMU ne posait pas les bits delta du MSR (DCTS, DDSR, DDCD, TERI) au passage en mode boucle (MCR.LOOP) ou à
  la sortie de ce mode ;
- il ne levait pas non plus l'interruption d'état modem correspondante ;
- le pilote COM.SYS d'OS/2 détecte CTS et DSR de cette façon ; sans le correctif, Screen Reader/2 signale
  « The synthesizer did not respond ».

Ce comportement relève **entièrement de QEMU**. Apolo-emu ne peut ni le provoquer ni le corriger, et ne modifie
pas QEMU. Avec un QEMU non corrigé, le problème se pose pareillement, quel que soit le programme branché sur la
socket.

## Modes de connexion

| Mode | Apolo-emu | QEMU |
|---|---|---|
| Écoute (défaut du lanceur) | `--listen CHEMIN` | `-chardev socket,id=X,path=CHEMIN[,reconnect-ms=1000]` (client) |
| Connexion | `--connect CHEMIN` | `-chardev socket,id=X,path=CHEMIN,server=on,wait=off` (serveur) |

- Une seule connexion à la fois, comme un câble. En mode écoute, une seconde connexion est refusée.
- L'appareil garde son état d'une connexion à l'autre : débrancher le câble n'éteint pas un Apollo.
- Une réponse produite pendant que rien n'est connecté est perdue, et le journal le signale.
- **Socket obsolète** (mode écoute) : si le chemin est une socket sur laquelle plus personne n'écoute, elle est
  supprimée. Un chemin utilisé par un autre processus, ou qui n'est pas une socket, est refusé.
- La socket est créée avec des droits réservés à l'utilisateur.
- **Reconnexion** :
  - en mode connexion, Apolo-emu réessaie chaque seconde ;
  - en mode écoute, c'est QEMU qui se reconnecte, s'il a l'option `reconnect-ms`.
