"""API serializers for the InvenTreeLocation plugin."""

import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from .conflicts import (
    detect_location_reservation_conflicts,
    detect_reservation_conflicts,
    register_location_conflict_history,
    register_stock_conflict_history,
)
from .models import (
    Groupe,
    LignePrestation,
    LigneReservation,
    Lieu,
    Manifestation,
    Reservation,
    ReservationStatusLog,
    Prestation,
    RentableItem,
    ReturnIncident,
    ReturnIncidentType,
    StatutManifestation,
    StatutReservation,
)
from .services.workflow_service import transition_reservation_status
from .stock import compute_prestation_stock
from .ramassage import lignes_a_ramasser
from .retours import appliquer_etat_retour
from .sav import get_real_available_stock


# Produit français : on restreint le géocodage à la France pour éviter les
# faux positifs à l'étranger (ex. « Champ de Mars » → un pic au Québec).
GEOCODE_COUNTRY_CODES = "fr"


def _nominatim_search(address, limit):
    """Query OpenStreetMap Nominatim (restricted to France) and return the raw list."""

    query = urlencode({
        "q": address,
        "format": "json",
        "limit": limit,
        "countrycodes": GEOCODE_COUNTRY_CODES,
    })

    url = f"https://nominatim.openstreetmap.org/search?{query}"

    request = Request(
        url,
        headers={
            "User-Agent": "inventree-location-plugin/0.1",
        },
    )

    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def geocode_candidates(address, limit=5):
    """Return up to ``limit`` geocoding candidates for an address.

    Une recherche texte libre est souvent ambiguë (« Champs de Mars » matche
    plusieurs lieux en France) : on renvoie donc plusieurs candidats pour que
    l'utilisateur choisisse le bon plutôt que de deviner à sa place.
    """

    if not address:
        return []

    payload = _nominatim_search(address, limit)

    return [
        {
            "display_name": item.get("display_name"),
            "latitude": _round_coord(item.get("lat")),
            "longitude": _round_coord(item.get("lon")),
        }
        for item in payload
    ]


def geocode_address(address):
    """Return the single best GPS match for an address (auto-geocode serveur)."""

    if not address:
        return None

    payload = _nominatim_search(address, 1)

    if not payload:
        return None

    first_result = payload[0]

    return {
        "address": address,
        "display_name": first_result.get("display_name"),
        "latitude": _round_coord(first_result.get("lat")),
        "longitude": _round_coord(first_result.get("lon")),
        "source": "OpenStreetMap Nominatim",
    }


def _round_coord(value):
    """Round a coordinate to 6 decimal places (the DB column precision).

    Nominatim renvoie souvent 7+ décimales, ce qui dépasse le
    ``decimal_places=6`` du modèle ``Lieu`` et fait échouer la validation.
    """

    if value is None:
        return None

    try:
        rounded = Decimal(str(value)).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, ValueError):
        return value

    # Fixed-point (jamais de notation scientifique), sans zéros de fin.
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")

    return text


def _user_label(user):
    """Nom lisible d'un utilisateur : « Prénom Nom (username) », sinon username."""

    if user is None:
        return ""

    full_name = f"{user.first_name} {user.last_name}".strip()

    return f"{full_name} ({user.username})" if full_name else user.username


def _user_phone(user):
    """Téléphone de l'utilisateur (via son `Profile`), vide si non renseigné.

    `Profile` n'est jamais auto-créé (pas de signal) : l'accès reverse
    OneToOne lève `Profile.DoesNotExist`, pas une `AttributeError` — un
    `getattr(user, "location_profile", None)` ne l'attraperait pas.

    On attrape `ObjectDoesNotExist`, la classe mère de Django, et non
    `Profile.DoesNotExist` : dans le conteneur, le chargeur de plugins importe
    `inventree_location.models` deux fois, si bien que le `Profile` de ce module
    n'est pas celui auquel la relation inverse est rattachée. Un `except
    Profile.DoesNotExist` ne filtrait donc rien et `/deliveries/` répondait 500
    (« User has no location_profile. ») pour tout utilisateur sans profil. La
    suite pytest ne peut pas voir ce cas : hors InvenTree, le module n'existe
    qu'en un seul exemplaire.
    """

    if user is None:
        return ""

    try:
        return user.location_profile.telephone
    except ObjectDoesNotExist:
        return ""


class LigneReservationSerializer(serializers.ModelSerializer):
    """Sérialiseur d'une ligne de réservation."""

    class Meta:
        """Configuration du serializer LigneReservation."""

        model = LigneReservation
        fields = [
            "id",
            "part",
            "quantite_demandee",
            "quantite_livree",
            "quantite_retournee",
            "quantite_ramassee",
            "quantite_sav",
            "quantite_detruite",
            "quantite_manquante",
            "facturer_client",
            "etat_retour",
            "quantite_retour_ok",
            "quantite_retour_manquant",
            "quantite_retour_casse",
            "commentaire",
        ]
        # Le détail du retour n'appartient qu'au check-in magasinier
        # (`ReservationCheckinView` / `ReturnCheckinPermission`) : exposé en
        # écriture ici, il serait modifiable par tout rôle autorisé à éditer
        # une réservation, et remis à zéro à chaque réécriture des lignes.
        read_only_fields = [
            "id",
            "quantite_retour_ok",
            "quantite_retour_manquant",
            "quantite_retour_casse",
        ]


def sync_ligne_etat_retour(ligne):
    """Recalcule `etat_retour` d'une ligne (cf. `retours.py`).

    Conservée comme point d'entrée des vues d'incidents ; la règle elle-même
    vit dans `retours.appliquer_etat_retour`, partagée avec le check-in et la
    saisie de ramassage.
    """

    appliquer_etat_retour(ligne)


class ReturnIncidentSerializer(serializers.ModelSerializer):
    """Sérialiseur d'un incident de retour."""

    # Déclaré explicitement : le `ChoiceField` implicite du ModelSerializer
    # rejette la valeur avant tout `validate_type`, dont le message français
    # n'atteignait donc jamais le client.
    type = serializers.ChoiceField(
        choices=ReturnIncidentType.choices,
        error_messages={
            "invalid_choice": "Type d'incident invalide : manquant ou cassé attendu."
        },
    )
    qty = serializers.IntegerField(
        min_value=1,
        error_messages={"min_value": "La quantité signalée doit être d'au moins 1."},
    )
    line_part_name = serializers.CharField(source="line.part.name", read_only=True)
    line_reservation_numero = serializers.CharField(
        source="line.reservation.numero", read_only=True
    )
    reported_by_username = serializers.CharField(
        source="reported_by.username", read_only=True, allow_null=True
    )

    class Meta:
        """Configuration du serializer ReturnIncident."""

        model = ReturnIncident
        fields = [
            "id",
            "line",
            "line_part_name",
            "line_reservation_numero",
            "type",
            "qty",
            "comment",
            "bill_client",
            "reported_at",
            "reported_by",
            "reported_by_username",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "line_part_name",
            "line_reservation_numero",
            "reported_at",
            "reported_by",
            "reported_by_username",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        """Le cumul des incidents d'une ligne ne peut pas dépasser sa quantité.

        Le plafond porte sur le cumul, pas sur l'incident isolé : deux
        signalements de 3 sur une ligne de 3 passaient tous les deux, et la
        ligne se retrouvait avec 6 unités en incident pour 3 engagées.
        """

        line = attrs.get("line") or getattr(self.instance, "line", None)

        if line is not None:
            qty = attrs.get("qty", getattr(self.instance, "qty", 0))
            # `quantite_livree` n'est renseignée par aucun endpoint à ce jour :
            # le plafond retombe alors sur la quantité demandée.
            max_qty = line.quantite_livree or line.quantite_demandee

            autres = line.incidents.all()

            if self.instance is not None:
                autres = autres.exclude(pk=self.instance.pk)

            deja_signale = autres.aggregate(total=Sum("qty"))["total"] or 0

            if deja_signale + qty > max_qty:
                raise serializers.ValidationError({
                    "qty": (
                        f"La quantité signalée ({deja_signale + qty} au total) "
                        f"dépasse la quantité disponible ({max_qty})."
                    )
                })

        return attrs

    def create(self, validated_data):
        """Crée l'incident et met à jour l'état de retour de la ligne."""

        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            validated_data["reported_by"] = request.user

        incident = super().create(validated_data)
        self._reporter_sur_la_ligne(incident)

        return incident

    def update(self, instance, validated_data):
        """Met à jour l'incident, puis réaligne l'état de retour de la ligne."""

        incident = super().update(instance, validated_data)
        self._reporter_sur_la_ligne(incident)

        return incident

    @staticmethod
    def _reporter_sur_la_ligne(incident):
        """Réaligne la ligne : état recalculé, commentaire jamais effacé."""

        ligne = incident.line

        # Le commentaire de la ligne appartient au magasinier : il n'est repris
        # que si l'incident en fournit un, jamais remis à blanc.
        if incident.comment:
            ligne.commentaire = incident.comment
            ligne.save(update_fields=["commentaire", "updated_at"])

        sync_ligne_etat_retour(ligne)


class ReturnIncidentHistorySerializer(ReturnIncidentSerializer):
    """Incident enrichi du contexte réservation / manifestation (SCRUM-100).

    Ces champs vivaient sur le sérialiseur partagé, ce qui coûtait cher :
    `event_name` traverse `line.reservation.prestation.manifestation`, et seule
    la vue historique avait le `select_related` correspondant. La liste et le
    détail des incidents payaient deux requêtes de plus par incident pour des
    champs qu'ils n'exposent pas.
    """

    part_name = serializers.CharField(source="line.part.name", read_only=True)
    reservation_id = serializers.IntegerField(
        source="line.reservation_id", read_only=True
    )
    reservation_number = serializers.CharField(
        source="line.reservation.numero", read_only=True
    )
    event_name = serializers.CharField(
        source="line.reservation.prestation.manifestation.nom", read_only=True
    )

    class Meta(ReturnIncidentSerializer.Meta):
        """Ajoute le contexte d'affichage aux champs de base."""

        fields = ReturnIncidentSerializer.Meta.fields + [
            "part_name",
            "reservation_id",
            "reservation_number",
            "event_name",
        ]
        read_only_fields = ReturnIncidentSerializer.Meta.read_only_fields + [
            "part_name",
            "reservation_id",
            "reservation_number",
            "event_name",
        ]


class ReservationStatusLogSerializer(serializers.ModelSerializer):
    """Sérialiseur du journal de transition de statut."""

    changed_by_username = serializers.CharField(
        source="changed_by.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        """Configuration du serializer ReservationStatusLog."""

        model = ReservationStatusLog
        fields = [
            "id",
            "reservation",
            "changed_by",
            "changed_by_username",
            "from_status",
            "to_status",
            "comment",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "reservation",
            "changed_by",
            "changed_by_username",
            "from_status",
            "to_status",
            "comment",
            "created_at",
        ]


class ReservationTransitionSerializer(serializers.Serializer):
    """Serializer utilisé pour demander une transition de statut."""

    statut = serializers.ChoiceField(
        choices=StatutReservation.choices,
        required=True,
        help_text="Nouveau statut demandé pour la réservation.",
    )
    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Commentaire facultatif lié à la transition.",
    )


class CheckinLigneSerializer(serializers.Serializer):
    """Une ligne de check-in retour (SCRUM-94) : OK / manquant / cassé + commentaire.

    La validation de la somme (== quantité demandée) se fait au niveau de la
    vue, une fois la ligne de réservation résolue par `id`.

    `commentaire` n'a volontairement pas de valeur par défaut : absent du
    payload, il reste absent de `validated_data`, et la vue laisse alors
    intact le commentaire déjà saisi sur la ligne de réservation.
    """

    id = serializers.IntegerField(required=True)
    ok = serializers.IntegerField(required=True, min_value=0)
    manquant = serializers.IntegerField(required=True, min_value=0)
    casse = serializers.IntegerField(required=True, min_value=0)
    commentaire = serializers.CharField(required=False, allow_blank=True)


class ReservationCheckinSerializer(serializers.Serializer):
    """Payload du check-in retour d'une réservation (POST checkin)."""

    lignes = CheckinLigneSerializer(many=True, required=True)


class RetourLigneSerializer(serializers.Serializer):
    """Une ligne du bon de réservation avec sa quantité rendue (SCRUM-95)."""

    id = serializers.IntegerField(required=True)
    quantite_rendue = serializers.IntegerField(required=True, min_value=0)


class PrestationRetourSerializer(serializers.Serializer):
    """Payload de déclaration du retour d'une prestation (POST retour)."""

    lignes = RetourLigneSerializer(many=True, required=True)


class ReservationSerializer(serializers.ModelSerializer):
    """Sérialiseur DRF pour le modèle Reservation, avec lignes imbriquées."""

    lignes = LigneReservationSerializer(many=True, required=False)
    status_logs = ReservationStatusLogSerializer(many=True, read_only=True)
    prestation_nom = serializers.CharField(source="prestation.nom", read_only=True)
    demandeur_nom = serializers.SerializerMethodField()
    validateur_nom = serializers.SerializerMethodField()

    class Meta:
        """Configuration du serializer Reservation."""

        model = Reservation
        fields = [
            "id",
            "numero",
            "prestation",
            "prestation_nom",
            "demandeur",
            "demandeur_nom",
            "validateur",
            "validateur_nom",
            "statut",
            "forced",
            "date_demande",
            "date_retrait_prevue",
            "date_retour_prevue",
            "date_retrait_reelle",
            "date_retour_reelle",
            "commentaire",
            "lignes",
            "status_logs",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "numero", "created_at", "updated_at", "status_logs"]

    @staticmethod
    def _user_label(user):
        """Nom lisible d'un utilisateur : « Prénom Nom (username) », sinon username."""

        return _user_label(user)

    def get_demandeur_nom(self, obj):
        """Nom lisible du demandeur."""

        return self._user_label(obj.demandeur)

    def get_validateur_nom(self, obj):
        """Nom lisible du validateur."""

        return self._user_label(obj.validateur)

    def validate(self, attrs):
        """Règles métier : permissives en brouillon, strictes au-delà.

        Une réservation en statut `brouillon` peut être sauvegardée
        incomplète. Dès qu'elle est soumise (ou plus), le demandeur, la
        prestation, la période, au moins une ligne et au moins un article
        virtuel (ex: prestation de nettoyage) deviennent obligatoires, la
        période doit couvrir au minimum les dates de la prestation, et les
        objets référencés doivent être actifs et louables.
        """

        statut = attrs.get(
            "statut", getattr(self.instance, "statut", StatutReservation.BROUILLON)
        )

        if statut == StatutReservation.BROUILLON:
            return attrs

        def effective(field):
            if field in attrs:
                return attrs[field]
            return getattr(self.instance, field, None) if self.instance else None

        prestation = effective("prestation")
        date_retrait = effective("date_retrait_prevue")
        date_retour = effective("date_retour_prevue")

        errors = {}

        if not date_retrait:
            errors["date_retrait_prevue"] = (
                "La date de retrait est obligatoire pour soumettre la réservation."
            )

        if not date_retour:
            errors["date_retour_prevue"] = (
                "La date de retour est obligatoire pour soumettre la réservation."
            )

        if date_retrait and date_retour:
            if date_retrait > date_retour:
                errors["date_retour_prevue"] = (
                    "La date de retour doit être postérieure ou égale à la date de retrait."
                )
            elif prestation:
                if date_retrait > prestation.date_debut:
                    errors["date_retrait_prevue"] = (
                        "La période doit couvrir au moins les dates de la prestation."
                    )

                if date_retour < prestation.date_fin:
                    errors["date_retour_prevue"] = (
                        "La période doit couvrir au moins les dates de la prestation."
                    )

        lignes = attrs.get("lignes")

        if lignes is None and self.instance is not None:
            lignes = list(self.instance.lignes.all())

        lignes = lignes or []

        if not lignes:
            errors["lignes"] = (
                "Au moins une ligne de matériel est obligatoire pour soumettre la réservation."
            )
        else:
            part_ids = [
                ligne.part_id if hasattr(ligne, "part_id") else ligne["part"].pk
                for ligne in lignes
            ]

            # Les trois règles portent sur la même clé : on les cumule au lieu
            # de les écraser, sinon un objet inactif remontait « il manque un
            # article virtuel » — un message qui ne désigne pas le problème.
            lignes_errors = []

            if self._has_inactive_part(part_ids):
                lignes_errors.append(
                    "Un objet non actif ne peut pas être ajouté à une réservation."
                )

            if RentableItem.objects.filter(
                part_id__in=part_ids,
                is_rentable=False,
            ).exists():
                lignes_errors.append(
                    "Un objet non louable ne peut pas être ajouté à une réservation."
                )

            if not RentableItem.objects.filter(
                part_id__in=part_ids,
                is_virtual=True,
            ).exists():
                lignes_errors.append(
                    "Au moins un article virtuel (ex: prestation de nettoyage) "
                    "est obligatoire pour soumettre la réservation."
                )

            if lignes_errors:
                errors["lignes"] = lignes_errors

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    @staticmethod
    def _has_inactive_part(part_ids) -> bool:
        """Vrai si au moins une des Parts est désactivée côté InvenTree.

        Le contrôle porte sur `Part.active` et non sur `RentableItem` : une
        Part sans extension louable l'est par défaut, mais elle peut très bien
        être désactivée — passer par `RentableItem` laissait filtrer ces Parts.
        """

        from part.models import Part

        return Part.objects.filter(pk__in=part_ids, active=False).exists()

    @transaction.atomic
    def create(self, validated_data):
        """Crée une réservation, ses lignes, et refuse la validation en conflit."""

        lignes_data = validated_data.pop("lignes", None)
        reservation = super().create(validated_data)

        if lignes_data:
            self._replace_lignes(reservation, lignes_data)

        self._register_conflict_history(reservation)
        self._validate_stock_conflicts_if_needed(reservation)

        return reservation

    @transaction.atomic
    def update(self, instance, validated_data):
        """Met à jour une réservation et refuse la validation en conflit."""

        lignes_data = validated_data.pop("lignes", None)
        reservation = super().update(instance, validated_data)

        if lignes_data is not None:
            self._replace_lignes(reservation, lignes_data)

        self._register_conflict_history(reservation)
        self._validate_stock_conflicts_if_needed(reservation)

        return reservation

    def _replace_lignes(self, reservation, lignes_data):
        """Remplace l'intégralité des lignes de la réservation."""

        reservation.lignes.all().delete()

        LigneReservation.objects.bulk_create([
            LigneReservation(reservation=reservation, **ligne_data)
            for ligne_data in lignes_data
        ])

    def _register_conflict_history(self, reservation):
        """Journalise les conflits détectés, qu'ils bloquent ou non (SCRUM-110).

        L'historique et le blocage sont deux choses distinctes : une demande
        peut être enregistrée en conflit et arbitrée plus tard, mais le conflit
        doit rester tracé. Les fonctions d'enregistrement existaient sans
        qu'aucun appel ne les atteigne : l'historique restait vide.
        """

        if not reservation.date_retrait_prevue or not reservation.date_retour_prevue:
            return

        register_stock_conflict_history(
            reservation, detect_reservation_conflicts(reservation)
        )
        register_location_conflict_history(
            reservation, detect_location_reservation_conflicts(reservation)
        )

    def _validate_stock_conflicts_if_needed(self, reservation):
        """Refuse la validation d'une réservation en conflit de stock non forcé."""

        if reservation.statut != StatutReservation.VALIDEE or reservation.forced:
            return

        conflict_result = detect_reservation_conflicts(reservation)

        if conflict_result["has_conflict"]:
            raise serializers.ValidationError({
                "detail": (
                    "Validation refusée : conflit de stock détecté. "
                    "Résolvez le conflit ou passez forced=true."
                ),
                "conflicts": conflict_result["conflicts"],
            })


class RamassageSerializer(serializers.ModelSerializer):
    """Sérialiseur pour SCRUM-89 : liste des ramassages à effectuer."""

    prestation_nom = serializers.CharField(source="prestation.nom", read_only=True)
    manifestation_nom = serializers.CharField(
        source="prestation.manifestation.nom",
        read_only=True,
    )
    demandeur_nom = serializers.SerializerMethodField()
    date_ramassage = serializers.DateTimeField(
        source="date_retour_prevue",
        read_only=True,
    )
    lieu = serializers.SerializerMethodField()
    nb_objets = serializers.SerializerMethodField()
    quantite_totale = serializers.SerializerMethodField()
    recap_par_vehicule = serializers.SerializerMethodField()

    class Meta:
        """Configuration du serializer Ramassage."""

        model = Reservation
        fields = [
            "id",
            "numero",
            "prestation",
            "prestation_nom",
            "manifestation_nom",
            "demandeur",
            "demandeur_nom",
            "statut",
            "date_ramassage",
            "date_retrait_prevue",
            "date_retour_prevue",
            "lieu",
            "nb_objets",
            "quantite_totale",
            "recap_par_vehicule",
        ]

    def get_demandeur_nom(self, obj):
        """Nom lisible du demandeur."""

        return ReservationSerializer._user_label(obj.demandeur)

    def get_lieu(self, obj):
        """Lieu de la prestation, ou None (ORG-02 : un seul lieu, nullable)."""

        lieu = obj.prestation.lieu

        if lieu is None:
            return None

        return {
            "id": lieu.id,
            "nom": lieu.nom,
            "adresse": lieu.adresse,
            "latitude": str(lieu.latitude) if lieu.latitude is not None else None,
            "longitude": str(lieu.longitude) if lieu.longitude is not None else None,
        }

    def get_nb_objets(self, obj):
        """Nombre de lignes à ramasser.

        `len()` sur le prefetch plutôt que `.count()`, qui repartirait en base
        une fois par ligne de la liste.
        """

        return len(lignes_a_ramasser(obj))

    def get_quantite_totale(self, obj):
        """Quantité totale à ramasser."""

        total = 0

        for ligne in lignes_a_ramasser(obj):
            total += ligne.quantite_livree or ligne.quantite_demandee or 0

        return total

    def get_recap_par_vehicule(self, obj):
        """Récap quantité totale par véhicule.

        MVP : aucun modèle véhicule n'existe encore.
        On retourne donc un regroupement "Non attribué".
        """

        return [
            {
                "vehicule": "Non attribué",
                "quantite_totale": self.get_quantite_totale(obj),
            }
        ]


class BonRamassageSerializer(RamassageSerializer):
    """Sérialiseur détaillé pour le bon de ramassage imprimable."""

    lignes = serializers.SerializerMethodField()

    class Meta(RamassageSerializer.Meta):
        """Configuration du serializer BonRamassage."""

        fields = RamassageSerializer.Meta.fields + [
            "lignes",
            "commentaire",
        ]

    def get_lignes(self, obj):
        """Détail des articles à ramasser."""

        lignes = []

        # Pas de `select_related` ici : la vue a déjà préchargé `lignes__part`,
        # et le rajouter annulerait ce prefetch au profit d'une requête neuve.
        for ligne in lignes_a_ramasser(obj):
            lignes.append({
                "id": ligne.id,
                "part": ligne.part_id,
                "part_nom": ligne.part.name,
                "quantite_demandee": ligne.quantite_demandee,
                "quantite_livree": ligne.quantite_livree,
                "quantite_a_ramasser": ligne.quantite_livree or ligne.quantite_demandee,
                "quantite_retournee": ligne.quantite_retournee,
                "quantite_ramassee": ligne.quantite_ramassee,
                "quantite_sav": ligne.quantite_sav,
                "quantite_detruite": ligne.quantite_detruite,
                "quantite_manquante": ligne.quantite_manquante,
                "facturer_client": ligne.facturer_client,
                "etat_retour": ligne.etat_retour,
                "commentaire": ligne.commentaire,
            })

        return lignes


class RentableItemSerializer(serializers.ModelSerializer):
    """Drapeaux location d'un Part.

    Le stock physique n'y figure pas : il appartient à InvenTree et se met à
    jour par les `StockItem`, pas par ce formulaire. `stock_total` reste
    exposé en lecture par `CatalogPartSerializer`, calculé depuis InvenTree.
    """

    class Meta:
        """Configuration du serializer RentableItem."""

        model = RentableItem
        fields = [
            "part",
            "is_rentable",
            "consommable",
            "is_virtual",
            "caution",
            "valeur_remplacement",
            "seuil_alerte_bas",
            "seuil_alerte_haut",
        ]
        read_only_fields = ["part"]


class ExampleSerializer(serializers.Serializer):
    """Example serializer for the InvenTreeLocation plugin."""

    class Meta:
        """Meta options for this serializer."""

        fields = [
            "random_text",
            "part_count",
            "today",
        ]

    random_text = serializers.CharField(
        max_length=100,
        required=True,
        label="Random Text",
        help_text="A text field containing randomly generated data.",
    )

    part_count = serializers.IntegerField(
        label="Number of Parts",
        help_text="Total number of Parts in the InvenTree database.",
    )

    today = serializers.DateField(
        required=False,
        label="Today",
        help_text="The current date.",
    )


class RoundedDecimalField(serializers.DecimalField):
    """DecimalField qui arrondit l'entrée au lieu de rejeter l'excès de décimales.

    Les coordonnées GPS collées depuis une carte comportent souvent plus de
    décimales que le ``decimal_places`` autorisé ; on quantifie plutôt que
    de renvoyer une 400.
    """

    def validate_precision(self, value):
        """Round to the allowed decimal places before precision validation."""

        if self.decimal_places is not None:
            value = value.quantize(
                Decimal(1).scaleb(-self.decimal_places),
                rounding=ROUND_HALF_UP,
            )

        return super().validate_precision(value)


class LieuSerializer(serializers.ModelSerializer):
    """Serializer for location places with GPS coordinates."""

    latitude = RoundedDecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )

    longitude = RoundedDecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )

    auto_geocode = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
        help_text="Active le géocodage automatique à partir de l'adresse.",
    )

    class Meta:
        """Meta options for LieuSerializer."""

        model = Lieu
        fields = [
            "id",
            "nom",
            "adresse",
            "latitude",
            "longitude",
            "capacite",
            "auto_geocode",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def validate_latitude(self, value):
        """Validate latitude range."""

        if value is not None and (value < -90 or value > 90):
            raise serializers.ValidationError(
                "La latitude doit être comprise entre -90 et 90."
            )

        return value

    def validate_longitude(self, value):
        """Validate longitude range."""

        if value is not None and (value < -180 or value > 180):
            raise serializers.ValidationError(
                "La longitude doit être comprise entre -180 et 180."
            )

        return value

    def create(self, validated_data):
        """Create a place and optionally geocode its address."""

        auto_geocode = validated_data.pop("auto_geocode", False)
        self._apply_auto_geocode(validated_data, auto_geocode)

        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Update a place and optionally geocode its address."""

        auto_geocode = validated_data.pop("auto_geocode", False)
        self._apply_auto_geocode(validated_data, auto_geocode)

        return super().update(instance, validated_data)

    def _apply_auto_geocode(self, validated_data, auto_geocode):
        """Fill latitude and longitude from address when requested."""

        if not auto_geocode:
            return

        address = validated_data.get("adresse")

        if not address:
            return

        if validated_data.get("latitude") is not None:
            return

        if validated_data.get("longitude") is not None:
            return

        try:
            result = geocode_address(address)
        except (HTTPError, URLError, TimeoutError):
            return

        if not result:
            return

        validated_data["latitude"] = result.get("latitude")
        validated_data["longitude"] = result.get("longitude")


class DeliveryLigneSerializer(serializers.ModelSerializer):
    """Ligne de matériel d'une livraison, avec le nom de l'article (lecture seule)."""

    part_name = serializers.CharField(source="part.name", read_only=True)

    class Meta:
        """Configuration du serializer DeliveryLigne."""

        model = LigneReservation
        fields = ["id", "part", "part_name", "quantite_demandee"]
        read_only_fields = fields


class DeliverySerializer(serializers.ModelSerializer):
    """Vue « tournée livreur » d'une réservation validée (US livreur).

    Réutilise `Reservation` en lecture seule, enrichi des informations dont
    un livreur a besoin pour organiser sa tournée : lieu géolocalisé,
    contact de l'organisateur, matériel et quantité totale. Sérialiseur
    dédié (plutôt qu'extension de `ReservationSerializer`) pour ne pas
    changer la forme du payload consommé par le formulaire de réservation.
    """

    prestation_nom = serializers.CharField(source="prestation.nom", read_only=True)
    demandeur_nom = serializers.SerializerMethodField()
    lieu_detail = LieuSerializer(source="prestation.lieu", read_only=True)
    organisateur_nom = serializers.SerializerMethodField()
    organisateur_telephone = serializers.SerializerMethodField()
    lignes = DeliveryLigneSerializer(many=True, read_only=True)
    quantite_totale = serializers.SerializerMethodField()

    class Meta:
        """Configuration du serializer Delivery."""

        model = Reservation
        fields = [
            "id",
            "numero",
            "statut",
            "prestation_nom",
            "demandeur_nom",
            "lieu_detail",
            "organisateur_nom",
            "organisateur_telephone",
            "date_retrait_prevue",
            "date_retour_prevue",
            "commentaire",
            "lignes",
            "quantite_totale",
        ]
        read_only_fields = fields

    def get_demandeur_nom(self, obj):
        """Nom lisible du demandeur (gérant interne)."""

        return _user_label(obj.demandeur)

    def get_organisateur_nom(self, obj):
        """Nom lisible de l'organisateur de la manifestation."""

        return _user_label(obj.prestation.manifestation.organisateur)

    def get_organisateur_telephone(self, obj):
        """Téléphone de l'organisateur, vide si non renseigné."""

        return _user_phone(obj.prestation.manifestation.organisateur)

    def get_quantite_totale(self, obj):
        """Somme des quantités demandées sur toutes les lignes (déjà prefetchées)."""

        return sum(ligne.quantite_demandee for ligne in obj.lignes.all())


class CatalogPartSerializer(serializers.Serializer):
    """Serializer used to expose InvenTree Parts in the rental catalog."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True, allow_blank=True)
    IPN = serializers.CharField(read_only=True, allow_blank=True, allow_null=True)
    active = serializers.BooleanField(read_only=True)
    category = serializers.IntegerField(source="category_id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    stock_available = serializers.SerializerMethodField()
    stock_reel_disponible = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    rentable = serializers.SerializerMethodField()
    consommable = serializers.SerializerMethodField()
    is_virtual = serializers.SerializerMethodField()
    stock_total = serializers.SerializerMethodField()
    seuil_alerte_bas = serializers.SerializerMethodField()
    seuil_alerte_haut = serializers.SerializerMethodField()

    def _rentable_info(self, obj):
        """Récupère l'extension RentableItem attachée par la vue catalogue."""

        attached = getattr(obj, "_location_rentable_info", None)

        if attached is not None:
            return attached

        try:
            return getattr(obj, "rentable_info", None)
        except Exception:
            return None

    def get_stock_available(self, obj):
        """Disponibilité **sur la période demandée**, annotée par la vue.

        À ne pas confondre avec `stock_reel_disponible` (SCRUM-112) : ici on
        répond « combien puis-je réserver du 12 au 14 mars », là-bas « combien
        reste-t-il en état de servir, hors SAV et casse ». Les deux chiffres
        diffèrent légitimement et portaient le même nom.
        """

        for attr in ["stock_available", "available_stock"]:
            value = getattr(obj, attr, None)

            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return 0

        return 0

    def get_stock_reel_disponible(self, obj):
        """Stock en état de servir : total InvenTree moins SAV et détruits."""

        return get_real_available_stock(obj.id)

    def get_image_url(self, obj):
        """URL de l'image principale si le modèle en expose une."""

        for attr in ["image", "image_url", "thumbnail", "thumbnail_url"]:
            value = getattr(obj, attr, None)

            if value:
                return str(value)

        return None

    def get_rentable(self, obj):
        """Drapeau louable issu de RentableItem.

        Une Part désactivée côté InvenTree n'est jamais louable, quels que
        soient ses drapeaux plugin (SCRUM-111 : « Désactiver » dans le
        back-office doit sortir l'objet du catalogue louable).
        """

        if not bool(getattr(obj, "active", True)):
            return False

        if not bool(getattr(obj, "active", True)):
            return False

        rentable_info = self._rentable_info(obj)

        if rentable_info is None:
            return True

        return bool(rentable_info.is_rentable)

    def get_consommable(self, obj):
        """Drapeau consommable issu de RentableItem."""

        rentable_info = self._rentable_info(obj)

        if rentable_info is None:
            return False

        return bool(rentable_info.consommable)

    def get_is_virtual(self, obj):
        """Drapeau article virtuel issu de RentableItem (False par défaut)."""

        rentable_info = getattr(obj, "rentable_info", None)

        if rentable_info is None:
            return False

        return bool(rentable_info.is_virtual)

    def get_stock_total(self, obj):
        """Stock physique louable, tel qu'InvenTree le connaît."""

        from .conflicts import get_part_total_stock

        return get_part_total_stock(obj)

    def get_seuil_alerte_bas(self, obj):
        """Seuil bas configurable du part (null par défaut)."""

        rentable_info = getattr(obj, "rentable_info", None)

        if rentable_info is None:
            return None

        return rentable_info.seuil_alerte_bas

    def get_seuil_alerte_haut(self, obj):
        """Seuil haut configurable du part (null par défaut)."""

        rentable_info = getattr(obj, "rentable_info", None)

        if rentable_info is None:
            return None

        return rentable_info.seuil_alerte_haut


class GroupeSerializer(serializers.ModelSerializer):
    """Sérialiseur léger d'un groupe scout (sélecteur manifestation)."""

    class Meta:
        """Configuration du serializer Groupe."""

        model = Groupe
        fields = ["id", "nom", "code", "adresse"]
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    """Sérialiseur léger d'un utilisateur InvenTree."""

    class Meta:
        """Configuration du serializer User."""

        model = get_user_model()
        fields = ["id", "username", "first_name", "last_name", "email"]
        read_only_fields = fields


class LignePrestationSerializer(serializers.ModelSerializer):
    """Article + quantité rattaché à une prestation (RES-09)."""

    part_name = serializers.CharField(source="part.name", read_only=True)

    class Meta:
        """Configuration du serializer LignePrestation."""

        model = LignePrestation
        fields = [
            "id",
            "part",
            "part_name",
            "quantite",
            "commentaire",
        ]
        read_only_fields = ["id", "part_name"]


class PrestationSerializer(serializers.ModelSerializer):
    """CRUD d'une prestation : manifestation, lieu unique et liste d'articles.

    Une prestation se déroule sur un seul lieu (ORG-02) et porte sa propre liste
    de matériel + quantités (RES-09). Les lignes sont imbriquées et remplacées
    intégralement à chaque écriture, comme pour les réservations.
    """

    manifestation_nom = serializers.CharField(
        source="manifestation.nom",
        read_only=True,
    )
    lieu_detail = LieuSerializer(source="lieu", read_only=True)
    lignes = LignePrestationSerializer(
        source="lignes_prestation", many=True, required=False
    )

    class Meta:
        """Configuration du serializer Prestation."""

        model = Prestation
        fields = [
            "id",
            "nom",
            "date_debut",
            "date_fin",
            "description",
            "manifestation",
            "manifestation_nom",
            "lieu",
            "lieu_detail",
            "lignes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "manifestation_nom",
            "lieu_detail",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        """Dates de prestation incluses dans celles de la manifestation."""

        def effective(field):
            if field in attrs:
                return attrs[field]
            return getattr(self.instance, field, None) if self.instance else None

        date_debut = effective("date_debut")
        date_fin = effective("date_fin")
        manifestation = effective("manifestation")

        errors = {}

        # Nouvelle prestation seulement sur une manif pas encore démarrée.
        if (
            self.instance is None
            and manifestation
            and not manifestation.accepte_nouvelles_prestations
        ):
            errors["manifestation"] = (
                "Impossible d'ajouter une prestation : la manifestation est "
                f"« {manifestation.get_statut_display().lower()} » "
                f"(statut effectif : {manifestation.statut_effectif})."
            )

        if date_debut and date_fin and date_debut > date_fin:
            errors["date_fin"] = (
                "La date de fin doit être postérieure ou égale à la date de début."
            )

        # Bornage au jour, dans le fuseau courant (localdate sur les deux dates
        # sinon le jour décale à minuit entre l'entrée DRF et l'UTC en base).
        if (
            manifestation
            and date_debut
            and timezone.localdate(date_debut)
            < timezone.localdate(manifestation.date_debut)
        ):
            errors["date_debut"] = (
                "La prestation doit se dérouler pendant la manifestation "
                f"(à partir du {timezone.localdate(manifestation.date_debut):%d/%m/%Y})."
            )

        if (
            manifestation
            and date_fin
            and timezone.localdate(date_fin)
            > timezone.localdate(manifestation.date_fin)
        ):
            errors["date_fin"] = (
                "La prestation doit se dérouler pendant la manifestation "
                f"(jusqu'au {timezone.localdate(manifestation.date_fin):%d/%m/%Y})."
            )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Crée une prestation et ses lignes, puis contrôle le stock (STK-01)."""

        lignes_data = validated_data.pop("lignes_prestation", None)
        prestation = super().create(validated_data)

        if lignes_data:
            self._replace_lignes(prestation, lignes_data)

        self._validate_stock(prestation)

        return prestation

    @transaction.atomic
    def update(self, instance, validated_data):
        """Met à jour une prestation et ses lignes, puis contrôle le stock."""

        lignes_data = validated_data.pop("lignes_prestation", None)
        prestation = super().update(instance, validated_data)

        if lignes_data is not None:
            self._replace_lignes(prestation, lignes_data)

        self._validate_stock(prestation)

        return prestation

    def _replace_lignes(self, prestation, lignes_data):
        """Remplace l'intégralité des lignes d'articles de la prestation."""

        prestation.lignes_prestation.all().delete()

        LignePrestation.objects.bulk_create([
            LignePrestation(prestation=prestation, **ligne_data)
            for ligne_data in lignes_data
        ])

    def _validate_stock(self, prestation):
        """Bloque la sauvegarde si le stock est insuffisant (STK-01).

        Le calcul est au jour entier ; la ValidationError est levée dans la
        transaction de create/update, ce qui annule donc la sauvegarde.
        """

        result = compute_prestation_stock(prestation)

        if result["has_shortage"]:
            shortages = [line for line in result["lines"] if line["shortage"]]

            raise serializers.ValidationError({
                "detail": (
                    "Stock insuffisant : la prestation ne peut pas être "
                    "enregistrée en l'état."
                ),
                "stock": shortages,
            })


class ManifestationSerializer(serializers.ModelSerializer):
    """CRUD d'une manifestation (événement)."""

    organisateur_nom = serializers.SerializerMethodField()
    prestations_count = serializers.IntegerField(
        source="prestations.count", read_only=True
    )
    statut_effectif = serializers.CharField(read_only=True)

    #: en_cours / terminée sont dérivés des dates, pas posables à la main.
    STATUTS_MANUELS = (
        StatutManifestation.BROUILLON,
        StatutManifestation.PLANIFIEE,
        StatutManifestation.ANNULEE,
    )

    class Meta:
        """Configuration du serializer Manifestation."""

        model = Manifestation
        fields = [
            "id",
            "nom",
            "description",
            "date_debut",
            "date_fin",
            "statut",
            "statut_effectif",
            "organisateur",
            "organisateur_nom",
            "groupe",
            "prestations_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "statut_effectif",
            "organisateur_nom",
            "prestations_count",
            "created_at",
            "updated_at",
        ]

    def get_organisateur_nom(self, obj):
        """Nom lisible de l'organisateur."""

        user = obj.organisateur
        full_name = f"{user.first_name} {user.last_name}".strip()

        return f"{full_name} ({user.username})" if full_name else user.username

    def validate_statut(self, value):
        """Refuse un statut dérivé posé à la main."""

        if value not in self.STATUTS_MANUELS:
            raise serializers.ValidationError(
                "Ce statut est calculé automatiquement d'après les dates et ne "
                "peut pas être défini manuellement (statuts posables : "
                "brouillon, planifiée, annulée)."
            )
        return value

    def validate(self, attrs):
        """La date de fin doit être postérieure ou égale à la date de début."""

        def effective(field):
            if field in attrs:
                return attrs[field]
            return getattr(self.instance, field, None) if self.instance else None

        date_debut = effective("date_debut")
        date_fin = effective("date_fin")

        if date_debut and date_fin and date_debut > date_fin:
            raise serializers.ValidationError({
                "date_fin": (
                    "La date de fin doit être postérieure ou égale à la date de début."
                )
            })

        return attrs

    @transaction.atomic
    def update(self, instance, validated_data):
        """Annulation en cascade : les réservations liées sont annulées aussi."""

        becoming_annulee = (
            validated_data.get("statut") == StatutManifestation.ANNULEE
            and instance.statut != StatutManifestation.ANNULEE
        )

        manifestation = super().update(instance, validated_data)

        if becoming_annulee:
            self._cancel_related_reservations(manifestation)

        return manifestation

    @staticmethod
    def _cancel_related_reservations(manifestation):
        """Annule les réservations pré-livraison ; les livrées/retournées
        (matériel sorti) sont laissées au circuit retour."""

        cancellables = Reservation.objects.filter(
            prestation__manifestation=manifestation,
            statut__in=[
                StatutReservation.BROUILLON,
                StatutReservation.SOUMISE,
                StatutReservation.VALIDEE,
            ],
        )

        for reservation in cancellables:
            transition_reservation_status(
                reservation,
                StatutReservation.ANNULEE,
                comment="Manifestation annulée",
            )
