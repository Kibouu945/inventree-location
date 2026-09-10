# -*- coding: utf-8 -*-
"""Génère la « Visite guidée du code », support de préparation à la revue.

Usage :
    python3 guide.py
    "…/Google Chrome" --headless --no-pdf-header-footer \
        --print-to-pdf="$HOME/Downloads/<nom>.pdf" visite.html

Le document se construit étape par étape : chaque entrée de `ETAPES` est une
séance. Écrit pour quelqu'un qui ne pratique pas Django et qui devra défendre
ce code devant un encadrant — d'où les sections « ce qu'on va te demander » et
les exercices, qui sont la seule partie que le lecteur fait lui-même.
"""

import html
import re
from pathlib import Path

ICI = Path(__file__).parent


def mono(texte):
    """`x` devient du monospace."""

    return re.sub(r"`([^`]+)`", r"<code>\1</code>", texte)


# ---------------------------------------------------------------------------
# Étape 0 — la carte
# ---------------------------------------------------------------------------

ETAPE_0 = {
    "numero": "0",
    "titre": "La carte",
    "chapeau": "Où on est, et par où passe une requête. Sans cette carte, tous "
    "les fichiers se valent — avec elle, chacun a une place.",
    "blocs": [
        (
            "prose",
            "<b>Le plugin n'est pas une application autonome.</b> Il n'a ni "
            "`manage.py` ni serveur à lui : il s'exécute <i>à l'intérieur</i> "
            "d'InvenTree, qui est lui-même une application Django. C'est pour "
            "cela que tout passe par Docker, et que les tests ont besoin d'une "
            "application `part` factice pour tourner hors conteneur.",
        ),
        (
            "prose",
            "<b>`core.py` est la porte d'entrée</b> — le seul fichier "
            "qu'InvenTree connaît. Une classe, et des <i>mixins</i> qui "
            "déclarent ce que le plugin sait faire.",
        ),
        (
            "table",
            (
                ["Mixin", "Ce qu'il apporte", "Où ça se voit"],
                [
                    [
                        "`AppMixin`",
                        "« j'ai des modèles » — donc des tables et des migrations",
                        "`models.py`, `migrations/`",
                    ],
                    [
                        "`UrlsMixin`",
                        "« j'ai des URL » — `setup_urls()`",
                        "`core.py:54`",
                    ],
                    [
                        "`UserInterfaceMixin`",
                        "« je pose des écrans » — widgets du tableau de bord",
                        "`core.py`, `frontend/`",
                    ],
                    [
                        "`SettingsMixin`",
                        "des réglages dans l'administration",
                        "`SETTINGS`",
                    ],
                    [
                        "`EventMixin`",
                        "réagir aux évènements d'InvenTree",
                        "`process_event`",
                    ],
                ],
            ),
        ),
        (
            "prose",
            "<b>Le trajet d'une requête</b>, celui que tu dois pouvoir raconter "
            "de mémoire :",
        ),
        (
            "code",
            """navigateur
   │  GET /plugin/inventree-location/tournees/?date=2026-09-11
   ▼
core.py     setup_urls()      quelle vue répond à cette URL
   ▼
views.py    TourneeView       lit les paramètres, orchestre
   ▼
permissions.py                a-t-il le droit ?  (401 / 403 sinon)
   └── roles.py                quel rôle porte cet utilisateur
   ▼
execution.py                  la logique métier : calculs, règles
   ▼
models.py  →  ORM  →  PostgreSQL
   ▲
serializers.py                objets Python → JSON (et l'inverse en écriture)
   ▼
réponse JSON""",
        ),
        (
            "note",
            "<b>La décision d'architecture à défendre ici.</b> Pourquoi "
            "`execution.py`, `roles.py`, `retours.py`, `conflicts.py` existent-ils "
            "au lieu de vivre dans `views.py` ? Parce que <b>`core.py` n'est pas "
            "importable hors d'InvenTree</b> : un test qui l'importe échoue sur "
            "`No module named 'plugin'`. Toute la logique qu'on veut tester sans "
            "lancer Docker a donc été sortie dans des modules purs. Ce n'est pas "
            "de l'esthétique : c'est ce qui rend possibles 1 016 tests en "
            "70 secondes, sans conteneur.",
        ),
        (
            "table",
            (
                ["Fichier", "Taille", "Rôle"],
                [
                    ["`models.py`", "1 883 lignes", "le modèle de données"],
                    ["`views.py`", "2 806 lignes", "les endpoints"],
                    ["`serializers.py`", "1 891 lignes", "les contrats d'API"],
                    [
                        "modules métier",
                        "≈ 2 900 lignes",
                        "roles, retours, execution, conflicts, stock, sav, livraison…",
                    ],
                    ["`migrations/`", "31 fichiers", "l'histoire du schéma"],
                    ["`tests/`", "41 fichiers, 13 573 lignes", "1 016 tests"],
                    ["`frontend/src`", "86 fichiers", "les écrans (React + Mantine)"],
                ],
            ),
        ),
        (
            "qr",
            [
                (
                    "Pourquoi un plugin plutôt qu'une application Django séparée ?",
                    "Parce que le stock, les articles, les utilisateurs et les "
                    "commandes fournisseurs existent déjà dans InvenTree. Une "
                    "application séparée aurait dupliqué le stock — et le cahier "
                    "des charges classe justement « photo, lieux de stockage, "
                    "achat fournisseur » comme déjà satisfaits par InvenTree.",
                ),
                (
                    "Où est la logique métier ?",
                    "Pas dans les vues : dans des modules purs, pour être testable "
                    "sans conteneur. Exemple à montrer : `retours.py`, où trois "
                    "fonctionnalités écrivaient le même fait avec trois "
                    "vocabulaires différents, désormais unifiés.",
                ),
            ],
        ),
    ],
}


# ---------------------------------------------------------------------------
# Étape 1 — modèle, migration, base
# ---------------------------------------------------------------------------

ETAPE_1 = {
    "numero": "1",
    "titre": "Modèle → migration → base",
    "chapeau": "Le cœur de ce qu'on te demandera : comment une classe Python "
    "devient une table, et comment on la fait évoluer sans perdre de données.",
    "blocs": [
        ("titre", "1.1 — Un modèle est une table"),
        (
            "prose",
            "Une classe qui hérite de `models.Model` <b>est</b> une table. "
            "Chaque attribut est une colonne. Voici `Contact`, écrit au lot L2, "
            "en entier :",
        ),
        (
            "code",
            """class Contact(TimestampedModel):          # → table inventree_location_contact
    client = models.ForeignKey(           # → colonne client_id + clé étrangère
        Client,
        on_delete=models.CASCADE,         # si le client part, ses contacts partent
        related_name="contacts",          # chemin inverse : client.contacts
    )
    nom = models.CharField(max_length=120)
    prenom = models.CharField(blank=True, default="")
    email = models.EmailField(unique=True, null=True, blank=True)
    telephone = models.CharField(max_length=30, blank=True, default="")
    actif = models.BooleanField(default=True)

    class Meta:                           # options de la table, pas une colonne
        ordering = ["client", "nom", "prenom"]

    def __str__(self):                    # comment l'objet s'affiche
        return f"{self.prenom} {self.nom}".strip()""",
        ),
        (
            "table",
            (
                ["Élément", "Ce que c'est"],
                [
                    ["la classe", "une table"],
                    ["un attribut", "une colonne"],
                    [
                        "`TimestampedModel`",
                        "une classe <b>abstraite</b> : elle n'a pas de table à "
                        "elle, elle ajoute `created_at` et `updated_at` à celles "
                        "qui en héritent",
                    ],
                    [
                        "`class Meta`",
                        "les options de la table : tri par défaut, contraintes, "
                        "index, libellés",
                    ],
                    [
                        "`__str__`",
                        "l'affichage de l'objet — dans l'admin, dans les logs, "
                        "dans un message d'erreur",
                    ],
                    [
                        '`_("…")`',
                        "un marqueur de traduction : c'est ce qui permet à "
                        "l'interface d'être en français",
                    ],
                ],
            ),
        ),
        ("titre", "1.2 — Les champs, et le piège `null` / `blank`"),
        (
            "table",
            (
                ["Champ", "Colonne", "Chez nous"],
                [
                    ["`CharField(max_length=…)`", "texte court", "`nom`, `telephone`"],
                    ["`TextField`", "texte long", "`adresse`, `commentaire`"],
                    ["`EmailField`", "texte + validation", "`Client.email`"],
                    ["`BooleanField`", "vrai / faux", "`actif`, `facturer_client`"],
                    [
                        "`PositiveIntegerField`",
                        "entier ≥ 0",
                        "toutes les quantités",
                    ],
                    ["`DecimalField`", "décimal exact", "prix, latitude, longitude"],
                    ["`DateTimeField`", "date + heure", "`date_retrait_prevue`"],
                    ["`ForeignKey`", "un lien vers une autre table", "voir 1.3"],
                    [
                        "`ManyToManyField`",
                        "une table de liaison, créée automatiquement",
                        "`Livraison.livreurs`",
                    ],
                    [
                        "`TextChoices`",
                        "une liste fermée de valeurs",
                        "`StatutReservation`, `EtatRetour`",
                    ],
                ],
            ),
        ),
        (
            "note",
            "<b>`null` et `blank` ne sont pas synonymes</b>, et c'est une "
            "question de revue classique. `null=True` autorise l'absence <b>en "
            "base</b>. `blank=True` autorise le champ vide <b>dans un "
            "formulaire</b>. Notre règle : un texte se laisse vide "
            '(`blank=True, default=""`) et n\'est <b>jamais</b> `null` — sinon '
            "il existe deux façons de dire « rien ». <b>Sauf `email`</b> : il "
            "est `unique=True`, or l'unicité tolère plusieurs `NULL` mais refuse "
            "deux chaînes vides. D'où `null=True` sur lui seul, et le front qui "
            'envoie `null` plutôt que `""`.',
        ),
        ("titre", "1.3 — La clé étrangère et `on_delete` : la question de revue"),
        (
            "prose",
            "Une `ForeignKey` oblige à répondre à une question : <b>que "
            "devient cette ligne si celle qu'elle pointe disparaît ?</b> Django "
            "refuse de choisir à ta place. Nos trois réponses, et leurs raisons :",
        ),
        (
            "table",
            (
                ["Relation", "Choix", "Pourquoi"],
                [
                    [
                        "`Manifestation.client`",
                        "`PROTECT`",
                        "supprimer un client effacerait son historique. La base "
                        "<b>refuse</b> la suppression. Doctrine du dépôt : on "
                        "désactive (`actif`), on ne supprime pas.",
                    ],
                    [
                        "`Contact.client`",
                        "`CASCADE`",
                        "un contact n'existe pas sans son client : il part avec lui.",
                    ],
                    [
                        "`Client.gestionnaire`",
                        "`SET_NULL`",
                        "un salarié quitte l'entreprise, le client reste — il "
                        "perd seulement son référent.",
                    ],
                    [
                        "`ReturnIncident.line`",
                        "`CASCADE`",
                        "voulu… mais c'est exactement ce qui causait le bug "
                        "corrigé au lot L5 : remplacer les lignes d'un bon "
                        "effaçait son registre de retour en silence.",
                    ],
                ],
            ),
        ),
        (
            "prose",
            "<b>`related_name` est le chemin inverse.</b> `Contact.client` porte "
            '`related_name="contacts"`, donc on écrit `client.contacts.all()`. '
            "Deux relations ne peuvent pas revendiquer le même chemin : au lot "
            "L6, `Livraison.livreurs` et `Reservation.livreur_assigne` "
            "réclamaient tous deux `user.livraisons_assignees`, et Django a "
            "refusé de démarrer (`fields.E304`).",
        ),
        ("titre", "1.4 — `Meta` : le tri, et surtout les contraintes"),
        (
            "table",
            (
                ["Contrainte", "Ce qu'elle interdit", "Lot"],
                [
                    [
                        "`unique_reservation_part`",
                        "deux fois le même article sur un bon",
                        "d'origine",
                    ],
                    [
                        "`incident_unique_par_ligne_et_type`",
                        "deux incidents de même nature sur une ligne",
                        "L5",
                    ],
                    [
                        "`livraison_unique_par_bon_et_sequence`",
                        "deux passages numéro 1 sur un même bon",
                        "L6",
                    ],
                ],
            ),
        ),
        (
            "note",
            "<b>« Pourquoi une contrainte en base plutôt qu'un contrôle dans le "
            "code ? »</b> — question quasi certaine. Réponse : le code protège "
            "<b>un chemin</b>, la base protège <b>tous les chemins</b> — le POST "
            "direct, le shell, un script d'import, l'endpoint que quelqu'un "
            "écrira dans six mois. Le lot L5 en est la démonstration : "
            "`projeter_incidents` supposait l'unicité depuis toujours, un POST "
            "direct la violait, et personne ne le voyait parce que les totaux "
            "comptaient simplement double.",
        ),
        ("titre", "1.5 — La migration"),
        (
            "prose",
            "Une migration est un <b>fichier Python versionné qui décrit un "
            "changement de schéma</b>. Ce n'est pas du SQL écrit à la main : "
            "Django le traduit selon la base (PostgreSQL en production, SQLite "
            "dans les tests). Deux commandes, à ne pas confondre :",
        ),
        (
            "table",
            (
                ["Commande", "Ce qu'elle fait"],
                [
                    [
                        "`makemigrations`",
                        "compare les modèles au schéma décrit par les migrations "
                        "existantes et <b>écrit un fichier</b>. Ne touche pas la base.",
                    ],
                    [
                        "`migrate`",
                        "<b>applique</b> à la base les fichiers non encore appliqués, "
                        "et note lesquels dans la table `django_migrations`.",
                    ],
                    [
                        "`makemigrations --check`",
                        "« le code et le schéma sont-ils d'accord ? » — c'est notre "
                        "garde-fou après chaque lot.",
                    ],
                    [
                        "`showmigrations`",
                        "la liste, avec une croix devant celles qui sont appliquées.",
                    ],
                ],
            ),
        ),
        (
            "prose",
            "<b>Anatomie d'une migration</b> : `dependencies` dit ce qui doit "
            "être appliqué avant (c'est un graphe, pas une simple numérotation), "
            "`operations` liste les changements. Quatre familles suffisent à "
            "lire les nôtres :",
        ),
        (
            "table",
            (
                ["Famille", "Opérations", "Exemple chez nous"],
                [
                    [
                        "schéma",
                        "`CreateModel`, `AddField`, `RemoveField`, `AlterField`",
                        "`0031` crée les quatre tables d'exécution",
                    ],
                    [
                        "renommage",
                        "`RenameModel`, `RenameField`",
                        "`0026` : `Groupe` devient `Client`",
                    ],
                    [
                        "contrainte",
                        "`AddConstraint`, `RemoveConstraint`",
                        "`0030` : unicité du registre d'incidents",
                    ],
                    [
                        "données",
                        "`RunPython`",
                        "`0027` : un `Contact` créé par organisateur existant",
                    ],
                ],
            ),
        ),
        (
            "note",
            "<b>Le point fort à mettre en avant.</b> Faire passer "
            "`Manifestation.groupe` (obligatoire) à `Manifestation.client` "
            "semblait imposer la séquence classique en trois temps : ajouter une "
            "colonne facultative, recopier les valeurs, puis la rendre "
            "obligatoire et supprimer l'ancienne. `RenameModel` et `RenameField` "
            "renomment <b>sur place</b> : la colonne n'est jamais recréée, sa "
            "contrainte « non nulle » n'est jamais violée, et on économise "
            "≈ 200 lignes de migration et une fenêtre d'incohérence. C'est écrit "
            "en tête de `0026`.",
        ),
        (
            "prose",
            "<b>Réversibilité.</b> Chaque opération de schéma sait s'annuler. "
            "Un `RunPython` prend une seconde fonction, son inverse — ou "
            "`migrations.RunPython.noop` quand revenir en arrière n'a pas de "
            "sens (on ne « dé-déduplique » pas). En production, notre filet "
            "n'est de toute façon pas la migration inverse mais la restauration "
            "d'un dump pris juste avant.",
        ),
        (
            "prose",
            "<b>Deux pièges propres à ce projet</b>, tous deux payés d'une "
            "séance de débogage :",
        ),
        (
            "table",
            (
                ["Piège", "Symptôme", "Règle"],
                [
                    [
                        "dépendance vers l'application factice",
                        "boucle de démarrage du conteneur, `NodeNotFoundError`",
                        "toutes nos migrations dépendent de `part/0001_initial`, "
                        "jamais d'une migration de l'app factice des tests",
                    ],
                    [
                        "clé primaire non déclarée",
                        "`makemigrations` reproposait le même `AlterField` à "
                        "chaque passage",
                        "les quatre tables concernées déclarent désormais "
                        "`id = models.BigAutoField(primary_key=True)`",
                    ],
                ],
            ),
        ),
        ("titre", "1.6 — À faire toi-même"),
        (
            "exo",
            [
                "Ouvre `inventree_location/models.py` à la ligne 254 et lis "
                "`Contact` en entier. Trouve la seule colonne qui accepte `null` "
                "et dis pourquoi elle, et pas les autres.",
                "Ouvre `inventree_location/migrations/0026_client_et_contact.py`. "
                "Lis d'abord `dependencies`, puis les trois premières "
                "`operations`. Raconte à voix haute ce que la base va faire.",
                "Dans le conteneur : `python manage.py showmigrations "
                "inventree_location | tail -12`. Retrouve `0031` et sa croix.",
                "Puis `python manage.py makemigrations --check --dry-run`. "
                "« No changes detected » signifie que le code et la base disent "
                "la même chose — c'est la phrase à montrer en revue.",
            ],
        ),
        ("titre", "1.7 — Ce qu'on va te demander"),
        (
            "qr",
            [
                (
                    "Pourquoi `PROTECT` ici et `CASCADE` là ?",
                    "Parce que la question n'est pas technique mais métier : un "
                    "client porte un historique qu'on ne doit pas pouvoir effacer "
                    "d'un clic, un contact n'a pas d'existence sans son client. "
                    "Et parce que la doctrine du projet est de désactiver plutôt "
                    "que supprimer — d'où les champs `actif` ajoutés au lot L2.",
                ),
                (
                    "Comment garantissez-vous qu'une migration ne perd pas de données ?",
                    "Trois précautions. L'ordre : `0027` <b>lit</b> les "
                    "organisateurs pour en faire des contacts, `0028` seulement "
                    "après supprime les colonnes. Le garde-fou : `0028` commence "
                    "par lever une erreur nommant les manifestations restées sans "
                    "contact. Et la répétition : `seed_demo` fabrique une base "
                    "non vide, parce qu'une migration de données passe toujours "
                    "au vert sur une base vide sans avoir rien fait.",
                ),
                (
                    "Une contrainte en base ou un contrôle dans le code ?",
                    "Les deux, et pas pour la même raison. La base est le filet "
                    "qui tient sur tous les chemins ; le code donne le message "
                    "lisible. Au lot L5 on a même écarté le validateur "
                    "automatique de Django REST, qui répondait « must make a "
                    "unique set » en anglais sans dire quel enregistrement — "
                    "remplacé par un message qui nomme celui à corriger.",
                ),
                (
                    "Que se passe-t-il si deux personnes créent la migration 0032 "
                    "en même temps ?",
                    "Le graphe a deux têtes et Django refuse d'appliquer. Ça se "
                    "répare avec `makemigrations --merge`, mais ça se prévient : "
                    "les numéros sont réservés par lot à l'avance, ce qui est "
                    "écrit dans le plan.",
                ),
            ],
        ),
    ],
}


ETAPES = [ETAPE_0, ETAPE_1]

#: Ce qui reste à parcourir, annoncé pour que le lecteur sache où il en est.
SUITE = [
    (
        "2",
        "Le sérialiseur",
        "Le contrat d'API : `validate`, champs calculés, "
        "lecture seule, et pourquoi on a désactivé un validateur automatique.",
    ),
    (
        "3",
        "Vue et permission",
        "Comment un rôle devient un droit, et comment la "
        "barre de navigation d'InvenTree s'y branche sans le moindre patch.",
    ),
    (
        "4",
        "L'ORM",
        "`filter`, `aggregate`, `select_related`, et le piège du "
        "double import de `models` propre aux plugins.",
    ),
    (
        "5",
        "Les tests",
        "pytest, les fixtures, la factory partagée — et pourquoi "
        "elle a été écrite avant la bascule du modèle.",
    ),
]


# ---------------------------------------------------------------------------
# Rendu
# ---------------------------------------------------------------------------


def rendre_bloc(bloc):
    genre, contenu = bloc

    if genre == "titre":
        return f"<h3>{mono(contenu)}</h3>"

    if genre == "prose":
        return f"<p>{mono(contenu)}</p>"

    if genre == "note":
        return f'<div class="note">{mono(contenu)}</div>'

    if genre == "code":
        return f"<pre>{html.escape(contenu)}</pre>"

    if genre == "table":
        entetes, lignes = contenu
        tete = "".join(f"<th>{titre}</th>" for titre in entetes)
        corps = "".join(
            "<tr>" + "".join(f"<td>{mono(cellule)}</td>" for cellule in ligne) + "</tr>"
            for ligne in lignes
        )
        return f"<table><thead><tr>{tete}</tr></thead><tbody>{corps}</tbody></table>"

    if genre == "qr":
        return "".join(
            f'<div class="qr"><div class="q">{mono(question)}</div>'
            f'<div class="r">{mono(reponse)}</div></div>'
            for question, reponse in contenu
        )

    if genre == "exo":
        items = "".join(f"<li>{mono(item)}</li>" for item in contenu)
        return f'<ol class="exo">{items}</ol>'

    raise ValueError(f"Bloc inconnu : {genre}")


def rendre_etape(etape):
    blocs = "".join(rendre_bloc(bloc) for bloc in etape["blocs"])

    return (
        f'<h2><span class="num">Étape {etape["numero"]}</span>{etape["titre"]}</h2>'
        f'<p class="chapeau">{mono(etape["chapeau"])}</p>'
        f"{blocs}"
    )


suite = "".join(
    f'<tr><td class="id">{numero}</td><td><b>{titre}</b></td>'
    f'<td class="det">{mono(resume)}</td></tr>'
    for numero, titre, resume in SUITE
)

corps = '<div class="page"></div>'.join(rendre_etape(etape) for etape in ETAPES)

html_final = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Visite guidée du code</title>
<style>
@page {{ size: A4; margin: 14mm 12mm 16mm; }}
* {{ box-sizing: border-box; }}
body {{ font: 10.5pt/1.5 -apple-system, "Helvetica Neue", Arial, sans-serif; color:#111827; margin:0; }}
h1 {{ font-size: 21pt; margin:0 0 4px; letter-spacing:-.4px; }}
.sub {{ color:#6b7280; font-size:10pt; margin-bottom:18px; }}
h2 {{ font-size:13pt; margin:22px 0 6px; padding-bottom:4px; border-bottom:2px solid #2563eb;
     color:#1e3a8a; break-after:avoid; page-break-after:avoid; }}
h2 .num {{ display:inline-block; margin-right:10px; color:#2563eb; font-size:10pt;
           text-transform:uppercase; letter-spacing:.6px; }}
h3 {{ font-size:10.5pt; margin:16px 0 5px; color:#1f2937; break-after:avoid; }}
p {{ margin:6px 0; }}
.chapeau {{ color:#4b5563; font-size:10pt; margin-bottom:10px; }}
table {{ width:100%; border-collapse:collapse; margin:8px 0; }}
th {{ text-align:left; font-size:8.5pt; text-transform:uppercase; letter-spacing:.5px; color:#6b7280;
      border-bottom:1px solid #d1d5db; padding:4px 6px; }}
td {{ padding:5px 6px; border-bottom:1px solid #eef2f7; vertical-align:top; font-size:9.7pt; }}
td.id {{ font-weight:700; color:#1d4ed8; width:34px; }}
td.det {{ color:#4b5563; font-size:9.2pt; }}
tr {{ break-inside:avoid; page-break-inside:avoid; }}
code {{ font:9.2pt ui-monospace, Menlo, monospace; background:#f3f4f6; padding:.5px 3px; border-radius:3px; }}
pre {{ background:#f8fafc; border:1px solid #e5e7eb; border-left:3px solid #2563eb; border-radius:3px;
       padding:9px 11px; font:8.9pt/1.45 ui-monospace, Menlo, monospace; overflow-x:auto;
       break-inside:avoid; page-break-inside:avoid; white-space:pre; }}
.note {{ background:#fffbeb; border-left:3px solid #f59e0b; padding:8px 10px; font-size:9.6pt;
         margin:10px 0; break-inside:avoid; }}
.qr {{ margin:9px 0; break-inside:avoid; page-break-inside:avoid; }}
.qr .q {{ font-weight:700; color:#1e3a8a; }}
.qr .q::before {{ content:"« "; }}
.qr .q::after {{ content:" »"; }}
.qr .r {{ color:#374151; font-size:9.7pt; margin-top:2px; padding-left:10px;
          border-left:2px solid #dbeafe; }}
ol.exo {{ margin:6px 0 6px 18px; padding:0; }}
ol.exo li {{ margin:5px 0; font-size:9.8pt; }}
.page {{ break-after:page; page-break-after:always; }}
footer {{ margin-top:22px; padding-top:8px; border-top:1px solid #e5e7eb; color:#9ca3af; font-size:8.5pt; }}
</style></head><body>

<h1>Visite guidée du code</h1>
<div class="sub">InvenTree Location — préparation à la revue d'encadrement<br>
Étapes 0 et 1 · 11/09/2026 · à lire dans l'ordre, le dépôt ouvert à côté</div>

{corps}

<h2><span class="num">Suite</span>Ce qui reste à parcourir</h2>
<table><thead><tr><th>#</th><th>Étape</th><th>Ce qu'on y verra</th></tr></thead>
<tbody>{suite}</tbody></table>

<footer>Généré par <code>docs/visite/guide.py</code> · les numéros de ligne
renvoient au dépôt à la date du document.</footer>
</body></html>"""

sortie = ICI / "visite.html"
sortie.write_text(html_final, encoding="utf-8")
print(f"html ok {len(html_final)} octets")
