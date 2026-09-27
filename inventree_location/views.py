"""API views for the InvenTreeLocation plugin."""

from datetime import date, timedelta
import random
import string
from urllib.error import HTTPError, URLError

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import ProtectedError
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import generics, permissions, status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.pagination import LimitOffsetPagination, PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .conflicts import (
    conflict_still_active,
    CONFLICT_STATUSES,
    compute_part_availability,
    detect_reservation_conflicts,
    list_current_conflicts,
    sync_conflict_registry,
)
from . import roles
from .models import (
    ConflictHistory,
    ConflictState,
    ConflictType,
    Client,
    Lieu,
    LigneReservation,
    Manifestation,
    Prestation,
    RentableItem,
    Reservation,
    ReturnIncident,
    ReturnIncidentType,
    StatutReservation,
)
from .calendrier import FenetreInvalide, bornes_fenetre, evenements_calendrier
from .execution import tournee_du_jour
from .livraison import (
    LivraisonRefusee,
    accepter_livraison,
    changer_etat_livraison,
    relacher_livraison,
)
from .ramassage import lignes_a_ramasser
from .permissions import (
    CatalogPermission,
    DeliveryAssignationPermission,
    DeliveryPermission,
    LieuPermission,
    ManifestationPermission,
    MarquerLivreePermission,
    PrestationPermission,
    PrestationRetourPermission,
    ReservationPermission,
    ReturnCheckinPermission,
    RoleBasedPermission,
)
from .retours import (
    CHAMPS_CHECKIN,
    etat_retour_de_la_ligne,
    projeter_incidents,
    quantites_depuis_payload,
    quantites_du_retour,
)
from .serializers import (
    STATUTS_DEJA_SORTIS,
    STATUTS_SANS_ENGAGEMENT,
    CatalogPartSerializer,
    DeliverySerializer,
    ExampleSerializer,
    ClientSerializer,
    LieuSerializer,
    ManifestationSerializer,
    PrestationRetourSerializer,
    PrestationSerializer,
    RentableItemSerializer,
    ReservationCheckinSerializer,
    ReservationSerializer,
    BonRamassageSerializer,
    RamassageSerializer,
    ReservationTransitionSerializer,
    ReturnIncidentHistorySerializer,
    ReturnIncidentSerializer,
    UserSerializer,
    geocode_candidates,
    sync_ligne_etat_retour,
)
from .stock import (
    _as_date,
    compute_part_availability_calendar,
    compute_prestation_stock,
    compute_stock_availability,
)
from .services.return_report import build_return_report
from .services.return_report_pdf import (
    PdfEngineUnavailable,
    generate_return_report_pdf,
)
from .services.workflow_service import (
    get_available_transitions,
    transition_reservation_status,
)


def _parse_csv_int_values(values):
    """Parse les valeurs CSV / répétables en une liste d'entiers uniques."""

    parsed = []
    seen = set()

    for value in values:
        for chunk in value.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue

            try:
                candidate = int(chunk)
            except ValueError:
                continue

            if candidate in seen:
                continue

            seen.add(candidate)
            parsed.append(candidate)

    return parsed


def _borne_journee(champ, valeur, sens):
    """Filtre de borne temporelle, comparé au jour entier si la borne est un jour."""

    valeur = valeur.strip()

    # `parse_datetime` accepte aussi une date seule : c'est l'absence d'heure
    # qui distingue « toute la journée » d'un instant précis.
    if ":" not in valeur and parse_date(valeur) is not None:
        return {f"{champ}__date__{sens}": valeur}

    return {f"{champ}__{sens}": valeur}


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


class ReservationPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 200


class CatalogPagination(PageNumberPagination):
    """Pagination for catalog results."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 100


class DeliveryPagination(PageNumberPagination):
    """Pagination de la tournée livreur."""

    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class LieuListCreateView(generics.ListCreateAPIView):
    """List and create places with GPS coordinates."""

    permission_classes = [LieuPermission]
    serializer_class = LieuSerializer
    pagination_class = LieuPagination

    def get_queryset(self):
        """Return places, with optional search filter."""

        queryset = Lieu.objects.all().order_by("nom")

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(nom__icontains=search) | Q(adresse__icontains=search)
            )

        return queryset


class SuppressionRefusee(APIException):
    """On a demandé de supprimer ce que d'autres objets retiennent encore."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Cet élément est encore référencé : suppression refusée."


def _retenu_par(refus):
    """Nomme, compte, et accorde ce qui retient la suppression."""

    par_modele = {}

    for objet in refus.protected_objects:
        libelle = str(objet._meta.verbose_name)
        par_modele[libelle] = par_modele.get(libelle, 0) + 1

    morceaux = [
        f"{nombre} {libelle}{'s' if nombre > 1 and not libelle.endswith('s') else ''}"
        for libelle, nombre in sorted(par_modele.items())
    ]

    total = sum(par_modele.values())
    verbe = "s'y rattache" if total == 1 else "s'y rattachent"

    return f"{', '.join(morceaux)} {verbe} encore"


class RefusDeSuppressionLisible:
    """Traduit le verrou de la base en refus lisible."""

    #: Ce qu'on supprimait, au singulier, tel qu'il se lit dans la phrase.
    objet_supprime = "cet élément"

    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except ProtectedError as refus:
            # « ce qui en dépend » plutôt qu'un pronom : « les » ou « la »
            # demanderait de connaître le genre et le nombre de ce qui bloque.
            raise SuppressionRefusee(
                f"Impossible de supprimer {self.objet_supprime} : "
                f"{_retenu_par(refus)}. "
                "Retirez d'abord ce qui en dépend, ou annulez plutôt que de "
                "supprimer."
            )


class LieuDetailView(RefusDeSuppressionLisible, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a place."""

    objet_supprime = "ce lieu"

    permission_classes = [LieuPermission]
    serializer_class = LieuSerializer
    queryset = Lieu.objects.all()


class GeocodeAddressView(APIView):
    """Geocode an address and return latitude / longitude."""

    permission_classes = [LieuPermission]

    def get(self, request, *args, **kwargs):
        """Return a list of geocoding candidates for a given address."""

        address = request.query_params.get("address", "").strip()

        if not address:
            return Response(
                {"detail": "Le paramètre address est obligatoire."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            results = geocode_candidates(address)
        except (HTTPError, URLError, TimeoutError) as error:
            return Response(
                {
                    "detail": "Le service de géocodage est temporairement indisponible.",
                    "error": str(error),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not results:
            return Response(
                {"detail": "Aucune coordonnée trouvée pour cette adresse."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({"results": results}, status=status.HTTP_200_OK)


class ReservationListCreateView(generics.ListCreateAPIView):
    """CRUD réservation — partie collection."""

    serializer_class = ReservationSerializer
    permission_classes = [ReservationPermission]
    pagination_class = ReservationPagination

    def get_queryset(self):
        """Retourne les réservations, filtrées par statut, période et recherche."""

        queryset = (
            Reservation.objects.select_related("prestation", "demandeur")
            .prefetch_related("lignes")
            .all()
            .order_by("-date_demande")
        )

        include_archived = self.request.query_params.get("include_archived")

        if str(include_archived).lower() not in {"1", "true", "yes"}:
            queryset = queryset.filter(is_archived=False)

        if roles.sees_only_deliverable_reservations(self.request.user):
            queryset = queryset.filter(statut=StatutReservation.VALIDEE)

        # Symétrique du filtre `manifestation` des prestations : l'arborescence
        # charge les bons au dépliage.
        prestation_id = self.request.query_params.get("prestation")

        if prestation_id:
            queryset = queryset.filter(prestation_id=prestation_id)

        statuts = self.request.query_params.getlist("statut")

        if statuts:
            queryset = queryset.filter(statut__in=statuts)

        categories = _parse_csv_int_values(
            self.request.query_params.getlist("categories")
        )

        if categories:
            queryset = queryset.filter(
                lignes__part__category_id__in=categories
            ).distinct()

        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if date_from:
            queryset = queryset.filter(
                **_borne_journee("date_retour_prevue", date_from, "gte")
            )

        if date_to:
            queryset = queryset.filter(
                **_borne_journee("date_retrait_prevue", date_to, "lte")
            )

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


class ReservationCalendarView(APIView):
    """Évènements du calendrier mensuel des réservations (DIS-01)."""

    permission_classes = [ReservationPermission]

    def get(self, request, *args, **kwargs):
        """Retourne les réservations de la fenêtre, au format FullCalendar."""

        try:
            debut, fin = bornes_fenetre(
                request.query_params.get("from"),
                request.query_params.get("to"),
            )

            # Une réservation est affichée dès qu'elle chevauche la fenêtre :
            # celle qui a commencé le mois dernier et court toujours reste
            evenements = evenements_calendrier(
                request.user,
                debut={"fin_calendrier__date__gte": debut},
                fin={"debut_calendrier__date__lte": fin},
            )
        except FenetreInvalide as refus:
            return Response(
                {"detail": refus.detail}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(evenements, status=status.HTTP_200_OK)


class DeliveryMarquerLivreeView(APIView):
    """Marque une réservation livrée depuis la tournée du livreur."""

    permission_classes = [MarquerLivreePermission]

    def post(self, request, pk, *args, **kwargs):
        """Applique la transition si la réservation est bien validée."""

        reservation = Reservation.objects.filter(pk=pk).first()

        if reservation is None:
            return Response(
                {"detail": "Réservation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if reservation.statut != StatutReservation.VALIDEE:
            return Response(
                {
                    "detail": (
                        "Seule une réservation validée peut être marquée livrée."
                    ),
                    "current_status": reservation.statut,
                },
                status=status.HTTP_409_CONFLICT,
            )

        transition_reservation_status(
            reservation,
            StatutReservation.LIVREE,
            user=request.user,
            comment=request.data.get("commentaire", ""),
        )
        reservation.refresh_from_db()

        return Response(
            {"reservation": reservation.pk, "statut": reservation.statut},
            status=status.HTTP_200_OK,
        )


def _refus_livraison(refus):
    """Traduit un refus métier de livraison en réponse HTTP."""

    return Response({"detail": refus.detail}, status=refus.status_code)


class DeliveryAccepterView(APIView):
    """Pool commun des livraisons (US-18) : prendre en charge, ou relâcher."""

    permission_classes = [DeliveryAssignationPermission]
    serializer_class = DeliverySerializer

    def post(self, request, pk, *args, **kwargs):
        """S'attribue la livraison si elle est encore libre."""

        try:
            reservation = accepter_livraison(pk, request.user)
        except LivraisonRefusee as refus:
            return _refus_livraison(refus)

        return Response(DeliverySerializer(reservation).data, status=status.HTTP_200_OK)

    def delete(self, request, pk, *args, **kwargs):
        """Remet la livraison dans le pool commun."""

        try:
            reservation = relacher_livraison(pk, request.user)
        except LivraisonRefusee as refus:
            return _refus_livraison(refus)

        return Response(DeliverySerializer(reservation).data, status=status.HTTP_200_OK)


class DeliveryEtatView(APIView):
    """Progression d'une livraison assignée (US-19) : en route, livrée, problème."""

    permission_classes = [DeliveryAssignationPermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = DeliverySerializer

    def patch(self, request, pk, *args, **kwargs):
        """Applique le changement d'état demandé."""

        etat = str(request.data.get("etat") or "").strip()
        commentaire = str(request.data.get("commentaire") or "")

        try:
            reservation = changer_etat_livraison(
                pk,
                etat,
                request.user,
                commentaire=commentaire,
                photo=request.FILES.get("photo"),
            )
        except LivraisonRefusee as refus:
            return _refus_livraison(refus)

        return Response(DeliverySerializer(reservation).data, status=status.HTTP_200_OK)


class TourneeView(APIView):
    """Tournée d'une journée : les arrêts par lieu, plus le récapitulatif global."""

    permission_classes = [DeliveryPermission]

    def get(self, request):
        parametre = request.query_params.get("date")

        if parametre:
            jour = parse_date(parametre)

            if jour is None:
                raise ValidationError({"date": "Date illisible : AAAA-MM-JJ attendu."})
        else:
            jour = timezone.localdate()

        bons = Reservation.objects.select_related(
            "prestation__lieu",
            "prestation__manifestation__client",
        ).prefetch_related("lignes__part", "lignes__livraisons")

        # Un livreur pur ne voit que ce qui est à livrer, comme sur sa liste.
        if roles.sees_only_deliverable_reservations(request.user):
            bons = bons.filter(statut=StatutReservation.VALIDEE)

        tournee = tournee_du_jour(jour, bons)

        return Response(
            {
                "date": tournee["date"],
                "arrets": [
                    {
                        **arret,
                        "lieu": (
                            LieuSerializer(arret["lieu"]).data
                            if arret["lieu"] is not None
                            else None
                        ),
                    }
                    for arret in tournee["arrets"]
                ],
                "recap_total": tournee["recap_total"],
                "quantite_totale": tournee["quantite_totale"],
            },
            status=status.HTTP_200_OK,
        )


class DeliveryListView(generics.ListAPIView):
    """Tournée livreur : réservations à livrer / livrées, enrichies (US livreur)."""

    serializer_class = DeliverySerializer
    permission_classes = [DeliveryPermission]
    pagination_class = DeliveryPagination

    #: Statuts affichés par défaut quand `statut` n'est pas fourni.
    DEFAULT_STATUTS = (StatutReservation.VALIDEE, StatutReservation.LIVREE)

    def get_queryset(self):
        """Retourne les réservations à livrer, filtrées par statut, période et lieu."""

        queryset = (
            Reservation.objects.select_related(
                "prestation",
                "prestation__lieu",
                "prestation__manifestation",
                "prestation__manifestation__contact",
                "prestation__manifestation__client",
                "livreur_assigne",
                # `demandeur_nom` du sérialiseur lit ce compte : sans jointure,
                # c'est une requête par bon de la tournée.
                "demandeur",
            )
            .prefetch_related(
                "lignes__part__rentable_info",
                # Sans ce préchargement, `quantite_deposee` et sa restante
                # coûtent une requête par ligne de chaque bon de la tournée.
                "lignes__livraisons",
                "livraison_status_logs__changed_by",
            )
            .all()
            .order_by("date_retrait_prevue")
        )

        # Un livreur pur ne voit que les réservations validées.
        if roles.sees_only_deliverable_reservations(self.request.user):
            queryset = queryset.filter(statut=StatutReservation.VALIDEE)
        else:
            statuts = self.request.query_params.getlist("statut")
            queryset = queryset.filter(statut__in=statuts or self.DEFAULT_STATUTS)

        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if date_from:
            queryset = queryset.filter(
                **_borne_journee("date_retour_prevue", date_from, "gte")
            )

        if date_to:
            queryset = queryset.filter(
                **_borne_journee("date_retrait_prevue", date_to, "lte")
            )

        lieux = _parse_csv_int_values(self.request.query_params.getlist("lieu"))

        if lieux:
            queryset = queryset.filter(prestation__lieu_id__in=lieux)

        return queryset


class ReservationDetailView(
    RefusDeSuppressionLisible, generics.RetrieveUpdateDestroyAPIView
):
    """CRUD réservation — partie instance unique."""

    objet_supprime = "ce bon"

    queryset = Reservation.objects.prefetch_related(
        "lignes",
        "status_logs",
    ).all()
    serializer_class = ReservationSerializer
    permission_classes = [ReservationPermission]

    #: Une réservation n'est modifiable qu'avant validation.
    STATUTS_EDITABLES = (StatutReservation.BROUILLON, StatutReservation.SOUMISE)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.statut not in self.STATUTS_EDITABLES:
            raise ValidationError({
                "detail": (
                    f"Une réservation « {instance.get_statut_display().lower()} » "
                    "n'est plus modifiable."
                )
            })
        return super().update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        # Seul un brouillon se supprime ; au-delà on annule via une transition.
        if instance.statut != StatutReservation.BROUILLON:
            raise ValidationError({
                "detail": "Seule une réservation en brouillon peut être supprimée."
            })
        # Par `super()`, et non `instance.delete()` : c'est ce qui laisse le
        # mixin traduire un refus de la base en 409 plutôt qu'en 500.
        super().perform_destroy(instance)


class RamassageListView(generics.ListAPIView):
    """SCRUM-89 — Liste des ramassages à effectuer."""

    serializer_class = RamassageSerializer
    permission_classes = [ReservationPermission]
    pagination_class = LieuPagination

    def get_queryset(self):
        """Retourne les réservations à ramasser."""

        queryset = (
            Reservation.objects.select_related(
                "prestation",
                "prestation__manifestation",
                "prestation__lieu",
                "demandeur",
            )
            .prefetch_related(
                "lignes__part__rentable_info",
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

        # Un livreur pur ne voit que les réservations validées, comme sur
        # `reservations/` et `deliveries/` (cf. roles.py).
        if roles.sees_only_deliverable_reservations(self.request.user):
            queryset = queryset.filter(statut=StatutReservation.VALIDEE)

        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        lieu = self.request.query_params.get("lieu")
        search = self.request.query_params.get("search")
        statuts = self.request.query_params.getlist("statut")

        if not statuts:
            statut_param = self.request.query_params.get("statut")

            if statut_param:
                statuts = [
                    value.strip() for value in statut_param.split(",") if value.strip()
                ]

        if statuts:
            queryset = queryset.filter(statut__in=statuts)

        if date_from:
            queryset = queryset.filter(
                **_borne_journee("date_retour_prevue", date_from, "gte")
            )

        if date_to:
            queryset = queryset.filter(
                **_borne_journee("date_retour_prevue", date_to, "lte")
            )

        if lieu:
            queryset = queryset.filter(
                Q(prestation__lieu__nom__icontains=lieu)
                | Q(prestation__lieu__adresse__icontains=lieu)
            )

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
                "prestation__lieu",
                "demandeur",
            )
            .prefetch_related(
                "lignes__part__rentable_info",
            )
            .filter(pk=pk)
            .first()
        )

        if reservation is None:
            return Response(
                {"detail": "Réservation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Même restriction que la liste : un livreur pur n'imprime pas le bon
        # d'une réservation qu'il n'a pas le droit de voir.
        if (
            roles.sees_only_deliverable_reservations(request.user)
            and reservation.statut != StatutReservation.VALIDEE
        ):
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
    """Détection des conflits de stock d'une réservation (US-03 / SCRUM-76)."""

    permission_classes = [ReservationPermission]

    def get(self, request, pk, *args, **kwargs):
        """Retourne les conflits de stock de la réservation."""

        reservation = (
            Reservation.objects.prefetch_related("lignes").filter(pk=pk).first()
        )

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

        new_status = serializer.validated_data["statut"]

        # L'arbitrage (valider / refuser) est réservé au gestionnaire et à l'admin.
        arbitrage = {StatutReservation.VALIDEE, StatutReservation.REFUSEE}
        if new_status in arbitrage and not roles.can_arbitrate_reservations(
            request.user
        ):
            return Response(
                {"detail": "Seul un gestionnaire peut valider ou refuser."},
                status=status.HTTP_403_FORBIDDEN,
            )

        result = transition_reservation_status(
            reservation=reservation,
            new_status=new_status,
            user=request.user,
            comment=serializer.validated_data.get("comment", ""),
        )

        return Response(result, status=status.HTTP_200_OK)


class StockAvailabilityCheckView(APIView):
    """Verifie en temps reel la disponibilite stock d'un article sur une periode."""

    permission_classes = [ReservationPermission]

    def get(self, request, *args, **kwargs):
        from part.models import Part

        part_id = request.query_params.get("part")
        quantity = request.query_params.get("quantity", "1")
        start_raw = request.query_params.get("date_retrait_prevue")
        end_raw = request.query_params.get("date_retour_prevue")
        reservation_raw = request.query_params.get("reservation")

        if not part_id or not start_raw or not end_raw:
            return Response(
                {
                    "detail": (
                        "Les parametres part, date_retrait_prevue et "
                        "date_retour_prevue sont obligatoires."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            part_id = int(part_id)
            quantity = max(int(quantity), 1)
        except ValueError:
            return Response(
                {"detail": "Les parametres part et quantity doivent etre numeriques."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start = parse_datetime(start_raw) or parse_date(start_raw)
        end = parse_datetime(end_raw) or parse_date(end_raw)

        if start is None or end is None:
            return Response(
                {
                    "detail": (
                        "Les dates fournies sont invalides. "
                        "Utilisez un format ISO 8601."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        part = Part.objects.filter(pk=part_id).first()

        if part is None:
            return Response(
                {"detail": "Article introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        exclude_reservation_id = None

        if reservation_raw:
            try:
                exclude_reservation_id = int(reservation_raw)
            except ValueError:
                return Response(
                    {"detail": "Le parametre reservation doit etre numerique."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        availability = compute_part_availability(
            part,
            quantity,
            start,
            end,
            exclude_resa_id=exclude_reservation_id,
        )

        return Response(
            {
                "part_id": part.pk,
                "part_name": getattr(part, "name", str(part)),
                "requested_quantity": quantity,
                "total_stock": availability["total_stock"],
                "already_reserved_quantity": availability["already_reserved_quantity"],
                "available_quantity": availability["available_quantity"],
                "missing_quantity": availability["missing_quantity"],
                "is_virtual": availability["is_virtual"],
                "has_conflict": availability["has_conflict"],
                "tension_level": availability["tension_level"],
                "occupation_rate": availability["occupation_rate"],
            },
            status=(
                status.HTTP_409_CONFLICT
                if availability["has_conflict"]
                else status.HTTP_200_OK
            ),
        )


class ReservationRetourView(APIView):
    """Déclaration du retour d'une prestation ligne par ligne (SCRUM-95)."""

    permission_classes = [PrestationRetourPermission]
    serializer_class = PrestationRetourSerializer

    #: Consultable tant que le bon est livré ou déjà retourné.
    ELIGIBLE_STATUTS = {StatutReservation.LIVREE, StatutReservation.RETOURNEE}
    #: Déclarable seulement tant que le bon est livré.
    DECLARABLE_STATUTS = {StatutReservation.LIVREE}

    NOT_DECLARABLE_DETAIL = (
        "La déclaration de retour n'est accessible que pour une réservation livrée."
    )
    NOT_ELIGIBLE_DETAIL = (
        "La déclaration de retour n'est accessible que pour "
        "une réservation livrée ou déjà en cours de retour."
    )

    def _get_reservation(self, pk, *, lock=False):
        """Charge la réservation ; `lock` pose un verrou de ligne."""

        queryset = Reservation.objects.prefetch_related(
            "lignes", "lignes__part", "lignes__part__rentable_info"
        )

        if lock:
            queryset = queryset.select_for_update()

        return queryset.filter(pk=pk).first()

    def _conflict_response(self, reservation, detail):
        return Response(
            {"detail": detail, "current_status": reservation.statut},
            status=status.HTTP_409_CONFLICT,
        )

    @staticmethod
    def _statut_retour(lignes):
        total_demandee = sum(ligne.quantite_demandee for ligne in lignes)
        total_rendue = sum(
            min(ligne.quantite_retournee, ligne.quantite_demandee) for ligne in lignes
        )

        if total_demandee <= 0 or total_rendue <= 0:
            return "aucun", total_demandee, total_rendue

        if total_rendue >= total_demandee:
            return "complet", total_demandee, total_rendue

        return "partiel", total_demandee, total_rendue

    def _serialize_lignes(self, lignes):
        return [
            {
                "id": ligne.pk,
                "part": ligne.part_id,
                "part_name": getattr(ligne.part, "name", str(ligne.part)),
                "quantite_demandee": ligne.quantite_demandee,
                "quantite_retournee": ligne.quantite_retournee,
            }
            for ligne in lignes
        ]

    def get(self, request, pk, *args, **kwargs):
        """Retourne la réservation et ses lignes si un retour est possible."""

        reservation = self._get_reservation(pk)

        if reservation is None:
            return Response(
                {"detail": "Réservation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if reservation.statut not in self.ELIGIBLE_STATUTS:
            return self._conflict_response(reservation, self.NOT_ELIGIBLE_DETAIL)

        # Même périmètre que le bon de ramassage : un service ne revient pas,
        # le compter classait en « partiel » un bon dont tout le matériel était
        lignes = lignes_a_ramasser(reservation)
        statut_retour, total_demandee, total_rendue = self._statut_retour(lignes)

        return Response(
            {
                "reservation": reservation.pk,
                "numero": reservation.numero,
                "statut": reservation.statut,
                "statut_retour": statut_retour,
                "quantite_demandee_totale": total_demandee,
                "quantite_rendue_totale": total_rendue,
                "lignes": self._serialize_lignes(lignes),
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, pk, *args, **kwargs):
        """Enregistre les quantités rendues et met à jour le statut de retour."""

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Les écritures de lignes et la transition sont indissociables : sans
        # la transaction, une transition qui échoue laissait les quantités déjà
        with transaction.atomic():
            reservation = self._get_reservation(pk, lock=True)

            if reservation is None:
                return Response(
                    {"detail": "Réservation introuvable."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if reservation.statut not in self.DECLARABLE_STATUTS:
                return self._conflict_response(reservation, self.NOT_DECLARABLE_DETAIL)

            lignes_by_id = {ligne.pk: ligne for ligne in lignes_a_ramasser(reservation)}
            errors = {}
            vues = set()

            for entry in serializer.validated_data["lignes"]:
                ligne = lignes_by_id.get(entry["id"])

                if ligne is None:
                    errors[str(entry["id"])] = (
                        "Cette ligne n'appartient pas à la réservation."
                    )
                    continue

                # Un doublon était traité en dernier-gagnant silencieux : deux
                # envois pour la même ligne sous-comptaient le retour.
                if entry["id"] in vues:
                    errors[str(entry["id"])] = (
                        "Cette ligne est présente plusieurs fois dans l'envoi."
                    )
                    continue

                vues.add(entry["id"])

                if entry["quantite_rendue"] > ligne.quantite_demandee:
                    errors[str(entry["id"])] = (
                        f"La quantité rendue ({entry['quantite_rendue']}) ne peut "
                        f"pas dépasser la quantité demandée "
                        f"({ligne.quantite_demandee})."
                    )

            if errors:
                return Response({"lignes": errors}, status=status.HTTP_400_BAD_REQUEST)

            for entry in serializer.validated_data["lignes"]:
                ligne = lignes_by_id[entry["id"]]
                ligne.quantite_retournee = entry["quantite_rendue"]
                ligne.save(update_fields=["quantite_retournee", "updated_at"])

            lignes = list(lignes_by_id.values())
            statut_retour, total_demandee, total_rendue = self._statut_retour(lignes)

            if statut_retour == "complet":
                transition_reservation_status(
                    reservation=reservation,
                    new_status=StatutReservation.RETOURNEE,
                    user=request.user,
                    comment="Retour complet déclaré (SCRUM-95).",
                )
                reservation.refresh_from_db()

        return Response(
            {
                "reservation": reservation.pk,
                "numero": reservation.numero,
                "statut": reservation.statut,
                "statut_retour": statut_retour,
                "quantite_demandee_totale": total_demandee,
                "quantite_rendue_totale": total_rendue,
                "lignes": self._serialize_lignes(lignes),
            },
            status=status.HTTP_200_OK,
        )


class ReturnIncidentListCreateView(generics.ListCreateAPIView):
    """Liste et crée les incidents de retour (manquant / cassé)."""

    permission_classes = [ReturnCheckinPermission]
    serializer_class = ReturnIncidentSerializer

    def get_queryset(self):
        """Retourne les incidents, filtrés par réservation et type."""

        queryset = (
            ReturnIncident.objects.select_related(
                "line__part", "line__reservation", "reported_by"
            )
            .all()
            .order_by("-reported_at")
        )

        # Validé plutôt que passé tel quel : `?reservation=abc` remontait
        # jusqu'au ORM et sortait en 500 au lieu d'un 400.
        reservation_id = parse_optional_int_param(self.request, "reservation")

        if reservation_id is not None:
            queryset = queryset.filter(line__reservation_id=reservation_id)

        incident_type = self.request.query_params.get("type")

        if incident_type:
            queryset = queryset.filter(type=incident_type)

        return queryset


class ReturnIncidentHistoryView(generics.ListAPIView):
    """Retourne les incidents de retour des 90 derniers jours."""

    permission_classes = [ReturnCheckinPermission]
    serializer_class = ReturnIncidentHistorySerializer

    #: Profondeur d'historique exposée par la vue (SCRUM-100).
    HISTORY_DAYS = 90

    def get_queryset(self):
        cutoff = timezone.now() - timedelta(days=self.HISTORY_DAYS)
        queryset = (
            ReturnIncident.objects.filter(reported_at__gte=cutoff)
            .select_related(
                "line__part",
                "line__reservation__prestation__manifestation",
                "reported_by",
            )
            .order_by("-reported_at")
        )

        incident_type = self.request.query_params.get("type")
        if incident_type:
            # Un type inconnu renvoyait 200 avec une liste vide : sur une vue
            # de suivi qualité, une faute de frappe se lisait « aucun incident ».
            if incident_type not in ReturnIncidentType.values:
                raise ValidationError({
                    "type": (
                        "Type d'incident inconnu : "
                        f"{', '.join(ReturnIncidentType.values)} attendus."
                    )
                })

            queryset = queryset.filter(type=incident_type)

        object_name = self.request.query_params.get("object")
        if object_name:
            queryset = queryset.filter(line__part__name__icontains=object_name)

        event_name = self.request.query_params.get("event")
        if event_name:
            queryset = queryset.filter(
                line__reservation__prestation__manifestation__nom__icontains=event_name
            )

        return queryset


class ReturnIncidentDetailView(
    RefusDeSuppressionLisible, generics.RetrieveUpdateDestroyAPIView
):
    """Détail, mise à jour et suppression d'un incident de retour."""

    objet_supprime = "cet incident"

    permission_classes = [ReturnCheckinPermission]
    serializer_class = ReturnIncidentSerializer
    queryset = ReturnIncident.objects.select_related(
        "line__part", "line__reservation", "reported_by"
    )

    def perform_destroy(self, instance):
        """Supprime l'incident puis réaligne l'état de retour de la ligne."""

        ligne = instance.line
        super().perform_destroy(instance)
        sync_ligne_etat_retour(ligne)


class ReturnLossReportView(APIView):
    """Rapport de pertes agrégé : manquants, cassés, détruits et facturés."""

    permission_classes = [ReturnCheckinPermission]

    #: Clés d'agrégation par type d'incident, alignées sur ReturnIncidentType.
    TOTAL_KEYS = {
        ReturnIncidentType.MISSING: "missing",
        ReturnIncidentType.BROKEN: "broken",
        ReturnIncidentType.DESTROYED: "destroyed",
    }

    def _nouvelle_entree(self, **identite):
        """Entrée de ventilation à zéro, une clé par type plus « facturé »."""

        entree = dict(identite)
        entree.update({cle: 0 for cle in self.TOTAL_KEYS.values()})
        entree["billed"] = 0

        return entree

    def get(self, request, *args, **kwargs):
        """Retourne le rapport de pertes agrégé."""

        reservation_id = parse_optional_int_param(request, "reservation")

        incidents = ReturnIncident.objects.select_related(
            "line__part", "line__reservation"
        )

        if reservation_id is not None:
            incidents = incidents.filter(line__reservation_id=reservation_id)

        incidents = list(incidents)

        totaux = self._nouvelle_entree()
        by_part = {}
        by_reservation = {}

        for incident in incidents:
            # Un type ajouté au modèle sans passer ici ne doit pas faire tomber
            # le rapport sur un KeyError : il reste compté dans `count` et,
            cle = self.TOTAL_KEYS.get(incident.type)

            part_entry = by_part.setdefault(
                incident.line.part_id,
                self._nouvelle_entree(
                    part_id=incident.line.part_id,
                    part_name=incident.line.part.name,
                ),
            )
            reservation_entry = by_reservation.setdefault(
                incident.line.reservation_id,
                self._nouvelle_entree(
                    reservation_id=incident.line.reservation_id,
                    reservation_numero=incident.line.reservation.numero,
                ),
            )

            if cle is not None:
                totaux[cle] += incident.qty
                part_entry[cle] += incident.qty
                reservation_entry[cle] += incident.qty

            if incident.bill_client:
                totaux["billed"] += incident.qty
                part_entry["billed"] += incident.qty
                reservation_entry["billed"] += incident.qty

        return Response(
            {
                "count": len(incidents),
                "total_missing": totaux["missing"],
                "total_broken": totaux["broken"],
                "total_destroyed": totaux["destroyed"],
                "total_billed": totaux["billed"],
                "by_part": sorted(
                    by_part.values(), key=lambda item: item["part_name"].lower()
                ),
                "by_reservation": sorted(
                    by_reservation.values(),
                    key=lambda item: item["reservation_numero"],
                ),
            },
            status=status.HTTP_200_OK,
        )


class ReturnReportView(APIView):
    """Rapport synthétique du retour d'une réservation (JSON)."""

    permission_classes = [ReturnCheckinPermission]

    def get(self, request, pk, *args, **kwargs):
        """Retourne le récap retour : rendu / manquant / cassé / détruit."""
        try:
            report = build_return_report(pk)
        except ValueError:
            return Response(
                {"detail": "Réservation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(report, status=status.HTTP_200_OK)


class ReturnReportPdfView(APIView):
    """Export PDF imprimable du rapport de retour."""

    permission_classes = [ReturnCheckinPermission]

    def get(self, request, pk, *args, **kwargs):
        """Génère et renvoie le PDF du rapport de retour."""
        try:
            pdf_buffer = generate_return_report_pdf(pk)
        except ValueError:
            return Response(
                {"detail": "Réservation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except PdfEngineUnavailable as error:
            # L'absence du moteur PDF ne concerne que cet export : elle ne doit
            # pas ressortir en 500 opaque.
            return Response(
                {"detail": str(error)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        response = HttpResponse(
            pdf_buffer.getvalue(),
            content_type="application/pdf",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="rapport-retour-{pk}.pdf"'
        )
        return response


class ReservationCheckinView(APIView):
    """Check-in retour ligne par ligne (SCRUM-94) : OK / manquant / casse."""

    permission_classes = [ReturnCheckinPermission]
    serializer_class = ReservationCheckinSerializer

    NOT_FOUND_DETAIL = "Reservation introuvable."
    NOT_LIVREE_DETAIL = (
        "Le check-in retour n'est accessible que pour une reservation livree."
    )

    def _get_reservation(self, pk, *, lock=False):
        """Charge la reservation et ses lignes ; `lock` pose un verrou de ligne."""

        queryset = Reservation.objects.prefetch_related(
            "lignes", "lignes__part", "lignes__part__rentable_info"
        )

        if lock:
            queryset = queryset.select_for_update()

        return queryset.filter(pk=pk).first()

    def _not_found_response(self):
        return Response(
            {"detail": self.NOT_FOUND_DETAIL},
            status=status.HTTP_404_NOT_FOUND,
        )

    def _not_livree_response(self, reservation):
        return Response(
            {
                "detail": self.NOT_LIVREE_DETAIL,
                "current_status": reservation.statut,
            },
            status=status.HTTP_409_CONFLICT,
        )

    def get(self, request, pk, *args, **kwargs):
        """Retourne la reservation et ses lignes si elle est livree."""

        reservation = self._get_reservation(pk)

        if reservation is None:
            return self._not_found_response()

        if reservation.statut != StatutReservation.LIVREE:
            return self._not_livree_response(reservation)

        return Response(
            {
                "reservation": reservation.pk,
                "numero": reservation.numero,
                "statut": reservation.statut,
                "lignes": [
                    self._ligne_pointee(ligne)
                    for ligne in lignes_a_ramasser(reservation)
                ],
            },
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _validate_payload_lignes(payload_lignes, lignes_by_id):
        """Erreurs par ligne : appartenance, somme, et couverture complete."""

        errors = {}
        seen = set()

        for entry in payload_lignes:
            ligne = lignes_by_id.get(entry["id"])

            if ligne is None:
                errors[str(entry["id"])] = (
                    "Cette ligne n'appartient pas a la reservation."
                )
                continue

            if entry["id"] in seen:
                errors[str(entry["id"])] = "Cette ligne est presente en double."
                continue

            seen.add(entry["id"])
            total = entry["ok"] + entry["manquant"] + entry["casse"]

            if total != ligne.quantite_demandee:
                errors[str(entry["id"])] = (
                    "La somme OK + manquant + casse (" + str(total) + ") doit "
                    "egaler la quantite demandee ("
                    + str(ligne.quantite_demandee)
                    + ")."
                )

        for ligne_id in lignes_by_id:
            if ligne_id not in seen:
                errors[str(ligne_id)] = (
                    "Cette ligne doit etre pointee pour cloturer le check-in."
                )

        return errors

    @staticmethod
    def _ligne_pointee(ligne):
        """Ligne telle que la renvoie le check-in."""

        quantites = quantites_du_retour(ligne)

        return {
            "id": ligne.pk,
            "part": ligne.part_id,
            "part_name": getattr(ligne.part, "name", str(ligne.part)),
            "quantite_demandee": ligne.quantite_demandee,
            "quantite_retour_ok": quantites["ok"],
            "quantite_retour_manquant": quantites["manquant"],
            "quantite_retour_casse": quantites["casse"],
            "commentaire": ligne.commentaire,
        }

    @staticmethod
    def _apply_checkin_ligne(ligne, entry, user=None):
        """Reporte une entree de check-in sur la ligne et la sauvegarde."""

        # Seule quantité conservée sur la ligne : ce qui est revenu
        # physiquement. Le manquant n'est pas revenu, le cassé si.
        ligne.quantite_retournee = entry["ok"] + entry["casse"]

        update_fields = [
            "quantite_retournee",
            "etat_retour",
            "updated_at",
        ]

        # `commentaire` porte aussi la note saisie a la reservation : on ne
        # l'ecrase que si le check-in en fournit une explicitement.
        if "commentaire" in entry:
            ligne.commentaire = entry["commentaire"]
            update_fields.append("commentaire")

        ligne.save(update_fields=update_fields)

        # Le pointage alimente le registre d'incidents comme la saisie de
        # ramassage, sinon un objet cassé constaté au check-in n'apparaissait
        projeter_incidents(
            ligne,
            user,
            quantites_depuis_payload(entry, CHAMPS_CHECKIN),
        )
        # La règle était réécrite ici alors qu'elle existait déjà dans
        # `retours.py` : deux copies pour une seule règle.
        ligne.etat_retour = etat_retour_de_la_ligne(ligne)
        ligne.save(update_fields=["etat_retour", "updated_at"])

    def post(self, request, pk, *args, **kwargs):
        """Enregistre le check-in retour et cloture la reservation."""

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload_lignes = serializer.validated_data["lignes"]

        # Ecritures des lignes et transitions de statut dans une seule
        # transaction : un echec en cours de route ne doit pas laisser la
        with transaction.atomic():
            reservation = self._get_reservation(pk, lock=True)

            if reservation is None:
                return self._not_found_response()

            if reservation.statut != StatutReservation.LIVREE:
                return self._not_livree_response(reservation)

            lignes_by_id = {ligne.pk: ligne for ligne in lignes_a_ramasser(reservation)}
            errors = self._validate_payload_lignes(payload_lignes, lignes_by_id)

            if errors:
                return Response({"lignes": errors}, status=status.HTTP_400_BAD_REQUEST)

            incidents = []

            for entry in payload_lignes:
                ligne = lignes_by_id[entry["id"]]
                self._apply_checkin_ligne(ligne, entry, request.user)

                if entry["manquant"] > 0 or entry["casse"] > 0:
                    incidents.append(
                        str(getattr(ligne.part, "name", ligne.part_id))
                        + ": "
                        + str(entry["manquant"])
                        + " manquant(s), "
                        + str(entry["casse"])
                        + " casse(s)"
                    )

            incident_comment = (
                "Incidents check-in : " + "; ".join(incidents)
                if incidents
                else "Check-in retour sans incident."
            )

            transition_reservation_status(
                reservation=reservation,
                new_status=StatutReservation.RETOURNEE,
                user=request.user,
                comment=incident_comment,
            )
            transition_reservation_status(
                reservation=reservation,
                new_status=StatutReservation.CLOTUREE,
                user=request.user,
                comment="Cloturee automatiquement apres check-in retour.",
            )

        return Response(
            {
                "reservation": reservation.pk,
                "statut": reservation.statut,
                "incidents": incidents,
            },
            status=status.HTTP_200_OK,
        )


class ConflictsListView(APIView):
    """Liste les réservations actuellement en conflit."""

    permission_classes = [ReservationPermission]

    def get(self, request, *args, **kwargs):
        """Retourne les réservations en conflit triées par date de retrait prévue."""

        conflits = list_current_conflicts()
        sync_conflict_registry(conflits)

        return Response(conflits, status=status.HTTP_200_OK)


class ConflictHistoryListView(APIView):
    """Liste l'historique des conflits (ouverts et resolus)."""

    permission_classes = [ReservationPermission]

    def get(self, request, *args, **kwargs):
        conflict_type = request.query_params.get("type", "all")
        state = request.query_params.get("state", "all")
        reservation_id = request.query_params.get("reservation")

        queryset = (
            ConflictHistory.objects.select_related(
                "reservation",
                "conflicting_reservation",
                "resolved_by",
                "part",
            )
            .all()
            .order_by("-created_at")
        )

        if conflict_type in {ConflictType.STOCK, ConflictType.LOCATION}:
            queryset = queryset.filter(conflict_type=conflict_type)

        if state in {ConflictState.OPEN, ConflictState.RESOLVED}:
            queryset = queryset.filter(state=state)

        if reservation_id and str(reservation_id).isdigit():
            queryset = queryset.filter(reservation_id=int(reservation_id))

        payload = []
        for item in queryset:
            payload.append({
                "id": item.pk,
                "conflict_type": item.conflict_type,
                "state": item.state,
                "reservation_id": item.reservation_id,
                "reservation_numero": item.reservation.numero,
                "conflicting_reservation_id": item.conflicting_reservation_id,
                "part_id": item.part_id,
                "part_name": getattr(item.part, "name", "") if item.part_id else "",
                "period_start": item.period_start,
                "period_end": item.period_end,
                "location_key": item.location_key,
                "details": item.details,
                "created_at": item.created_at,
                "resolved_at": item.resolved_at,
                "resolved_by": (
                    item.resolved_by.get_full_name() or item.resolved_by.username
                    if item.resolved_by
                    else ""
                ),
                "resolution_note": item.resolution_note,
            })

        return Response(payload, status=status.HTTP_200_OK)


class ConflictHistoryResolveView(APIView):
    """Marque une entree d'historique de conflit comme resolue."""

    permission_classes = [ReservationPermission]

    def patch(self, request, pk, *args, **kwargs):
        conflict = ConflictHistory.objects.filter(pk=pk).first()

        if conflict is None:
            return Response(
                {"detail": "Conflit introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if conflict.state == ConflictState.RESOLVED:
            return Response(
                {"detail": "Conflit deja resolu."},
                status=status.HTTP_200_OK,
            )

        # Clore une entrée dont la cause tient encore ne résolvait rien : le
        # registre affirmait « traité » pendant que la pénurie restait entière.
        encore_actif, motif = conflict_still_active(conflict)

        if encore_actif:
            return Response(
                {
                    "detail": (
                        f"Conflit toujours actif : {motif}. "
                        "Traitez la cause avant de le clore."
                    ),
                    "reason": motif,
                    "state": conflict.state,
                },
                status=status.HTTP_409_CONFLICT,
            )

        conflict.state = ConflictState.RESOLVED
        conflict.resolved_at = timezone.now()
        conflict.resolved_by = request.user
        conflict.resolution_note = str(request.data.get("note", "")).strip()
        conflict.save(
            update_fields=[
                "state",
                "resolved_at",
                "resolved_by",
                "resolution_note",
                "updated_at",
            ]
        )

        return Response(
            {
                "id": conflict.pk,
                "state": conflict.state,
                "resolved_at": conflict.resolved_at,
                "resolved_by": conflict.resolved_by.username,
                "resolution_note": conflict.resolution_note,
            },
            status=status.HTTP_200_OK,
        )


class StockAlertListView(APIView):
    """Liste les objets en alerte de seuil / tension, avec option email."""

    permission_classes = [RoleBasedPermission]

    def get(self, request, *args, **kwargs):
        manifestation_id = request.query_params.get("manifestation")
        lieu_id = request.query_params.get("lieu")
        notify = str(request.query_params.get("notify", "")).lower() in {
            "1",
            "true",
            "yes",
        }

        alerts = self._build_alerts(
            manifestation_id=int(manifestation_id)
            if str(manifestation_id).isdigit()
            else None,
            lieu_id=int(lieu_id) if str(lieu_id).isdigit() else None,
        )

        email_sent = False
        if notify and alerts:
            email_sent = self._send_alert_email(alerts)

        return Response(
            {
                "count": len(alerts),
                "email_sent": email_sent,
                "alerts": alerts,
            },
            status=status.HTTP_200_OK,
        )

    def _build_alerts(self, manifestation_id=None, lieu_id=None):
        scope_ids = None

        if manifestation_id is not None or lieu_id is not None:
            scoped_lines = LigneReservation.objects.select_related(
                "reservation__prestation"
            )

            if manifestation_id is not None:
                scoped_lines = scoped_lines.filter(
                    reservation__prestation__manifestation_id=manifestation_id
                )

            if lieu_id is not None:
                scoped_lines = scoped_lines.filter(
                    reservation__prestation__lieu_id=lieu_id
                )

            scope_ids = set(scoped_lines.values_list("part_id", flat=True))

        # Les articles virtuels (services, ex. « nettoyage ») n'ont pas de
        # stock physique : ni seuil, ni tension n'ont de sens pour eux.
        rentable_items = (
            RentableItem.objects.select_related("part")
            .filter(is_virtual=False, alertes_desactivees=False)
            .all()
        )

        if scope_ids is not None:
            rentable_items = rentable_items.filter(part_id__in=scope_ids)

        from .conflicts import get_parts_total_stock
        from .stock import compute_parts_availability

        rentable_items = list(rentable_items)
        alerts = []
        now = timezone.now()
        part_ids = [rentable.part_id for rentable in rentable_items]

        # Une seule passe pour la disponibilité du jour de tous les articles.
        availability = compute_parts_availability(part_ids)

        # Deux passes de plus, groupées elles aussi.
        stock_par_part = get_parts_total_stock([
            rentable.part for rentable in rentable_items
        ])
        tensions = self._projected_tensions(
            part_ids=part_ids,
            now=now,
            manifestation_id=manifestation_id,
            lieu_id=lieu_id,
        )

        for rentable in rentable_items:
            part = rentable.part
            # Deux grandeurs distinctes, une seule source : ce qu'on possède de
            # louable (InvenTree) et ce qu'il en reste de libre aujourd'hui.
            stock_total = stock_par_part.get(part.pk, 0)
            stock_available = availability.get(part.pk, stock_total)
            low, low_source = self._seuil_bas(rentable, part)
            high = rentable.seuil_alerte_haut

            part_reasons = []

            # Les seuils portent sur ce qu'on possède, pas sur ce qui est libre
            # à l'instant : réapprovisionner se décide sur le parc, pas sur le
            if low is not None and stock_total <= low:
                part_reasons.append({
                    "type": "low_threshold",
                    "message": (
                        f"Stock trop bas : {stock_total} en stock, "
                        f"seuil bas fixé à {low}{low_source}"
                    ),
                })

            # Seuil haut réservé aux consommables comme le seuil bas : le CDC
            # V06 attache les deux seuils au consommable.
            if rentable.consommable and high is not None and stock_total >= high:
                part_reasons.append({
                    "type": "high_threshold",
                    "message": (
                        f"Stock au-dessus du seuil haut : "
                        f"{stock_total} en stock, seuil haut fixé à {high}"
                    ),
                })

            projected = self._tension_de(tensions, part.pk, max(stock_total, 1))

            if projected["occupation_rate"] >= 90:
                part_reasons.append({
                    "type": "projected_tension",
                    "message": (
                        f"Tension projetée {projected['occupation_rate']:.1f} % : "
                        f"{projected['reserved_quantity']} réservé(s) sur "
                        f"{stock_total} louable(s), "
                        f"alerte au-delà de 90 %"
                    ),
                })

            if not part_reasons:
                continue

            alerts.append({
                "part_id": part.pk,
                "part_name": getattr(part, "name", str(part)),
                "consommable": rentable.consommable,
                "stock_available": stock_available,
                "stock_total": stock_total,
                "seuil_alerte_bas": low,
                "seuil_alerte_haut": high,
                "projected_reserved_quantity": projected["reserved_quantity"],
                "projected_occupation_rate": round(projected["occupation_rate"], 2),
                "reasons": part_reasons,
            })

        alerts.sort(key=lambda item: item["part_name"].lower())

        return alerts

    def _seuil_bas(self, rentable, part):
        """Seuil bas applicable, et d'où il vient."""

        if rentable.seuil_alerte_bas is not None:
            return rentable.seuil_alerte_bas, ""

        minimum = getattr(part, "minimum_stock", None)

        if minimum is None:
            return None, ""

        try:
            minimum = int(minimum)
        except (TypeError, ValueError):
            return None, ""

        # `minimum_stock` vaut 0 par défaut chez InvenTree : le prendre pour un
        # seuil mettrait en alerte tout article à stock nul, sans que personne
        if minimum <= 0:
            return None, ""

        return minimum, " (stock minimum InvenTree)"

    def _projected_tensions(self, part_ids, now, manifestation_id=None, lieu_id=None):
        """Quantités engagées sur trente jours, pour tous les articles à la fois."""

        end = now + timedelta(days=30)
        lines = LigneReservation.objects.filter(
            part_id__in=part_ids,
            reservation__statut__in=CONFLICT_STATUSES,
            reservation__date_retrait_prevue__lte=end,
            reservation__date_retour_prevue__gte=now,
        )

        if manifestation_id is not None:
            lines = lines.filter(
                reservation__prestation__manifestation_id=manifestation_id
            )

        if lieu_id is not None:
            lines = lines.filter(reservation__prestation__lieu_id=lieu_id)

        engagements = lines.values("part_id").annotate(total=Sum("quantite_demandee"))

        return {ligne["part_id"]: int(ligne["total"] or 0) for ligne in engagements}

    @staticmethod
    def _tension_de(tensions, part_id, total_stock):
        """Le taux d'occupation d'un article, à partir des sommes groupées."""

        reserved = tensions.get(part_id, 0)

        return {
            "reserved_quantity": reserved,
            "occupation_rate": float((reserved / max(total_stock, 1)) * 100),
        }

    def _send_alert_email(self, alerts):
        cache_key = "inventree_location_stock_alert_email_last_sent"
        last_sent = cache.get(cache_key)

        if last_sent:
            return False

        recipients = list(
            get_user_model()
            .objects.filter(groups__name__in=["admin", "gestionnaire"], is_active=True)
            .exclude(email="")
            .values_list("email", flat=True)
            .distinct()
        )

        if not recipients:
            return False

        lines = [
            f"- {item['part_name']} (stock {item['stock_available']}/{item['stock_total']})"
            for item in alerts
        ]

        subject = "[InvenTree Location] Alerte seuil stock"
        body = "Objets en alerte:\n\n" + "\n".join(lines)

        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(
                settings, "DEFAULT_FROM_EMAIL", "noreply@inventree.local"
            ),
            recipient_list=recipients,
            fail_silently=True,
        )
        cache.set(cache_key, timezone.now().isoformat(), timeout=3600)
        return True


def parse_optional_date_param(request, name):
    """Lit un paramètre de date optionnel de la query string."""

    raw = request.query_params.get(name)

    if raw is None or not raw.strip():
        return None

    try:
        return _as_date(raw)
    except ValueError:
        raise ValidationError({
            name: "Date invalide : format attendu AAAA-MM-JJ (ou ISO 8601)."
        }) from None


def parse_optional_int_param(request, name):
    """Lit un paramètre entier optionnel de la query string (None si absent)."""

    raw = request.query_params.get(name)

    if raw is None or not str(raw).strip():
        return None

    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError({
            name: "Identifiant invalide : entier attendu."
        }) from None


def annotate_stock_available(
    parts, date_debut=None, date_fin=None, exclude_reservation_id=None
):
    """Attache `.stock_available` à chaque Part pour la sérialisation catalogue."""

    from .stock import compute_parts_availability

    parts = list(parts)
    availability = compute_parts_availability(
        [part.pk for part in parts],
        date_debut,
        date_fin,
        exclude_reservation_id=exclude_reservation_id,
    )

    for part in parts:
        part.stock_available = availability.get(part.pk)


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
            queryset = queryset.filter(
                category_id__in=self._with_descendants(category_ids)
            )

        active_value = self._parse_boolean(active)

        if active_value is not None:
            queryset = queryset.filter(active=active_value)

        queryset = self._filter_rentable(queryset, rentable)
        queryset = self._filter_virtual(queryset, virtual)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)

        annotate_stock_available(
            page,
            parse_optional_date_param(request, "date_debut"),
            parse_optional_date_param(request, "date_fin"),
            parse_optional_int_param(request, "exclude_reservation"),
        )

        serializer = self.serializer_class(page, many=True)

        return paginator.get_paginated_response(serializer.data)

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

    def _with_descendants(self, category_ids):
        """Étend une liste de catégories à leurs sous-catégories."""

        try:
            from part.models import PartCategory
        except ImportError:
            return category_ids

        racines = PartCategory.objects.filter(pk__in=category_ids)

        try:
            # MPTT sait descendre tout un ensemble de nœuds en une requête
            # (`TreeQuerySet.get_descendants`). C'est la voie normale.
            branche = racines.get_descendants(include_self=True)
        except AttributeError:
            # Manager sans l'extension queryset : on descend nœud par nœud.
            try:
                branche = PartCategory.objects.none()

                for racine in racines:
                    branche = branche | racine.get_descendants(include_self=True)
            except (AttributeError, TypeError):
                # Modèle sans arbre du tout : le filtre plat reste correct,
                # juste moins large.
                return category_ids

        try:
            ids = list(branche.values_list("pk", flat=True))
        except (AttributeError, TypeError):
            return category_ids

        # Une catégorie demandée mais absente en base doit rester dans le
        # filtre : elle ne rendra rien, ce qui est le résultat attendu.
        return sorted(set(ids) | set(category_ids))

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

    def _filter_virtual(self, queryset, virtual):
        """Filtre optionnel sur le drapeau article virtuel de RentableItem."""

        virtual_value = self._parse_boolean(virtual)

        if virtual_value is None:
            return queryset

        if virtual_value:
            return queryset.filter(rentable_info__is_virtual=True)

        return queryset.filter(
            Q(rentable_info__is_virtual=False) | Q(rentable_info__isnull=True)
        )


class CatalogPartDetailView(APIView):
    """Fiche détail d'un Part du catalogue."""

    permission_classes = [CatalogPermission]
    serializer_class = CatalogPartSerializer

    def get(self, request, pk, *args, **kwargs):
        """Retourne le détail d'un article du catalogue."""

        from part.models import Part

        part = (
            Part.objects.select_related("category", "rentable_info")
            .filter(pk=pk)
            .first()
        )

        if part is None:
            return Response(
                {"detail": "Part introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        annotate_stock_available(
            [part],
            parse_optional_date_param(request, "date_debut"),
            parse_optional_date_param(request, "date_fin"),
            parse_optional_int_param(request, "exclude_reservation"),
        )

        serializer = self.serializer_class(part)

        return Response(serializer.data, status=status.HTTP_200_OK)


class PartAvailabilityHistogramView(APIView):
    """Histogramme de disponibilité d'un article, jour par jour (CDC §99)."""

    permission_classes = [CatalogPermission]

    def get(self, request, pk, *args, **kwargs):
        """Retourne la disponibilité au jour d'un article sur une période."""

        from part.models import Part

        part = Part.objects.filter(pk=pk).select_related("rentable_info").first()

        if part is None:
            return Response(
                {"detail": "Part introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        today = timezone.localdate()
        date_debut = parse_optional_date_param(request, "date_debut") or today
        date_fin = parse_optional_date_param(
            request, "date_fin"
        ) or date_debut + timedelta(days=6)

        rentable_info = getattr(part, "rentable_info", None)
        days = compute_part_availability_calendar(part, date_debut, date_fin)

        return Response(
            {
                "part_id": part.pk,
                "part_name": getattr(part, "name", str(part)),
                "is_virtual": bool(rentable_info and rentable_info.is_virtual),
                "days": days,
            },
            status=status.HTTP_200_OK,
        )


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

        # Le stock ne se règle pas ici : il appartient à InvenTree et se met à
        # jour par les StockItem (cf. conflicts.get_part_total_stock).
        if "stock_total" in request.data:
            return Response(
                {
                    "stock_total": (
                        "Le stock est celui d'InvenTree : mettez l'article en "
                        "stock (StockItem) plutôt que de saisir une quantité ici."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not defaults:
            return Response(
                {
                    "detail": (
                        "Fournir au moins is_rentable, consommable ou is_virtual."
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


#: Chemin du niveau agrégé, vu depuis `LigneReservation` puis depuis
#: `Reservation`.
DEPUIS_LIGNE = {
    "manifestation": "reservation__prestation__manifestation",
    "prestation": "reservation__prestation",
}
DEPUIS_BON = {
    "manifestation": "prestation__manifestation",
    "prestation": "prestation",
}


def _volume_engage_par(maille):
    """Somme des quantités demandées sous une maille donnée, annulés exclus."""

    champ = DEPUIS_LIGNE[maille]

    return (
        LigneReservation.objects.filter(**{champ: OuterRef("pk")})
        .exclude(reservation__statut__in=STATUTS_SANS_ENGAGEMENT)
        .values(champ)
        .annotate(total=Sum("quantite_demandee"))
        .values("total")[:1]
    )


def _bons_par(maille, *, sortis=False):
    """Nombre de bons sous une maille — tous, ou seulement ceux sortis."""

    champ = DEPUIS_BON[maille]

    queryset = Reservation.objects.filter(**{champ: OuterRef("pk")}).exclude(
        statut__in=STATUTS_SANS_ENGAGEMENT
    )

    if sortis:
        queryset = queryset.filter(statut__in=STATUTS_DEJA_SORTIS)

    return queryset.values(champ).annotate(total=Count("id")).values("total")[:1]


class ManifestationListCreateView(generics.ListCreateAPIView):
    """CRUD manifestation — collection (ORG-01)."""

    permission_classes = [ManifestationPermission]
    serializer_class = ManifestationSerializer
    pagination_class = LieuPagination

    def get_queryset(self):
        """Manifestations, filtrées par statut, recherche et période."""

        queryset = (
            Manifestation.objects.select_related("client", "contact")
            .annotate(
                volume_engage=Coalesce(
                    Subquery(_volume_engage_par("manifestation")), 0
                ),
                bons_engages=Coalesce(Subquery(_bons_par("manifestation")), 0),
                bons_livres=Coalesce(
                    Subquery(_bons_par("manifestation", sortis=True)), 0
                ),
                # `distinct` obligatoire : ce `Count` joint, là où les trois
                # autres agrégats sont des sous-requêtes.
                prestations_total=Count("prestations", distinct=True),
            )
            .order_by("-date_debut")
        )

        statuts = self.request.query_params.getlist("statut")

        if statuts:
            queryset = queryset.filter(statut__in=statuts)

        # « Rechercher les manifestations d'un client défini » (recette du
        # 11/09).
        client_id = self.request.query_params.get("client")

        if client_id:
            queryset = queryset.filter(client_id=client_id)

        search = self.request.query_params.get("search")

        if search:
            # Le nom du client compte autant que celui de la manifestation :
            # un client sans manifestation restait introuvable, et on le
            # recréait en double. Recette Tassin du 27/09, point 4.2.4.
            queryset = queryset.filter(
                Q(nom__icontains=search) | Q(client__nom__icontains=search)
            )

        # Filtre Futur / Passé / Tout de la maquette.
        periode = self.request.query_params.get("periode")

        if periode in {"futur", "passe"}:
            aujourdhui = timezone.localdate()

            if periode == "futur":
                queryset = queryset.filter(date_fin__date__gte=aujourdhui)
            else:
                queryset = queryset.filter(date_fin__date__lt=aujourdhui)

        # Fenêtre du planning : on veut ce qui **chevauche** la période, pas ce
        # qui y tient entièrement.
        depuis = self.request.query_params.get("from")
        jusqua = self.request.query_params.get("to")

        if depuis:
            queryset = queryset.filter(**_borne_journee("date_fin", depuis, "gte"))

        if jusqua:
            queryset = queryset.filter(**_borne_journee("date_debut", jusqua, "lte"))

        return queryset


class ManifestationDetailView(
    RefusDeSuppressionLisible, generics.RetrieveUpdateDestroyAPIView
):
    """CRUD manifestation — instance unique (ORG-01)."""

    objet_supprime = "cette manifestation"

    permission_classes = [ManifestationPermission]
    serializer_class = ManifestationSerializer
    queryset = Manifestation.objects.select_related("client", "contact")


def _prestation_queryset():
    """Queryset commun aux vues prestation, avec relations préchargées."""

    return (
        Prestation.objects.select_related("manifestation", "lieu")
        .prefetch_related("lignes_prestation__part")
        .all()
    )


class PrestationListCreateView(generics.ListCreateAPIView):
    """CRUD prestation — collection (ORG-01 / RES-09)."""

    permission_classes = [PrestationPermission]
    serializer_class = PrestationSerializer
    pagination_class = LieuPagination

    def get_queryset(self):
        """Retourne les prestations, filtrées par manifestation, fenêtre et recherche."""

        queryset = (
            _prestation_queryset()
            .annotate(
                volume_engage=Coalesce(Subquery(_volume_engage_par("prestation")), 0),
                bons_engages=Coalesce(Subquery(_bons_par("prestation")), 0),
                bons_livres=Coalesce(Subquery(_bons_par("prestation", sortis=True)), 0),
            )
            .order_by("-date_debut")
        )

        manifestation_id = self.request.query_params.get("manifestation")

        if manifestation_id:
            queryset = queryset.filter(manifestation_id=manifestation_id)

        depuis = self.request.query_params.get("from")
        jusqua = self.request.query_params.get("to")

        if depuis:
            queryset = queryset.filter(**_borne_journee("date_fin", depuis, "gte"))

        if jusqua:
            queryset = queryset.filter(**_borne_journee("date_debut", jusqua, "lte"))

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(nom__icontains=search) | Q(manifestation__nom__icontains=search)
            )

        return queryset


class PrestationDetailView(
    RefusDeSuppressionLisible, generics.RetrieveUpdateDestroyAPIView
):
    """CRUD prestation — instance unique (ORG-01 / RES-09)."""

    objet_supprime = "cette prestation"

    permission_classes = [PrestationPermission]
    serializer_class = PrestationSerializer
    queryset = _prestation_queryset()


class PrestationStockView(APIView):
    """Disponibilité au jour des articles d'une prestation enregistrée (STK-01)."""

    permission_classes = [PrestationPermission]

    def get(self, request, pk, *args, **kwargs):
        """Retourne la disponibilité de stock de la prestation."""

        prestation = (
            Prestation.objects.prefetch_related("lignes_prestation")
            .filter(pk=pk)
            .first()
        )

        if prestation is None:
            return Response(
                {"detail": "Prestation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        result = compute_prestation_stock(prestation)

        response_status = (
            status.HTTP_409_CONFLICT if result["has_shortage"] else status.HTTP_200_OK
        )

        return Response(result, status=response_status)


class PrestationStockPreviewView(APIView):
    """Disponibilité au jour AVANT sauvegarde (temps réel côté front, STK-01)."""

    permission_classes = [PrestationPermission]

    def post(self, request, *args, **kwargs):
        """Calcule la disponibilité pour une saisie non encore enregistrée."""

        date_debut = request.data.get("date_debut")
        date_fin = request.data.get("date_fin")
        lignes = request.data.get("lignes") or []

        if not date_debut or not date_fin:
            return Response(
                {"detail": "date_debut et date_fin sont obligatoires."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        requested_lines = [
            {"part_id": ligne.get("part"), "quantite": ligne.get("quantite", 0)}
            for ligne in lignes
            if ligne.get("part") is not None
        ]

        result = compute_stock_availability(
            date_debut,
            date_fin,
            requested_lines,
            exclude_prestation_id=request.data.get("exclude_prestation"),
        )

        response_status = (
            status.HTTP_409_CONFLICT if result["has_shortage"] else status.HTTP_200_OK
        )

        return Response(result, status=response_status)


class ClientListView(generics.ListAPIView):
    """Liste des clients (lecture seule) : sélecteur de manifestation et « mes clients »."""

    permission_classes = [RoleBasedPermission]
    serializer_class = ClientSerializer
    pagination_class = CatalogPagination

    def get_queryset(self):
        """Retourne les clients, filtrés par recherche texte et par gestionnaire."""

        queryset = Client.objects.select_related("gestionnaire").order_by("nom")

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(nom__icontains=search) | Q(email__icontains=search)
            )

        gestionnaire = self.request.query_params.get("gestionnaire")

        if gestionnaire == "me":
            queryset = queryset.filter(gestionnaire=self.request.user)
        elif gestionnaire and gestionnaire.isdigit():
            queryset = queryset.filter(gestionnaire_id=int(gestionnaire))

        actif = self.request.query_params.get("actif")

        if actif is not None:
            queryset = queryset.filter(actif=actif.lower() in ("true", "1"))

        return queryset


class UserListView(generics.ListAPIView):
    """Liste des utilisateurs actifs (lecture seule), pour les sélecteurs."""

    permission_classes = [RoleBasedPermission]
    serializer_class = UserSerializer
    pagination_class = CatalogPagination

    def get_queryset(self):
        """Retourne les utilisateurs actifs, filtrés par recherche et rôle."""

        queryset = get_user_model().objects.filter(is_active=True).order_by("username")

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )

        # Filtres de rôle.
        roles_demandes = self._roles_param("roles")
        roles_exclus = self._roles_param("exclude_roles")

        if roles_demandes:
            queryset = queryset.filter(groups__name__in=roles_demandes)

        if roles_exclus:
            queryset = queryset.exclude(groups__name__in=roles_exclus)

        # Un compte cumulant deux rôles demandés serait sinon rendu deux fois.
        return queryset.distinct() if (roles_demandes or roles_exclus) else queryset

    def _roles_param(self, name):
        """Lit une liste de rôles en CSV, en ignorant les noms inconnus."""

        raw = self.request.query_params.get(name)

        if not raw:
            return []

        demandes = {valeur.strip() for valeur in str(raw).split(",") if valeur.strip()}

        return sorted(demandes & set(roles.ALL_ROLES))
