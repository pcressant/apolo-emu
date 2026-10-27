[English](requirements.md) | Français

# Projet Apolo-emu : émulateur de synthétiseur vocal Apollo II

## Contexte

Je souhaite créer un nouveau projet indépendant nommé **Apolo-emu**.

L'objectif est de reproduire aussi fidèlement que possible le comportement d'un synthétiseur vocal matériel **Apollo II**, tel qu'il était utilisé dans les années 1990 avec les lecteurs d'écran DOS, Windows et OS/2.

Il ne s'agit pas simplement de convertir du texte reçu sur un port série en parole.

Je veux émuler le comportement du périphérique historique : son protocole, ses commandes, ses réponses, ses mécanismes de synchronisation, son contrôle de flux et, dans la mesure du possible, ses particularités.

Le moteur vocal moderne pourra être eSpeak NG, notamment via Speech Dispatcher. Je ne cherche pas nécessairement à reproduire le timbre exact de la voix Apollo II, mais à obtenir une compatibilité protocolaire et comportementale aussi fidèle que possible.

Le projet doit être autonome, réutilisable et indépendant des lecteurs d'écran qui l'utilisent.

## 1. Projets existants à examiner

Deux projets voisins contiennent déjà des expérimentations fonctionnelles :

- `../pc486` : environnement DOS / Windows 3.11, Sonolect 7.11 et Épaulard.
- `../os2` : OS/2 Warp 4 avec IBM Screen Reader/2 2.01.

Ces projets disposent de passerelles Apollo II vers Speech Dispatcher.

Elles fonctionnent au moins partiellement, mais leur implémentation est expérimentale.

**Tu peux lire librement ces deux projets pour comprendre leur fonctionnement et récupérer les connaissances acquises.**

En revanche :

- Ne modifie aucun fichier dans `../pc486` ou `../os2`.
- Ne modifie pas leurs machines virtuelles.
- N'interromps pas leurs processus.
- Ne modifie pas leurs configurations QEMU.
- Ne considère pas leurs implémentations comme des références incontestables.

Elles constituent des prototypes dont il faut identifier les comportements corrects, les approximations et les erreurs.

Le nouveau projet doit être créé dans son propre répertoire `Apolo-emu`.

## 2. Recherche documentaire préalable

Avant d'implémenter quoi que ce soit, examine les documents et les sources disponibles.

### Documentation Apollo

Le projet `../os2` contient des documents historiques relatifs à Apollo et Apollo II.

Cherche notamment dans :

`../os2/media/screen-reader/apollo-source/`

Les documents `APOLLO.TXT` et `APOLLO2.TXT` sont particulièrement intéressants.

Examine également les archives d'origine, les pilotes Apollo présents dans IBM Screen Reader/2 et les notes déjà rédigées dans les deux projets.

L'objectif est d'identifier précisément :

- Le protocole série.
- Les paramètres de communication.
- Les commandes de configuration.
- Les commandes de prononciation.
- Les commandes de débit, volume et hauteur.
- La gestion des caractères et des encodages.
- Les commandes de réinitialisation.
- Les mécanismes d'interruption.
- Les mécanismes de synchronisation et d'acquittement.
- Les éventuelles commandes d'identification.
- Le comportement du contrôle de flux matériel.
- Les différences entre Apollo et Apollo II.

Attention aux commandes qui portent le même nom mais dont la signification varie entre versions.

### Sources Linux Speakup

Examine également le code du noyau Linux relatif à Speakup, en particulier ses pilotes de synthétiseurs Apollo.

Cherche dans les sources Linux, notamment sous :

`drivers/accessibility/speakup/`

Le code Speakup peut apporter des informations précieuses sur :

- Les séquences d'initialisation.
- Les commandes réellement envoyées aux synthétiseurs.
- Les délais de transmission.
- La gestion des tampons.
- Le contrôle de flux.
- Les comportements particuliers du matériel.

Vérifie les noms et les pilotes réellement présents dans les sources, sans supposer qu'ils correspondent tous au même modèle Apollo.

Utilise si nécessaire les sources officielles du noyau Linux.

Tu peux également rechercher d'autres documentations publiques ou pilotes historiques pertinents.

**Ne déduis pas une commande de son seul nom : confronte les différentes sources.**

### Traçabilité

Crée une documentation distinguant :

1. Les comportements confirmés par la documentation historique.
2. Les comportements observés dans les pilotes existants.
3. Les comportements déduits par analyse.
4. Les approximations nécessaires.
5. Les fonctionnalités encore inconnues.

Je préfère une émulation honnêtement documentée à une prétendue compatibilité complète qui repose sur des suppositions.

## 3. Architecture générale

Le projet doit être indépendant de QEMU.

QEMU émule déjà les contrôleurs série UART. Il n'est donc pas nécessaire de développer un périphérique interne QEMU ni de modifier son code.

L'architecture cible est :

```text
Machine virtuelle DOS / Windows / OS/2
                |
         Pilote Apollo II
                |
             COM1
                |
        UART émulée QEMU
                |
           Socket Unix
                |
          Apolo-emu
                |
       Émulation du protocole
                |
          Backend vocal
                |
       Speech Dispatcher
                |
           eSpeak NG
```

Apolo-emu doit se comporter comme le périphérique connecté au port série.

Le cœur de l'émulation doit être indépendant :

- Du transport série.
- De QEMU.
- Du moteur vocal.
- Du système d'exploitation invité.
- Du lecteur d'écran utilisé.

Sépare clairement les responsabilités.

## 4. Émulation du protocole

Implémente un véritable analyseur de protocole, avec un état interne explicite.

Il doit gérer correctement :

- Les commandes reçues.
- Les commandes éventuellement réparties sur plusieurs lectures.
- Les séquences incomplètes.
- Les caractères de contrôle.
- Les paramètres persistants.
- Les changements de débit et de voix.
- Les interruptions.
- Les réinitialisations.
- Les réponses envoyées au logiciel invité.
- La synchronisation de la lecture.

Ne suppose jamais qu'une lecture sur la socket correspond à une commande complète.

Le protocole doit être traité comme un flux d'octets.

Les commandes inconnues doivent être journalisées proprement, sans provoquer de comportement arbitraire.

### Synchronisation

Porte une attention particulière aux mécanismes d'écho et de synchronisation, notamment aux commandes `@e` utilisées par IBM Screen Reader/2.

Une réponse de synchronisation doit correspondre autant que possible à la progression réelle de la synthèse.

Il faut distinguer :

- La réception des octets.
- L'analyse du protocole.
- La mise en attente du texte.
- Le début de la synthèse.
- La progression dans le texte.
- La fin de la synthèse.
- L'interruption.

Étudie l'utilisation des marqueurs SSML et des notifications `INDEX_MARKS` de Speech Dispatcher.

Vérifie leur prise en charge effective par le moteur utilisé.

Si une synchronisation exacte est impossible, documente cette limite et adopte un comportement déterministe, sans prétendre reproduire une garantie que le backend ne fournit pas.

Évite absolument le découpage systématique de la parole en un message par mot si une solution plus fluide est possible.

### Compatibilité historique

Attention : Épaulard utilise actuellement certaines extensions expérimentales, notamment autour de `@I`.

Ces extensions ne doivent pas modifier silencieusement la signification des commandes Apollo II authentiques.

Si des extensions sont nécessaires, elles doivent être isolées, documentées et désactivées par défaut.

La priorité est la compatibilité avec les pilotes historiques.

## 5. Transport série et contrôle de flux

Apolo-emu doit pouvoir communiquer avec QEMU au moyen d'une socket Unix bidirectionnelle.

Étudie attentivement la façon dont QEMU expose les signaux de modem et le contrôle de flux de son UART au backend choisi.

**Une socket Unix transmet des octets, mais ne reproduit pas à elle seule les signaux RTS, CTS, DTR et DSR.**

Il faut donc distinguer clairement :

- Le comportement émulé par QEMU.
- Le transport entre QEMU et Apolo-emu.
- Le comportement propre à Apollo II.

Ne prétends pas implémenter un contrôle de flux matériel complet si l'interface utilisée ne permet pas de piloter les signaux correspondants.

Le projet `../os2` contient déjà une investigation et un correctif QEMU relatifs au comportement du port série.

Étudie-les.

L'objectif est de comprendre précisément ce qui relève de QEMU et ce qui relève de l'émulateur Apollo.

Ne modifie pas QEMU dans ce projet.

## 6. Backend vocal

Utilise dans un premier temps Speech Dispatcher avec eSpeak NG.

Conçois cependant une interface permettant de remplacer le backend vocal.

Le backend doit proposer autant que possible :

- L'envoi de texte.
- L'interruption immédiate.
- Le réglage du débit.
- Le réglage de la hauteur.
- Le réglage du volume.
- Les notifications de progression.
- Les notifications de fin de lecture.

Il faudra déterminer comment traduire les paramètres Apollo II vers ceux du moteur moderne.

Cette traduction doit être documentée et testable.

Évite les transformations destructrices du texte et les conversions d'encodage implicites.

## 7. Lanceur QEMU intégré

Je souhaite également disposer d'un lanceur facilitant l'utilisation de l'émulateur avec QEMU.

L'utilisateur doit pouvoir démarrer Apolo-emu et une machine virtuelle sans devoir gérer manuellement les sockets et les processus.

Prévois deux modes.

### Mode autonome

Démarrage de l'émulateur seul, avec une socket Unix configurable.

Exemple d'interface souhaitée :

```bash
apolo-emu --socket /tmp/apollo.sock
```

### Mode lanceur

Démarrage coordonné de l'émulateur et de QEMU.

Exemple d'interface possible :

```bash
apolo-emu run -- qemu-system-i386 [options]
```

Ce ne sont que des propositions d'interface : adapte-les si une autre conception est plus robuste.

Le lanceur doit :

- Créer une socket propre à l'instance.
- Démarrer les composants dans le bon ordre.
- Ajouter ou configurer le port série QEMU.
- Éviter les conflits avec les options série déjà présentes.
- Gérer les erreurs de démarrage.
- Propager correctement les signaux d'arrêt.
- Nettoyer ses propres ressources.
- Éviter les sockets obsolètes.
- Préserver les codes de retour utiles.
- Permettre plusieurs instances indépendantes.

Il ne doit pas tuer arbitrairement des processus QEMU existants.

Il ne doit pas non plus arrêter brutalement une VM lorsqu'un arrêt propre du système invité est nécessaire.

Prévois une documentation pour intégrer Apolo-emu à des commandes QEMU déjà existantes.

Le lanceur ne doit pas imposer une configuration particulière de disque, de mémoire, de processeur ou de système invité.

## 8. Tests

Je veux une suite de tests automatisés sérieuse.

Elle doit notamment vérifier :

- L'analyse des commandes Apollo.
- Les commandes reçues en plusieurs fragments.
- Les commandes successives dans un même bloc.
- Les paramètres de synthèse.
- Les interruptions.
- Les réinitialisations.
- Les acquittements.
- Les réponses au logiciel invité.
- Les encodages.
- Les commandes inconnues.
- Les erreurs de transport.
- Les reconnexions.
- La gestion de plusieurs instances.
- Le nettoyage des processus et sockets.

Utilise un faux backend vocal pour tester le protocole sans produire réellement de parole.

Les tests de synchronisation doivent pouvoir simuler précisément la progression de la lecture.

Prévois également des tests d'intégration avec Speech Dispatcher et, lorsque c'est possible, avec QEMU.

Les tests automatisés ne doivent pas dépendre systématiquement du démarrage complet d'OS/2 ou de Windows 3.11.

### Validation avec les logiciels historiques

Les deux projets existants pourront ensuite servir de bancs d'essai :

- Sonolect 7.11 sous DOS.
- IBM Screen Reader/2 2.01 sous OS/2.
- Épaulard sous Windows 3.11.

Mais **ne lance pas et ne modifie pas leurs machines virtuelles sans nécessité ni autorisation explicite**.

Commence par les tests unitaires et les simulations de flux série.

## 9. Documentation

Le projet doit contenir au minimum :

- Un README présentant le projet et son fonctionnement.
- Une documentation du protocole Apollo II.
- Une description de l'architecture.
- Une documentation du lanceur QEMU.
- Une matrice de compatibilité des commandes.
- Une description des limitations connues.
- Les instructions d'installation.
- Des exemples d'utilisation.
- Les références documentaires utilisées.

La matrice de compatibilité doit distinguer les commandes :

- Implémentées et vérifiées.
- Implémentées mais non vérifiées sur un véritable Apollo II.
- Partiellement émulées.
- Non implémentées.
- Inconnues ou insuffisamment documentées.

## 10. Contraintes de développement

Le projet est destiné à Linux.

Python convient parfaitement si ses performances et sa gestion des événements sont suffisantes.

Je ne souhaite pas une réécriture en C simplement pour faire plus proche du matériel.

Privilégie :

- Une architecture simple.
- Un code lisible.
- Peu de dépendances.
- Des interfaces clairement définies.
- Des tests reproductibles.
- Une journalisation exploitable.
- Un fonctionnement sans privilèges root.

Le programme ne doit pas nécessiter de modification de QEMU.

Il doit être utilisable en dehors de NixOS, même si une intégration Nix pourra être ajoutée.

Ne copie pas aveuglément le code existant : vérifie également les licences et la provenance des éléments réutilisés.

## 11. Méthode de travail

Travaille de manière autonome, mais procède par étapes.

**Phase 1 : investigation**

Examine les deux projets, la documentation historique et les sources Speakup.

Produis un état des connaissances et identifie les principales difficultés.

**Phase 2 : architecture**

Définis les interfaces internes, le modèle de protocole, le transport série et le backend vocal.

**Phase 3 : implémentation**

Construis progressivement Apolo-emu, en réutilisant les parties pertinentes des prototypes lorsque leur comportement est compris et validé.

**Phase 4 : tests**

Exécute les tests automatisés, corrige les problèmes et vérifie la robustesse.

**Phase 5 : intégration QEMU**

Implémente le lanceur et valide le fonctionnement sur une VM de test indépendante.

**Phase 6 : bilan**

Rédige un compte rendu comprenant :

- Les fonctionnalités implémentées.
- Les sources historiques consultées.
- Les résultats des tests.
- Les limites de fidélité.
- Les commandes encore manquantes.
- Les éventuelles incompatibilités découvertes dans les passerelles existantes.
- Les prochaines améliorations pertinentes.

## 12. Priorités

L'ordre des priorités est le suivant :

1. Fidélité au protocole Apollo II historique.
2. Compatibilité avec les lecteurs d'écran d'époque.
3. Fiabilité des échanges série.
4. Synchronisation correcte de la parole.
5. Indépendance vis-à-vis de QEMU et des systèmes invités.
6. Simplicité d'utilisation avec le lanceur intégré.
7. Qualité et maintenabilité du code.

Ne cherche pas à reproduire le timbre vocal exact du matériel si cela compromet les objectifs précédents.

Ne transforme pas le projet en framework générique de synthèse vocale.

**L'objectif est d'émuler un appareil précis : l'Apollo II.**

Tu disposes déjà de deux prototypes fonctionnels, de documentation historique et de plusieurs pilotes d'époque à étudier.

Appuie-toi sur ces éléments pour construire une émulation cohérente, plutôt qu'une nouvelle collection de contournements.

Tu peux commencer l'investigation et poursuivre le développement de façon autonome, sans attendre une validation après chaque étape.

En revanche, respecte strictement l'intégrité des projets voisins.

**Le résultat attendu est un projet Apolo-emu autonome, fonctionnel, documenté et testé, capable de servir de synthétiseur Apollo II virtuel à des logiciels historiques.**
