"""Back-office Parts pour SCRUM-111.

Objectif :
- créer / modifier une Part InvenTree depuis le front ;
- créer / modifier son RentableItem ;
- créer un stock initial via StockItem ;
- exposer une API simple réservée aux admins.

Note importante :
Sur certaines versions InvenTree, un save() sur Part peut déclencher une tâche
interne Django-Q qui plante avec KeyError('func') si la queue a été corrompue.
Pour l'édition, on utilise donc QuerySet.update() afin d'éviter ce déclenchement.
"""

from django.db import transaction
from django.db.models import Q
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .backoffice import BackOfficePermission
from .models import RentableItem


def _model_has_field(model, field_name: str) -> bool:
    """Vérifie qu'un modèle Django possède un champ donné."""

    return any(field.name == field_name for field in model._meta.fields)


def _set_if_field_exists(instance, field_name: str, value):
    """Affecte une valeur uniquement si le champ existe sur le modèle."""

    if _model_has_field(instance.__class__, field_name):
        setattr(instance, field_name, value)


def _get_default_stock_location():
    """Retourne ou crée un emplacement de stock par défaut."""

    try:
        from stock.models import StockLocation
    except Exception:
        return None

    location = StockLocation.objects.order_by("pk").first()

    if location is not None:
        return location

    try:
        return StockLocation.objects.create(name="Stock location")
    except Exception:
        return None


def _create_stock_item(part, quantity):
    """Crée un StockItem initial pour la Part."""

    if quantity is None:
        return None

    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        return None

    if quantity <= 0:
        return None

    try:
        from stock.models import StockItem
    except Exception:
        return None

    location = _get_default_stock_location()

    payload = {
        "part": part,
        "quantity": quantity,
    }

    if location is not None and _model_has_field(StockItem, "location"):
        payload["location"] = location

    try:
        return StockItem.objects.create(**payload)
    except Exception:
        return None


def _get_stock_total(part):
    """Calcule le stock total existant d'une Part."""

    try:
        from stock.models import StockItem
    except Exception:
        return 0

    try:
        total = 0

        for item in StockItem.objects.filter(part=part):
            quantity = getattr(item, "quantity", 0) or 0
            total += float(quantity)

        return total
    except Exception:
        return 0


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


def _part_update_payload(part_model, data: dict) -> dict:
    """Construit un payload update uniquement avec les champs existants."""

    payload = {}

    mapping = {
        "NOI": "IPN",
        "name": "name",
        "description": "description",
        "link": "link",
        "active": "active",
        "salable": "salable",
        "virtual": "virtual",
    }

    for input_field, model_field in mapping.items():
        if input_field not in data:
            continue

        if _model_has_field(part_model, model_field):
            payload[model_field] = data[input_field]

    return payload


class PartBackOfficePagination(PageNumberPagination):
    """Pagination de la liste Parts back-office."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class PartBackOfficeSerializer(serializers.Serializer):
    """Serializer back-office pour gérer une Part de bout en bout."""

    id = serializers.IntegerField(read_only=True)

    # Part InvenTree
    NOI = serializers.CharField(required=False, allow_blank=True, max_length=100)
    name = serializers.CharField(required=True, max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, max_length=500)
    link = serializers.URLField(required=False, allow_blank=True)
    active = serializers.BooleanField(required=False, default=True)
    salable = serializers.BooleanField(required=False, default=False)
    virtual = serializers.BooleanField(required=False, default=False)

    # Infos calculées
    pack = serializers.BooleanField(read_only=True)
    stock_total_inventree = serializers.FloatField(read_only=True)

    # RentableItem
    is_rentable = serializers.BooleanField(required=False, default=True)
    consommable = serializers.BooleanField(required=False, default=False)
    stock_total = serializers.IntegerField(required=False, min_value=0, default=0)
    seuil_alerte_bas = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
    )

    # Champs préparés pour le front SCRUM-111.
    # Persistés uniquement si les colonnes existent dans le modèle.
    seuil_alerte_haut = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=0,
    )
    alertes_desactivees = serializers.BooleanField(required=False, default=False)

    # Stock initial / stock additionnel
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
            "stock_total_inventree": _get_stock_total(part),
            "is_rentable": bool(rentable_item.is_rentable)
            if rentable_item
            else False,
            "consommable": bool(rentable_item.consommable)
            if rentable_item
            else False,
            "stock_total": rentable_item.stock_total if rentable_item else 0,
            "seuil_alerte_bas": rentable_item.seuil_alerte_bas
            if rentable_item
            else None,
            "seuil_alerte_haut": getattr(
                rentable_item,
                "seuil_alerte_haut",
                None,
            )
            if rentable_item
            else None,
            "alertes_desactivees": getattr(
                rentable_item,
                "alertes_desactivees",
                False,
            )
            if rentable_item
            else False,
        }

    def validate(self, attrs):
        """Règles métier SCRUM-111."""

        consommable = attrs.get("consommable", False)
        virtual = attrs.get("virtual", False)

        current_pack = _is_pack(self.instance) if self.instance is not None else False

        if current_pack and consommable:
            raise serializers.ValidationError({
                "consommable": "Un PACK ne peut pas être consommable."
            })

        if consommable and virtual:
            raise serializers.ValidationError({
                "virtual": "Un consommable ne doit pas être déclaré comme virtuel."
            })

        seuil_bas = attrs.get("seuil_alerte_bas")
        seuil_haut = attrs.get("seuil_alerte_haut")

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
            "stock_total": validated_data.pop("stock_total", 0),
            "seuil_alerte_bas": validated_data.pop("seuil_alerte_bas", None),
        }

        seuil_alerte_haut = validated_data.pop("seuil_alerte_haut", None)
        alertes_desactivees = validated_data.pop("alertes_desactivees", False)

        noi = validated_data.pop("NOI", "")

        part = Part()

        _set_if_field_exists(part, "IPN", noi)
        _set_if_field_exists(part, "name", validated_data.get("name", ""))
        _set_if_field_exists(
            part,
            "description",
            validated_data.get("description", ""),
        )
        _set_if_field_exists(part, "link", validated_data.get("link", ""))
        _set_if_field_exists(part, "active", validated_data.get("active", True))
        _set_if_field_exists(part, "salable", validated_data.get("salable", False))
        _set_if_field_exists(part, "virtual", validated_data.get("virtual", False))

        # Champs souvent présents dans InvenTree.
        _set_if_field_exists(part, "component", False)
        _set_if_field_exists(part, "purchaseable", False)
        _set_if_field_exists(part, "assembly", False)
        _set_if_field_exists(part, "trackable", False)

        part.save()

        rentable_item = RentableItem.objects.create(
            part=part,
            **rentable_data,
        )

        if _model_has_field(RentableItem, "seuil_alerte_haut"):
            rentable_item.seuil_alerte_haut = seuil_alerte_haut

        if _model_has_field(RentableItem, "alertes_desactivees"):
            rentable_item.alertes_desactivees = alertes_desactivees

        rentable_item.save()

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
            "stock_total",
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

        part_payload = _part_update_payload(Part, validated_data)

        if part_payload:
            Part.objects.filter(pk=part.pk).update(**part_payload)
            part.refresh_from_db()

        rentable_item, _created = RentableItem.objects.get_or_create(part=part)

        for field, value in rentable_data.items():
            if _model_has_field(RentableItem, field):
                setattr(rentable_item, field, value)

        rentable_item.save()

        _create_stock_item(part, stock_initial)

        part.refresh_from_db()

        return part


class PartBackOfficeListCreateView(generics.ListCreateAPIView):
    """Liste et création des Parts depuis le back-office."""

    permission_classes = [BackOfficePermission]
    serializer_class = PartBackOfficeSerializer
    pagination_class = PartBackOfficePagination

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

    def create(self, request, *args, **kwargs):
        """Création avec réponse complète."""

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        part = serializer.save()

        return Response(
            self.get_serializer(part).data,
            status=status.HTTP_201_CREATED,
        )


class PartBackOfficeDetailView(generics.RetrieveUpdateAPIView):
    """Détail / édition d'une Part depuis le back-office."""

    permission_classes = [BackOfficePermission]
    serializer_class = PartBackOfficeSerializer

    def get_queryset(self):
        """Queryset Part."""

        from part.models import Part

        return Part.objects.all()

    def update(self, request, *args, **kwargs):
        """PATCH / PUT avec réponse complète."""

        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        part = serializer.save()

        return Response(self.get_serializer(part).data, status=status.HTTP_200_OK)