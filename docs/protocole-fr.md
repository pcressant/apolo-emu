[English](protocol.md) | Français

# Protocole Apollo II — état des connaissances

Ce document rassemble ce que l'on sait du protocole Apollo II. Il a été établi en phase 1 et sert de référence à
l'implémentation. Il précise d'où vient chaque information et quel crédit on peut lui accorder. Les sources sont décrites dans
[references-fr.md](references-fr.md).

## Niveaux de confiance

Chaque affirmation est marquée par un niveau :

| Code | Signification |
|---|---|
| **[DOC]** | Confirmé par la documentation historique de Dolphin : APOLLO.TXT (1989/1992), Technical Bulletin 25 (APOLLO2.TXT, 1993), *Series 2 Synthesizers User Guide* (1998). |
| **[ROM]** | Observé dans la décompilation du firmware UK V2.01 4.04 (projet *Dolphin-Apollo-II-Reborn*). Source secondaire, faite avec l'aide d'un LLM, mais validée contre la ROM trame par trame. Elle décrit une seule version de ROM. |
| **[PIL]** | Observé dans un pilote existant : Speakup, emacspeak-ss, profil Screen Reader/2, Sonolect, prototypes `pc486` et `os2`. |
| **[DED]** | Déduit par analyse ou par recoupement. |
| **[APP]** | Approximation nécessaire dans l'émulateur. |
| **[INC]** | Inconnu ou insuffisamment documenté. |

## 1. Liaison série

- Le format par défaut est 9600 bauds, 8 bits, sans parité, 1 bit d'arrêt [DOC] [PIL] (Speakup, emacspeak, IBM, Épaulard).
- **Apollo I.** La vitesse se règle par cavaliers : 300, 1200, 9600 ou 19200 bauds [DOC].
- **Apollo II.** La vitesse se règle aussi par logiciel, avec `@Y` : 300 à 57600 bauds, parité, 7 ou 8 bits, puis 5 octets de synchronisation [DOC, manuel 1998]. `@Y` est absent de la table de commandes de la ROM 2.01 [ROM].
- **Poignée de main RTS/CTS dans les deux sens, à l'alternat** [DOC, TB25 §5.1 et manuel, annexe 6] :
  - Le PC est maître de la liaison.
  - **Pour émettre**, le PC lève RTS et attend CTS. L'Apollo baisse CTS brièvement après chaque octet reçu.
  - **Pour lire**, le PC baisse RTS. L'Apollo lève CTS pendant qu'il émet, puis le rebaisse. S'il n'a rien à envoyer, il répond NAK (0x15) [DOC 1998] [ROM].
  - DSR n'apparaît dans aucun protocole décrit. Il figure seulement dans le brochage du manuel de 1998 [DOC].
  - Le sens réel des niveaux est douteux : James Van Zandt estime que « raise » signifie « assert » [PIL emacspeak] [INC].
- Le firmware n'a pas de signal « tampon plein ». Le busy (CTS) n'est actif que pendant le traitement d'un octet, et l'anneau d'entrée n'a aucun test de débordement [ROM].
  - Pour l'Apollo I, APOLLO.TXT indique un tampon de 8 Ko : au-delà, des données sont perdues [DOC].
  - L'anneau de la ROM 2.01 occupe environ 6 Ko ($2100-$38FF) [ROM].
- **Speakup** :
  - il force CRTSCTS et ne lit jamais la ligne ;
  - quand le tty est plein, il envoie une impulsion RTS puis attend 40 s [PIL].
- **Sonolect et Épaulard** n'utilisent pas le contrôle de flux matériel [PIL].
- **Screen Reader/2** exige CTS et DSR en sortie : le pilote COM.SYS d'OS/2 attend ces lignes [PIL os2].

### Ce que fait QEMU (chardev socket)

- Une socket Unix ne transporte que des octets. QEMU ne transmet pas au périphérique les lignes RTS et DTR de l'invité, et ne laisse pas le périphérique piloter CTS, DSR ou DCD.
- Faute de `TIOCMGET`, l'UART émulée garde son MSR de réinitialisation : DCD, DSR et CTS sont actifs en permanence [PIL os2] [DED, analyse de `hw/char/serial.c`].
- QEMU ne cadence pas les octets au débit en bauds. Il ne lit la socket que s'il reste de la place dans la FIFO de réception [DED].
- Le correctif QEMU du projet `os2` (`tools/qemu-serial-loopback-msr.patch`) répare un défaut de l'UART : QEMU ne posait pas les bits delta du MSR au passage en mode boucle (MCR.LOOP), ni l'interruption MSI correspondante. Or COM.SYS en a besoin pour détecter CTS et DSR. **Cela relève de QEMU, pas de l'Apollo.**

**Conséquence pour Apolo-emu [APP] :**
- Le contrôle de flux matériel ne peut être ni émulé ni observé : CTS est vu actif en permanence.
- L'émulateur ne peut pas ralentir l'invité. Il accepte donc tout ce qui arrive, et peut seulement signaler qu'un véritable Apollo aurait débordé.
- Le NAK de lecture à vide n'a pas de sens sans RTS : il n'est pas émulé.

## 2. Deux étages de traitement

La conception d'Apolo-emu repose sur ce point.

### 2.1 Étage communication (à la réception de chaque octet)

Cet étage est confirmé par [DOC, TB25 §6.2.1] et détaillé par [ROM].

- **Ctrl-A (0x01) ou Ctrl-X (0x18) : mute.**
  - L'anneau d'entrée est vidé et la parole s'arrête immédiatement.
  - La proposition en cours est abandonnée.
  - Le caractère de commande redevient `@`.
  - Le compteur d'index est conservé, avec un drapeau « remise à zéro au prochain `@I+` » [DOC] [ROM].
  - Cela vaut même au milieu d'une séquence `@` [ROM].
  - Les réponses déjà mises dans l'anneau d'émission ne sont pas effacées [ROM].
- **`@` : passage en « mode commande immédiate ».**
  - Les octets suivants sont comparés, sans tenir compte de la casse, aux deux seuls motifs immédiats `I+` et `I?` [ROM]. TB25 cite aussi `@=n` comme commande immédiate [DOC], mais dans la ROM 2.01 `@=` est une commande différée [ROM].
  - `@I?` produit **tout de suite** la réponse `I` + compteur + `T` ou `M`, et ne laisse aucune trace dans le texte [DOC] [ROM].
  - `@I+` : le premier qui suit un mute remet le compteur à zéro. Ensuite, le compteur augmente de 1, et `@I+` est transmis au texte pour être compté à rebours pendant la parole [DOC] [ROM].
  - **Toute autre suite**, par exemple `@e`, `@W`, `@IA`, est recopiée telle quelle dans l'anneau d'entrée [ROM].
  - Un second `@` relance le mode commande : le premier `@` est perdu [ROM].
- **Tout autre octet** va dans l'anneau d'entrée [ROM].

### 2.2 Étage proposition (*clause*, ou « phrase » dans la documentation)

Cet étage est confirmé par [DOC] (APOLLO.TXT, TB25 §6.2) et détaillé par [ROM].

- **Ce qui termine une proposition** [ROM] :
  - CR, qui n'est pas conservé ;
  - l'un des signes `.` `,` `:` `;` `!` `?` ;
  - une longueur de 250 octets ;
  - à partir de 220 octets, une espace ou un `@`. Dans ce cas, le `@` est reporté au début de la proposition suivante.
  - Une espace finale est ajoutée à la proposition.
- La documentation dit qu'il faut un CR pour que l'appareil parle (APOLLO.TXT), ou qu'il « n'a pas encore reçu une virgule, un point… » (TB25) [DOC]. **Un texte sans CR ni ponctuation reste en attente indéfiniment** [DED].
- La lecture est **séquentielle** [ROM] : l'appareil analyse une proposition, la convertit, la prononce **jusqu'au bout**, puis passe à la suivante.
- **Les commandes `@` différées** sont reconnues à l'analyse de la proposition [ROM] :
  - Une table de motifs est appliquée au texte mis en majuscules, dans un ordre fixe : la première correspondance l'emporte.
  - `*` correspond à n'importe quel caractère, `#` à un chiffre.
  - Une commande reconnue est retirée du texte.
  - **Une commande non reconnue reste dans le texte**, `@` compris.
- **Moment d'exécution** [DOC TB25 §6.2.2] [ROM] :
  - La plupart des commandes s'exécutent quand la proposition est convertie, juste avant qu'elle soit prononcée. Une commande placée au milieu d'une proposition agit donc sur toute la proposition.
  - Font exception les commandes **synchronisées avec la parole** : `@A` (volume), `@B` (voisement), `@T` (effet sonore) et `@I+` (décompte).
  - TB25 range aussi `@V` et `@$` parmi les commandes synchronisées [DOC], mais la ROM 2.01 les applique à la conversion [ROM].

### 2.3 Écho `@E`

- `@Ec` renvoie l'octet `c` « quand il est traité, avant que la ligne soit prononcée ». Pour savoir quand un texte est fini, il faut envoyer `texte<CR>@Ex<CR>` [DOC APOLLO.TXT].
- Sur l'Apollo II, `@E` reste traité à l'étage proposition [DOC TB25 §6.2] [ROM].
- Puisque la lecture est séquentielle, **l'écho part quand la proposition qui le contient commence à être traitée**, c'est-à-dire juste après la fin de la parole de la proposition précédente [DED, à partir de ROM et DOC].
- L'argument est renvoyé brut, sans passage en majuscules [ROM].
- Un `@E` placé dans une proposition effacée par un mute n'est jamais renvoyé [ROM].
- Screen Reader/2 envoie `@e<TAB>` avant chaque mot, sans CR entre les mots, et la phrase se termine par `.` puis CR [PIL os2]. Sur un vrai Apollo II, **tous les échos d'une même proposition partent ensemble, au début de celle-ci** [DED].
- Les deux prototypes renvoient un écho par mot en coupant la parole en un message par mot. Ce n'est pas fidèle.
- On ne sait pas si SRD2 attend ces échos avant de continuer [INC].

### 2.4 Index `@I+` et `@I?`

Sources : [DOC TB25 §1, manuel 1998] et [ROM].

- **Compteur** : il tient sur un octet et compte les unités reçues mais pas encore prononcées. Il augmente à la réception d'un `@I+` et diminue quand la parole atteint la marque, sans descendre sous 0.
- **Réponse à `@I?`** : 4 octets, `I`, puis les 2 chiffres hexadécimaux du compteur, puis `T` ou `M`.
  - Les chiffres sont envoyés **quartet bas en premier** [ROM]. TB25 dit seulement « two ASCII characters » ; le manuel de 1998 précise l'ordre quartet bas, quartet haut pour `@c?`.
  - La casse des chiffres A-F n'est pas connue : majuscules supposées [INC].
- **Sens de `T` et `M`** :
  - D'après la documentation, l'appareil peut avoir du texte en tampon et répondre `M`, s'il n'a pas encore reçu de ponctuation [DOC].
  - D'après la ROM, une proposition en cours d'accumulation donne `T` [ROM].
  - **Contradiction [INC].** Apolo-emu suit la documentation : `T` signifie « parole en cours ou propositions complètes en attente ». Ce choix est réglable.
- Après un mute, le compteur est conservé, puis remis à zéro au premier `@I+` [DOC].

### 2.5 Interrogations

Sources : [DOC 1998] et [ROM].

- **`@c?`** donne une réponse de 3 octets : la lettre, puis la valeur en hexadécimal, quartet bas en premier.
  - Lettres valides : `A B C D F H K M P Q R S V W X Z = $`.
  - Une autre lettre ne donne aucune réponse [ROM].
  - Exemple du manuel : `@A?` donne `A60`, ce qui correspond au volume 6 à la mise sous tension [ROM]. **Deux sources indépendantes concordent.**
  - `@C?` donne l'état de la batterie du Juno. L'Apollo 2 n'a pas de batterie.
- **`@L`** renvoie la liste des langues : `L`, le nombre d'enregistrements (7) et leur taille (14) en hexadécimal quartet bas d'abord, soit `70E0`, puis 7 enregistrements de 14 octets, puis CR [DOC] [ROM]. Le contenu exact des emplacements vides est inconnu [INC].
- **`@?`** fait **dire** les numéros de version de la ROM : rien n'est renvoyé sur la ligne [DOC].

## 3. Commandes Apollo II

L'état d'implémentation est suivi dans [compatibilite-fr.md](compatibilite-fr.md). Ce tableau indique la syntaxe reconnue par la ROM 2.01, comparée à la documentation.

| Commande | Motif ROM | Effet | Défaut ROM | Sources, remarques |
|---|---|---|---|---|
| `@Wd` | `W#` | débit 1-9 (environ 80-580 mots/min) | 3 | DOC 1998 (APOLLO.TXT : `@Wh` hexadécimal, Apollo I). Speakup envoie 1-9 ; SRD2 envoie `@w0`…`@wf`, dont `0`, `b` et `f` sont rejetés par la ROM. |
| `@Fh`, `@F+`, `@F-` | `F*` | centre de hauteur 0-F ; `+` ou `-` fixent un léger décalage de hauteur, non cumulatif | 8 | DOC, ROM |
| `@Ah` | `A*` | volume 0-F, en proportion du bouton, synchronisé avec la parole | 6 | **Homonyme** : sur l'Apollo I, `@A` sans argument fait défiler les amplitudes [DOC]. Le manuel dit que la valeur normale est A, la ROM démarre à 6. |
| `@Ro` | `R#`, `R***` | prosodie 0-7, ou réglage d'un paramètre de prosodie (lettre + 2 chiffres hexadécimaux) | 3 | DOC, ROM |
| `@Sb` | `S#` | épellation | 0 | DOC |
| `@Pb` | `P#` | ponctuation dite | 0 | DOC |
| `@Qd` | `Q#` | pause entre les mots, 0-9 | 0 | DOC |
| `@Dh` | `D*` | pause de fin de proposition, 0-F | B | DOC 1998. APOLLO.TXT utilisait `@,h`. |
| `@Bd` | `B#` | voisement 0-8, synchronisé | 8 | DOC, ROM |
| `@Vd` | `V#` | voix préréglée 1-6 ; `@V0` coupe la voix | 1 | DOC. APOLLO.TXT : `@Vb` « speech on/off ». |
| `@Kb` | `K#` | table du locuteur, masculine ou non | 0 | DOC 1998. Speakup envoie `@K1` à l'initialisation. |
| `@Mhh` | `M**` | rapport cyclique, 0-3F | 14 (hexa) | DOC 1998 annonce 16. **Écart [INC].** |
| `@$o` | `$#` | source et filtre, 0-7 | 0 | DOC |
| `@u d hh±` | `U#*±`, `U#**±` | formants | — | DOC 1998. APOLLO.TXT : `@@dh±`. |
| `@Hb` | `H#` | hypermode | 0 | DOC |
| `@Xb` | `X#` | mode phonétique | 0 | DOC |
| `@Th` | `T*` | effet sonore 0-F ; `@Tx` donne une pause d'environ 100 ms | — | **Homonyme** : sur l'Apollo I, `@T` lance une boucle d'autotest [DOC]. |
| `@=d,` | `=#` | emplacement de ROM, donc langue | 1 | DOC. La virgule ferme la proposition. |
| `@Ec` | `E*` | écho | — | voir §2.3 |
| `@I+`, `@I?` | immédiats | index | — | voir §2.4 |
| `@c?`, `@L`, `@?` | `*?`, `L`, `?` | interrogations | — | voir §2.5 |
| `@J` | absent | réinitialisation douce | — | DOC 1998 seulement, absent de la ROM 2.01. **[INC]** |
| `@Gb`, `@+c`, `@I^` | `G#`, `+*`, `I^` | sans effet à partir de la ROM 2 | — | DOC 1998, ROM. TB25 décrivait `@G` (accueil) et APOLLO.TXT `@!c` (caractère d'échappement). |
| `@Y…` | absent | réglage série | — | DOC 1998 seulement |
| Ctrl-A, Ctrl-X | immédiats | mute | — | DOC, ROM |

**Valeurs de `cmd_hex_value` [ROM].**
- `0`-`9` valent 0-9 et `A`-`Z` valent 10-35, sans tenir compte de la casse.
- `:` à `@` valent 35.
- Chaque commande rejette les valeurs hors de sa plage, sans rien faire.

## 4. Caractères et encodage

- La table `cmd_case_map` de la ROM [ROM] :
  - passe les minuscules en majuscules, ainsi que quelques lettres accentuées de la page de codes 437 ;
  - change `[ ]` en `( )` ;
  - remplace les codes de contrôle autres que CR et ESC par des espaces, de même que plusieurs codes au-dessus de 0x7F.
- Le profil SRD2 contient la valeur 437 [PIL]. Sonolect et Épaulard envoient du CP850 [PIL].
- **Choix d'Apolo-emu [APP]** :
  - décodage en CP437 par défaut, réglable ;
  - casse d'origine conservée pour le moteur moderne ;
  - aucune normalisation destructive.

## 5. Ce qu'envoient réellement les logiciels

| Logiciel | Séquences | Source |
|---|---|---|
| Speakup | `@R3@D0@K1\r` puis `@W`, `@F`, `@A` (hexa minuscule), `@V`, `@=n,` ; flush = vidage du tty + Ctrl-X ; un `\r` est ajouté à la première espace venue | PIL |
| emacspeak-ss | init `@W3@F8@R3@S0@P0@Q0@B8@Db@V1` ; marques `@I+`, interrogation `@I?` jusqu'à recevoir `I00M` ; `@E.` et `@A?`…`@$?` au démarrage | PIL |
| Screen Reader/2 | init `@=1\r @w4\r`, puis `@=3` (choix de « voix ») ; débit `@w0`…`@wf`, volume `@a1`…`@a9`, hauteur `@f0`…`@ff`, voix `@=1`…`@=6`, `@r6`, `@r7` ; mute Ctrl-A ou Ctrl-X ; `@e<TAB>` avant chaque mot | PIL |
| Sonolect 7.11 | `^X@W4@A3@F9.` puis le texte et CR ; aucune lecture de la ligne ; pas de Ctrl-X pendant la frappe | PIL |
| Épaulard | **extension non authentique** : `@I<c>.` avant le texte, en attendant `c` à la fin de la parole. Sur un vrai Apollo II, `@IA.` serait prononcé. | PIL |

## 6. Prototypes : comportements corrects, approximatifs et erronés

Les deux passerelles (`../pc486/gateway/apollo2spd.py` et `../os2/gateway/apollo2spd.py`) sont presque identiques.

- **Corrects** :
  - Ctrl-X annule ;
  - CR déclenche la parole ;
  - `@E` renvoie l'octet après la parole qui précède, et le perd en cas d'annulation ;
  - réglages rejoués à la reconnexion à SSIP.
- **Approximations** :
  - formules de débit, hauteur et volume arbitraires ;
  - un écho par mot ;
  - LF équivaut à CR ;
  - le texte est prononcé après 0,3 s d'inactivité ;
  - interruption automatique sur un silence entre deux rafales (`burst_gap`, pc486) ;
  - espaces normalisées.
- **Erreurs vis-à-vis de l'Apollo II** :
  - `@@` devient `@` ;
  - argument toujours d'un seul caractère : `M**` et `U…` ne sont pas reconnus ;
  - Ctrl-X ou Ctrl-A est avalé au milieu d'une séquence `@` ;
  - aucune réponse à `@I?`, `@c?` ou `@L` ;
  - `@I<c>` (pc486) donne un autre sens à `@I` ;
  - la ponctuation ne termine pas la proposition, alors que `@W4@A3@F9.` en dépend ;
  - `@V`, `@P`, `@S` et `@=` sont ignorés.
- **Licence** : aucune. Le code a été écrit dans ces projets. Apolo-emu ne le recopie pas : il en reprend seulement les connaissances.

## 7. Principales difficultés

1. **Synchronisation.** L'Apollo prononce une proposition à la fois et renvoie les échos et les décomptes d'index au fil de la parole. Le moteur moderne reçoit des messages entiers.
   - On a vérifié que les marques SSML (`<mark/>`) et les notifications `INDEX_MARKS` (événement 700) de Speech Dispatcher fonctionnent avec eSpeak NG sur l'hôte. Elles arrivent au rythme réel de la parole : test du 25 octobre 2026, Speech Dispatcher 0.12.1.
   - On peut donc placer une marque au début de chaque proposition et à chaque `@I+`, dans un seul message fluide.
2. **Contrôle de flux** : impossible au travers de la socket (§1).
3. **Commandes homonymes** entre l'Apollo I et l'Apollo II, et entre versions de ROM : `@A`, `@T`, `@V`, `@W`, `@G`, `@!` et `@+`, `@@` et `@u`.
4. **Correspondance des paramètres** : il n'existe aucune mesure des débits et hauteurs réels. Les correspondances sont des approximations documentées et réglables.
5. **Extensions des prototypes** (`@I<c>` d'Épaulard, interruption par rafale de Sonolect, débit hexadécimal de SRD2) : elles doivent rester isolées et désactivées par défaut.
