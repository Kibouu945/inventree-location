"""Back-office Parts pour SCRUM-111.

Objectif :
- créer / modifier une Part InvenTree depuis le front ;
- créer / modifier son RentableItem ;
- créer un stock initial via StockItem ;
- exposer une API simple réservée aux admins.

Le stock n'est **pas** un champ de ce formulaire : il appartient à InvenTree et
se lit via `conflicts.get_part_total_stock`. Le seul levier offert ici est
`stock_initial`, qui crée un `StockItem` — c'est-à-dire du vrai stock InvenTree,
pas un compteur parallèle (cf. `0010_remove_rentableitem_stock_total`).

Note importante :
Sur certaines versions InvenTree, un save() sur Part peut déclencher une tâche
interne Django-Q qui plante avec KeyError('func') si la queue a été corrompue.
Pour l'édition, on utilise donc QuerySet.update() afin d'éviter ce déclenchement.
"""

from django.db import transaction
from django.db.models import Q
from rest_framework import generics, serializers

from .backoffice import BackOfficePagination, BackOfficePermission
from .conflicts import get_part_total_stock
from .models import RentableItem


#: Champs du formulaire → champs du modèle `part.Part`.
PART_FIELDS = {
    "NOI": "IPN",
    "name": "name",
    "description": "description",
    "link": "link",
    "active": "active",
    "salable": "salable",
    "virtual": "virtual",
}


def _model_has_field(model, field_name: str) -> bool:
    """Vérifie qu'un modèle Django possède un champ donné."""

    return any(field.name == field_name for field in model._meta.fields)


def _get_default_stock_location():
    """Retourne l'emplacement de stock par défaut, ou None s'il n'y en a pas.

    On ne crée pas d'emplacement fantôme : le rangement du matériel est une
    décision d'exploitation, pas un effet de bord d'un formulaire.
    """

    try:
        from stock.models import StockLocation
    except ImportError:
        return None

    return StockLocation.objects.order_by("pk").first()


def _create_stock_item(part, quantity):
    """Crée un StockItem initial pour la Part.

    Un échec n'est pas silencieux : l'admin a saisi une quantité, il doit
    savoir si elle est entrée en stock ou non.
    """

    if quantity is None:
        return None

    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        raise serializers.ValidationError({
            "stock_initial": "Quantité invalide."
        }) from None

    if quantity <= 0:
        return None

    try:
        from stock.models import StockItem
    except ImportError:
        raise serializers.ValidationError({
            "stock_initial": (
                "Le stock InvenTree n'est pas accessible : impossible de créer "
                "le stock initial."
            )
        }) from None

    location = _get_default_stock_location()

    payload = {
        "part": part,
        "quantity": quantity,
    }

    if location is not None and _model_has_field(StockItem, "location"):
        payload["location"] = location

    return StockItem.objects.create(**payload)


def _is_pack(part) -> bool:
    """Détermine si une Part est un PACK via la BOM native InvenTree."""

    for related_name in ["bom_items", "bom_items_in", "bomitem_set"]:
        manager = getattr(part, related_name, None)

        if manager is None:
            continue

        try:
            if manager.exists():
                return True
        except Exception:
            continue

    return False


def _part_update_payload(data: dict) -> dict:
    """Traduit les champs du formulaire présents en payload `Part.update()`."""

    return {
        model_field: data[input_field]
        for input_field, model_field in PART_FIELDS.items()
        if input_field in data
    }


class PartBackOfficeSerializer(serializers.Serializer):
    """Serializer back-office pour gérer une Part de bout en bout."""

    id = serializers.IntegerField(read_only=True)

    # Part InvenTree
    NOI = serializers.CharField(required=False, allow_blank=True, max_length=100)
    name = serializers.CharField(required=True, max_length=100)
    description = serializers.CharField(
        required=False, allow_blank=True, max_length=500
    )
    link = serializers.URLField(required=False, allow_blank=True)
    active = serializers.BooleanField(required=False, default=True)
    salable = serializers.BooleanField(required=False, default=False)
    virtual = serializers.BooleanField(required=False, default=False)

    # Infos calculées
    pack = serializers.BooleanField(read_only=True)
    #: Stock physique louable selon InvenTree — jamais saisi ici.
    stock_total = serializers.IntegerField(read_only=True)

    # RentableItem
    is_rentable = serializers.BooleanField(required=False, default=True)
    consommable = serializers.BooleanField(required=False, default=False)
    seuil_alerte_bas = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
    )
    seuil_alerte_haut = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
    )
    alertes_desactivees = serializers.BooleanField(required=False, default=False)

    # Stock initial : crée un StockItem InvenTree (pas un compteur local).
    stock_initial = serializers.FloatField(required=False, min_value=0, default=0)

    def to_representation(self, part):
        """Convertit une Part InvenTree + RentableItem en JSON back-office."""

        rentable_item = RentableItem.objects.filter(part=part).first()

        return {
            "id": part.pk,
            "NOI": getattr(part, "IPN", "") or "",
            "name": getattr(part, "name", "") or "",
            "description": getattr(part, "description", "") or "",
            "link": getattr(part, "link", "") or "",
            "active": bool(getattr(part, "active", True)),
            "salable": bool(getattr(part, "salable", False)),
            "virtual": bool(getattr(part, "virtual", False)),
            "pack": _is_pack(part),
            "stock_total": get_part_total_stock(part),
            "is_rentable": bool(rentable_item.is_rentable) if rentable_item else False,
            "consommable": bool(rentable_item.consommable) if rentable_item else False,
            "seuil_alerte_bas": rentable_item.seuil_alerte_bas
            if rentable_item
            else None,
            "seuil_alerte_haut": rentable_item.seuil_alerte_haut
            if rentable_item
            else None,
            "alertes_desactivees": bool(rentable_item.alertes_desactivees)
            if rentable_item
            else False,
        }

    def _effective(self, attrs, field, default=False):
        """Valeur du champ après application du patch.

        En PATCH partiel, un champ absent vaut celui de l'objet en base : le
        lire à `False` faisait passer les règles métier à côté de l'état réel.
        """

        if field in attrs:
            return attrs[field]

        if self.instance is None:
            return default

        if field in {"virtual", "active", "salable"}:
            return getattr(self.instance, field, default)

        rentable_item = RentableItem.objects.filter(part=self.instance).first()

        if rentable_item is None:
            return default

        return getattr(rentable_item, field, default)

    def validate(self, attrs):
        """Règles métier SCRUM-111."""

        consommable = bool(self._effective(attrs, "consommable"))
        virtual = bool(self._effective(attrs, "virtual"))

        current_pack = _is_pack(self.instance) if self.instance is not None else False

        if current_pack and consommable:
            raise serializers.ValidationError({
                "consommable": "Un PACK ne peut pas être consommable."
            })

        if consommable and virtual:
            raise serializers.ValidationError({
                "virtual": "Un consommable ne doit pas être déclaré comme virtuel."
            })

        seuil_bas = self._effective(attrs, "seuil_alerte_bas", default=None)
        seuil_haut = self._effective(attrs, "seuil_alerte_haut", default=None)

        if seuil_bas is not None and seuil_haut is not None and seuil_bas > seuil_haut:
            raise serializers.ValidationError({
                "seuil_alerte_haut": (
                    "Le seuil haut doit être supérieur ou égal au seuil bas."
                )
            })

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Crée une Part + son RentableItem + stock initial."""

        from part.models import Part

        stock_initial = validated_data.pop("stock_initial", 0)

        virtual = validated_data.get("virtual", False)

        rentable_data = {
            "is_rentable": validated_data.pop("is_rentable", True),
            "consommable": validated_data.pop("consommable", False),
            "is_virtual": virtual,
            "seuil_alerte_bas": validated_data.pop("seuil_alerte_bas", None),
            "seuil_alerte_haut": validated_data.pop("seuil_alerte_haut", None),
            "alertes_desactivees": validated_data.pop("alertes_desactivees", False),
        }

        part = Part(
            IPN=validated_data.get("NOI", ""),
            name=validated_data.get("name", ""),
            description=validated_data.get("description", ""),
            link=validated_data.get("link", ""),
            active=validated_data.get("active", True),
            salable=validated_data.get("salable", False),
            virtual=virtual,
        )

        part.save()

        RentableItem.objects.create(
            part=part,
            **rentable_data,
        )

        _create_stock_item(part, stock_initial)

        return part

    @transaction.atomic
    def update(self, part, validated_data):
        """Met à jour une Part + son RentableItem.

        On évite volontairement part.save() afin de ne pas déclencher les tâches
        internes InvenTree qui peuvent planter avec KeyError('func').
        """

        from part.models import Part

        stock_initial = validated_data.pop("stock_initial", None)

        rentable_fields = [
            "is_rentable",
            "consommable",
            "seuil_alerte_bas",
            "seuil_alerte_haut",
            "alertes_desactivees",
        ]

        rentable_data = {}

        for field in rentable_fields:
            if field in validated_data:
                rentable_data[field] = validated_data.pop(field)

        if "virtual" in validated_data:
            rentable_data["is_virtual"] = validated_data["virtual"]

        part_payload = _part_update_payload(validated_data)

        if part_payload:
            Part.objects.filter(pk=part.pk).update(**part_payload)
            part.refresh_from_db()

        rentable_item, _created = RentableItem.objects.get_or_create(part=part)

        for field, value in rentable_data.items():
            setattr(rentable_item, field, value)

        rentable_item.save()

        _create_stock_item(part, stock_initial)

        part.refresh_from_db()

        return part


class PartBackOfficeListCreateView(generics.ListCreateAPIView):
    """Liste et création des Parts depuis le back-office."""

    permission_classes = [BackOfficePermission]
    serializer_class = PartBackOfficeSerializer
    pagination_class = BackOfficePagination

    def get_queryset(self):
        """Liste filtrable des Parts."""

        from part.models import Part

        queryset = Part.objects.all().order_by("name")

        search = self.request.query_params.get("search", "").strip()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(IPN__icontains=search)
            )

        return queryset


class PartBackOfficeDetailView(generics.RetrieveUpdateAPIView):
    """Détail / édition d'une Part depuis le back-office."""

    permission_classes = [BackOfficePermission]
    serializer_class = PartBackOfficeSerializer

    def get_queryset(self):
        """Queryset Part."""

        from part.models import Part

        return Part.objects.all()
