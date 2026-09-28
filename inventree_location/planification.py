"""Contrôles préalables au passage d'une manifestation en « planifiée » (4.5.4)."""

from __future__ import annotations

from django.utils import timezone

from .models import Manifestation, StatutManifestation


def _jour(moment) -> str:
    """Date lisible, dans le fuseau de l'instance (cf. INVENTREE_TIMEZONE)."""

    return timezone.localtime(moment).strftime("%d/%m/%Y à %H:%M")


def obstacles_a_la_planification(manifestation: Manifestation) -> list[str]:
    """Ce qui empêche de planifier, en clair. Liste vide : la manif est prête."""

    if manifestation.statut != StatutManifestation.BROUILLON:
        # Les autres contrôles n'ont plus d'objet : seul un brouillon se planifie.
        return ["Seule une manifestation en brouillon peut être planifiée."]

    obstacles = []
    maintenant = timezone.now()

    # Planifier ce qui a déjà commencé afficherait aussitôt « en cours » ou
    # « terminée » : le statut effectif se dérive des dates.
    if manifestation.date_fin < maintenant:
        obstacles.append(
            f"La manifestation est terminée depuis le {_jour(manifestation.date_fin)}."
        )
    elif manifestation.date_debut <= maintenant:
        obstacles.append(
            f"La manifestation a commencé le {_jour(manifestation.date_debut)}."
        )

    prestations = list(manifestation.prestations.all())

    if not prestations:
        obstacles.append("Aucune prestation n'est rattachée à cette manifestation.")

    sans_lieu = [p.nom for p in prestations if p.lieu_id is None]

    if sans_lieu:
        obstacles.append(f"Prestation sans lieu : {', '.join(sans_lieu)}.")

    return obstacles


def peut_planifier(manifestation: Manifestation) -> bool:
    """Raccourci lisible pour les appelants qui ne veulent pas les motifs."""

    return not obstacles_a_la_planification(manifestation)
