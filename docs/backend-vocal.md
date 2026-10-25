# Backend vocal

## Speech Dispatcher (`--backend ssip`, par défaut)

`ssip.py` est un client SSIP écrit directement, sans le module Python `speechd`.

**Connexion** : `$SPEECHD_ADDRESS`, sinon `$XDG_RUNTIME_DIR/speech-dispatcher/speechd.sock`. Si la socket est
absente, Apolo-emu lance `speech-dispatcher --spawn` une fois (désactivable avec `--no-autospawn`).

**Initialisation** :

```text
SET self CLIENT_NAME utilisateur:apolo-emu:main
SET self OUTPUT_MODULE …          (si --module)
SET self PRIORITY message         (--priority)
SET self SSML_MODE on
SET self NOTIFICATION all on
```

- **Priorité `message`** : les énoncés se suivent sans s'annuler. Le mute envoie `CANCEL self`, qui n'arrête
  que les messages d'Apolo-emu.
- **Un énoncé devient un message SSML** :
  `<speak>texte<mark name="m12"/>suite<break time="100ms"/></speak>`.
  - Le texte est échappé pour XML ; une ligne commençant par `.` est doublée selon SSIP.
  - Rien d'autre n'est transformé : ni la casse, ni les espaces, ni la ponctuation.
- **Événements reçus** :
  - 701 (BEGIN) donne `begin` ;
  - 700 (INDEX MARK) donne `mark` ;
  - 702 (END) donne `end` ;
  - 703 (CANCELED) donne `cancel`.
- **Réglages** : ils sont envoyés avant un message quand ils diffèrent de ceux déjà appliqués, et renvoyés
  après une reconnexion.

### Marques et synchronisation : vérification

Vérification faite sur l'hôte le 25 octobre 2026 (Speech Dispatcher 0.12.1, module espeak-ng) :
- les marques `<mark/>` d'un message SSML reviennent en événements 700, **au moment où la parole les atteint**
  (sonde, puis `tests/test_speechd_integration.py`) ;
- un message de deux phrases avec un `@I+` au milieu a donné l'écho de début, `@I?` → `I10T` pendant la
  parole, l'écho de la deuxième phrase à son début, puis l'écho final après la fin.

**Si un module ne gère pas les marques**, aucune marque ne revient. Les actions rattachées s'exécutent alors à
la fin du message (END) : la synchronisation reste juste, mais elle est moins fine.

**Incident de connexion** :
- Si Speech Dispatcher s'arrête ou devient injoignable, les énoncés transmis et pas encore terminés sont
  déclarés finis, et le journal le signale. L'invité reçoit ainsi ses échos au lieu d'attendre indéfiniment.
- La connexion est rétablie au message suivant.
- Un message refusé est traité de la même façon.

## Correspondance des réglages (`mapping.py`)

Il n'existe aucune mesure de l'appareil réel. Les correspondances suivent trois principes :
- la valeur par défaut de l'Apollo donne la valeur par défaut du moteur ;
- les valeurs extrêmes donnent les valeurs extrêmes ;
- la progression est monotone.

Elles sont vérifiées par `tests/test_mapping.py` et ajustables avec `--rate-offset`, `--pitch-offset`,
`--volume-offset` et `--no-volume`.

| Apollo | Plage, défaut | SSIP | Formule |
|---|---|---|---|
| `@W` débit | 1-9, 3 (environ 80-580 mots/min) | `RATE` -100..100 | W ≤ 3 : (W−3)×35 ; W > 3 : (W−3)×100/6. Donc W1 = −70, W3 = 0, W9 = +100. |
| `@F` hauteur | 0-F, 8 | `PITCH` | (F−8)×12,5. F0 = −100, F8 = 0, FF = +88. |
| `@F+`, `@F-` | décalage léger, non cumulatif | `PITCH` | +10 ou −10, jusqu'au prochain `@Fh` |
| `@A` volume | 0-F, 6 | `VOLUME` | A×200/15 − 100. A0 = −100, A6 = −20, AA = +33, AF = +100. |
| `@V1`-`@V3` | voix masculines | `VOICE_TYPE` | `MALE1`-`MALE3` |
| `@V4`-`@V6` | voix non masculines | `VOICE_TYPE` | `FEMALE1`-`FEMALE3` |
| `@V0` | voix coupée | — | rien n'est envoyé au moteur ; échos et index fonctionnent comme si la parole avait été instantanée |
| `@P1` / `@P0` | ponctuation dite | `PUNCTUATION` | `all` / `none` |
| `@S1` / `@S0` | épellation | `SPELLING` | `on` / `off` |
| `@=n` | emplacement de ROM | `LANGUAGE` | langue de l'emplacement, d'après `--languages` (« 1=en,2=fr ») |

- **Le volume** est relatif au bouton de l'appareil. La ROM démarre à 6 ; le manuel appelle « normal » la
  valeur A. Le volume par défaut est donc un peu plus bas que celui du moteur ; `--volume-offset` corrige ce
  point.
- **Avec `--voice`** (voix nommée du moteur), `VOICE_TYPE` n'est plus envoyé : la voix choisie l'emporte sur
  `@V`.
- **Le caractère `@`** resté dans le texte, c'est-à-dire une commande non reconnue, est remplacé par une espace
  quand la ponctuation est désactivée. Le moteur moderne dirait sinon « arobase », alors que l'appareil le
  traite comme une ponctuation muette.

## Autres backends

- **`--backend simulated`** : sans son. La durée de parole est simulée à `--cps` caractères par seconde, et les
  marques sont signalées à leur position. Ce backend sert aux essais et aux tests d'intégration.
- **`--backend null`** : sans son. Chaque énoncé est fini aussitôt.

Pour écrire un autre backend, voir l'interface dans [architecture.md](architecture.md).
