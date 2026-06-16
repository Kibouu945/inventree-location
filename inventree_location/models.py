"""Modèles Django du plugin InvenTreeLocation (zone MVP, schéma DB-01 v2).

Le catalogue matériel (`Part`, `PartCategory`) et l'historique stock
(`StockItemTracking`) sont fournis nativement par InvenTree — on ne les
recrée pas ici. Le plugin se limite à 8 tables propres :

1. Groupe — Organisation scoute propriétaire (mono-tenant MVP)
2. Profile — Extension OneToOne du User Django
3. RentableItem — Extension OneToOne de `part.Part` (drapeau louable + champs location)
4. Manifestation — Événement (camp, formation, week-end)
5. Prestation — Sous-événement / besoin matériel d'une Manifestation
6. Lieu — Localisation physique rattachée à une Prestation
7. Reservation — Demande de location liée à une Prestation
8. LigneReservation — Détail (Part native × quantité) d'une Reservation
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
    """Organisation scoute propriétaire (mono-tenant MVP)."""

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
    """Extension OneToOne du User Django — attributs métier."""

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
# 2. Catalogue louable (extension du Part natif)
# ---------------------------------------------------------------------------


class RentableItem(TimestampedModel):
    """Extension OneToOne de `part.Part` — drapeau louable + champs location.

    On n'ajoute pas un catalogue parallèle : la référence matérielle reste
    `part.Part` (natif InvenTree). Cette table porte uniquement les
    attributs propres au domaine location.
    """

    part = models.OneToOneField(
        "part.Part",
        on_delete=models.CASCADE,
        related_name="rentable_info",
        verbose_name=_("part"),
    )
    is_rentable = models.BooleanField(default=True, verbose_name=_("louable"))
    consommable = models.BooleanField(default=False, verbose_name=_("consommable"))
    caution = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("caution"),
    )
    valeur_remplacement = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("valeur de remplacement"),
    )
    seuil_alerte_bas = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("seuil d'alerte bas")
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["part_id"]
        verbose_name = _("article louable")
        verbose_name_plural = _("articles louables")
        indexes = [models.Index(fields=["is_rentable"])]

    def __str__(self):
        return f"RentableItem(part_id={self.part_id})"


# ---------------------------------------------------------------------------
# 3. Événements
# ---------------------------------------------------------------------------


class Manifestation(TimestampedModel):
    """Événement scout (camp, formation, week-end)."""

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
    """Créneau / service interne à une manifestation."""

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
    """Site physique rattaché à une prestation."""

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
# 4. Réservations
# ---------------------------------------------------------------------------


class Reservation(TimestampedModel):
    """Demande de matériel liée à une prestation."""

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
    # CON-01 : confirmée malgré conflit de dispo détecté à la création
    forced = models.BooleanField(default=False, verbose_name=_("forcée"))
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
    """Détail d'une réservation : un Part natif et ses quantités."""

    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name=_("réservation"),
    )
    part = models.ForeignKey(
        "part.Part",
        on_delete=models.PROTECT,
        related_name="ligne_reservations",
        verbose_name=_("part"),
    )
    quantite_demandee = models.PositiveIntegerField(verbose_name=_("quantité demandée"))
    quantite_livree = models.PositiveIntegerField(
        default=0, verbose_name=_("quantité livrée")
    )
    quantite_retournee = models.PositiveIntegerField(
        default=0, verbose_name=_("quantité retournée")
    )
    # Valeurs applicatives MVP : "ok" | "manquant" | "casse" (pas de choices au modèle)
    etat_retour = models.CharField(
        max_length=20, blank=True, default="", verbose_name=_("état du retour")
    )
    commentaire = models.TextField(
        blank=True, default="", verbose_name=_("commentaire")
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["reservation", "part"]
        verbose_name = _("ligne de réservation")
        verbose_name_plural = _("lignes de réservation")
        constraints = [
            models.UniqueConstraint(
                fields=["reservation", "part"],
                name="unique_reservation_part",
            ),
        ]

    def __str__(self):
        return f"part#{self.part_id} x{self.quantite_demandee}"
