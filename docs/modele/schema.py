# -*- coding: utf-8 -*-
"""Génère le SVG du modèle de données cible (cf. README.md)."""

from pathlib import Path

ICI = Path(__file__).parent

W, H = 1180, 1560

BOXES = {
    # cle: (x, y, w, titre, [champs], couleur)
    "user": (
        40,
        30,
        250,
        "Utilisateur  (auth.User)",
        ["1 rôle unique (auth.Group)", "interne uniquement"],
        "acteur",
    ),
    "client": (
        450,
        30,
        280,
        "Client",
        [
            "nom · email ✦ · telephone",
            "type_client · siret · actif",
            "gestionnaire → User",
        ],
        "client",
    ),
    "contact": (
        880,
        30,
        260,
        "Contact",
        ["nom · prenom", "email ✦ · telephone · actif"],
        "client",
    ),
    "devis": (
        40,
        240,
        300,
        "Devis",
        [
            "numero ✦ · statut",
            "date_acceptation · motif_refus",
            "support_acceptation",
            "signataire_contact → Contact",
            "signataire_libelle (figé)",
            "montant_ht / tva / ttc (figés)",
        ],
        "devis",
    ),
    "manif": (
        450,
        240,
        280,
        "Manifestation",
        [
            "nom · date_debut · date_fin",
            "couleur · statut",
            "pourcent_remise_globale",
            "contact → Contact",
        ],
        "coeur",
    ),
    "facture": (
        40,
        470,
        300,
        "FactureReservation",
        ["date_emission · remise_pct", "montant_total_ht", "entierement_regle"],
        "devis",
    ),
    "presta": (
        450,
        470,
        280,
        "Prestation",
        [
            "nom · heure_debut · heure_fin",
            "statut · description",
            "modifie_apres_devis",
            "lieu → Lieu  (nullable)",
        ],
        "coeur",
    ),
    "lieu": (
        880,
        470,
        260,
        "Lieu",
        ["nom · description", "adresse · latitude · longitude"],
        "ref",
    ),
    "lignedevis": (
        40,
        690,
        300,
        "LigneDevis   [snapshot figé]",
        ["part · quantite", "prix_unitaire_ht · taux_tva", "remise_pct · montant_ht"],
        "devis",
    ),
    "bon": (
        450,
        690,
        280,
        "Bon de réservation",
        [
            "numero ✦ · statut",
            "date_livraison_attendue",
            "date_retrait / retour prévus",
        ],
        "coeur",
    ),
    "article": (
        880,
        690,
        260,
        "Article",
        [
            "part.Part  (natif InvenTree)",
            "NOI = IPN · nom · actif · vendable",
            "RentableItem : poids, virtuel,",
            "consommable, seuils, caution,",
            "prix_location_ht, taux_tva",
        ],
        "ref",
    ),
    "ligne": (
        450,
        910,
        280,
        "Ligne de réservation",
        ["part · quantite", "etat : normale | hors_devis |", "            annulee"],
        "coeur",
    ),
    "modif": (
        40,
        910,
        300,
        "LigneModification",
        ["auteur · canal · message", "horodatage"],
        "devis",
    ),
    "livr": (
        110,
        1120,
        330,
        "Livraison   (DeliveryTask)",
        [
            "lieu · heure_prevue · statut",
            "quantite_livree",
            "commentaires · preuves (photo)",
            "livreur(s)  (M:N)",
        ],
        "exec",
    ),
    "ram": (
        610,
        1120,
        340,
        "Ramassage   (PickupTask)",
        [
            "lieu · date_heure_ramassage · statut",
            "qte_ramassee · qte_cassee",
            "qte_detruite · qte_manquante",
            "facturation_souhaitee",
            "ramassage_termine · preuves",
            "livreur(s)  (M:N)",
        ],
        "exec",
    ),
    "repair": (
        610,
        1360,
        340,
        "RepairTicket",
        [
            "part · motif · quantite",
            "duree_estimee / reelle",
            "date_ticket · date_reparation",
            "statut · facturation_client",
        ],
        "exec",
    ),
}

# (depuis, vers, cardinalité, style)  style: v = vertical, h = horizontal
LINKS = [
    ("client", "contact", "1", "N", "h"),
    ("user", "client", "1", "N", "h"),
    ("client", "manif", "1", "N", "v"),
    ("manif", "devis", "1", "N", "h-left"),
    ("manif", "presta", "1", "1..N", "v"),
    ("devis", "facture", "1", "0..1", "v"),
    ("devis", "lignedevis", "1", "1..N", "left-bypass"),
    ("devis", "bon", "M", "N", "devis-bon"),
    ("presta", "lieu", "N", "1", "h"),
    ("presta", "bon", "1", "N", "v"),
    ("bon", "ligne", "1", "1..N", "v"),
    ("article", "ligne", "1", "N", "art-ligne"),
    ("ligne", "modif", "1", "N", "h-left"),
    ("ligne", "livr", "1", "N", "v-left"),
    ("ligne", "ram", "1", "N", "v-right"),
    ("ram", "repair", "1", "0..N", "v"),
]


COLORS = {
    "acteur": ("#eef2ff", "#4f46e5"),
    "client": ("#ecfdf5", "#059669"),
    "coeur": ("#eff6ff", "#2563eb"),
    "devis": ("#fef3c7", "#b45309"),
    "exec": ("#fce7f3", "#be185d"),
    "ref": ("#f1f5f9", "#475569"),
}

LH = 17  # hauteur de ligne d'un champ
HEAD = 30  # hauteur du bandeau titre
PAD = 10


def box_h(fields):
    return HEAD + PAD + len(fields) * LH + 4


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def geom(key):
    x, y, w, title, fields, _ = BOXES[key]
    return x, y, w, box_h(fields)


out = []
out.append(
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%">'
)
out.append(
    "<style>"
    ".t{font:600 13.5px -apple-system,Helvetica,sans-serif;fill:#fff}"
    ".f{font:11.5px ui-monospace,Menlo,monospace;fill:#1f2937}"
    ".c{font:600 11px -apple-system,Helvetica,sans-serif;fill:#6b7280}"
    ".lnk{stroke:#94a3b8;stroke-width:1.6;fill:none}"
    "</style>"
)


# --- liens d'abord (sous les boîtes) ---
def anchor(key, side):
    x, y, w, h = geom(key)
    return {
        "t": (x + w / 2, y),
        "b": (x + w / 2, y + h),
        "l": (x, y + h / 2),
        "r": (x + w, y + h / 2),
    }[side]


for a, b, ca, cb, style in LINKS:
    if style == "v":
        p1, p2 = anchor(a, "b"), anchor(b, "t")
        pts = f"{p1[0]},{p1[1]} {p1[0]},{(p1[1] + p2[1]) / 2} {p2[0]},{(p1[1] + p2[1]) / 2} {p2[0]},{p2[1]}"
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    elif style == "v2":
        p1, p2 = anchor(a, "b"), anchor(b, "t")
        pts = f"{p1[0]},{p1[1]} {p2[0]},{p2[1]}"
        mx, my = p1[0], (p1[1] + p2[1]) / 2
    elif style in ("h", "h2"):
        p1, p2 = anchor(a, "r"), anchor(b, "l")
        pts = f"{p1[0]},{p1[1]} {p2[0]},{p2[1]}"
        mx, my = (p1[0] + p2[0]) / 2, p1[1] - 6
    elif style == "h-left":
        p1, p2 = anchor(a, "l"), anchor(b, "r")
        pts = f"{p1[0]},{p1[1]} {p2[0]},{p2[1]}"
        mx, my = (p1[0] + p2[0]) / 2, p1[1] - 6
    elif style == "left-bypass":
        x1, y1, w1, h1 = geom(a)
        x2, y2, w2, h2 = geom(b)
        p1 = (x1 + 60, y1 + h1)
        p2 = (x2 + 60, y2)
        pts = f"{p1[0]},{p1[1]} 22,{p1[1]} 22,{p2[1]} {p2[0]},{p2[1]}"
        mx, my = 78, p1[1] + 30
    elif style == "devis-bon":
        x1, y1, w1, h1 = geom(a)
        x2, y2, w2, h2 = geom(b)
        p1 = (x1 + w1, y1 + h1 - 22)
        p2 = (x2, y2 + 46)
        pts = f"{p1[0]},{p1[1]} 396,{p1[1]} 396,{p2[1]} {p2[0]},{p2[1]}"
        mx, my = 396, (p1[1] + p2[1]) / 2
    elif style == "art-ligne":
        x1, y1, w1, h1 = geom(a)
        x2, y2, w2, h2 = geom(b)
        p1 = (x1 + w1 / 2, y1 + h1)
        p2 = (x2 + w2, y2 + h2 / 2)
        pts = f"{p1[0]},{p1[1]} {p1[0]},{p2[1]} {p2[0]},{p2[1]}"
        mx, my = (p1[0] + p2[0]) / 2, p2[1] - 6
    elif style in ("v-left", "v-right"):
        p1 = anchor(a, "b")
        p2 = anchor(b, "t")
        mid = p1[1] + 60
        pts = f"{p1[0]},{p1[1]} {p1[0]},{mid} {p2[0]},{mid} {p2[0]},{p2[1]}"
        mx, my = p2[0], mid - 6
    out.append(f'<polyline class="lnk" points="{pts}"/>')
    out.append(f'<text class="c" x="{mx - 16:.0f}" y="{my - 3:.0f}">{ca}</text>')
    out.append(f'<text class="c" x="{mx + 8:.0f}" y="{my - 3:.0f}">{cb}</text>')

# --- boîtes ---
for key, (x, y, w, title, fields, kind) in BOXES.items():
    bg, br = COLORS[kind]
    h = box_h(fields)
    out.append(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{bg}" stroke="{br}" stroke-width="1.6"/>'
    )
    out.append(
        f'<path d="M{x} {y + HEAD} v-{HEAD - 7} a7 7 0 0 1 7-7 h{w - 14} a7 7 0 0 1 7 7 v{HEAD - 7} z" fill="{br}"/>'
    )
    out.append(f'<text class="t" x="{x + 11}" y="{y + 20}">{esc(title)}</text>')
    for i, f in enumerate(fields):
        out.append(
            f'<text class="f" x="{x + 11}" y="{y + HEAD + 16 + i * LH}">{esc(f)}</text>'
        )

out.append(
    f'<text class="c" x="40" y="{H - 14}">✦ = unique   ·   M:N = table de liaison   ·   [figé] = copie non recalculée</text>'
)
out.append("</svg>")

(ICI / "schema.svg").write_text("\n".join(out))
print("svg ok")
