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


@admin.register(Groupe)
class GroupeAdmin(admin.ModelAdmin):
    list_display = ("nom", "code")
    search_fields = ("nom", "code")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "groupe", "telephone")
    list_filter = ("groupe",)
    search_fields = ("user__username", "user__email", "telephone")


@admin.register(RentableItem)
class RentableItemAdmin(admin.ModelAdmin):
    list_display = ("part", "is_rentable", "consommable", "caution", "seuil_alerte_bas")
    list_filter = ("is_rentable", "consommable")
    search_fields = ("part__name", "part__IPN")


@admin.register(Manifestation)
class ManifestationAdmin(admin.ModelAdmin):
    list_display = ("nom", "date_debut", "date_fin", "statut", "organisateur", "groupe")
    list_filter = ("statut", "groupe")
    search_fields = ("nom",)


@admin.register(Prestation)
class PrestationAdmin(admin.ModelAdmin):
    list_display = ("nom", "manifestation", "date_debut", "date_fin")
    list_filter = ("manifestation",)
    search_fields = ("nom",)


@admin.register(Lieu)
class LieuAdmin(admin.ModelAdmin):
    list_display = ("nom", "prestation", "adresse", "latitude", "longitude", "capacite")
    list_filter = ("prestation",)
    search_fields = ("nom", "adresse")


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("pk", "prestation", "demandeur", "statut", "forced", "date_demande")
    list_filter = ("statut", "forced")
    search_fields = ("demandeur__username",)


@admin.register(LigneReservation)
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
