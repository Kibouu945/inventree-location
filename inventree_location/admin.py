"""Admin site configuration for the InvenTreeLocation plugin."""

from django.contrib import admin

from .models import (
    Article,
    Categorie,
    Groupe,
    LigneReservation,
    Lieu,
    Manifestation,
    Mouvement,
    Prestation,
    Profile,
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
    list_display = ("nom", "prestation", "capacite")
    list_filter = ("prestation",)
    search_fields = ("nom", "adresse")


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ("nom", "parent")
    list_filter = ("parent",)
    search_fields = ("nom",)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "nom",
        "categorie",
        "groupe",
        "quantite_totale",
        "unite",
    )
    list_filter = ("categorie", "groupe")
    search_fields = ("reference", "nom")


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("pk", "prestation", "demandeur", "statut", "date_demande")
    list_filter = ("statut",)
    search_fields = ("demandeur__username",)


@admin.register(LigneReservation)
class LigneReservationAdmin(admin.ModelAdmin):
    list_display = (
        "reservation",
        "article",
        "quantite_demandee",
        "quantite_livree",
        "quantite_retournee",
    )
    search_fields = ("article__nom",)


@admin.register(Mouvement)
class MouvementAdmin(admin.ModelAdmin):
    list_display = ("article", "type", "quantite", "date", "utilisateur")
    list_filter = ("type",)
    search_fields = ("article__nom",)

