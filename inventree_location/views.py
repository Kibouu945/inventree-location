"""API views for the InvenTreeLocation plugin."""

from datetime import date
import random
import string
from urllib.error import HTTPError, URLError

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .conflicts import (
    detect_reservation_conflicts,
    list_current_conflicts,
)
from .models import (
    Lieu,
    Prestation,
    RentableItem,
    Reservation,
    StatutReservation,
)
from .permissions import (
    CatalogPermission,
    LieuPermission,
    ReservationPermission,
    RoleBasedPermission,
)
from .serializers import (
    BonRamassageSerializer,
    CatalogPartSerializer,
    ExampleSerializer,
    LieuSerializer,
    PrestationSerializer,
    RamassageSerializer,
    RentableItemSerializer,
    ReservationSerializer,
    ReservationTransitionSerializer,
    UserSerializer,
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
        """Retourne les réservations, filtrées par statut, période et recherche."""

        queryset = (
            Reservation.objects.select_related("prestation", "demandeur")
            .prefetch_related("lignes")
            .all()
            .order_by("-date_demande")
        )

        statuts = self.request.query_params.getlist("statut")

        if statuts:
            queryset = queryset.filter(statut__in=statuts)

        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if date_from:
            queryset = queryset.filter(date_retour_prevue__gte=date_from)

        if date_to:
            queryset = queryset.filter(date_retrait_prevue__lte=date_to)

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(numero__icontains=search)
                | Q(prestation__nom__icontains=search)
                | Q(demandeur__username__icontains=search)
                | Q(demandeur__first_name__icontains=search)
                | Q(demandeur__last_name__icontains=search)
            )

        return queryset


class ReservationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """CRUD réservation — partie instance unique."""

    queryset = Reservation.objects.prefetch_related(
        "lignes",
        "status_logs",
    ).all()
    serializer_class = ReservationSerializer
    permission_classes = [ReservationPermission]


class RamassageListView(generics.ListAPIView):
    """SCRUM-89 — Liste des ramassages à effectuer.

    Un ramassage correspond à une réservation avec une date de retour prévue.

    Filtres disponibles :
    - date_from : ramassages dont la date de retour prévue est >= à cette date
    - date_to   : ramassages dont la date de retour prévue est <= à cette date
    - lieu      : recherche sur le nom ou l'adresse du lieu
    - statut    : filtre sur un ou plusieurs statuts
    - search    : recherche sur numéro, prestation, manifestation ou demandeur
    """

    serializer_class = RamassageSerializer
    permission_classes = [ReservationPermission]
    pagination_class = LieuPagination

    def get_queryset(self):
        """Retourne les réservations à ramasser."""

        queryset = (
            Reservation.objects.select_related(
                "prestation",
                "prestation__manifestation",
                "demandeur",
            )
            .prefetch_related(
                "lignes",
                "prestation__lieux",
            )
            .filter(date_retour_prevue__isnull=False)
            .exclude(
                statut__in=[
                    StatutReservation.ANNULEE,
                    StatutReservation.REFUSEE,
                    StatutReservation.CLOTUREE,
                ]
            )
            .order_by("date_retour_prevue")
        )

        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        lieu = self.request.query_params.get("lieu")
        search = self.request.query_params.get("search")
        statuts = self.request.query_params.getlist("statut")

        if not statuts:
            statut_param = self.request.query_params.get("statut")

            if statut_param:
                statuts = [
                    value.strip()
                    for value in statut_param.split(",")
                    if value.strip()
                ]

        if statuts:
            queryset = queryset.filter(statut__in=statuts)

        if date_from:
            queryset = queryset.filter(date_retour_prevue__gte=date_from)

        if date_to:
            queryset = queryset.filter(date_retour_prevue__lte=date_to)

        if lieu:
            queryset = queryset.filter(
                Q(prestation__lieux__nom__icontains=lieu)
                | Q(prestation__lieux__adresse__icontains=lieu)
            ).distinct()

        if search:
            queryset = queryset.filter(
                Q(numero__icontains=search)
                | Q(prestation__nom__icontains=search)
                | Q(prestation__manifestation__nom__icontains=search)
                | Q(demandeur__username__icontains=search)
                | Q(demandeur__first_name__icontains=search)
                | Q(demandeur__last_name__icontains=search)
            )

        return queryset


class BonRamassageView(APIView):
    """SCRUM-89 — Bon de ramassage imprimable."""

    permission_classes = [ReservationPermission]
    serializer_class = BonRamassageSerializer

    def get(self, request, pk, *args, **kwargs):
        """Retourne les données nécessaires pour imprimer un bon de ramassage."""

        reservation = (
            Reservation.objects.select_related(
                "prestation",
                "prestation__manifestation",
                "demandeur",
            )
            .prefetch_related(
                "lignes",
                "lignes__part",
                "prestation__lieux",
            )
            .filter(pk=pk)
            .first()
        )

        if reservation is None:
            return Response(
                {"detail": "Réservation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(reservation)

        return Response(
            {
                "titre": f"Bon de ramassage {reservation.numero}",
                "generated_at": timezone.now(),
                "reservation": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class ReservationConflictCheckView(APIView):
    """Détection des conflits de stock d'une réservation."""

    permission_classes = [ReservationPermission]

    def get(self, request, pk, *args, **kwargs):
        """Retourne les conflits de stock de la réservation."""

        reservation = Reservation.objects.prefetch_related("lignes").filter(pk=pk).first()

        if reservation is None:
            return Response(
                {"detail": "Réservation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        conflict_result = detect_reservation_conflicts(reservation)

        response_status = (
            status.HTTP_409_CONFLICT
            if conflict_result["has_conflict"]
            else status.HTTP_200_OK
        )

        return Response(conflict_result, status=response_status)


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
                "available_transitions": get_available_transitions(reservation.statut),
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


class ConflictsListView(APIView):
    """Liste les réservations actuellement en conflit."""

    permission_classes = [ReservationPermission]

    def get(self, request, *args, **kwargs):
        """Retourne les réservations en conflit triées par date de retrait prévue."""

        return Response(list_current_conflicts(), status=status.HTTP_200_OK)


class CatalogPartListView(APIView):
    """List InvenTree parts with catalog filters."""

    permission_classes = [CatalogPermission]
    serializer_class = CatalogPartSerializer
    pagination_class = CatalogPagination

    def get(self, request, *args, **kwargs):
        """Return a filtered and paginated catalog of InvenTree parts."""

        from part.models import Part

        queryset = Part.objects.select_related("category").all().order_by("name")

        search = request.query_params.get("search")
        category = request.query_params.get("category")
        categories = request.query_params.get("categories")
        active = request.query_params.get("active")
        rentable = request.query_params.get("rentable")
        virtual = request.query_params.get("virtual")
        ids = request.query_params.get("ids")

        if ids:
            queryset = queryset.filter(pk__in=self._parse_ids(ids))

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
        queryset = self._filter_virtual(queryset, virtual)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)

        self._attach_rentable_items(page)

        serializer = self.serializer_class(page, many=True)

        return paginator.get_paginated_response(serializer.data)

    def _attach_rentable_items(self, parts):
        """Attache RentableItem aux objets Part sans utiliser de reverse relation fragile."""

        part_ids = [part.id for part in parts]
        rentable_items = RentableItem.objects.filter(part_id__in=part_ids)
        rentable_by_part_id = {item.part_id: item for item in rentable_items}

        for part in parts:
            part._location_rentable_info = rentable_by_part_id.get(part.id)

    def _parse_ids(self, ids):
        """Parse une liste d'identifiants de Part séparés par des virgules."""

        return [int(value) for value in str(ids).split(",") if value.strip().isdigit()]

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

        part_ids = RentableItem.objects.filter(
            is_rentable=rentable_value
        ).values_list("part_id", flat=True)

        if rentable_value:
            return queryset.filter(Q(pk__in=part_ids) | ~Q(pk__in=RentableItem.objects.values_list("part_id", flat=True)))

        return queryset.filter(pk__in=part_ids)

    def _filter_virtual(self, queryset, virtual):
        """Filtre optionnel sur le drapeau article virtuel de RentableItem."""

        virtual_value = self._parse_boolean(virtual)

        if virtual_value is None:
            return queryset

        part_ids = RentableItem.objects.filter(
            is_virtual=virtual_value
        ).values_list("part_id", flat=True)

        if virtual_value:
            return queryset.filter(pk__in=part_ids)

        virtual_part_ids = RentableItem.objects.filter(
            is_virtual=True
        ).values_list("part_id", flat=True)

        return queryset.exclude(pk__in=virtual_part_ids)


class CatalogPartDetailView(APIView):
    """Fiche détail d'un Part du catalogue."""

    permission_classes = [CatalogPermission]
    serializer_class = CatalogPartSerializer

    def get(self, request, pk, *args, **kwargs):
        """Retourne le détail d'un article du catalogue."""

        from part.models import Part

        part = Part.objects.select_related("category").filter(pk=pk).first()

        if part is None:
            return Response(
                {"detail": "Part introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        part._location_rentable_info = RentableItem.objects.filter(part_id=pk).first()

        serializer = self.serializer_class(part)

        return Response(serializer.data, status=status.HTTP_200_OK)


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

        if "is_virtual" in request.data:
            defaults["is_virtual"] = bool(request.data.get("is_virtual"))

        if "stock_total" in request.data:
            defaults["stock_total"] = int(request.data.get("stock_total"))

        if not defaults:
            return Response(
                {
                    "detail": (
                        "Fournir au moins is_rentable, consommable, "
                        "is_virtual ou stock_total."
                    )
                },
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
                    "is_virtual": False,
                    "stock_total": 0,
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


class PrestationListView(generics.ListAPIView):
    """Liste des prestations, pour le sélecteur événement."""

    permission_classes = [RoleBasedPermission]
    serializer_class = PrestationSerializer
    pagination_class = LieuPagination

    def get_queryset(self):
        """Retourne les prestations, filtrées par recherche texte."""

        queryset = (
            Prestation.objects.select_related("manifestation")
            .prefetch_related("lieux")
            .all()
            .order_by("-date_debut")
        )

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(nom__icontains=search) | Q(manifestation__nom__icontains=search)
            )

        return queryset


class UserListView(generics.ListAPIView):
    """Liste des utilisateurs actifs, pour le sélecteur demandeur."""

    permission_classes = [RoleBasedPermission]
    serializer_class = UserSerializer
    pagination_class = CatalogPagination

    def get_queryset(self):
        """Retourne les utilisateurs actifs, filtrés par recherche texte."""

        queryset = get_user_model().objects.filter(is_active=True).order_by("username")

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )

        return queryset