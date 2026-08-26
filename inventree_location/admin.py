"""Admin site configuration for the InvenTreeLocation plugin."""

from django.contrib import admin

from .models import (
    Groupe,
    Lieu,
    LignePrestation,
    LigneReservation,
    Manifestation,
    Prestation,
    Profile,
    RentableItem,
    Reservation,
    ReturnIncident,
)


def _register(model, admin_class):
    """Enregistre un modèle en tolérant les rechargements du plugin.

    InvenTree ré-exécute ce module à chaque rechargement de plugin
    (``importlib.reload``). Le décorateur ``@admin.register`` lèverait alors
    ``AlreadyRegistered`` sur les modèles déjà connus : on désenregistre
    d'abord si nécessaire.
    """

    try:
        admin.site.unregister(model)
    except admin.sites.NotRegistered:
        pass
    admin.site.register(model, admin_class)


class GroupeAdmin(admin.ModelAdmin):
    list_display = ("nom", "code")
    search_fields = ("nom", "code")


class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "groupe", "telephone")
    list_filter = ("groupe",)
    search_fields = ("user__username", "user__email", "telephone")


class RentableItemAdmin(admin.ModelAdmin):
    list_display = (
        "part",
        "is_rentable",
        "consommable",
        "caution",
        "seuil_alerte_bas",
        "seuil_alerte_haut",
    )
    list_filter = ("is_rentable", "consommable")
    search_fields = ("part__name", "part__IPN")


class ManifestationAdmin(admin.ModelAdmin):
    list_display = ("nom", "date_debut", "date_fin", "statut", "organisateur", "groupe")
    list_filter = ("statut", "groupe")
    search_fields = ("nom",)


class PrestationAdmin(admin.ModelAdmin):
    list_display = ("nom", "manifestation", "lieu", "date_debut", "date_fin")
    list_filter = ("manifestation", "lieu")
    search_fields = ("nom",)


class LieuAdmin(admin.ModelAdmin):
    list_display = ("nom", "adresse", "latitude", "longitude", "capacite")
    search_fields = ("nom", "adresse")


class LignePrestationAdmin(admin.ModelAdmin):
    list_display = ("prestation", "part", "quantite")
    search_fields = ("part__name", "part__IPN")


class ReservationAdmin(admin.ModelAdmin):
    list_display = ("pk", "prestation", "demandeur", "statut", "forced", "date_demande")
    list_filter = ("statut", "forced")
    search_fields = ("demandeur__username",)


class LigneReservationAdmin(admin.ModelAdmin):
    list_display = (
        "reservation",
        "part",
        "quantite_demandee",
        "quantite_livree",
        "quantite_retournee",
        "etat_retour",
    )
    search_fields = ("part__name", "part__IPN")


class ReturnIncidentAdmin(admin.ModelAdmin):
    list_display = (
        "line",
        "type",
        "qty",
        "reported_at",
        "reported_by",
    )
    list_filter = ("type",)
    search_fields = ("line__part__name", "line__reservation__numero", "comment")


_register(Groupe, GroupeAdmin)
_register(Profile, ProfileAdmin)
_register(RentableItem, RentableItemAdmin)
_register(Manifestation, ManifestationAdmin)
_register(Prestation, PrestationAdmin)
_register(Lieu, LieuAdmin)
_register(LignePrestation, LignePrestationAdmin)
_register(Reservation, ReservationAdmin)
_register(LigneReservation, LigneReservationAdmin)
_register(ReturnIncident, ReturnIncidentAdmin)
