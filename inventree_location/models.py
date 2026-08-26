"""Modèles Django du plugin InvenTreeLocation (zone MVP, schéma DB-01 v2).

Le catalogue matériel (`Part`, `PartCategory`) et l'historique stock
(`StockItemTracking`) sont fournis nativement par InvenTree — on ne les
recrée pas ici. Le plugin se limite à 8 tables propres :

1. Groupe — Organisation scoute propriétaire (mono-tenant MVP)
2. Profile — Extension OneToOne du User Django
3. RentableItem — Extension OneToOne de `part.Part` (drapeau louable + champs
   location) ; le stock physique reste celui d'InvenTree (`StockItem`)
4. Manifestation — Événement (camp, formation, week-end)
5. Prestation — Sous-événement / besoin matériel d'une Manifestation
6. Lieu — Localisation physique rattachée à une Prestation
7. Reservation — Demande de location liée à une Prestation
8. LigneReservation — Détail (Part native × quantité) d'une Reservation
9. ConflictHistory — Journal des conflits (stock / lieu)

S'y ajoutent, avec le SAV et les ramassages, les tables du domaine retour.
"""

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils import timezone
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
    ANNULEE = "annulee", _("Annulée")
    LIVREE = "livree", _("Livrée")
    RETOURNEE = "retournee", _("Retournée")
    CLOTUREE = "cloturee", _("Clôturée")


class TypeSavTicket(models.TextChoices):
    REPARATION = "reparation", _("Réparation")
    DESTRUCTION = "destruction", _("Destruction")


class StatutSavTicket(models.TextChoices):
    OUVERT = "ouvert", _("Ouvert")
    EN_REPARATION = "en_reparation", _("En réparation")
    REPARE = "repare", _("Réparé")
    DETRUIT = "detruit", _("Détruit")
    CLOTURE = "cloture", _("Clôturé")


class ConflictType(models.TextChoices):
    STOCK = "stock", _("Conflit de stock")
    LOCATION = "location", _("Conflit de lieu")


class ConflictState(models.TextChoices):
    OPEN = "open", _("Ouvert")
    RESOLVED = "resolved", _("Résolu")


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
        return self.user.get_full_name() or self.user.get_username()


# ---------------------------------------------------------------------------
# 2. Catalogue louable (extension du Part natif)
# ---------------------------------------------------------------------------


class RentableItem(TimestampedModel):
    """Extension OneToOne de `part.Part` — drapeau louable + champs location."""

    part = models.OneToOneField(
        "part.Part",
        on_delete=models.CASCADE,
        related_name="rentable_info",
        verbose_name=_("part"),
    )
    is_rentable = models.BooleanField(default=True, verbose_name=_("louable"))
    consommable = models.BooleanField(default=False, verbose_name=_("consommable"))
    is_virtual = models.BooleanField(default=False, verbose_name=_("article virtuel"))
    # Pas de champ « stock total » ici : le stock physique appartient à
    # InvenTree (`StockItem`). Un compteur parallèle divergeait en silence dès
    # qu'une casse, un achat ou un inventaire était saisi côté InvenTree.
    # Cf. `conflicts.get_part_total_stock`.
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
    seuil_alerte_haut = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("seuil d'alerte haut")
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

    #: Statuts où l'on peut encore ajouter des prestations.
    STATUTS_MODIFIABLES = (
        StatutManifestation.BROUILLON,
        StatutManifestation.PLANIFIEE,
    )

    @property
    def statut_effectif(self):
        """Statut réel : brouillon/annulée explicites, en_cours/terminée dérivés
        des dates dès qu'elle est planifiée."""

        if self.statut in (
            StatutManifestation.BROUILLON,
            StatutManifestation.ANNULEE,
        ):
            return self.statut

        now = timezone.now()

        if now > self.date_fin:
            return StatutManifestation.TERMINEE
        if now >= self.date_debut:
            return StatutManifestation.EN_COURS

        return StatutManifestation.PLANIFIEE

    @property
    def accepte_nouvelles_prestations(self) -> bool:
        """Vrai tant que la manif n'a pas démarré."""

        return self.statut_effectif in self.STATUTS_MODIFIABLES


class Prestation(TimestampedModel):
    """Créneau / service interne à une manifestation."""

    manifestation = models.ForeignKey(
        Manifestation,
        on_delete=models.PROTECT,
        related_name="prestations",
        verbose_name=_("manifestation"),
    )
    # ORG-02 : une prestation se déroule sur un seul lieu (géolocalisé), qu'un
    # même lieu peut porter pour plusieurs prestations (base de CON-06).
    # Nullable pour autoriser les brouillons de prestation.
    lieu = models.ForeignKey(
        "Lieu",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="prestations",
        verbose_name=_("lieu"),
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
    """Site physique géolocalisé, réutilisable par plusieurs prestations.

    Autonome (ORG-01/ORG-02) : le lieu porte adresse et coordonnées GPS et
    n'appartient plus à une prestation. C'est la prestation qui référence son
    lieu unique (``Prestation.lieu``), un même lieu pouvant servir à plusieurs
    prestations — socle de la détection de conflit de lieu (CON-06).
    """

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


class LignePrestation(TimestampedModel):
    """Article (Part natif) et quantité nécessaires à une prestation (RES-09).

    Chaque prestation porte sa propre liste de matériel + quantités. Ces lignes
    alimentent le calcul de stock disponible au jour (STK-01) et la détection
    des conflits de stock.
    """

    prestation = models.ForeignKey(
        Prestation,
        on_delete=models.CASCADE,
        related_name="lignes_prestation",
        verbose_name=_("prestation"),
    )
    part = models.ForeignKey(
        "part.Part",
        on_delete=models.PROTECT,
        related_name="lignes_prestation",
        verbose_name=_("part"),
    )
    quantite = models.PositiveIntegerField(verbose_name=_("quantité"))
    commentaire = models.TextField(
        blank=True, default="", verbose_name=_("commentaire")
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["prestation", "part"]
        verbose_name = _("ligne de prestation")
        verbose_name_plural = _("lignes de prestation")
        constraints = [
            models.UniqueConstraint(
                fields=["prestation", "part"],
                name="unique_prestation_part",
            ),
        ]

    def __str__(self):
        return f"part#{self.part_id} x{self.quantite}"


# ---------------------------------------------------------------------------
# 4. Réservations
# ---------------------------------------------------------------------------


def _generate_reservation_numero(year: int) -> str:
    """Calcule le prochain numéro `RES-{année}-{NNNN}` pour l'année donnée."""

    prefix = f"RES-{year}-"
    last_numero = (
        Reservation.objects.filter(numero__startswith=prefix)
        .order_by("-numero")
        .values_list("numero", flat=True)
        .first()
    )

    next_seq = 1

    if last_numero:
        try:
            next_seq = int(last_numero.rsplit("-", 1)[-1]) + 1
        except ValueError:
            next_seq = 1

    return f"{prefix}{next_seq:04d}"


class Reservation(TimestampedModel):
    """Demande de matériel liée à une prestation."""

    numero = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        blank=True,
        default="",
        verbose_name=_("numéro"),
    )
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
    forced = models.BooleanField(default=False, verbose_name=_("forcée"))
    date_demande = models.DateTimeField(
        default=timezone.now, verbose_name=_("date de demande")
    )
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
    is_archived = models.BooleanField(default=False, verbose_name=_("archivée"))

    class Meta:
        app_label = "inventree_location"
        ordering = ["-date_demande"]
        verbose_name = _("réservation")
        verbose_name_plural = _("réservations")
        indexes = [
            models.Index(
                fields=["date_retrait_prevue", "date_retour_prevue", "statut"],
                name="resa_periode_statut_idx",
            ),
            models.Index(fields=["statut"], name="resa_statut_idx"),
            models.Index(fields=["date_retrait_prevue"], name="resa_retrait_idx"),
            models.Index(fields=["date_retour_prevue"], name="resa_retour_idx"),
            models.Index(fields=["is_archived"], name="resa_archived_idx"),
        ]

    def __str__(self):
        return f"Réservation #{self.pk} — {self.get_statut_display()}"

    def save(self, *args, **kwargs):
        """Génère le numéro `RES-AAAA-NNNN` à la première sauvegarde."""

        if self.numero:
            super().save(*args, **kwargs)
            return

        year = (self.date_demande or timezone.now()).year
        attempts = 5

        for _attempt in range(attempts):
            self.numero = _generate_reservation_numero(year)

            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                return
            except IntegrityError:
                self.numero = ""
                continue

        raise IntegrityError("Impossible de générer un numéro de réservation unique.")


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

    # SCRUM-112 — détail du ramassage et du stock réel.
    quantite_ramassee = models.PositiveIntegerField(
        default=0,
        verbose_name=_("quantité ramassée bonne"),
        help_text=_("Quantité ramassée en bon état, réintégrable au stock réel."),
    )
    quantite_sav = models.PositiveIntegerField(
        default=0,
        verbose_name=_("quantité à mettre au SAV"),
    )
    quantite_detruite = models.PositiveIntegerField(
        default=0,
        verbose_name=_("quantité détruite"),
    )
    quantite_manquante = models.PositiveIntegerField(
        default=0,
        verbose_name=_("quantité manquante"),
    )
    facturer_client = models.BooleanField(
        default=False,
        verbose_name=_("facturer le client"),
    )

    # Valeurs applicatives MVP : "ok" | "sav" | "detruit" | "manquant" | "mixte"
    etat_retour = models.CharField(
        max_length=20, blank=True, default="", verbose_name=_("état du retour")
    )
    # Détail du check-in retour (SCRUM-94) : la somme des 3 doit égaler
    # quantite_demandee. quantite_retournee reste la vue agrégée (ok + casse).
    quantite_retour_ok = models.PositiveIntegerField(
        default=0, verbose_name=_("quantité retournée OK")
    )
    quantite_retour_manquant = models.PositiveIntegerField(
        default=0, verbose_name=_("quantité manquante")
    )
    quantite_retour_casse = models.PositiveIntegerField(
        default=0, verbose_name=_("quantité cassée")
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


class ReturnIncidentType(models.TextChoices):
    MISSING = "missing", _("Manquant")
    BROKEN = "broken", _("Cassé")
    DESTROYED = "destroyed", _("Détruit")


class ReturnIncident(TimestampedModel):
    line = models.ForeignKey(
        LigneReservation,
        on_delete=models.CASCADE,
        related_name="incidents",
        verbose_name=_("ligne de réservation"),
    )
    type = models.CharField(
        max_length=20,
        choices=ReturnIncidentType.choices,
        verbose_name=_("type d'incident"),
    )
    qty = models.PositiveIntegerField(verbose_name=_("quantité"))
    comment = models.TextField(
        blank=True,
        default="",
        verbose_name=_("commentaire"),
    )
    reported_at = models.DateTimeField(
        default=timezone.now,
        verbose_name=_("date de signalement"),
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reported_incidents",
        verbose_name=_("signalé par"),
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["-reported_at"]
        verbose_name = _("incident de retour")
        verbose_name_plural = _("incidents de retour")

    def __str__(self):
        return f"Incident #{self.pk} ({self.type}) — Ligne#{self.line_id}"


class ReservationStatusLog(TimestampedModel):
    """Journal des transitions de statut d'une réservation."""

    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="status_logs",
        verbose_name=_("réservation"),
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reservation_status_changes",
        verbose_name=_("modifié par"),
    )
    from_status = models.CharField(
        max_length=20,
        choices=StatutReservation.choices,
        verbose_name=_("ancien statut"),
    )
    to_status = models.CharField(
        max_length=20,
        choices=StatutReservation.choices,
        verbose_name=_("nouveau statut"),
    )
    comment = models.TextField(
        blank=True,
        default="",
        verbose_name=_("commentaire"),
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["-created_at"]
        verbose_name = _("log de statut de réservation")
        verbose_name_plural = _("logs de statut de réservation")
        indexes = [
            models.Index(
                fields=["reservation", "created_at"],
                name="resa_status_log_idx",
            ),
        ]

    def __str__(self):
        return (
            f"Réservation #{self.reservation_id}: {self.from_status} → {self.to_status}"
        )


# ---------------------------------------------------------------------------
# 5. SAV / stock réel
# ---------------------------------------------------------------------------


class SavTicket(TimestampedModel):
    """Ticket SAV ou destruction lié à une ligne de réservation.

    SCRUM-112 :
    - un article endommagé sort du stock réellement disponible ;
    - il peut être réintégré après réparation ;
    - les destructions restent consultables par période.
    """

    ligne_reservation = models.ForeignKey(
        LigneReservation,
        on_delete=models.CASCADE,
        related_name="sav_tickets",
        verbose_name=_("ligne de réservation"),
    )
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="sav_tickets",
        verbose_name=_("réservation"),
    )
    part = models.ForeignKey(
        "part.Part",
        on_delete=models.PROTECT,
        related_name="location_sav_tickets",
        verbose_name=_("part"),
    )
    type_ticket = models.CharField(
        max_length=20,
        choices=TypeSavTicket.choices,
        default=TypeSavTicket.REPARATION,
        verbose_name=_("type de ticket"),
    )
    statut = models.CharField(
        max_length=20,
        choices=StatutSavTicket.choices,
        default=StatutSavTicket.OUVERT,
        verbose_name=_("statut"),
    )
    quantite = models.PositiveIntegerField(default=1, verbose_name=_("quantité"))
    facturer_client = models.BooleanField(
        default=False,
        verbose_name=_("facturer le client"),
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name=_("description"),
    )
    diagnostic = models.TextField(
        blank=True,
        default="",
        verbose_name=_("diagnostic"),
    )
    resolution = models.TextField(
        blank=True,
        default="",
        verbose_name=_("résolution"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sav_tickets_created",
        verbose_name=_("créé par"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sav_tickets_updated",
        verbose_name=_("modifié par"),
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("date de clôture"),
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["-created_at"]
        verbose_name = _("ticket SAV")
        verbose_name_plural = _("tickets SAV")
        constraints = [
            models.UniqueConstraint(
                fields=["ligne_reservation", "type_ticket"],
                name="unique_sav_ticket_by_line_type",
            ),
        ]
        indexes = [
            models.Index(fields=["part", "statut"], name="sav_part_statut_idx"),
            models.Index(fields=["created_at"], name="sav_created_at_idx"),
        ]

    def __str__(self):
        return f"SAV #{self.pk} — part#{self.part_id} x{self.quantite} — {self.statut}"


class ConflictHistory(TimestampedModel):
    """Historique des conflits détectés (ouverts et résolus)."""

    conflict_type = models.CharField(
        max_length=20,
        choices=ConflictType.choices,
        verbose_name=_("type de conflit"),
    )
    state = models.CharField(
        max_length=20,
        choices=ConflictState.choices,
        default=ConflictState.OPEN,
        verbose_name=_("état"),
    )
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="conflict_history",
        verbose_name=_("réservation"),
    )
    conflicting_reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="conflicted_by_history",
        verbose_name=_("réservation en conflit"),
    )
    part = models.ForeignKey(
        "part.Part",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="conflict_history",
        verbose_name=_("article"),
    )
    period_start = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("début période"),
    )
    period_end = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("fin période"),
    )
    location_key = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("clé de lieu"),
    )
    details = models.JSONField(default=dict, blank=True, verbose_name=_("détails"))
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("résolu le"),
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="resolved_conflicts",
        verbose_name=_("résolu par"),
    )
    resolution_note = models.TextField(
        blank=True,
        default="",
        verbose_name=_("note de résolution"),
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["-created_at"]
        verbose_name = _("historique de conflit")
        verbose_name_plural = _("historiques de conflit")
        indexes = [
            models.Index(
                fields=["conflict_type", "state"], name="conflict_type_state_idx"
            ),
            models.Index(
                fields=["reservation", "state"], name="conflict_resa_state_idx"
            ),
            models.Index(fields=["created_at"], name="conflict_created_at_idx"),
        ]

    def __str__(self):
        return f"{self.conflict_type}:{self.reservation_id}:{self.state}"
