# Limitations connues

## Fidélité

- **Voix et prosodie** : la voix est celle d'eSpeak NG. Ne sont pas rendus :
  - les débits, hauteurs et volumes absolus de l'appareil ;
  - les pauses `@Q` et `@D` ;
  - la prosodie `@R`, le voisement `@B`, le rapport cyclique `@M`, la source `@$` et les formants `@u` ;
  - l'hypermode `@H`, le mode phonétique `@X` et les phonèmes `_XX`.

  Ces réglages sont seulement mémorisés et interrogeables.
- **Effets sonores `@T`** : remplacés par des silences.
- **Règles de lecture** : la prononciation, l'épellation automatique d'un mot sans voyelle, les noms de la
  ponctuation et le traitement des chiffres sont ceux du moteur, et non ceux de l'Apollo.
- **Une seule ROM de référence** : le détail de l'analyse suit la ROM UK 2.01, connue par une décompilation (une
  source secondaire). D'autres ROM (2A, versions US, autres langues) peuvent différer. `@J` et `@Y`, documentés
  en 1998, en sont l'exemple : ils sont absents de cette ROM.
- **Contenu de `@L` et de `@?`** : approximé.
- **Sens de `T` et `M`** dans la réponse à `@I?` pendant la réception d'un texte sans ponctuation : les sources se
  contredisent (option `--talking-rule`).

## Synchronisation

- **Granularité** : la synchronisation dépend des marques SSML du moteur. Elle a été vérifiée avec eSpeak NG.
  Avec un module qui ne gère pas les marques, les échos et décomptes d'index arrivent à la fin du message, au
  lieu de leur position.
- **Messages SSIP** : les propositions reçues en une seule lecture forment un seul message. Celles qui arrivent
  dans des lectures séparées (envoi très lent, octet par octet) forment des messages successifs, que Speech
  Dispatcher enchaîne avec un court intervalle.
- **Panne du moteur vocal** : si Speech Dispatcher devient injoignable, les énoncés en cours sont déclarés
  terminés. L'invité reçoit ses échos alors que rien n'a été dit, ce qui vaut mieux que de bloquer.

## Liaison série

- **Aucun contrôle de flux** : CTS est vu actif en permanence par l'invité, et l'émulateur ne peut pas le
  freiner. Un envoi qui ferait déborder un véritable Apollo II est signalé, sans perte de données (voir
  [transport-serie.md](transport-serie.md)).
- **Débit en bauds** sans effet : QEMU ne cadence pas les octets. `@Y` n'est pas émulé.
- **Une réponse émise** pendant que la socket n'est pas connectée est perdue.
- **Correctif QEMU d'OS/2** : le défaut du MSR en mode boucle doit être corrigé dans QEMU, comme dans le projet
  `os2`. Apolo-emu n'y peut rien.

## Lanceur

- `-readconfig` et les ports série définis dans des fichiers de configuration ne sont pas analysés.
- Un `-device isa-serial` sans `index` peut entrer en conflit avec le port choisi : le lanceur avertit, mais ne
  peut pas savoir quel port QEMU lui attribuera.
- L'arrêt propre d'un invité DOS, Windows 3.x ou OS/2 ne peut pas être demandé par un signal : ces systèmes ne
  gèrent pas l'ACPI. Utiliser `--on-signal wait`, puis arrêter le système invité soi-même.
