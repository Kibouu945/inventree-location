"""API serializers for the InvenTreeLocation plugin."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from .conflicts import detect_reservation_conflicts
from .models import (
    LigneReservation,
    Lieu,
    Reservation,
    ReservationStatusLog,
    Prestation,
    RentableItem,
    StatutReservation,
)


def geocode_address(address):
    """Return GPS coordinates for an address using OpenStreetMap Nominatim."""

    if not address:
        return None

    query = urlencode({
        "q": address,
        "format": "json",
        "limit": 1,
    })

    url = f"https://nominatim.openstreetmap.org/search?{query}"

    request = Request(
        url,
        headers={
            "User-Agent": "inventree-location-plugin/0.1",
        },
    )

    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not payload:
        return None

    first_result = payload[0]

    return {
        "address": address,
        "display_name": first_result.get("display_name"),
        "latitude": first_result.get("lat"),
        "longitude": first_result.get("lon"),
        "source": "OpenStreetMap Nominatim",
    }


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
            "etat_retour",
            "commentaire",
        ]
        read_only_fields = ["id"]


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

        if user is None:
            return ""

        full_name = f"{user.first_name} {user.last_name}".strip()

        return f"{full_name} ({user.username})" if full_name else user.username

    def get_demandeur_nom(self, obj):
        """Nom lisible du demandeur."""

        return self._user_label(obj.demandeur)

    def get_validateur_nom(self, obj):
        """Nom lisible du validateur."""

        return self._user_label(obj.validateur)

    def validate(self, attrs):
        """Règles métier : permissives en brouillon, strictes au-delà."""

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

            inactive_part_ids = RentableItem.objects.filter(
                part_id__in=part_ids,
                part__active=False,
            ).values_list("part_id", flat=True)

            if inactive_part_ids:
                errors["lignes"] = (
                    "Un objet non actif ne peut pas être ajouté à une réservation."
                )

            non_rentable_part_ids = RentableItem.objects.filter(
                part_id__in=part_ids,
                is_rentable=False,
            ).values_list("part_id", flat=True)

            if non_rentable_part_ids:
                errors["lignes"] = (
                    "Un objet non louable ne peut pas être ajouté à une réservation."
                )

            if not RentableItem.objects.filter(
                part_id__in=part_ids,
                is_virtual=True,
            ).exists():
                errors["lignes"] = (
                    "Au moins un article virtuel (ex: prestation de nettoyage) "
                    "est obligatoire pour soumettre la réservation."
                )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Crée une réservation, ses lignes, et refuse la validation en conflit."""

        lignes_data = validated_data.pop("lignes", None)
        reservation = super().create(validated_data)

        if lignes_data:
            self._replace_lignes(reservation, lignes_data)

        self._validate_stock_conflicts_if_needed(reservation)

        return reservation

    @transaction.atomic
    def update(self, instance, validated_data):
        """Met à jour une réservation et refuse la validation en conflit."""

        lignes_data = validated_data.pop("lignes", None)
        reservation = super().update(instance, validated_data)

        if lignes_data is not None:
            self._replace_lignes(reservation, lignes_data)

        self._validate_stock_conflicts_if_needed(reservation)

        return reservation

    def _replace_lignes(self, reservation, lignes_data):
        """Remplace l'intégralité des lignes de la réservation."""

        reservation.lignes.all().delete()

        LigneReservation.objects.bulk_create([
            LigneReservation(reservation=reservation, **ligne_data)
            for ligne_data in lignes_data
        ])

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
    lieux = serializers.SerializerMethodField()
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
            "lieux",
            "nb_objets",
            "quantite_totale",
            "recap_par_vehicule",
        ]

    def get_demandeur_nom(self, obj):
        """Nom lisible du demandeur."""

        return ReservationSerializer._user_label(obj.demandeur)

    def get_lieux(self, obj):
        """Lieux liés à la prestation."""

        lieux = []

        for lieu in obj.prestation.lieux.all():
            lieux.append({
                "id": lieu.id,
                "nom": lieu.nom,
                "adresse": lieu.adresse,
                "latitude": str(lieu.latitude) if lieu.latitude is not None else None,
                "longitude": str(lieu.longitude) if lieu.longitude is not None else None,
            })

        return lieux

    def get_nb_objets(self, obj):
        """Nombre de lignes à ramasser."""

        return obj.lignes.count()

    def get_quantite_totale(self, obj):
        """Quantité totale à ramasser."""

        total = 0

        for ligne in obj.lignes.all():
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

        for ligne in obj.lignes.select_related("part").all():
            lignes.append({
                "part": ligne.part_id,
                "part_nom": ligne.part.name,
                "quantite_demandee": ligne.quantite_demandee,
                "quantite_livree": ligne.quantite_livree,
                "quantite_a_ramasser": ligne.quantite_livree
                or ligne.quantite_demandee,
                "quantite_retournee": ligne.quantite_retournee,
                "etat_retour": ligne.etat_retour,
                "commentaire": ligne.commentaire,
            })

        return lignes


class RentableItemSerializer(serializers.ModelSerializer):
    """Drapeaux location d'un Part."""

    class Meta:
        """Configuration du serializer RentableItem."""

        model = RentableItem
        fields = [
            "part",
            "is_rentable",
            "consommable",
            "is_virtual",
            "stock_total",
            "caution",
            "valeur_remplacement",
            "seuil_alerte_bas",
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


class LieuSerializer(serializers.ModelSerializer):
    """Serializer for location places with GPS coordinates."""

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
            "prestation",
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
    image_url = serializers.SerializerMethodField()
    rentable = serializers.SerializerMethodField()
    consommable = serializers.SerializerMethodField()
    is_virtual = serializers.SerializerMethodField()
    stock_total = serializers.SerializerMethodField()

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
        """Stock disponible de la Part, exposé à 0 si non renseigné."""

        for attr in ["stock_available", "available_stock"]:
            value = getattr(obj, attr, None)

            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return 0

        return 0

    def get_image_url(self, obj):
        """URL de l'image principale si le modèle en expose une."""

        for attr in ["image", "image_url", "thumbnail", "thumbnail_url"]:
            value = getattr(obj, attr, None)

            if value:
                return str(value)

        return None

    def get_rentable(self, obj):
        """Drapeau louable issu de RentableItem."""

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
        """Drapeau article virtuel issu de RentableItem."""

        rentable_info = self._rentable_info(obj)

        if rentable_info is None:
            return False

        return bool(rentable_info.is_virtual)

    def get_stock_total(self, obj):
        """Stock total louable issu de RentableItem."""

        rentable_info = self._rentable_info(obj)

        if rentable_info is None:
            return 0

        return rentable_info.stock_total


class UserSerializer(serializers.ModelSerializer):
    """Sérialiseur léger d'un utilisateur InvenTree."""

    class Meta:
        """Configuration du serializer User."""

        model = get_user_model()
        fields = ["id", "username", "first_name", "last_name", "email"]
        read_only_fields = fields


class PrestationSerializer(serializers.ModelSerializer):
    """Sérialiseur de lecture d'une prestation, avec manifestation et lieux."""

    manifestation_nom = serializers.CharField(
        source="manifestation.nom",
        read_only=True,
    )
    lieux = LieuSerializer(many=True, read_only=True)

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
            "lieux",
        ]
        read_only_fields = fields