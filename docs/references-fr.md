[English](references.md) | Français

# Références

Ces documents ont été lus pour concevoir Apolo-emu. Les comportements repris sont
attribués à leur source dans [protocole-fr.md](protocole-fr.md). L'implémentation vise à
reproduire l'interface observable de l'appareil, sans embarquer son firmware.
La consultation d'une décompilation est explicitement déclarée ; elle ne permet
pas de revendiquer une conception en salle blanche. La proximité initiale de la
conversion numérique avec cette source et sa reformulation sont décrites dans
[publication-fr.md](publication-fr.md).

Les chemins `../os2` et `../pc486` ci-dessous sont des indications de provenance
dans l'environnement de développement. Ces projets ne sont pas fournis et ne
sont nécessaires ni à l'installation ni aux tests automatisés d'Apolo-emu.

## Documentation Dolphin (sources primaires)

| Document | Date | Emplacement consulté |
|---|---|---|
| *Brief guide to the Apollo speech synthesiser* (APOLLO.TXT), Release 1 | février 1989 (fichier de 1992) | `../os2/media/screen-reader/apollo-source/APOLLO.TXT`, venant de `ZIP.zip` → `APOLLO.ZIP` (Internet Archive, item « IBMScreenReader ») |
| *Technical Bulletin 25 — Pre-Release Information for the Apollo II* (APOLLO2.TXT) | 4 février 1993 | même archive |
| *Dolphin Speech Synthesizer User Guide — Series 2 Synthesizers* (Apollo 2, PC 2, Juno), ROM 2A et suivantes | 1998 | http://www.perkristian.net/misc/On-line_Series_2_Speech_Synthesizer_manual.htm ; https://archive.org/details/DolphinApollo2Manual |

Aucune licence n'est indiquée pour ces documents. Ils ne sont pas copiés dans ce dépôt.

## Firmware

- **Dolphin-Apollo-II-Reborn** : décompilation de la ROM UK V2.01 4.04 (processeur Mitsubishi 740), faite avec
  l'aide d'un LLM et validée trame par trame contre la ROM.
  - https://github.com/rommix0/Dolphin-Apollo-II-Reborn, commit `4bd78b4e2cb59bab9977adfc03939e9cddd5b78b`.
  - Fichiers consultés : `src/firmware/ser.c`, `boot_input.c`, `cmd_scan.c`, `cmd_match.c`, `cmd_imm.c`,
    `cmd_reply.c`, `cmd_set.c`, `tn_convert.c`, `par_play.c`, `boot.c`, `data/cmd_data.c`, ainsi que
    `ghidra740/annotations/command.txt`.
  - C'est une source secondaire, sans licence déclarée : on n'en a repris que des faits.

## Pilotes et logiciels

- **Linux Speakup**, `drivers/accessibility/speakup/speakup_apollo.c` (Kirk Reiser, David Borowski ; v2.21),
  `synth.c`, `spk_ttyio.c`, ancien `serialio.c`, et `speakup_dectlk.c` pour comparaison.
  - https://github.com/torvalds/linux, branche master au 25 octobre 2026. Dernier commit sur speakup :
    `97a551fa49682a33cc2fb6c5699a9175663803cf`. Dernier commit sur speakup_apollo.c :
    `5e3e27f040ec3611db14a5efe23c9108831c38be`.
  - Versions 2.6.37, 4.4 et 4.19 consultées pour l'historique.
- **emacspeak-ss 1.12.1** (James R. Van Zandt) : `apollo.in`, `ping-apollo.c`, `README.apollo`, `ChangeLog`.
  - https://deb.debian.org/debian/pool/main/e/emacspeak-ss/
  - Message du 12 janvier 1999 sur le contrôle de flux :
    https://www.cs.vassar.edu/~priestdo/emacspeak/list.archive.1999/msg00009.html
- **IBM Screen Reader/2 2.01** : profils `APOLLO2.TTS` et `APOLLO.TTS`, décodés par comparaison avec le profil
  DECtalk ; « Synthesizers Supported by Screen Reader.txt » ; message ERR0021.
  - Fichiers dans `../os2/media/screen-reader/extracted/SRD22/`.
- **Sonolect 7.11** : séquences émises, d'après le désassemblage et les journaux du projet `pc486`
  (`../pc486/docs/protocole-apollo.md`, `../pc486/logs/`).
- **Épaulard** : `../pc486/epaulard/src/epaulard.c` (fonctions `say_mark`, `sa_*`, `com_read`).

## Prototypes et études voisines

- `../pc486/gateway/apollo2spd.py` et `../os2/gateway/apollo2spd.py` : passerelles prototypes, sans licence
  déclarée.
- `../os2/docs/REPRISE.md` et `../os2/tools/qemu-serial-loopback-msr.patch` : investigation du MSR en mode
  boucle sous QEMU.

## Vérifications faites sur l'hôte

- Marques SSML et événements `INDEX_MARKS` avec Speech Dispatcher 0.12.1 et espeak-ng, le 25 octobre 2026.
- Comportement des options série de QEMU 10.2.4 :
  - deux UART au même emplacement sans erreur ;
  - `-serial none` consomme un numéro ;
  - effet de `reconnect-ms` ;
  - MSR = 0xB0 avec un chardev socket.
