"""Assignation et progression des livraisons (US-18 / US-19)."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from . import roles
from .execution import projeter_le_bon
from .models import (
    EtatLivraison,
    LivraisonStatusLog,
    Reservation,
    StatutReservation,
)
from .services.workflow_service import transition_reservation_status

#: Pas d'assignation : la livraison est dans le pool commun.
LIBRE = ""

#: Transitions autorisées d'un état de livraison vers les suivants.
TRANSITIONS_ETAT: dict[str, tuple[str, ...]] = {
    LIBRE: (EtatLivraison.ASSIGNEE,),
    EtatLivraison.ASSIGNEE: (EtatLivraison.EN_COURS, LIBRE),
    # Un problème n'est pas une impasse : le livreur repart ou termine.
    EtatLivraison.EN_COURS: (EtatLivraison.LIVREE, EtatLivraison.PROBLEME),
    EtatLivraison.PROBLEME: (EtatLivraison.EN_COURS, EtatLivraison.LIVREE),
    EtatLivraison.LIVREE: (),
}

#: États qu'un livreur peut demander lui-même depuis l'écran de tournée.
ETATS_DEMANDABLES = (
    EtatLivraison.EN_COURS,
    EtatLivraison.LIVREE,
    EtatLivraison.PROBLEME,
)


class LivraisonRefusee(Exception):
    """Refus métier, porteur du message et du code HTTP à renvoyer."""

    def __init__(self, detail: str, status_code: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def transitions_possibles(etat: str) -> tuple[str, ...]:
    """États atteignables depuis celui-ci."""

    return TRANSITIONS_ETAT.get(etat or LIBRE, ())


def encadre_les_livraisons(user) -> bool:
    """Vrai pour qui peut agir sur la livraison d'un autre (admin, gestionnaire)."""

    return roles.user_has_any_role(user, roles.ARBITRAGE_ROLES)


def _journaliser(reservation, *, depuis, vers, user, commentaire="", photo=None):
    """Écrit une ligne de journal pour ce changement d'état."""

    return LivraisonStatusLog.objects.create(
        reservation=reservation,
        changed_by=user if getattr(user, "is_authenticated", False) else None,
        from_etat=depuis or LIBRE,
        to_etat=vers or LIBRE,
        commentaire=commentaire or "",
        photo=photo,
    )


def _refleter_l_execution(reservation) -> None:
    """Réaligne les tables d'exécution sur les colonnes du bon."""

    projeter_le_bon(reservation)


@transaction.atomic
def accepter_livraison(reservation_id: int, user) -> Reservation:
    """Attribue une livraison du pool commun à `user`."""

    reservation = (
        Reservation.objects.select_for_update().filter(pk=reservation_id).first()
    )

    if reservation is None:
        raise LivraisonRefusee("Réservation introuvable.", 404)

    if reservation.statut != StatutReservation.VALIDEE:
        raise LivraisonRefusee(
            "Seule une réservation validée peut être prise en charge.", 409
        )

    if reservation.livreur_assigne_id is not None:
        if reservation.livreur_assigne_id == getattr(user, "pk", None):
            raise LivraisonRefusee("Cette livraison vous est déjà assignée.", 409)

        raise LivraisonRefusee(
            "Cette livraison vient d'être prise par un autre livreur.", 409
        )

    reservation.livreur_assigne = user
    reservation.date_assignation = timezone.now()
    reservation.etat_livraison = EtatLivraison.ASSIGNEE
    reservation.save(
        update_fields=["livreur_assigne", "date_assignation", "etat_livraison"]
    )

    _journaliser(reservation, depuis=LIBRE, vers=EtatLivraison.ASSIGNEE, user=user)
    _refleter_l_execution(reservation)

    return reservation


@transaction.atomic
def relacher_livraison(reservation_id: int, user) -> Reservation:
    """Remet une livraison dans le pool commun."""

    reservation = (
        Reservation.objects.select_for_update().filter(pk=reservation_id).first()
    )

    if reservation is None:
        raise LivraisonRefusee("Réservation introuvable.", 404)

    if reservation.livreur_assigne_id is None:
        raise LivraisonRefusee("Cette livraison n'est assignée à personne.", 409)

    if reservation.livreur_assigne_id != getattr(
        user, "pk", None
    ) and not encadre_les_livraisons(user):
        raise LivraisonRefusee("Cette livraison est assignée à un autre livreur.", 403)

    if reservation.etat_livraison != EtatLivraison.ASSIGNEE:
        raise LivraisonRefusee(
            "Une livraison déjà commencée ne peut plus être relâchée.", 409
        )

    reservation.livreur_assigne = None
    reservation.date_assignation = None
    reservation.etat_livraison = LIBRE
    reservation.save(
        update_fields=["livreur_assigne", "date_assignation", "etat_livraison"]
    )

    _journaliser(reservation, depuis=EtatLivraison.ASSIGNEE, vers=LIBRE, user=user)
    _refleter_l_execution(reservation)

    return reservation


@transaction.atomic
def changer_etat_livraison(
    reservation_id: int, etat: str, user, *, commentaire: str = "", photo=None
) -> Reservation:
    """Fait avancer une livraison assignée, en journalisant le passage."""

    reservation = (
        Reservation.objects.select_for_update().filter(pk=reservation_id).first()
    )

    if reservation is None:
        raise LivraisonRefusee("Réservation introuvable.", 404)

    if etat not in ETATS_DEMANDABLES:
        raise LivraisonRefusee(f"État de livraison inconnu : « {etat} ».", 400)

    if reservation.livreur_assigne_id is None:
        raise LivraisonRefusee("Acceptez la livraison avant d'en changer l'état.", 409)

    if reservation.livreur_assigne_id != getattr(
        user, "pk", None
    ) and not encadre_les_livraisons(user):
        raise LivraisonRefusee("Cette livraison est assignée à un autre livreur.", 403)

    depuis = reservation.etat_livraison or LIBRE

    if etat not in transitions_possibles(depuis):
        raise LivraisonRefusee(
            "Passage d'état impossible depuis « "
            f"{reservation.get_etat_livraison_display() or 'non assignée'} ».",
            409,
        )

    reservation.etat_livraison = etat
    colonnes = ["etat_livraison"]

    # `date_retrait_reelle` n'avait aucun écrivain : l'heure du dépôt ne vivait
    # que dans le journal, et `Livraison.date_reelle` restait vide sur un bon
    if etat == EtatLivraison.LIVREE:
        reservation.date_retrait_reelle = timezone.now()
        colonnes.append("date_retrait_reelle")

    reservation.save(update_fields=colonnes)

    _journaliser(
        reservation,
        depuis=depuis,
        vers=etat,
        user=user,
        commentaire=commentaire,
        photo=photo,
    )

    if etat == EtatLivraison.LIVREE and reservation.statut == StatutReservation.VALIDEE:
        transition_reservation_status(
            reservation,
            StatutReservation.LIVREE,
            user=user,
            comment=commentaire,
        )

    reservation.refresh_from_db()

    # Pas redondant avec la greffe du service, qui vient de projeter si le
    # statut a bougé : un dépôt sur un bon déjà marqué livré par le
    _refleter_l_execution(reservation)

    return reservation
