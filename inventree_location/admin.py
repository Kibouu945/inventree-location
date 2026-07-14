"""Admin site configuration for the InvenTreeLocation plugin."""

from django.contrib import admin

from .models import (
    Groupe,
    Lieu,
    LigneReservation,
    Manifestation,
    Prestation,
    Profile,
    RentableItem,
    Reservation,
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
    list_display = ("part", "is_rentable", "consommable", "caution", "seuil_alerte_bas")
    list_filter = ("is_rentable", "consommable")
    search_fields = ("part__name", "part__IPN")


class ManifestationAdmin(admin.ModelAdmin):
    list_display = ("nom", "date_debut", "date_fin", "statut", "organisateur", "groupe")
    list_filter = ("statut", "groupe")
    search_fields = ("nom",)


class PrestationAdmin(admin.ModelAdmin):
    list_display = ("nom", "manifestation", "date_debut", "date_fin")
    list_filter = ("manifestation",)
    search_fields = ("nom",)


class LieuAdmin(admin.ModelAdmin):
    list_display = ("nom", "prestation", "adresse", "latitude", "longitude", "capacite")
    list_filter = ("prestation",)
    search_fields = ("nom", "adresse")


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


_register(Groupe, GroupeAdmin)
_register(Profile, ProfileAdmin)
_register(RentableItem, RentableItemAdmin)
_register(Manifestation, ManifestationAdmin)
_register(Prestation, PrestationAdmin)
_register(Lieu, LieuAdmin)
_register(Reservation, ReservationAdmin)
_register(LigneReservation, LigneReservationAdmin)
