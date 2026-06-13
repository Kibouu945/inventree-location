"""Modeles Django du plugin InvenTreeLocation.

Ce module definit les 10 modeles metier du plugin de gestion
des locations evenementielles pour InvenTree :

1. Groupe — Organisation scoute proprietaire (mono-tenant MVP)
2. Profile — Extension OneToOne du User Django
3. Manifestation — Evenement (camp, formation, week-end)
4. Prestation — Sous-evenement / besoin materiel d'une Manifestation
5. Lieu — Localisation physique rattachee a une Prestation
6. Categorie — Categorie d'article (hierarchique parent/enfant)
7. Article — Reference catalogue louable
8. Reservation — Demande de location liee a une Prestation
9. LigneReservation — Detail (Article x quantite) d'une Reservation
10. Mouvement — Audit log des sorties/retours physiques
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Enums (TextChoices)
# ---------------------------------------------------------------------------


class StatutManifestation(models.TextChoices):
    BROUILLON = "brouillon", _("Brouillon")
    PLANIFIEE = "planifiee", _("Planifiée")
    EN_COURS = "en_cours", _("En cours")
    TERMINEE = "terminee", _("Terminée")
    ANNULEE = "annulee", _("Annulée")


class StatutReservation(models.TextChoices):
    BROUILLON = "brouillon", _("Brouillon")
    SOUMISE = "soumise", _("Soumise")
    VALIDEE = "validee", _("Validée")
    REFUSEE = "refusee", _("Refusée")
    LIVREE = "livree", _("Livrée")
    RETOURNEE = "retournee", _("Retournée")
    CLOTUREE = "cloturee", _("Clôturée")


class TypeMouvement(models.TextChoices):
    ENTREE = "entree", _("Entrée")
    SORTIE = "sortie", _("Sortie")
    RETOUR = "retour", _("Retour")
    PERTE = "perte", _("Perte")
    REPARATION = "reparation", _("Réparation")
    AJUSTEMENT = "ajustement", _("Ajustement")


# ---------------------------------------------------------------------------
# Mixin abstrait
# ---------------------------------------------------------------------------


class TimestampedModel(models.Model):
    """Mixin abstrait ajoutant created_at et updated_at."""

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name=_("date de création")
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name=_("date de modification")
    )

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# 1. Organisation & Utilisateurs
# ---------------------------------------------------------------------------


class Groupe(TimestampedModel):
    """Organisation scoute proprietaire (mono-tenant MVP)."""

    nom = models.CharField(max_length=120, unique=True, verbose_name=_("nom"))
    code = models.CharField(max_length=20, unique=True, verbose_name=_("code"))
    adresse = models.TextField(blank=True, default="", verbose_name=_("adresse"))

    class Meta:
        app_label = "inventree_location"
        ordering = ["nom"]
        verbose_name = _("groupe")
        verbose_name_plural = _("groupes")

    def __str__(self):
        return self.nom


class Profile(models.Model):
    """Extension OneToOne du User Django — attributs metier."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="location_profile",
        verbose_name=_("utilisateur"),
    )
    groupe = models.ForeignKey(
        Groupe,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="profiles",
        verbose_name=_("groupe"),
    )
    telephone = models.CharField(
        max_length=20, blank=True, default="", verbose_name=_("téléphone")
    )
    avatar = models.CharField(
        max_length=255, blank=True, default="", verbose_name=_("avatar")
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["user__username"]
        verbose_name = _("profil")
        verbose_name_plural = _("profils")

    def __str__(self):
        return self.user.get_full_name() or self.user.username


# ---------------------------------------------------------------------------
# 2. Evenements
# ---------------------------------------------------------------------------


class Manifestation(TimestampedModel):
    """Evenement scout (camp, formation, week-end)."""

    nom = models.CharField(max_length=200, verbose_name=_("nom"))
    description = models.TextField(
        blank=True, default="", verbose_name=_("description")
    )
    date_debut = models.DateTimeField(verbose_name=_("date de début"))
    date_fin = models.DateTimeField(verbose_name=_("date de fin"))
    statut = models.CharField(
        max_length=20,
        choices=StatutManifestation.choices,
        default=StatutManifestation.BROUILLON,
        verbose_name=_("statut"),
    )
    organisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="manifestations_organisees",
        verbose_name=_("organisateur"),
    )
    groupe = models.ForeignKey(
        Groupe,
        on_delete=models.PROTECT,
        related_name="manifestations",
        verbose_name=_("groupe"),
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["-date_debut"]
        verbose_name = _("manifestation")
        verbose_name_plural = _("manifestations")

    def __str__(self):
        return self.nom


class Prestation(TimestampedModel):
    """Creneau / service interne a une manifestation."""

    manifestation = models.ForeignKey(
        Manifestation,
        on_delete=models.PROTECT,
        related_name="prestations",
        verbose_name=_("manifestation"),
    )
    nom = models.CharField(max_length=200, verbose_name=_("nom"))
    date_debut = models.DateTimeField(verbose_name=_("date de début"))
    date_fin = models.DateTimeField(verbose_name=_("date de fin"))
    description = models.TextField(
        blank=True, default="", verbose_name=_("description")
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["date_debut"]
        verbose_name = _("prestation")
        verbose_name_plural = _("prestations")

    def __str__(self):
        return self.nom


class Lieu(TimestampedModel):
    """Site physique rattache a une prestation."""

    prestation = models.ForeignKey(
        Prestation,
        on_delete=models.PROTECT,
        related_name="lieux",
        verbose_name=_("prestation"),
    )
    nom = models.CharField(max_length=200, verbose_name=_("nom"))
    adresse = models.TextField(blank=True, default="", verbose_name=_("adresse"))
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("latitude"),
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("longitude"),
    )
    capacite = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("capacité")
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["nom"]
        verbose_name = _("lieu")
        verbose_name_plural = _("lieux")

    def __str__(self):
        return self.nom


# ---------------------------------------------------------------------------
# 3. Catalogue materiel
# ---------------------------------------------------------------------------


class Categorie(TimestampedModel):
    """Arborescence des categories (materiel camping, cuisine, etc.)."""

    nom = models.CharField(max_length=100, verbose_name=_("nom"))
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="enfants",
        verbose_name=_("catégorie parente"),
    )
    description = models.TextField(
        blank=True, default="", verbose_name=_("description")
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["nom"]
        verbose_name = _("catégorie")
        verbose_name_plural = _("catégories")

    def __str__(self):
        return self.nom


class Article(TimestampedModel):
    """Reference materiel — sera mappe sur inventree.Part en V2."""

    reference = models.CharField(
        max_length=50, unique=True, verbose_name=_("référence")
    )
    nom = models.CharField(max_length=200, verbose_name=_("nom"))
    description = models.TextField(
        blank=True, default="", verbose_name=_("description")
    )
    categorie = models.ForeignKey(
        Categorie,
        on_delete=models.PROTECT,
        related_name="articles",
        verbose_name=_("catégorie"),
    )
    groupe = models.ForeignKey(
        Groupe,
        on_delete=models.PROTECT,
        related_name="articles",
        verbose_name=_("groupe"),
    )
    quantite_totale = models.PositiveIntegerField(
        default=0, verbose_name=_("quantité totale")
    )
    unite = models.CharField(max_length=20, default="piece", verbose_name=_("unité"))
    valeur_unitaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("valeur unitaire"),
    )
    photo = models.CharField(
        max_length=255, blank=True, default="", verbose_name=_("photo")
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["reference"]
        verbose_name = _("article")
        verbose_name_plural = _("articles")

    def __str__(self):
        return f"{self.reference} — {self.nom}"


# ---------------------------------------------------------------------------
# 4. Reservations
# ---------------------------------------------------------------------------


class Reservation(TimestampedModel):
    """Demande de materiel liee a une prestation."""

    prestation = models.ForeignKey(
        Prestation,
        on_delete=models.PROTECT,
        related_name="reservations",
        verbose_name=_("prestation"),
    )
    demandeur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reservations_demandees",
        verbose_name=_("demandeur"),
    )
    validateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reservations_validees",
        verbose_name=_("validateur"),
    )
    statut = models.CharField(
        max_length=20,
        choices=StatutReservation.choices,
        default=StatutReservation.BROUILLON,
        verbose_name=_("statut"),
    )
    date_demande = models.DateTimeField(verbose_name=_("date de demande"))
    date_retrait_prevue = models.DateTimeField(
        null=True, blank=True, verbose_name=_("date de retrait prévue")
    )
    date_retour_prevue = models.DateTimeField(
        null=True, blank=True, verbose_name=_("date de retour prévue")
    )
    date_retrait_reelle = models.DateTimeField(
        null=True, blank=True, verbose_name=_("date de retrait réelle")
    )
    date_retour_reelle = models.DateTimeField(
        null=True, blank=True, verbose_name=_("date de retour réelle")
    )
    commentaire = models.TextField(
        blank=True, default="", verbose_name=_("commentaire")
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["-date_demande"]
        verbose_name = _("réservation")
        verbose_name_plural = _("réservations")

    def __str__(self):
        return f"Réservation #{self.pk} — {self.get_statut_display()}"


class LigneReservation(TimestampedModel):
    """Detail d'une reservation : un article et ses quantites."""

    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name=_("réservation"),
    )
    article = models.ForeignKey(
        Article,
        on_delete=models.PROTECT,
        related_name="lignes_reservation",
        verbose_name=_("article"),
    )
    quantite_demandee = models.PositiveIntegerField(verbose_name=_("quantité demandée"))
    quantite_livree = models.PositiveIntegerField(
        default=0, verbose_name=_("quantité livrée")
    )
    quantite_retournee = models.PositiveIntegerField(
        default=0, verbose_name=_("quantité retournée")
    )
    commentaire = models.TextField(
        blank=True, default="", verbose_name=_("commentaire")
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["reservation", "article"]
        verbose_name = _("ligne de réservation")
        verbose_name_plural = _("lignes de réservation")
        constraints = [
            models.UniqueConstraint(
                fields=["reservation", "article"],
                name="unique_reservation_article",
            ),
        ]

    def __str__(self):
        return f"{self.article} x{self.quantite_demandee}"


# ---------------------------------------------------------------------------
# 5. Audit stock
# ---------------------------------------------------------------------------


class Mouvement(TimestampedModel):
    """Historique stock — quantite signee."""

    article = models.ForeignKey(
        Article,
        on_delete=models.PROTECT,
        related_name="mouvements",
        verbose_name=_("article"),
    )
    ligne_reservation = models.ForeignKey(
        LigneReservation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mouvements",
        verbose_name=_("ligne de réservation"),
    )
    type = models.CharField(  # noqa: A003
        max_length=20,
        choices=TypeMouvement.choices,
        verbose_name=_("type"),
    )
    quantite = models.IntegerField(verbose_name=_("quantité"))
    date = models.DateTimeField(verbose_name=_("date"))  # noqa: A003
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mouvements",
        verbose_name=_("utilisateur"),
    )
    commentaire = models.TextField(
        blank=True, default="", verbose_name=_("commentaire")
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["-date"]
        verbose_name = _("mouvement")
        verbose_name_plural = _("mouvements")

    def __str__(self):
        return f"{self.get_type_display()} — {self.article} ({self.quantite})"
