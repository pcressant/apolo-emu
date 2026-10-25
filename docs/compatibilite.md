# Matrice de compatibilité

Aucun véritable Apollo II n'a pu être utilisé. « Vérifiée » signifie donc :
- au moins deux sources indépendantes concordent sur le comportement ([protocole.md](protocole.md)) ;
- l'implémentation est couverte par un test automatique.

**États** :

| État | Signification |
|---|---|
| VÉRIFIÉE | implémentée et vérifiée, au sens ci-dessus |
| NON VÉRIFIÉE | implémentée, mais non vérifiée sur un véritable Apollo II : une seule source, ou déduction |
| PARTIELLE | partiellement émulée |
| NON IMPLÉMENTÉE | non implémentée |
| INCONNUE | inconnue ou insuffisamment documentée |

**Sources** :

| Code | Source |
|---|---|
| DOC | documentation Dolphin |
| ROM | décompilation de la ROM 2.01 |
| PIL | pilotes et logiciels d'époque |

## Liaison et flux

| Élément | État | Sources | Remarques |
|---|---|---|---|
| Ctrl-X, Ctrl-A : mute | VÉRIFIÉE | DOC, ROM, PIL | vide les tampons, arrête la parole, compteur d'index conservé ; agit aussi au milieu d'une séquence `@` |
| CR : fin de proposition | VÉRIFIÉE | DOC, ROM, PIL | |
| `. , : ; ! ?` : fin de proposition | VÉRIFIÉE | DOC (TB25), ROM | |
| Limites de 220 et 250 octets, report du `@` | NON VÉRIFIÉE | ROM | |
| Texte sans CR ni ponctuation | VÉRIFIÉE | DOC, ROM | reste en attente, comme sur l'appareil ; les prototypes le disaient après 0,3 s |
| Lecture séquentielle, effets au début de chaque proposition | NON VÉRIFIÉE | DOC (TB25 §6.2), ROM | déduction ; voir protocole.md §2.3 |
| Codes de contrôle traités comme des espaces | NON VÉRIFIÉE | ROM | |
| Page de codes | PARTIELLE | ROM, PIL | CP437 par défaut, réglable ; la table de la ROM n'est reprise que pour l'ASCII |
| RTS/CTS à l'alternat, chute de CTS après chaque octet | NON IMPLÉMENTÉE | DOC | impossible au travers d'une socket ; l'UART de QEMU voit CTS actif (MSR = 0xB0, mesuré) |
| NAK (0x15) sur lecture à vide | NON IMPLÉMENTÉE | DOC, ROM | suppose la connaissance de RTS |
| Débordement du tampon d'entrée | PARTIELLE | DOC, ROM | signalé dans le journal, sans perte de données |
| Liaison parallèle, carte PC 2, protocole NULL/SOH/ACK | NON IMPLÉMENTÉE | DOC | hors sujet (port série seulement) |
| Son ou bip à la mise sous tension, auto-test | NON IMPLÉMENTÉE | DOC | |

## Commandes

| Commande | Analyse | Rendu | Sources | Remarques |
|---|---|---|---|---|
| `@I?` | VÉRIFIÉE | — | DOC, ROM, PIL | réponse immédiate `I` + 2 chiffres hexa, quartet bas d'abord + `T`/`M` |
| `T`/`M` pendant la réception d'un texte sans ponctuation | INCONNUE | — | DOC ≠ ROM | `--talking-rule doc` (défaut) ou `rom` |
| `@I+` | VÉRIFIÉE | — | DOC, ROM, PIL | compté à la réception, décompté par une marque SSML quand la parole l'atteint ; remis à zéro au premier `@I+` après un mute |
| `@Ec` | VÉRIFIÉE | — | DOC, ROM, PIL | octet renvoyé brut ; un écho d'une proposition effacée est perdu |
| moment de l'écho `@E` | NON VÉRIFIÉE | — | DOC, ROM | au début de la proposition qui le contient ; `--extension word-echo` donne la position exacte |
| `@c?` | VÉRIFIÉE | — | DOC, ROM | lettres `A B C D F H K M P Q R S V W X Z = $` ; exemple du manuel `A60` retrouvé |
| `@C?` (batterie du Juno) | NON VÉRIFIÉE | — | DOC, ROM | renvoie 0 : pas de défaut d'auto-test |
| `@Z?` (interrupteurs) | NON VÉRIFIÉE | — | ROM | renvoie 0 |
| `@L` | PARTIELLE | — | DOC, ROM | format exact ; contenu des enregistrements approximé (indicatif, versions configurables, emplacements vides à `0`) |
| `@?` | PARTIELLE | PARTIELLE | DOC, ROM | dit un texte réglable (`--version-text`), et non les versions réelles |
| `@Wd` | VÉRIFIÉE | PARTIELLE | DOC, ROM, PIL | 1-9 ; `@W0` et `@Wb` rejetés, comme par la ROM ; débit approximé |
| `@Fh` | VÉRIFIÉE | PARTIELLE | DOC, ROM | hauteur approximée |
| `@F+`, `@F-` | NON VÉRIFIÉE | PARTIELLE | DOC, ROM | décalage léger, non cumulatif (ROM) |
| `@Ah` | VÉRIFIÉE | PARTIELLE | DOC, ROM | synchronisé avec la parole (coupe le message) ; l'homonyme `@A` de l'Apollo I n'est pas émulé |
| `@Vd` | VÉRIFIÉE | PARTIELLE | DOC, ROM | type de voix SSIP ; les réglages propres à chaque voix préréglée sont inconnus |
| `@V0` | VÉRIFIÉE | VÉRIFIÉE | DOC, ROM | plus rien n'est dit ; échos et index continuent |
| `@Pb` | VÉRIFIÉE | PARTIELLE | DOC, ROM | `PUNCTUATION all` ou `none` ; les noms dits sont ceux du moteur |
| `@Sb` | VÉRIFIÉE | PARTIELLE | DOC, ROM | `SPELLING` ; l'épellation automatique de la ROM (mot sans voyelle) n'est pas reproduite |
| `@=d,` | VÉRIFIÉE | PARTIELLE | DOC, ROM | change la langue de l'emplacement (`--languages`) ; un emplacement vide est ignoré ; changement de ROM sans réinitialisation |
| `@Kb` | VÉRIFIÉE | PARTIELLE | DOC, ROM | intervient dans le type de voix |
| `@Ro`, `@R` lettre + hexa | NON VÉRIFIÉE | NON IMPLÉMENTÉE | DOC, ROM | mémorisé, interrogeable, sans effet audible |
| `@Qd`, `@Dh` | VÉRIFIÉE | NON IMPLÉMENTÉE | DOC, ROM | mémorisés, interrogeables ; pauses non rendues |
| `@Bd` | VÉRIFIÉE | NON IMPLÉMENTÉE | DOC, ROM | synchronisé avec la parole ; mémorisé |
| `@Mhh`, `@$o`, `@u d hh±` | NON VÉRIFIÉE | NON IMPLÉMENTÉE | DOC, ROM | mémorisés ; la forme `@u` à un chiffre est reconnue sans effet (ROM) ; défaut de `@M` : 14 hexa (ROM), 16 (manuel) |
| `@Hb` | VÉRIFIÉE | NON IMPLÉMENTÉE | DOC, ROM | hypermode non émulé |
| `@Xb` | VÉRIFIÉE | NON IMPLÉMENTÉE | DOC, ROM | mode phonétique non émulé : le texte est lu tel quel |
| Phonèmes `_K_AE_T` dans le texte | NON IMPLÉMENTÉE | NON IMPLÉMENTÉE | DOC | lus comme du texte |
| `@Th` | VÉRIFIÉE | PARTIELLE | DOC, ROM | effets sonores remplacés par des silences de 60 à 500 ms |
| `@Tx` | NON VÉRIFIÉE | VÉRIFIÉE | DOC, ROM | silence de 100 ms |
| `@J` | NON VÉRIFIÉE | — | DOC | réinitialisation douce, documentée en 1998, absente de la ROM 2.01 |
| `@Gb`, `@+c`, `@I^` | VÉRIFIÉE | — | DOC, ROM | reconnus, sans effet (ROM 2) |
| `@Y m r p b` | NON IMPLÉMENTÉE | — | DOC | changement de débit série : sans objet sur une socket ; reste du texte, comme sur la ROM 2.01 |
| commande non reconnue (`@wb`, `@IA`, `@@44-`…) | VÉRIFIÉE | NON VÉRIFIÉE | ROM | reste dans le texte, comme sur l'appareil ; le `@` est rendu muet sans `@P1` |
| `@!c` (Apollo I) | NON IMPLÉMENTÉE | — | DOC | caractère d'échappement : sans effet sur l'Apollo II (`@+c` ignoré) |
| `@@dh±` (Apollo I) | NON IMPLÉMENTÉE | — | DOC | remplacé par `@u` sur l'Apollo II |
| `@T` autotest, `@A` pas d'amplitude, `@Vb` parole marche/arrêt (Apollo I) | NON IMPLÉMENTÉE | — | DOC | homonymes : seul le sens Apollo II est émulé |
