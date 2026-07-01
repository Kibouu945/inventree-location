"""API views for the InvenTreeLocation plugin."""

from datetime import date
import random
import string
from urllib.error import HTTPError, URLError

from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Lieu, RentableItem, Reservation
from .permissions import (
    CatalogPermission,
    LieuPermission,
    ReservationPermission,
)
from .serializers import (
    CatalogPartSerializer,
    ExampleSerializer,
    LieuSerializer,
    RentableItemSerializer,
    ReservationSerializer,
    ReservationTransitionSerializer,
    geocode_address,
)
from .services.workflow_service import (
    get_available_transitions,
    transition_reservation_status,
)


class ExampleView(APIView):
    """Example API view for the InvenTreeLocation plugin."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ExampleSerializer

    def get(self, request, *args, **kwargs):
        """Override the GET method to return example data."""

        from part.models import Part

        response_serializer = self.serializer_class(
            data={
                "random_text": "".join(random.choices(string.ascii_letters, k=50)),
                "part_count": Part.objects.count(),
                "today": date.today(),
            }
        )

        response_serializer.is_valid(raise_exception=True)

        return Response(response_serializer.data, status=200)


class LieuPagination(PageNumberPagination):
    """Pagination for location places."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class CatalogPagination(PageNumberPagination):
    """Pagination for catalog results."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100


class LieuListCreateView(generics.ListCreateAPIView):
    """List and create places with GPS coordinates."""

    permission_classes = [LieuPermission]
    serializer_class = LieuSerializer
    pagination_class = LieuPagination

    def get_queryset(self):
        """Return places, with optional filters."""

        queryset = (
            Lieu.objects.select_related("prestation", "prestation__manifestation")
            .all()
            .order_by("nom")
        )

        prestation_id = self.request.query_params.get("prestation")
        search = self.request.query_params.get("search")

        if prestation_id:
            queryset = queryset.filter(prestation_id=prestation_id)

        if search:
            queryset = queryset.filter(nom__icontains=search)

        return queryset


class LieuDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a place."""

    permission_classes = [LieuPermission]
    serializer_class = LieuSerializer
    queryset = Lieu.objects.select_related("prestation", "prestation__manifestation")


class GeocodeAddressView(APIView):
    """Geocode an address and return latitude / longitude."""

    permission_classes = [LieuPermission]

    def get(self, request, *args, **kwargs):
        """Return GPS coordinates for a given address."""

        address = request.query_params.get("address", "").strip()

        if not address:
            return Response(
                {"detail": "Le paramètre address est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = geocode_address(address)
        except (HTTPError, URLError, TimeoutError) as error:
            return Response(
                {
                    "detail": "Le service de géocodage est temporairement indisponible.",
                    "error": str(error),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if result is None:
            return Response(
                {"detail": "Aucune coordonnée trouvée pour cette adresse."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(result, status=status.HTTP_200_OK)


class ReservationListCreateView(generics.ListCreateAPIView):
    """CRUD réservation — partie collection."""

    serializer_class = ReservationSerializer
    permission_classes = [ReservationPermission]

    def get_queryset(self):
        """Retourne les réservations, filtrées par statut et période."""

        queryset = Reservation.objects.prefetch_related(
            "lignes",
            "status_logs",
        ).all()

        statuts = self.request.query_params.getlist("statut")

        if statuts:
            queryset = queryset.filter(statut__in=statuts)

        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if date_from:
            queryset = queryset.filter(date_retour_prevue__gte=date_from)

        if date_to:
            queryset = queryset.filter(date_retrait_prevue__lte=date_to)

        return queryset


class ReservationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """CRUD réservation — partie instance unique."""

    queryset = Reservation.objects.prefetch_related(
        "lignes",
        "status_logs",
    ).all()
    serializer_class = ReservationSerializer
    permission_classes = [ReservationPermission]


class ReservationTransitionView(APIView):
    """Endpoint permettant de faire évoluer le statut d'une réservation."""

    permission_classes = [ReservationPermission]
    serializer_class = ReservationTransitionSerializer

    def get(self, request, pk, *args, **kwargs):
        """Retourne les transitions disponibles pour la réservation."""

        reservation = Reservation.objects.filter(pk=pk).first()

        if reservation is None:
            return Response(
                {"detail": "Réservation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "reservation": reservation.pk,
                "current_status": reservation.statut,
                "available_transitions": get_available_transitions(
                    reservation.statut
                ),
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk, *args, **kwargs):
        """Applique une transition de statut à une réservation."""

        reservation = Reservation.objects.filter(pk=pk).first()

        if reservation is None:
            return Response(
                {"detail": "Réservation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = transition_reservation_status(
            reservation=reservation,
            new_status=serializer.validated_data["statut"],
            user=request.user,
            comment=serializer.validated_data.get("comment", ""),
        )

        return Response(result, status=status.HTTP_200_OK)


class CatalogPartListView(APIView):
    """List InvenTree parts with catalog filters."""

    permission_classes = [CatalogPermission]
    serializer_class = CatalogPartSerializer
    pagination_class = CatalogPagination

    def get(self, request, *args, **kwargs):
        """Return a filtered and paginated catalog of InvenTree parts."""

        from part.models import Part

        queryset = (
            Part.objects.select_related("category", "rentable_info")
            .all()
            .order_by("name")
        )

        search = request.query_params.get("search")
        category = request.query_params.get("category")
        categories = request.query_params.get("categories")
        active = request.query_params.get("active")
        rentable = request.query_params.get("rentable")

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(IPN__icontains=search)
            )

        category_ids = self._parse_category_ids(category, categories)

        if category_ids:
            queryset = queryset.filter(category_id__in=category_ids)

        active_value = self._parse_boolean(active)

        if active_value is not None:
            queryset = queryset.filter(active=active_value)

        queryset = self._filter_rentable(queryset, rentable)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)

        serializer = self.serializer_class(page, many=True)

        return paginator.get_paginated_response(serializer.data)

    def _parse_category_ids(self, category, categories):
        """Parse category filters from query parameters."""

        values = []

        if category:
            values.append(category)

        if categories:
            values.extend(categories.split(","))

        category_ids = []

        for value in values:
            value = str(value).strip()

            if value.isdigit():
                category_ids.append(int(value))

        return category_ids

    def _parse_boolean(self, value):
        """Parse boolean query parameter."""

        if value is None:
            return None

        value = str(value).lower().strip()

        if value in ["true", "1", "yes", "y"]:
            return True

        if value in ["false", "0", "no", "n"]:
            return False

        return None

    def _filter_rentable(self, queryset, rentable):
        """Filtre le catalogue selon le drapeau louable de RentableItem."""

        if rentable is not None and str(rentable).lower().strip() == "all":
            return queryset

        rentable_value = self._parse_boolean(rentable)

        if rentable_value is None:
            rentable_value = True

        if rentable_value:
            return queryset.filter(
                Q(rentable_info__is_rentable=True) | Q(rentable_info__isnull=True)
            )

        return queryset.filter(rentable_info__is_rentable=False)


class RentableFlagBulkUpdateView(APIView):
    """Met à jour en masse le drapeau louable / consommable de Part."""

    permission_classes = [CatalogPermission]

    def patch(self, request, *args, **kwargs):
        """Applique les drapeaux fournis à la liste de parts."""

        from part.models import Part

        part_ids = request.data.get("part_ids")

        if not isinstance(part_ids, list) or not part_ids:
            return Response(
                {"detail": "part_ids doit être une liste non vide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        defaults = {}

        if "is_rentable" in request.data:
            defaults["is_rentable"] = bool(request.data.get("is_rentable"))

        if "consommable" in request.data:
            defaults["consommable"] = bool(request.data.get("consommable"))

        if not defaults:
            return Response(
                {"detail": "Fournir au moins is_rentable ou consommable."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_ids = list(
            Part.objects.filter(pk__in=part_ids).values_list("pk", flat=True)
        )

        for part_id in valid_ids:
            RentableItem.objects.update_or_create(
                part_id=part_id,
                defaults=defaults,
            )

        return Response(
            {"updated": valid_ids, "applied": defaults},
            status=status.HTTP_200_OK,
        )


class RentablePartDetailView(APIView):
    """Drapeaux location d'un Part unique."""

    permission_classes = [CatalogPermission]
    serializer_class = RentableItemSerializer

    def get(self, request, pk, *args, **kwargs):
        """Retourne les drapeaux location du Part."""

        from part.models import Part

        if not Part.objects.filter(pk=pk).exists():
            return Response(
                {"detail": "Part introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        rentable_item = RentableItem.objects.filter(part_id=pk).first()

        if rentable_item is None:
            return Response(
                {
                    "part": pk,
                    "is_rentable": True,
                    "consommable": False,
                    "caution": None,
                    "valeur_remplacement": None,
                    "seuil_alerte_bas": None,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            self.serializer_class(rentable_item).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk, *args, **kwargs):
        """Crée ou met à jour les drapeaux location du Part."""

        from part.models import Part

        if not Part.objects.filter(pk=pk).exists():
            return Response(
                {"detail": "Part introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        rentable_item, _created = RentableItem.objects.get_or_create(part_id=pk)
        serializer = self.serializer_class(
            rentable_item,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data, status=status.HTTP_200_OK)