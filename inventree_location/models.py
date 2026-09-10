"""Modèles Django du plugin InvenTreeLocation (zone MVP, schéma DB-01 v2).

Le catalogue matériel (`Part`, `PartCategory`) et l'historique stock
(`StockItemTracking`) sont fournis nativement par InvenTree — on ne les
recrée pas ici. Le plugin se limite à 8 tables propres :

1. Client — Personne morale ou particulier, et ses Contact
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

from decimal import Decimal

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


class TypeClient(models.TextChoices):
    ENTREPRISE = "entreprise", _("Entreprise ou association")
    PARTICULIER = "particulier", _("Particulier")


class StatutPrestation(models.TextChoices):
    """Avancement d'une prestation.

    Les articles ne sont modifiables qu'en `brouillon` et `planifiee` : un devis
    accepté fait passer la prestation en `confirmee` et toute modification
    ultérieure devient une ligne « hors devis » (cf. `EtatLigne`).
    """

    BROUILLON = "brouillon", _("Brouillon")
    PLANIFIEE = "planifiee", _("Planifiée")
    CONFIRMEE = "confirmee", _("Confirmée")
    LIVREE = "livree", _("Livrée")
    CLOTUREE = "cloturee", _("Clôturée")
    ANNULEE = "annulee", _("Annulée")

    @classmethod
    def modifiables(cls):
        """Statuts où l'on peut encore ajouter ou retirer des articles."""

        return (cls.BROUILLON, cls.PLANIFIEE)


class StatutReservation(models.TextChoices):
    BROUILLON = "brouillon", _("Brouillon")
    SOUMISE = "soumise", _("Soumise")
    VALIDEE = "validee", _("Validée")
    REFUSEE = "refusee", _("Refusée")
    ANNULEE = "annulee", _("Annulée")
    LIVREE = "livree", _("Livrée")
    RETOURNEE = "retournee", _("Retournée")
    CLOTUREE = "cloturee", _("Clôturée")


class EtatLivraison(models.TextChoices):
    """Avancement d'une livraison prise en charge par un livreur (US-18/US-19).

    Orthogonal au statut de la réservation : une réservation validée reste
    « à livrer » tant que personne ne l'a prise, et la chaîne complète est
    assignée → en cours → livrée (ou problème signalé). La valeur vide, qui
    n'est pas un choix, dit « personne ne s'en occupe » : c'est l'état du pool
    commun où tout livreur peut se servir.
    """

    ASSIGNEE = "assignee", _("Assignée")
    EN_COURS = "en_cours", _("En cours de livraison")
    LIVREE = "livree", _("Livrée")
    PROBLEME = "probleme", _("Problème signalé")


class TypeSavTicket(models.TextChoices):
    REPARATION = "reparation", _("Réparation")
    DESTRUCTION = "destruction", _("Destruction")


class StatutSavTicket(models.TextChoices):
    OUVERT = "ouvert", _("Ouvert")
    EN_REPARATION = "en_reparation", _("En réparation")
    REPARE = "repare", _("Réparé")
    DETRUIT = "detruit", _("Détruit")
    CLOTURE = "cloture", _("Clôturé")


class EtatRetour(models.TextChoices):
    """Vocabulaire unique de `LigneReservation.etat_retour`.

    Trois fonctionnalités écrivaient cette colonne avec chacune ses valeurs —
    `casse` pour le journal d'incidents et le check-in, `sav` / `detruit` /
    `mixte` pour la saisie de ramassage. Un même retour s'affichait donc
    différemment selon l'écran qui l'avait saisi. La nuance « au SAV » ou
    « détruit » vit désormais dans les incidents et les tickets SAV, pas ici.

    Quand plusieurs natures coexistent sur une ligne, **la plus grave
    l'emporte** : c'est la règle de la PR #45, nommée par ses tests
    (« casse prime sur manquant »). Le `mixte` de la PR #40 la contredisait
    sans la remplacer — il disait qu'il s'était passé plusieurs choses sans dire
    lesquelles, et le détail est de toute façon dans les incidents.

    La valeur vide reste distincte : « pas encore pointé » n'est pas « OK ».
    """

    OK = "ok", _("Rendu conforme")
    MANQUANT = "manquant", _("Manquant")
    CASSE = "casse", _("Cassé")


class ConflictType(models.TextChoices):
    STOCK = "stock", _("Conflit de stock")
    LOCATION = "location", _("Conflit de lieu")


class ConflictState(models.TextChoices):
    OPEN = "open", _("Ouvert")
    RESOLVED = "resolved", _("Résolu")


#: Taux de TVA en vigueur en France (CDC §46). En choix et non en table : ils
#: changent par la loi, pas par la saisie.
TAUX_TVA_CHOICES = [
    (Decimal("20.00"), _("20 % — taux normal")),
    (Decimal("10.00"), _("10 % — taux intermédiaire")),
    (Decimal("5.50"), _("5,5 % — taux réduit")),
    (Decimal("2.10"), _("2,1 % — taux particulier")),
]


class EtatLigne(models.TextChoices):
    """État d'une ligne de bon vis-à-vis du devis accepté (CDC §45).

    Un devis signé ne verrouille pas le bon : une ligne ajoutée après coup est
    « hors devis », une retirée est « annulée ». Ce couple rend la facture
    calculable, et `ANNULEE` est la seule dispense à « livrer le bon en
    entier ».
    """

    NORMALE = "normale", _("Au devis")
    HORS_DEVIS = "hors_devis", _("Hors devis")
    ANNULEE = "annulee", _("Annulée")


class CanalModification(models.TextChoices):
    """Canal de la demande de modification (CDC §45 : « tél., mail, verbal »)."""

    TELEPHONE = "telephone", _("Téléphone")
    MAIL = "mail", _("E-mail")
    VERBAL = "verbal", _("Verbal")
    COURRIER = "courrier", _("Courrier")


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


class Client(TimestampedModel):
    """Personne morale ou particulier qui loue du matériel.

    Anciennement `Groupe`, dont le docstring disait lui-même « organisation
    propriétaire, mono-tenant » : c'était le tenant, pas le client. Le point du
    09/09/2026 a tranché — un client est une personne morale, et chaque
    interlocuteur est un `Contact`.

    `email` est unique mais **nullable** : les clients repris n'en avaient pas,
    et inventer une adresse mettrait de la fausse donnée en base. NULL ne
    collisionne pas dans un index unique.
    """

    nom = models.CharField(max_length=120, unique=True, verbose_name=_("nom"))
    adresse = models.TextField(blank=True, default="", verbose_name=_("adresse"))
    email = models.EmailField(
        unique=True, null=True, blank=True, verbose_name=_("e-mail")
    )
    telephone = models.CharField(
        max_length=30, blank=True, default="", verbose_name=_("téléphone")
    )
    type_client = models.CharField(
        max_length=20,
        choices=TypeClient.choices,
        blank=True,
        default="",
        verbose_name=_("type de client"),
    )
    siret = models.CharField(
        max_length=20, blank=True, default="", verbose_name=_("SIRET")
    )
    # Le portefeuille : « un gestionnaire client gère un ou plusieurs clients »
    # (09/09). C'est ce champ qui alimente « la liste de mes clients ».
    gestionnaire = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clients_geres",
        verbose_name=_("gestionnaire référent"),
    )
    # On désactive, on ne supprime pas : les manifestations passées doivent
    # rester lisibles.
    actif = models.BooleanField(default=True, verbose_name=_("actif"))

    class Meta:
        app_label = "inventree_location"
        ordering = ["nom"]
        verbose_name = _("client")
        verbose_name_plural = _("clients")

    def __str__(self):
        return self.nom


class Contact(TimestampedModel):
    """Personne physique rattachée à un client.

    Sans compte : le client externe n'accède pas à la plateforme, c'est le
    gestionnaire commercial qui le représente (09/09). `email` est unique
    globalement et nullable, pour la même raison que sur `Client`.
    """

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="contacts",
        verbose_name=_("client"),
    )
    nom = models.CharField(max_length=120, verbose_name=_("nom"))
    prenom = models.CharField(
        max_length=120, blank=True, default="", verbose_name=_("prénom")
    )
    email = models.EmailField(
        unique=True, null=True, blank=True, verbose_name=_("e-mail")
    )
    telephone = models.CharField(
        max_length=30, blank=True, default="", verbose_name=_("téléphone")
    )
    # Un contact qui quitte l'entreprise sort des listes sans disparaître des
    # devis qu'il a signés.
    actif = models.BooleanField(default=True, verbose_name=_("actif"))

    class Meta:
        app_label = "inventree_location"
        ordering = ["client", "nom", "prenom"]
        verbose_name = _("contact")
        verbose_name_plural = _("contacts")

    def __str__(self):
        return f"{self.prenom} {self.nom}".strip()


class Profile(models.Model):
    """Extension OneToOne du User Django — attributs métier."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="location_profile",
        verbose_name=_("utilisateur"),
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
    # Nul et non zéro : « inconnu » n'est pas « 0 kg », qui fausserait toute
    # somme de chargement de camion. Même doctrine que `caution`.
    poids = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name=_("poids unitaire (kg)"),
    )
    seuil_alerte_bas = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("seuil d'alerte bas")
    )
    seuil_alerte_haut = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("seuil d'alerte haut")
    )
    #: Coupe les alertes de seuil pour cet article, sans effacer les seuils
    #: eux-mêmes (CDC V06 : « seuil haut + seuil bas + booléen pour désactiver
    #: les alertes »). Un article dont on connaît les seuils mais qu'on ne veut
    #: pas voir remonter — surplus assumé, article en fin de vie.
    # Tarification (CDC §46). Deux voies exclusives : grille propre
    # (`PalierTarif`) ou table partagée (`TableRemise`). `prix_location_ht` est
    # le prix de base, quand aucun palier ne mord.
    prix_location_ht = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_("prix de location HT"),
    )
    taux_tva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        choices=TAUX_TVA_CHOICES,
        default=Decimal("20.00"),
        verbose_name=_("taux de TVA"),
    )
    table_remise = models.ForeignKey(
        "inventree_location.TableRemise",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="articles",
        verbose_name=_("table de remise"),
    )
    alertes_desactivees = models.BooleanField(
        default=False,
        verbose_name=_("alertes désactivées"),
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
    # Couleur d'affichage choisie par le gestionnaire. Le calendrier des
    # réservations garde ses couleurs par statut (`calendrier.STATUT_COULEURS`) :
    # celle-ci est destinée au planning au niveau manifestation.
    couleur = models.CharField(
        max_length=7,
        blank=True,
        default="",
        verbose_name=_("couleur"),
    )
    # Remise appliquée au total HT, après les paliers de quantité.
    pourcent_remise_globale = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("remise globale (%)"),
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="manifestations",
        verbose_name=_("client"),
    )
    # Le contact référent : celui qu'on appelle sur place, et celui qui signe.
    contact = models.ForeignKey(
        "Contact",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="manifestations",
        verbose_name=_("contact référent"),
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
    statut = models.CharField(
        max_length=20,
        choices=StatutPrestation.choices,
        default=StatutPrestation.BROUILLON,
        verbose_name=_("statut"),
    )
    # Levé dès qu'un article change après acceptation d'un devis. Le détail —
    # qui, par quel canal, quand — vit dans `ModificationBon`.
    modifie_apres_devis = models.BooleanField(
        default=False,
        verbose_name=_("modifiée après le devis"),
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
    description = models.TextField(
        blank=True, default="", verbose_name=_("description")
    )
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
    # US-18 : les livraisons validées forment un pool commun ; le premier
    # livreur qui accepte se l'attribue, et peut la relâcher tant qu'il ne l'a
    # pas commencée.
    livreur_assigne = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="livraisons_assignees",
        verbose_name=_("livreur assigné"),
    )
    date_assignation = models.DateTimeField(
        null=True, blank=True, verbose_name=_("date d'assignation")
    )
    etat_livraison = models.CharField(
        max_length=20,
        choices=EtatLivraison.choices,
        blank=True,
        default="",
        verbose_name=_("état de la livraison"),
    )
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
    #: Ce qui est revenu physiquement, conforme ou non — seule quantité de
    #: retour stockée ici. Trois fonctionnalités avaient ajouté sept colonnes
    #: pour dire ce que le registre `ReturnIncident` dit déjà (combien manque,
    #: combien est cassé, combien est détruit, et faut-il facturer) ; elles se
    #: contredisaient dès que deux écrans pointaient la même ligne. Cf.
    #: `retours.quantites_du_retour` et la migration `0021`.
    quantite_retournee = models.PositiveIntegerField(
        default=0, verbose_name=_("quantité revenue")
    )

    # Vocabulaire unique : cf. `EtatRetour` et `retours.py`.
    etat_retour = models.CharField(
        max_length=20,
        blank=True,
        default="",
        choices=EtatRetour.choices,
        verbose_name=_("état du retour"),
    )
    # Voir `EtatLigne`.
    etat = models.CharField(
        max_length=20,
        choices=EtatLigne.choices,
        default=EtatLigne.NORMALE,
        verbose_name=_("état vis-à-vis du devis"),
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
    # Déclaré explicitement : cette table a été créée en `BigAutoField`
    # (migration d'origine). Sans cette ligne, `makemigrations` propose de la
    # rétrograder en `AutoField` à chaque passage.
    id = models.BigAutoField(primary_key=True)

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
    #: Décision commerciale prise au constat, indépendante du type : un objet
    #: manquant n'est pas toujours refacturé (geste commercial, usure normale),
    #: et un objet cassé peut l'être. C'est ce drapeau, et non le type, qui
    #: alimente le total « facturé » du rapport de pertes (SCRUM-96).
    bill_client = models.BooleanField(
        default=False,
        verbose_name=_("facturer au client"),
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


class LivraisonStatusLog(TimestampedModel):
    """Journal des changements d'état d'une livraison (US-19).

    Distinct de `ReservationStatusLog`, qui suit le statut métier de la
    réservation : ici on trace le terrain — qui a pris la livraison, quand elle
    est partie, et la photo du problème éventuel.
    """

    # Déclaré explicitement : cette table a été créée en `BigAutoField`
    # (migration d'origine). Sans cette ligne, `makemigrations` propose de la
    # rétrograder en `AutoField` à chaque passage.
    id = models.BigAutoField(primary_key=True)

    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="livraison_status_logs",
        verbose_name=_("réservation"),
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="livraison_status_changes",
        verbose_name=_("modifié par"),
    )
    # Les deux bornes acceptent la chaîne vide : elle dit « pas d'assignation »,
    # au départ comme après un relâchement.
    from_etat = models.CharField(
        max_length=20,
        choices=EtatLivraison.choices,
        blank=True,
        default="",
        verbose_name=_("ancien état"),
    )
    to_etat = models.CharField(
        max_length=20,
        choices=EtatLivraison.choices,
        blank=True,
        default="",
        verbose_name=_("nouvel état"),
    )
    commentaire = models.TextField(
        blank=True,
        default="",
        verbose_name=_("commentaire"),
    )
    photo = models.ImageField(
        upload_to="inventree_location/livraisons/%Y/%m/",
        null=True,
        blank=True,
        verbose_name=_("photo"),
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["-created_at"]
        verbose_name = _("log d'état de livraison")
        verbose_name_plural = _("logs d'état de livraison")
        indexes = [
            models.Index(
                fields=["reservation", "created_at"],
                name="livraison_status_log_idx",
            ),
        ]

    def __str__(self):
        return (
            f"Livraison #{self.reservation_id}: "
            f"{self.from_etat or '—'} → {self.to_etat or '—'}"
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

    # Déclaré explicitement : cette table a été créée en `BigAutoField`
    # (migration d'origine). Sans cette ligne, `makemigrations` propose de la
    # rétrograder en `AutoField` à chaque passage.
    id = models.BigAutoField(primary_key=True)

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

    # Déclaré explicitement : cette table a été créée en `BigAutoField`
    # (migration d'origine). Sans cette ligne, `makemigrations` propose de la
    # rétrograder en `AutoField` à chaque passage.
    id = models.BigAutoField(primary_key=True)

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


# ---------------------------------------------------------------------------
# Tarification (CDC V06 § « Le devis est établi […] sur la base d'un tarif
# unitaire € HT pour chaque objet »)
# ---------------------------------------------------------------------------


class TableRemise(TimestampedModel):
    """Grille de remises par quantité, partagée par plusieurs objets.

    Seconde des deux voies de tarification du CDC §46 ; `PalierTarif` est la
    première. Exclusives par objet — règle applicative, elle porte sur
    l'existence de lignes liées.
    """

    nom = models.CharField(max_length=120, unique=True, verbose_name=_("nom"))
    description = models.TextField(
        blank=True, default="", verbose_name=_("description")
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["nom"]
        verbose_name = _("table de remise")
        verbose_name_plural = _("tables de remise")

    def __str__(self):
        return self.nom


class PalierRemise(models.Model):
    """Un des cinq niveaux d'une `TableRemise` : à partir de N, X % de remise."""

    table = models.ForeignKey(
        TableRemise,
        on_delete=models.CASCADE,
        related_name="paliers",
        verbose_name=_("table de remise"),
    )
    quantite_min = models.PositiveIntegerField(verbose_name=_("quantité minimale"))
    pourcentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name=_("pourcentage de remise"),
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["table", "quantite_min"]
        constraints = [
            models.UniqueConstraint(
                fields=["table", "quantite_min"],
                name="unique_palier_remise_par_quantite",
            ),
        ]
        verbose_name = _("palier de remise")
        verbose_name_plural = _("paliers de remise")

    def __str__(self):
        return f"≥{self.quantite_min} → −{self.pourcentage} %"


class PalierTarif(models.Model):
    """Grille de prix propre à un objet : à partir de N, tel prix unitaire HT.

    Le prix est **absolu**, pas une remise (exemple du CDC §46).
    """

    rentable_item = models.ForeignKey(
        RentableItem,
        on_delete=models.CASCADE,
        related_name="paliers_tarif",
        verbose_name=_("article louable"),
    )
    quantite_min = models.PositiveIntegerField(verbose_name=_("quantité minimale"))
    prix_ht = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("prix unitaire HT"),
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["rentable_item", "quantite_min"]
        constraints = [
            models.UniqueConstraint(
                fields=["rentable_item", "quantite_min"],
                name="unique_palier_tarif_par_quantite",
            ),
        ]
        verbose_name = _("palier de tarif")
        verbose_name_plural = _("paliers de tarif")

    def __str__(self):
        return f"≥{self.quantite_min} → {self.prix_ht} € HT"


# ---------------------------------------------------------------------------
# Devis et facturation
# ---------------------------------------------------------------------------


class StatutDevis(models.TextChoices):
    """Cycle de vie d'un devis.

    Un devis accepté n'a **aucune transition sortante** : c'est une pièce
    signée. La suite se joue sur les lignes des bons (`EtatLigne`).
    """

    BROUILLON = "brouillon", _("Brouillon")
    EMIS = "emis", _("Émis")
    ACCEPTE = "accepte", _("Accepté")
    REFUSE = "refuse", _("Refusé")
    ANNULE = "annule", _("Annulé")


class SupportAcceptation(models.TextChoices):
    """Par quel canal le client a accepté le devis (CDC § acceptation)."""

    EMAIL = "email", _("E-mail")
    COURRIER = "courrier", _("Courrier")
    TELEPHONE = "telephone", _("Téléphone")
    VERBAL = "verbal", _("Verbal")
    SUR_PLACE = "sur_place", _("Signature sur place")


class Devis(TimestampedModel):
    """Devis rattaché à une **manifestation**, pas à une réservation.

    N↔M vers les bons (CDC §45, §82), d'où le `ManyToMany`. Montants et
    libellé du signataire **figés à l'émission** : un devis signé ne change pas
    de total quand le tarif catalogue bouge.
    """

    manifestation = models.ForeignKey(
        Manifestation,
        on_delete=models.PROTECT,
        related_name="devis",
        verbose_name=_("manifestation"),
    )
    bons = models.ManyToManyField(
        Reservation,
        related_name="devis",
        blank=True,
        verbose_name=_("bons de réservation"),
    )
    numero = models.CharField(
        max_length=30,
        unique=True,
        verbose_name=_("numéro"),
    )
    statut = models.CharField(
        max_length=20,
        choices=StatutDevis.choices,
        default=StatutDevis.BROUILLON,
        verbose_name=_("statut"),
    )
    date_emission = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("date d'émission"),
    )
    date_acceptation = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("date d'acceptation"),
    )
    support_acceptation = models.CharField(
        max_length=20,
        choices=SupportAcceptation.choices,
        blank=True,
        default="",
        verbose_name=_("support d'acceptation"),
    )
    motif_refus = models.TextField(
        blank=True,
        default="",
        verbose_name=_("motif du refus"),
    )
    # Contact du client **ou** client lui-même. Instantané : si le contact part,
    # le devis doit toujours dire qui a signé. La FK `signataire_contact`
    # arrivera avec le modèle `Contact`.
    signataire_libelle = models.CharField(
        max_length=200,
        blank=True,
        default="",
        verbose_name=_("signataire"),
    )
    montant_ht = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name=_("montant HT"),
    )
    montant_tva = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name=_("montant TVA"),
    )
    montant_ttc = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name=_("montant TTC"),
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["statut"], name="devis_statut_idx"),
            models.Index(fields=["manifestation"], name="devis_manifestation_idx"),
        ]
        verbose_name = _("devis")
        verbose_name_plural = _("devis")

    def __str__(self):
        return self.numero


class LigneDevis(TimestampedModel):
    """Ligne d'un devis — **instantané figé**, pas une vue sur le catalogue.

    Prix, TVA et remise recopiés à l'émission : un devis se réédite à
    l'identique six mois plus tard.
    """

    devis = models.ForeignKey(
        Devis,
        on_delete=models.CASCADE,
        related_name="lignes",
        verbose_name=_("devis"),
    )
    part = models.ForeignKey(
        "part.Part",
        on_delete=models.PROTECT,
        related_name="lignes_devis",
        verbose_name=_("article"),
    )
    quantite = models.PositiveIntegerField(verbose_name=_("quantité"))
    prix_unitaire_ht = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name=_("prix unitaire HT"),
    )
    taux_tva = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        choices=TAUX_TVA_CHOICES,
        default=Decimal("20.00"),
        verbose_name=_("taux de TVA"),
    )
    remise_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("remise (%)"),
    )
    montant_ht = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name=_("montant HT"),
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["devis", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["devis", "part"],
                name="unique_ligne_devis_par_article",
            ),
        ]
        verbose_name = _("ligne de devis")
        verbose_name_plural = _("lignes de devis")

    def __str__(self):
        return f"{self.devis_id} — part#{self.part_id} ×{self.quantite}"


class FactureReservation(TimestampedModel):
    """Facture, rattachée à **un ou plusieurs** devis (CDC §88).

    Tables et clés étrangères seulement : aucun écran, aucun calcul de montant.
    """

    numero = models.CharField(
        max_length=30,
        unique=True,
        verbose_name=_("numéro"),
    )
    devis = models.ManyToManyField(
        Devis,
        related_name="factures",
        verbose_name=_("devis"),
    )
    date_emission = models.DateField(verbose_name=_("date d'émission"))
    montant_total_ht = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name=_("montant total HT"),
    )
    remise_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        verbose_name=_("remise (%)"),
    )
    entierement_regle = models.BooleanField(
        default=False,
        verbose_name=_("entièrement réglé"),
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["-date_emission"]
        verbose_name = _("facture")
        verbose_name_plural = _("factures")

    def __str__(self):
        return self.numero


# ---------------------------------------------------------------------------
# Traçabilité des modifications après acceptation d'un devis
# ---------------------------------------------------------------------------


class ModificationBon(TimestampedModel):
    """Journal des modifications d'objets d'un bon après acceptation d'un devis.

    Le CDC §45 exige quatre informations : personne, message, canal,
    horodatage. Rattaché au **bon** et non à la ligne : `_replace_lignes`
    recrée les lignes à chaque édition et effacerait le journal.
    """

    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="modifications",
        verbose_name=_("bon de réservation"),
    )
    part = models.ForeignKey(
        "part.Part",
        on_delete=models.PROTECT,
        related_name="modifications_bon",
        verbose_name=_("article"),
    )
    auteur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modifications_bon",
        verbose_name=_("auteur"),
    )
    canal = models.CharField(
        max_length=20,
        choices=CanalModification.choices,
        verbose_name=_("canal de la demande"),
    )
    message = models.TextField(
        blank=True,
        default="",
        verbose_name=_("message à l'origine"),
    )
    etat_resultant = models.CharField(
        max_length=20,
        choices=EtatLigne.choices,
        verbose_name=_("état résultant de la ligne"),
    )

    class Meta:
        app_label = "inventree_location"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["reservation"], name="modif_bon_resa_idx"),
        ]
        verbose_name = _("modification de bon")
        verbose_name_plural = _("modifications de bon")

    def __str__(self):
        return f"{self.reservation_id} — part#{self.part_id} → {self.etat_resultant}"
