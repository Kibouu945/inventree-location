# -*- coding: utf-8 -*-
"""Génère les schémas SVG du modèle de données (cf. README.md).

Le contenu est tiré des **clés étrangères réelles** du code, pas d'un souvenir :
`models.py` déclare vingt-six tables et cinquante-deux relations, toutes
représentées ici.

Trois planches plutôt qu'une : vingt-six tables sur une page A4 donneraient des
libellés illisibles. Le découpage suit les domaines — la chaîne métier, le
devis et sa tarification, l'exécution terrain et ses journaux — et les tables
déjà présentées sur une planche précédente sont **rappelées en gris** pour que
chaque planche se lise seule.

Cardinalités notées aux deux extrémités, à lire « un client porte zéro à
plusieurs contacts, un contact appartient à un et un seul client ».
"""

from pathlib import Path

ICI = Path(__file__).parent

# ---------------------------------------------------------------------------
# Les tables. clé : (titre, [lignes], domaine)
# ---------------------------------------------------------------------------

TABLES = {
    "user": (
        "Utilisateur",
        ["auth.User + auth.Group", "un seul rôle métier"],
        "acteur",
    ),
    "profile": ("Profile", ["telephone", "extension 1–1 du compte"], "acteur"),
    "client": (
        "Client",
        ["nom · email ✦ · telephone", "type_client · siret · actif"],
        "client",
    ),
    "contact": (
        "Contact",
        ["nom · prenom", "email ✦ · telephone · actif"],
        "client",
    ),
    "manif": (
        "Manifestation",
        ["nom · date_debut · date_fin", "statut · couleur · remise %"],
        "coeur",
    ),
    "presta": (
        "Prestation",
        ["nom · date_debut · date_fin", "statut · lieu (nullable)"],
        "coeur",
    ),
    "lignepresta": (
        "LignePrestation",
        ["part · quantite", "le prévisionnel"],
        "coeur",
    ),
    "bon": (
        "Reservation  (bon)",
        ["numero · statut", "etat_livraison · dates"],
        "coeur",
    ),
    "ligne": (
        "LigneReservation",
        ["part · quantite_demandee", "quantite_livree · retournee"],
        "coeur",
    ),
    "lieu": ("Lieu", ["nom · adresse", "latitude · longitude"], "ref"),
    "part": (
        "Part  (InvenTree)",
        ["l'article du catalogue", "stock = StockItem"],
        "ref",
    ),
    "rentable": (
        "RentableItem",
        ["1–1 avec Part", "prix_ht · taux_tva · poids"],
        "ref",
    ),
    "tremise": ("TableRemise", ["nom · actif"], "devis"),
    "premise": ("PalierRemise", ["quantite_min", "pourcentage"], "devis"),
    "ptarif": ("PalierTarif", ["quantite_min", "prix_ht"], "devis"),
    "devis": (
        "Devis",
        ["numero · statut · montants", "acceptation · signataire"],
        "devis",
    ),
    "lignedevis": (
        "LigneDevis",
        ["part · quantite · prix", "etat_ligne"],
        "devis",
    ),
    "facture": ("FactureReservation", ["numero · montants"], "devis"),
    "modif": (
        "ModificationBon",
        ["canal · auteur · message", "etat_resultant"],
        "devis",
    ),
    "livr": (
        "Livraison",
        ["sequence · lieu", "date prévue / réelle"],
        "exec",
    ),
    "livrl": ("LivraisonLigne", ["quantite_livree"], "exec"),
    "ram": (
        "Ramassage",
        ["sequence · lieu", "ramassage_termine"],
        "exec",
    ),
    "rama": (
        "RamassageArticle",
        ["recuperee · cassee", "detruite · manquante"],
        "exec",
    ),
    "incident": (
        "ReturnIncident",
        ["type · qty · bill_client", "le registre des retours"],
        "journal",
    ),
    "sav": ("SavTicket", ["type · statut · quantite"], "journal"),
    "logresa": ("ReservationStatusLog", ["from → to · auteur"], "journal"),
    "loglivr": ("LivraisonStatusLog", ["from → to · photo"], "journal"),
    "conflit": ("ConflictHistory", ["part · manquant · resolu"], "journal"),
}

# ---------------------------------------------------------------------------
# Les relations. (source, cible, card. côté source, card. côté cible, libellé)
# ---------------------------------------------------------------------------

RELATIONS = [
    ("user", "profile", "1", "0..1", ""),
    ("user", "client", "1", "0..N", "gestionnaire"),
    ("client", "contact", "1", "0..N", ""),
    ("client", "manif", "1", "0..N", ""),
    ("contact", "manif", "0..1", "0..N", "référent"),
    ("manif", "presta", "1", "1..N", ""),
    ("presta", "lieu", "0..N", "0..1", ""),
    ("presta", "lignepresta", "1", "0..N", ""),
    ("lignepresta", "part", "0..N", "1", ""),
    ("presta", "bon", "1", "0..N", ""),
    ("bon", "ligne", "1", "1..N", ""),
    ("ligne", "part", "0..N", "1", ""),
    ("user", "bon", "1", "0..N", "demandeur"),
    ("rentable", "part", "1", "1", ""),
    ("rentable", "ptarif", "1", "0..N", ""),
    ("rentable", "tremise", "0..N", "0..1", ""),
    ("tremise", "premise", "1", "1..N", ""),
    ("manif", "devis", "1", "0..N", ""),
    ("devis", "bon", "M", "N", "table de liaison"),
    ("devis", "lignedevis", "1", "1..N", ""),
    ("lignedevis", "part", "0..N", "1", ""),
    ("facture", "devis", "M", "N", ""),
    ("bon", "modif", "1", "0..N", ""),
    ("bon", "livr", "1", "0..N", ""),
    ("livr", "livrl", "1", "1..N", ""),
    ("livrl", "ligne", "0..N", "1", ""),
    ("livr", "lieu", "0..N", "0..1", ""),
    ("user", "livr", "M", "N", "livreurs"),
    ("bon", "ram", "1", "0..N", ""),
    ("ram", "rama", "1", "1..N", ""),
    ("rama", "ligne", "0..N", "1", ""),
    ("user", "ram", "M", "N", "livreurs"),
    ("ligne", "incident", "1", "0..N", ""),
    ("ligne", "sav", "1", "0..N", ""),
    ("bon", "logresa", "1", "0..N", ""),
    ("bon", "loglivr", "1", "0..N", ""),
    ("bon", "conflit", "1", "0..N", ""),
]

# ---------------------------------------------------------------------------
# Les planches. (titre, [(libellé de colonne, [clés])], rappels)
# ---------------------------------------------------------------------------

PLANCHES = [
    (
        "La chaîne métier",
        [
            ("Acteurs", ["user", "profile"]),
            ("Client", ["client", "contact"]),
            ("Cœur", ["manif", "presta", "lignepresta", "bon", "ligne"]),
            ("Référentiel", ["lieu", "part", "rentable"]),
        ],
        set(),
    ),
    (
        "Devis, tarification et facturation",
        [
            ("Rappel", ["manif", "bon"]),
            ("Devis", ["devis", "lignedevis", "facture"]),
            ("Traçabilité", ["modif"]),
            ("Tarification", ["rentable", "ptarif", "tremise", "premise"]),
            ("Rappel ", ["part"]),
        ],
        {"manif", "bon", "part"},
    ),
    (
        "Exécution terrain, retours et journaux",
        [
            ("Rappel", ["bon", "ligne"]),
            ("Livraison", ["livr", "livrl"]),
            ("Ramassage", ["ram", "rama"]),
            (
                "Retours & journaux",
                ["incident", "sav", "logresa", "loglivr", "conflit"],
            ),
        ],
        {"bon", "ligne"},
    ),
]

COULEURS = {
    "acteur": ("#eef2ff", "#4f46e5"),
    "client": ("#ecfdf5", "#059669"),
    "coeur": ("#eff6ff", "#2563eb"),
    "devis": ("#fef3c7", "#b45309"),
    "exec": ("#fce7f3", "#be185d"),
    "journal": ("#f5f3ff", "#7c3aed"),
    "ref": ("#f1f5f9", "#475569"),
    "rappel": ("#f8fafc", "#94a3b8"),
}

LARGEUR = 208  # largeur d'une boîte
GOUTTIERE = 74  # espace entre deux colonnes
LIGNE = 15  # hauteur d'une ligne de champ
BANDEAU = 24  # hauteur du bandeau de titre
MARGE = 26
ESPACE_V = 26  # espace vertical entre deux boîtes


def hauteur(cle):
    return BANDEAU + 6 + len(TABLES[cle][1]) * LIGNE + 6


def echappe(texte):
    return texte.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def disposer(colonnes, minimums=None):
    """Position de chaque boîte : colonnes en x, empilement en y.

    `minimums` impose une hauteur plancher : une table qui porte cinq relations
    d'un même côté a besoin de place pour cinq ancres, sinon les cardinalités
    se chevauchent.
    """

    minimums = minimums or {}
    positions = {}

    for index, (_, cles) in enumerate(colonnes):
        x = MARGE + index * (LARGEUR + GOUTTIERE)
        y = MARGE + 22

        for cle in cles:
            h = max(hauteur(cle), minimums.get(cle, 0))
            positions[cle] = {"x": x, "y": y, "h": h, "col": index}
            y += h + ESPACE_V

    return positions


def dessiner(titre, colonnes, rappels):
    """Rend une planche en SVG."""

    # Premier passage : combien de relations tombent de chaque côté de chaque
    # table, pour réserver la hauteur nécessaire aux ancres.
    provisoire = disposer(colonnes)
    liens_provisoires = [
        relation
        for relation in RELATIONS
        if relation[0] in provisoire and relation[1] in provisoire
    ]
    charge = {}

    for src, dst, *_ in liens_provisoires:
        if provisoire[src]["col"] == provisoire[dst]["col"]:
            continue

        gauche, droite = (
            (src, dst)
            if provisoire[src]["col"] < provisoire[dst]["col"]
            else (dst, src)
        )
        charge[(gauche, "droite")] = charge.get((gauche, "droite"), 0) + 1
        charge[(droite, "gauche")] = charge.get((droite, "gauche"), 0) + 1

    minimums = {}

    for (cle, _), nombre in charge.items():
        minimums[cle] = max(minimums.get(cle, 0), 19 * nombre + 16)

    positions = disposer(colonnes, minimums)
    largeur = MARGE * 2 + len(colonnes) * LARGEUR + (len(colonnes) - 1) * GOUTTIERE
    hauteur_totale = max(pos["y"] + pos["h"] for pos in positions.values()) + MARGE + 4

    liens = [
        relation
        for relation in RELATIONS
        if relation[0] in positions and relation[1] in positions
    ]

    # Répartition des ancres : plusieurs liens sur un même côté ne doivent pas
    # partir du même point, sinon les cardinalités se chevauchent.
    compteurs = {}

    for src, dst, *_ in liens:
        for cle, cote in (
            (
                src,
                "droite"
                if positions[src]["col"] <= positions[dst]["col"]
                else "gauche",
            ),
            (
                dst,
                "gauche"
                if positions[src]["col"] <= positions[dst]["col"]
                else "droite",
            ),
        ):
            compteurs.setdefault((cle, cote), 0)
            compteurs[(cle, cote)] += 1

    utilises = {}
    traits = []

    for index, (src, dst, card_src, card_dst, libelle) in enumerate(liens):
        a, b = positions[src], positions[dst]
        meme_colonne = a["col"] == b["col"]

        if meme_colonne:
            # Lien vertical : on sort par le bas du plus haut.
            haut, bas = (a, b) if a["y"] < b["y"] else (b, a)
            x = haut["x"] + LARGEUR / 2
            y1, y2 = haut["y"] + haut["h"], bas["y"]
            chemin = f"M {x} {y1} L {x} {y2}"
            pos_src = (x + 6, y1 + 12) if haut is a else (x + 6, y2 - 6)
            pos_dst = (x + 6, y2 - 6) if haut is a else (x + 6, y1 + 12)
        else:
            gauche, droite = (a, b) if a["col"] < b["col"] else (b, a)
            cote_src = "droite" if a["col"] < b["col"] else "gauche"

            def ancre(pos, cle, cote):
                total = compteurs.get((cle, cote), 1)
                rang = utilises.get((cle, cote), 0)
                utilises[(cle, cote)] = rang + 1

                return pos["y"] + pos["h"] * (rang + 1) / (total + 1)

            y_gauche = ancre(gauche, src if gauche is a else dst, "droite")
            y_droite = ancre(droite, dst if droite is b else src, "gauche")
            x1 = gauche["x"] + LARGEUR
            x2 = droite["x"]
            milieu = x1 + (x2 - x1) * (0.3 + 0.4 * ((index % 3) / 2))

            chemin = (
                f"M {x1} {y_gauche} L {milieu} {y_gauche} "
                f"L {milieu} {y_droite} L {x2} {y_droite}"
            )
            pos_gauche = (x1 + 5, y_gauche - 5)
            pos_droite = (x2 - 5, y_droite - 5)
            pos_src, pos_dst = (
                (pos_gauche, pos_droite)
                if cote_src == "droite"
                else (pos_droite, pos_gauche)
            )

        ancrage_src = "start" if pos_src[0] < pos_dst[0] else "end"
        ancrage_dst = "end" if pos_src[0] < pos_dst[0] else "start"

        traits.append(
            f'<path d="{chemin}" fill="none" stroke="#94a3b8" stroke-width="1.1"/>'
            f'<text x="{pos_src[0]:.0f}" y="{pos_src[1]:.0f}" class="card" '
            f'text-anchor="{ancrage_src}">{card_src}</text>'
            f'<text x="{pos_dst[0]:.0f}" y="{pos_dst[1]:.0f}" class="card" '
            f'text-anchor="{ancrage_dst}">{card_dst}</text>'
        )

        if libelle:
            mx = (pos_src[0] + pos_dst[0]) / 2
            my = (pos_src[1] + pos_dst[1]) / 2 - 4
            traits.append(
                f'<text x="{mx:.0f}" y="{my:.0f}" class="rel" '
                f'text-anchor="middle">{echappe(libelle)}</text>'
            )

    boites = []

    for cle, pos in positions.items():
        nom, champs, domaine = TABLES[cle]
        fond, bord = COULEURS["rappel" if cle in rappels else domaine]
        boites.append(
            f'<g><rect x="{pos["x"]}" y="{pos["y"]}" width="{LARGEUR}" '
            f'height="{pos["h"]}" rx="5" fill="{fond}" stroke="{bord}" '
            f'stroke-width="1.4"/>'
            f'<rect x="{pos["x"]}" y="{pos["y"]}" width="{LARGEUR}" '
            f'height="{BANDEAU}" rx="5" fill="{bord}"/>'
            f'<rect x="{pos["x"]}" y="{pos["y"] + BANDEAU - 5}" width="{LARGEUR}" '
            f'height="5" fill="{bord}"/>'
            f'<text x="{pos["x"] + 9}" y="{pos["y"] + 16}" class="t">'
            f"{echappe(nom)}</text>"
        )

        for rang, champ in enumerate(champs):
            boites.append(
                f'<text x="{pos["x"] + 9}" y="{pos["y"] + BANDEAU + 14 + rang * LIGNE}" '
                f'class="f">{echappe(champ)}</text>'
            )

        boites.append("</g>")

    entetes = "".join(
        f'<text x="{MARGE + index * (LARGEUR + GOUTTIERE)}" y="{MARGE + 6}" '
        f'class="col">{echappe(libelle.strip().upper())}</text>'
        for index, (libelle, _) in enumerate(colonnes)
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largeur} {hauteur_totale:.0f}" width="100%">
<style>
  .t {{ font: 700 11px -apple-system, Helvetica, Arial, sans-serif; fill: #fff; }}
  .f {{ font: 9.5px ui-monospace, Menlo, monospace; fill: #334155; }}
  .card {{ font: 700 9px -apple-system, Helvetica, Arial, sans-serif; fill: #1e3a8a; }}
  .rel {{ font: italic 8.5px -apple-system, Helvetica, Arial, sans-serif; fill: #64748b; }}
  .col {{ font: 700 8.5px -apple-system, Helvetica, Arial, sans-serif; fill: #94a3b8; letter-spacing: 1px; }}
</style>
{entetes}
{"".join(traits)}
{"".join(boites)}
</svg>"""


def main():
    rendus = []

    for titre, colonnes, rappels in PLANCHES:
        rendus.append((titre, dessiner(titre, colonnes, rappels)))

    for index, (titre, svg) in enumerate(rendus, start=1):
        (ICI / f"schema{index}.svg").write_text(svg, encoding="utf-8")
        print(f"schema{index}.svg — {titre} ({len(svg)} octets)")

    return rendus


if __name__ == "__main__":
    main()
