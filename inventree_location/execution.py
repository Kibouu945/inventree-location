"""Projection de l'exécution terrain : livraison et ramassage.

Les colonnes du bon restent la vérité. Ce module **recalcule** ce que les
tables d'exécution devraient contenir à partir de cette vérité, ce qui permet
trois choses sans toucher un seul endpoint d'écriture :

1. remplir les tables (`projeter_execution`) ;
2. vérifier qu'elles n'ont pas divergé (`verifier_projection`), en n'écrivant
   rien ;
3. lire la tournée d'une journée à la maille que demande le livreur — par lieu,
   avec le récapitulatif tous lieux confondus (R25, R30).

**Jamais d'instance en filtre, toujours un identifiant.** Le chargeur de
plugins d'InvenTree importe `models` deux fois : un bon obtenu depuis une
commande d'administration est une instance d'une *autre* classe que celle que
voient les clés étrangères d'ici, et Django refuse la requête (« Must be
"Reservation" instance »). Les relations inverses ont le même défaut. D'où les
`_id` partout dans ce module, et les querysets explicites plutôt que
`reservation.livraisons`.

Logique isolée de `views.py` pour rester testable : `core.py` n'est pas
importable hors InvenTree, comme `roles.py`, `retours.py` ou `livraison.py`.

**Ce que la vérité actuelle permet de savoir.** Aucun endpoint ne saisit de
livraison partielle : un bon est livré en entier ou pas du tout. La projection
pose donc, pour un bon livré, une quantité livrée égale à la quantité sortie.
Le jour où la saisie partielle existera (lot L7), c'est cette fonction qui
changera, pas les écrans.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (
    LigneReservation,
    Livraison,
    LivraisonLigne,
    Ramassage,
    RamassageArticle,
    Reservation,
    StatutReservation,
)
from .retours import (
    facturer_le_client,
    quantite_attendue_au_retour,
    quantites_du_retour,
)

#: Statuts d'un bon dont le matériel est physiquement sorti.
STATUTS_LIVRES = (
    StatutReservation.LIVREE,
    StatutReservation.RETOURNEE,
    StatutReservation.CLOTUREE,
)

#: Statuts d'un bon dont le matériel est revenu.
STATUTS_RAMASSES = (
    StatutReservation.RETOURNEE,
    StatutReservation.CLOTUREE,
)

#: Numéro du passage projeté. La vérité actuelle n'en connaît qu'un par bon ;
#: la séquence existe pour les suivants, que seule la saisie créera.
PREMIER_PASSAGE = 1


def _lignes_du_bon(reservation_id: int):
    """Les lignes du bon, relues en base plutôt que prises sur l'instance.

    Recalculer, c'est relire. Un appelant qui a préchargé ses lignes
    (`prefetch_related`) puis modifié leurs quantités par d'autres instances —
    c'est mot pour mot ce que fait la saisie de ramassage — porte un cache
    périmé, et la projection écrivait alors des zéros là où la vérité disait
    quatre. Le cas s'est produit, il est couvert par un test.
    """

    return LigneReservation.objects.filter(reservation_id=reservation_id)


def quantite_deposee(ligne) -> int:
    """Ce que tous les passages ont déposé sur cette ligne.

    Le chiffre que l'écran de livraison affiche en « livrée », et la seule
    source juste : la colonne `quantite_livree` du bon n'a aucun écrivain (cf.
    `retours.py`), et plusieurs passages ne tiendraient de toute façon pas dans
    une colonne (R23).

    Deux chemins pour le même résultat. Quand l'appelant a préchargé la relation
    (`prefetch_related("lignes__livraisons")`), on somme son cache : une liste de
    bons coûte alors une requête, pas une par ligne. Sinon on agrège par
    identifiant — jamais par instance, pour la raison donnée en tête de module.
    """

    cache = getattr(ligne, "_prefetched_objects_cache", None) or {}

    if "livraisons" in cache:
        return sum(passage.quantite_livree for passage in cache["livraisons"])

    return (
        LivraisonLigne.objects.filter(ligne_id=ligne.pk).aggregate(
            total=Sum("quantite_livree")
        )["total"]
        or 0
    )


def quantite_restant_a_livrer(ligne) -> int:
    """Ce qu'il reste à déposer sur cette ligne, tous passages confondus.

    Calculé, jamais stocké (R27) : une colonne se désynchroniserait du premier
    passage supplémentaire.
    """

    return max(quantite_attendue_au_retour(ligne) - quantite_deposee(ligne), 0)


def livraison_attendue(reservation) -> dict | None:
    """Ce que la table de livraison devrait contenir pour ce bon.

    `None` quand le bon n'est pas sorti, ou quand sa prestation n'a pas de lieu
    — un brouillon sans lieu est légitime (R13) et ne doit rien projeter. C'est
    la condition pour que la projection ne casse aucune fixture existante.
    """

    if reservation.statut not in STATUTS_LIVRES:
        return None

    prestation = reservation.prestation
    lieu = getattr(prestation, "lieu", None)

    if lieu is None:
        return None

    return {
        "lieu": lieu,
        "sequence": PREMIER_PASSAGE,
        "date_prevue": reservation.date_retrait_prevue,
        "date_reelle": reservation.date_retrait_reelle,
        "livreurs": [reservation.livreur_assigne]
        if reservation.livreur_assigne
        else [],
        "lignes": {
            ligne.pk: quantite_attendue_au_retour(ligne)
            for ligne in _lignes_du_bon(reservation.pk)
        },
    }


def ramassage_attendu(reservation) -> dict | None:
    """Ce que la table de ramassage devrait contenir pour ce bon.

    Les quatre compteurs viennent du registre d'incidents, seule source des
    natures (R32) : la projection ne réinvente aucun chiffre, elle change de
    maille. « À facturer » suit la décision déjà portée par les incidents (R37).
    """

    if reservation.statut not in STATUTS_RAMASSES:
        return None

    prestation = reservation.prestation
    lieu = getattr(prestation, "lieu", None)

    if lieu is None:
        return None

    articles = {}

    for ligne in _lignes_du_bon(reservation.pk):
        quantites = quantites_du_retour(ligne)

        articles[ligne.pk] = {
            "quantite_recuperee": quantites["ok"],
            "quantite_cassee": quantites["casse"],
            "quantite_detruite": quantites["detruit"],
            "quantite_manquante": quantites["manquant"],
            "facturer_client": facturer_le_client(ligne),
        }

    return {
        "lieu": lieu,
        "sequence": PREMIER_PASSAGE,
        "date_prevue": reservation.date_retour_prevue,
        "date_reelle": reservation.date_retour_reelle,
        # Un bon retourné est un ramassage terminé : c'est ce que dit le statut.
        "ramassage_termine": True,
        "livreurs": [reservation.livreur_assigne]
        if reservation.livreur_assigne
        else [],
        "articles": articles,
    }


def _retracter(modele, reservation_id: int) -> None:
    """Retire le passage projeté d'un bon qui n'en attend plus.

    Borné au passage **projeté** (`PREMIER_PASSAGE`) et non à tous les passages
    du bon : le jour où la saisie partielle en créera d'autres, ceux-là seront de
    la vérité saisie, et les retirer serait une perte de données — ce sera un
    arbitrage, pas une suppression.

    Les lignes et les articles partent avec, par cascade.
    """

    modele.objects.filter(
        reservation_id=reservation_id, sequence=PREMIER_PASSAGE
    ).delete()


@transaction.atomic
def projeter_le_bon(reservation) -> dict:
    """Aligne les tables d'exécution d'un bon sur la vérité actuelle.

    Idempotent : la clé d'identité du passage est `(bon, séquence)`, donc
    rejouer la projection met à jour au lieu de dupliquer.

    Aligner, c'est aussi **retirer** : un bon livré puis annulé n'attend plus
    aucun passage, et le laisser en place était une divergence que
    `divergences_du_bon` signalait sans que rien ne puisse la corriger.
    """

    resultat = {"livraison": None, "ramassage": None}

    attendue = livraison_attendue(reservation)

    if attendue is not None:
        livraison, _ = Livraison.objects.update_or_create(
            reservation_id=reservation.pk,
            sequence=attendue["sequence"],
            defaults={
                "lieu_id": attendue["lieu"].pk,
                "date_prevue": attendue["date_prevue"],
                "date_reelle": attendue["date_reelle"],
            },
        )
        livraison.livreurs.set(attendue["livreurs"])

        for ligne_id, quantite in attendue["lignes"].items():
            LivraisonLigne.objects.update_or_create(
                livraison=livraison,
                ligne_id=ligne_id,
                defaults={"quantite_livree": quantite},
            )

        LivraisonLigne.objects.filter(livraison_id=livraison.pk).exclude(
            ligne_id__in=attendue["lignes"]
        ).delete()
        resultat["livraison"] = livraison
    else:
        _retracter(Livraison, reservation.pk)

    attendu = ramassage_attendu(reservation)

    if attendu is not None:
        ramassage, _ = Ramassage.objects.update_or_create(
            reservation_id=reservation.pk,
            sequence=attendu["sequence"],
            defaults={
                "lieu_id": attendu["lieu"].pk,
                "date_prevue": attendu["date_prevue"],
                "date_reelle": attendu["date_reelle"],
                "ramassage_termine": attendu["ramassage_termine"],
            },
        )
        ramassage.livreurs.set(attendu["livreurs"])

        for ligne_id, quantites in attendu["articles"].items():
            RamassageArticle.objects.update_or_create(
                ramassage=ramassage, ligne_id=ligne_id, defaults=quantites
            )

        RamassageArticle.objects.filter(ramassage_id=ramassage.pk).exclude(
            ligne_id__in=attendu["articles"]
        ).delete()
        resultat["ramassage"] = ramassage
    else:
        _retracter(Ramassage, reservation.pk)

    return resultat


def divergences_du_bon(reservation) -> list[str]:
    """Écarts entre les tables d'exécution et la vérité, sans rien écrire.

    C'est le garde-fou de la stratégie additive : si la projection dérive, on
    l'apprend par cette commande, pas par un chiffre faux à l'écran.
    """

    ecarts = []
    attendue = livraison_attendue(reservation)
    livraison = Livraison.objects.filter(
        reservation_id=reservation.pk, sequence=PREMIER_PASSAGE
    ).first()

    if attendue is None and livraison is not None:
        ecarts.append("une livraison est projetée alors que le bon n'est pas sorti")
    elif attendue is not None and livraison is None:
        ecarts.append("livraison manquante")
    elif attendue is not None:
        if livraison.lieu_id != attendue["lieu"].pk:
            ecarts.append(
                f"lieu de livraison : {livraison.lieu_id} au lieu de "
                f"{attendue['lieu'].pk}"
            )

        # Les dates se comparent depuis le 17/09/2026 : un passage sans heure
        # réelle sur un bon livré est passé inaperçu parce que seuls le lieu et
        # les quantités étaient confrontés.
        for champ in ("date_prevue", "date_reelle"):
            if getattr(livraison, champ) != attendue[champ]:
                ecarts.append(
                    f"{champ} de livraison : {getattr(livraison, champ)} "
                    f"au lieu de {attendue[champ]}"
                )

        projetees = dict(
            LivraisonLigne.objects.filter(livraison_id=livraison.pk).values_list(
                "ligne_id", "quantite_livree"
            )
        )

        if projetees != attendue["lignes"]:
            ecarts.append(
                f"quantités livrées : {projetees} au lieu de {attendue['lignes']}"
            )

    attendu = ramassage_attendu(reservation)
    ramassage = Ramassage.objects.filter(
        reservation_id=reservation.pk, sequence=PREMIER_PASSAGE
    ).first()

    if attendu is None and ramassage is not None:
        ecarts.append("un ramassage est projeté alors que le bon n'est pas revenu")
    elif attendu is not None and ramassage is None:
        ecarts.append("ramassage manquant")
    elif attendu is not None:
        for article in RamassageArticle.objects.filter(ramassage_id=ramassage.pk):
            reference = attendu["articles"].get(article.ligne_id)

            if reference is None:
                ecarts.append(
                    f"article ramassé orphelin sur la ligne {article.ligne_id}"
                )
                continue

            constate = {
                "quantite_recuperee": article.quantite_recuperee,
                "quantite_cassee": article.quantite_cassee,
                "quantite_detruite": article.quantite_detruite,
                "quantite_manquante": article.quantite_manquante,
                "facturer_client": article.facturer_client,
            }

            if constate != reference:
                ecarts.append(
                    f"ligne {article.ligne_id} : {constate} au lieu de {reference}"
                )

    return ecarts


def bons_du_jour(jour, queryset=None):
    """Les bons dont le matériel doit sortir ce jour-là.

    « La journée » est celle du fuseau de l'application, jamais `dt.date()` sur
    de l'UTC (R43) : un créneau de 23 h à Paris appartient au bon jour.
    """

    if queryset is None:
        queryset = Reservation.objects.all()

    return queryset.filter(date_retrait_prevue__date=jour).exclude(
        statut__in=(
            StatutReservation.BROUILLON,
            StatutReservation.REFUSEE,
            StatutReservation.ANNULEE,
        )
    )


def tournee_du_jour(jour, queryset=None) -> dict:
    """La tournée d'une journée, groupée par lieu, avec le récapitulatif global.

    Le récapitulatif tous lieux confondus sert au chargement du véhicule : le
    livreur a besoin de savoir combien de tables partent au total, pas
    seulement combien par arrêt (R25). Les quantités affichées par lieu sont la
    somme de la journée sur ce lieu, parce que des objets circulent d'un lieu à
    l'autre (R30) — c'est une règle d'affichage, elle ne change pas la maille de
    stockage.
    """

    par_lieu: dict[int | None, dict] = {}
    total: dict[int, dict] = {}

    for reservation in bons_du_jour(jour, queryset):
        prestation = reservation.prestation
        lieu = getattr(prestation, "lieu", None)
        cle = lieu.pk if lieu is not None else None

        arret = par_lieu.setdefault(
            cle,
            {"lieu": lieu, "bons": [], "articles": {}, "quantite_totale": 0},
        )

        lignes = []

        for ligne in reservation.lignes.all():
            attendue = quantite_attendue_au_retour(ligne)

            lignes.append({
                "ligne": ligne.pk,
                "part": ligne.part_id,
                "part_nom": ligne.part.name,
                "quantite_demandee": ligne.quantite_demandee,
                # `quantite_livree` est la colonne du bon, que personne n'écrit ;
                # `quantite_deposee` est ce que les passages disent. Les deux
                # cohabitent le temps que les écrans basculent sur la seconde.
                "quantite_livree": ligne.quantite_livree,
                "quantite_deposee": quantite_deposee(ligne),
                "quantite_attendue": attendue,
                "quantite_restante": quantite_restant_a_livrer(ligne),
            })

            for cumul in (arret["articles"], total):
                agrege = cumul.setdefault(
                    ligne.part_id,
                    {"part": ligne.part_id, "part_nom": ligne.part.name, "quantite": 0},
                )
                agrege["quantite"] += attendue

            arret["quantite_totale"] += attendue

        arret["bons"].append({
            "reservation": reservation.pk,
            "numero": reservation.numero,
            "statut": reservation.statut,
            "etat_livraison": reservation.etat_livraison,
            "prestation": prestation.pk,
            "prestation_nom": prestation.nom,
            "manifestation_nom": prestation.manifestation.nom
            if getattr(prestation, "manifestation", None)
            else "",
            "client_nom": _nom_du_client(prestation),
            "date_retrait_prevue": reservation.date_retrait_prevue,
            "lignes": lignes,
        })

    arrets = [
        {
            "lieu": arret["lieu"],
            "bons": arret["bons"],
            "articles": sorted(arret["articles"].values(), key=lambda a: a["part_nom"]),
            "quantite_totale": arret["quantite_totale"],
        }
        for arret in par_lieu.values()
    ]

    return {
        "date": jour,
        "arrets": sorted(arrets, key=lambda a: a["lieu"].nom if a["lieu"] else ""),
        "recap_total": sorted(total.values(), key=lambda a: a["part_nom"]),
        "quantite_totale": sum(agrege["quantite"] for agrege in total.values()),
    }


def _nom_du_client(prestation) -> str:
    """Nom du client de la manifestation, vide s'il n'y en a pas."""

    manifestation = getattr(prestation, "manifestation", None)
    client = getattr(manifestation, "client", None)

    return client.nom if client is not None else ""


def aujourdhui():
    """La date du jour dans le fuseau de l'application."""

    return timezone.localdate()
