[English](extensions.md) | Français

# Extensions (non authentiques)

Les extensions reproduisent des comportements des passerelles prototypes, ou adaptent des logiciels qui ne
s'accordent pas exactement avec la ROM 2.01. Elles obéissent à trois règles :
- elles sont **désactivées par défaut** ;
- elles s'activent une par une avec `--extension NOM` ;
- elles ne changent **jamais** le sens d'une commande Apollo II authentique. Leurs motifs sont placés après les
  motifs de la ROM : `@I+`, `@I?` et `@I^` gardent leur sens.

`apolo-emu --list-extensions` les liste.

## `epaulard-index`

C'est l'extension `@I<c>` de l'ancienne passerelle `pc486`, utilisée par Épaulard jusqu'au 25 octobre 2026.
Épaulard emploie désormais l'écho authentique `@E` ; l'extension reste pour ses anciennes versions.
- **Ce qu'envoyait Épaulard** : `^X`, puis `@IA.`, puis le texte et CR. Il attend l'octet `A` quand ce texte a été
  entièrement prononcé, et ne l'attend plus après une annulation.
- **Sur un vrai Apollo II**, `@IA.` n'est pas une commande : l'appareil prononcerait « I A » et ne renverrait
  rien.
- **Avec l'extension** :
  - `@I` suivi d'un caractère autre que `+`, `?` et `^` mémorise ce caractère ;
  - il est renvoyé à la fin effective de la parole (événement END) de la prochaine proposition terminée par CR ;
  - il n'est jamais renvoyé après un mute.
- **Équivalent authentique** : `texte<CR>@Ec<CR>` (APOLLO.TXT), sans extension. C'est ce qu'envoie Épaulard
  aujourd'hui.

## `word-echo`

- **Sur l'appareil**, `@E` est traité au début de la proposition qui le contient. Screen Reader/2 place un
  `@e<TAB>` devant chaque mot d'une phrase : tous les échos de la phrase arrivent donc ensemble, au début de
  celle-ci.
- **Avec l'extension**, chaque écho est renvoyé quand la parole atteint sa position exacte, grâce à une marque
  SSML. Cela donne un suivi mot à mot, sans découper la parole.
- **Plus fin que le matériel.**

## `lenient-speed`

- Le profil Apollo 2 de Screen Reader/2 règle le débit avec `@w0`, `@w2`… `@w9`, `@wb`, `@wf`.
- La ROM 2.01 n'accepte qu'un chiffre de 1 à 9 :
  - `@w0` est ignoré ;
  - `@wb` et `@wf` ne sont pas des commandes et restent dans le texte.
- **Avec l'extension**, `@W` accepte un caractère quelconque : `0` vaut 1, et `A` à `F` valent 9.
- Il est possible qu'une autre version de ROM ait accepté l'hexadécimal, comme le `@Wh` de l'Apollo I. Ce
  n'est pas établi.

## `burst-interrupt`

C'est le `--burst-gap` de la passerelle `pc486`.
- **Le besoin** : Sonolect n'envoie jamais Ctrl-X pendant la frappe. Sur un appareil réel, l'écho des touches
  s'accumulerait donc.
- **Avec l'extension** : si un envoi arrive alors que la parole est en cours, qu'aucune proposition n'est en
  cours de réception, et que plus de 40 ms se sont écoulées depuis l'octet précédent, la parole en cours est
  coupée comme par un mute.
- **Exception** : la parole n'est jamais coupée tant qu'un écho `@E` (ou une marque `epaulard-index`) attend
  encore d'être renvoyé. L'invité synchronise alors lui-même sa file, comme Épaulard pendant le « dire tout »,
  et coupe la parole par Ctrl-X quand il le veut. La même configuration sert ainsi à Sonolect et à Épaulard.
- C'est une heuristique, sans équivalent sur l'appareil.
