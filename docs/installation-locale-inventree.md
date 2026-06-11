# Installation locale d’InvenTree avec Docker

## Objectif

Ce document explique comment installer et lancer InvenTree en local avec Docker afin de préparer l’environnement de développement du module de location.

Cette installation permet de :

* lancer InvenTree en local ;
* accéder à l’interface web ;
* créer un compte administrateur ;
* vérifier que la page des plugins est disponible ;
* préparer le développement du futur plugin de location.

---

## Prérequis

Avant de commencer, les outils suivants doivent être installés sur la machine :

* Docker Desktop ;
* Docker Compose ;
* Git ;
* VS Code ou un éditeur de code équivalent.

Vérification des versions :

```bash
docker --version
docker compose version
git --version
```

Exemple de résultat obtenu :

```bash
Docker version 29.1.3
Docker Compose version v2.40.3-desktop.1
git version 2.45.1.windows.1
```

---

## Clonage du dépôt InvenTree

Créer un dossier de travail :

```bash
cd ~
mkdir projet-annuel-inventree
cd projet-annuel-inventree
```

Cloner le dépôt officiel InvenTree :

```bash
git clone https://github.com/inventree/InvenTree.git
cd InvenTree
```

---

## Choix de la version InvenTree

Le cahier des charges du projet indique que la version cible d’InvenTree doit être épinglée sur une version `1.2.x`.

Lister les versions disponibles :

```bash
git tag | grep 1.2
```

Versions disponibles observées :

```bash
1.2.0
1.2.1
1.2.2
1.2.3
1.2.4
1.2.5
1.2.6
1.2.7
```

Se placer sur la version `1.2.7` :

```bash
git checkout 1.2.7
```

Vérifier l’état Git :

```bash
git status
```

---

## Lancement avec Docker Compose

Aller dans le dossier Docker fourni par InvenTree :

```bash
cd contrib/container
```

Vérifier les fichiers disponibles :

```bash
ls -la
```

Fichiers importants observés :

```bash
docker-compose.yml
dev-docker-compose.yml
docker.dev.env
Dockerfile
Caddyfile
init.sh
```

Lancer les conteneurs :

```bash
docker compose up -d
```

Vérifier que les conteneurs sont actifs :

```bash
docker compose ps
```

Exemple de services attendus :

```bash
inventree-cache
inventree-db
inventree-proxy
inventree-server
inventree-worker
```

---

## Correction du problème d’affichage initial

Lors du premier accès à InvenTree, un message d’erreur peut apparaître :

```text
If you see this text there might be an issue with your update.
See INVE-E1 in the docs for help.
```

Pour corriger ce problème, exécuter la commande de mise à jour :

```bash
docker compose run --rm inventree-server invoke update
```

Puis redémarrer les conteneurs :

```bash
docker compose down
docker compose up -d
```

Ensuite, vider le cache du navigateur avec :

```text
CTRL + F5
```

---

## Accès à l’interface web

Une fois les conteneurs lancés, accéder à InvenTree depuis le navigateur :

```text
http://inventree.localhost
```

ou :

```text
http://localhost
```

---

## Création d’un compte administrateur

Si aucun compte administrateur n’existe, créer un super utilisateur avec :

```bash
docker compose run --rm inventree-server invoke superuser
```

Renseigner ensuite :

```text
Username
Email address
Password
Password again
```

Si le mot de passe est jugé trop simple en environnement local, Django peut afficher :

```text
Bypass password validation and create user anyway? [y/N]:
```

Pour un environnement local uniquement, il est possible de répondre :

```bash
y
```

---

## Vérification de la connexion

Après création du super utilisateur, retourner sur l’interface web et se connecter avec les identifiants créés.

Une fois connecté, vérifier l’accès aux menus principaux :

* Dashboard ;
* Parts / Objets ;
* Stock ;
* Admin Center ;
* Plugins.

---

## Vérification de la page Plugins

Dans l’interface d’administration, vérifier que la page **Plugins** est visible.

Cette vérification est importante car le module Location du projet doit être développé sous forme de plugin InvenTree.

Résultat obtenu :

```text
La page Plugins est bien visible dans l’interface InvenTree.
```

---

## Remarque sur la version Docker

Même si le dépôt Git local a été placé sur le tag `1.2.7`, l’image Docker lancée peut afficher une version différente si le fichier `docker-compose.yml` utilise l’image :

```text
inventree/inventree:stable
```

Dans le test effectué, l’interface affichait :

```text
1.3.5
```

Une tâche complémentaire pourra être créée pour épingler explicitement l’image Docker sur une version compatible avec le cahier des charges, idéalement `1.2.x`.

---

## Résultat final

L’installation locale est fonctionnelle.

État validé :

* Docker fonctionne ;
* Docker Compose fonctionne ;
* InvenTree se lance en local ;
* les conteneurs principaux sont actifs ;
* un compte administrateur peut se connecter ;
* l’interface web est accessible ;
* la page Plugins est visible.

L’environnement est donc prêt pour la suite du développement du module Location.
