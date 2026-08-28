"""API SCRUM-112 — stock réel, retours ramassage et workflow SAV."""

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    LigneReservation,
    RentableItem,
    Reservation,
    ReturnIncident,
    ReturnIncidentType,
    SavTicket,
    StatutReservation,
    StatutSavTicket,
    TypeSavTicket,
)
from .permissions import ReturnCheckinPermission, SavPermission
from .ramassage import lignes_a_ramasser
from .retours import (
    INCIDENTS_RAMASSAGE,
    appliquer_etat_retour,
    projeter_incidents,
)


SAV_BLOCKING_STATUSES = [
    StatutSavTicket.OUVERT,
    StatutSavTicket.EN_REPARATION,
]

SAV_AVAILABLE_STATUSES = [
    StatutSavTicket.REPARE,
    StatutSavTicket.CLOTURE,
]


def _sum_or_zero(queryset, field_name: str) -> int:
    """Retourne une somme entière, 0 si aucune ligne."""

    result = queryset.aggregate(total=Sum(field_name))

    return int(result["total"] or 0)


def get_unavailable_stock_quantity(part_id: int) -> int:
    """Calcule les quantités qui sortent du stock réellement disponible.

    Règle SCRUM-112 :
    - SAV ouvert / en réparation : indisponible temporairement.
    - Détruit : indisponible définitivement.
    - Manquant : indisponible tant qu'un incident le signale.

    Deux sources, chacune pour ce qu'elle sait dire : les `SavTicket` portent un
    cycle de vie (un objet réparé revient au stock), le registre d'incidents
    porte le constat. Le manquant n'a pas de cycle de vie, il se lit donc dans
    le registre — et le registre est alimenté par le check-in comme par le
    ramassage.
    """

    sav_quantity = _sum_or_zero(
        SavTicket.objects.filter(
            part_id=part_id,
            type_ticket=TypeSavTicket.REPARATION,
            statut__in=SAV_BLOCKING_STATUSES,
        ),
        "quantite",
    )

    destroyed_quantity = _sum_or_zero(
        SavTicket.objects.filter(
            part_id=part_id,
            type_ticket=TypeSavTicket.DESTRUCTION,
            statut=StatutSavTicket.DETRUIT,
        ),
        "quantite",
    )

    # Les manquants se lisent dans le registre d'incidents, pas dans la colonne
    # `quantite_manquante` du ramassage : celle-ci ignorait les manquants
    # constatés au check-in, qui ne sortaient donc jamais du stock réel. Les
    # deux écrans alimentent le registre (cf. retours.py), une seule lecture
    # suffit désormais et couvre les deux.
    missing_quantity = _sum_or_zero(
        ReturnIncident.objects.filter(
            line__part_id=part_id,
            type=ReturnIncidentType.MISSING,
            line__reservation__statut__in=[
                StatutReservation.LIVREE,
                StatutReservation.RETOURNEE,
                StatutReservation.CLOTUREE,
            ],
        ),
        "qty",
    )

    return sav_quantity + destroyed_quantity + missing_quantity


def get_real_available_stock(part_id: int) -> int:
    """Stock réellement disponible pour les futures réservations.

    Le stock théorique vient d'InvenTree (`StockItem`), pas d'un compteur du
    plugin : `RentableItem.stock_total` n'existe plus, un compteur parallèle
    divergeant en silence dès qu'une casse ou un inventaire est saisi côté
    InvenTree.
    """

    from .conflicts import get_part_total_stock

    rentable_item = RentableItem.objects.filter(part_id=part_id).first()

    if rentable_item is None:
        return 0

    theoretical_stock = get_part_total_stock(
        rentable_item.part, rentable_item=rentable_item
    )
    unavailable_stock = get_unavailable_stock_quantity(part_id)

    return max(theoretical_stock - unavailable_stock, 0)


def _close_or_update_ticket(
    *,
    ligne: LigneReservation,
    type_ticket: str,
    quantite: int,
    statut_si_quantite: str,
    user,
    facturer_client: bool,
    description: str,
):
    """Crée, met à jour ou clôture un ticket lié à une ligne.

    Ramener une quantité à 0 clôture le ticket correspondant, **y compris une
    destruction**. Le refus précédent partait d'une idée juste — on ne
    « dé-détruit » pas un objet — mais produisait un état incohérent : la ligne
    affichait 0 détruit tandis que le ticket en gardait 1 hors du stock réel,
    sans aucun écran pour rattraper l'erreur de saisie. Une faute de frappe au
    ramassage amputait le parc définitivement.

    La correction laisse une trace : `resolution` dit d'où vient la clôture, et
    `closed_at` la date. Le ticket n'est jamais supprimé.
    """

    ticket = SavTicket.objects.filter(
        ligne_reservation=ligne,
        type_ticket=type_ticket,
    ).first()

    if quantite <= 0:
        if ticket and ticket.statut != StatutSavTicket.CLOTURE:
            etait_detruit = ticket.statut == StatutSavTicket.DETRUIT

            ticket.statut = StatutSavTicket.CLOTURE
            ticket.quantite = 0
            ticket.updated_by = user
            ticket.closed_at = timezone.now()
            ticket.resolution = (
                "Destruction annulée depuis la saisie retour (correction de "
                "saisie) : la quantité détruite est repassée à 0."
                if etait_detruit
                else "Ticket clôturé : quantité ramenée à 0 depuis la saisie retour."
            )
            ticket.save()

        return None

    if ticket is None:
        ticket = SavTicket.objects.create(
            ligne_reservation=ligne,
            reservation=ligne.reservation,
            part=ligne.part,
            type_ticket=type_ticket,
            statut=statut_si_quantite,
            quantite=quantite,
            facturer_client=facturer_client,
            description=description,
            created_by=user,
            updated_by=user,
        )

        return ticket

    ticket.quantite = quantite
    ticket.facturer_client = facturer_client
    ticket.description = description or ticket.description
    ticket.updated_by = user

    if ticket.statut in [StatutSavTicket.CLOTURE, StatutSavTicket.REPARE]:
        ticket.statut = statut_si_quantite
        ticket.closed_at = None

    ticket.save()

    return ticket


class RetourRamassageLigneSerializer(serializers.Serializer):
    """Entrée API pour saisir le retour d'une ligne de ramassage."""

    ligne = serializers.IntegerField(required=True)
    quantite_ramassee = serializers.IntegerField(required=False, min_value=0, default=0)
    quantite_sav = serializers.IntegerField(required=False, min_value=0, default=0)
    quantite_detruite = serializers.IntegerField(required=False, min_value=0, default=0)
    quantite_manquante = serializers.IntegerField(
        required=False, min_value=0, default=0
    )
    facturer_client = serializers.BooleanField(required=False, default=False)
    commentaire = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        """Contrôle que les quantités ne dépassent pas la quantité attendue."""

        ligne = (
            LigneReservation.objects.select_related("reservation")
            .filter(pk=attrs["ligne"])
            .first()
        )

        if ligne is None:
            raise serializers.ValidationError({
                "ligne": "Ligne de réservation introuvable."
            })

        expected = ligne.quantite_livree or ligne.quantite_demandee

        total = (
            attrs.get("quantite_ramassee", 0)
            + attrs.get("quantite_sav", 0)
            + attrs.get("quantite_detruite", 0)
            + attrs.get("quantite_manquante", 0)
        )

        if total > expected:
            raise serializers.ValidationError({
                "detail": (
                    "La somme ramassée + SAV + détruite + manquante "
                    "ne peut pas dépasser la quantité à ramasser."
                ),
                "ligne": ligne.pk,
                "quantite_attendue": expected,
                "quantite_saisie": total,
            })

        attrs["_ligne_instance"] = ligne

        return attrs


class RetourRamassageSerializer(serializers.Serializer):
    """Payload API du retour de ramassage."""

    lignes = RetourRamassageLigneSerializer(many=True, required=True)
    commentaire = serializers.CharField(required=False, allow_blank=True, default="")


class SavTicketSerializer(serializers.ModelSerializer):
    """Serializer lecture / édition d'un ticket SAV."""

    part_nom = serializers.CharField(source="part.name", read_only=True)
    reservation_numero = serializers.CharField(
        source="reservation.numero", read_only=True
    )
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
        allow_null=True,
    )
    updated_by_username = serializers.CharField(
        source="updated_by.username",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = SavTicket
        fields = [
            "id",
            "ligne_reservation",
            "reservation",
            "reservation_numero",
            "part",
            "part_nom",
            "type_ticket",
            "statut",
            "quantite",
            "facturer_client",
            "description",
            "diagnostic",
            "resolution",
            "created_by",
            "created_by_username",
            "updated_by",
            "updated_by_username",
            "closed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "ligne_reservation",
            "reservation",
            "reservation_numero",
            "part",
            "part_nom",
            "type_ticket",
            "created_by",
            "created_by_username",
            "updated_by",
            "updated_by_username",
            "closed_at",
            "created_at",
            "updated_at",
        ]

    def validate_statut(self, value):
        """Valide les statuts disponibles."""

        if value not in StatutSavTicket.values:
            raise serializers.ValidationError("Statut SAV invalide.")

        return value

    def update(self, instance, validated_data):
        """Met à jour le ticket et gère la clôture."""

        request = self.context.get("request")

        for field in ["statut", "diagnostic", "resolution", "facturer_client"]:
            if field in validated_data:
                setattr(instance, field, validated_data[field])

        if request and request.user and request.user.is_authenticated:
            instance.updated_by = request.user

        if instance.statut in [
            StatutSavTicket.REPARE,
            StatutSavTicket.DETRUIT,
            StatutSavTicket.CLOTURE,
        ]:
            if instance.closed_at is None:
                instance.closed_at = timezone.now()
        else:
            instance.closed_at = None

        instance.save()

        return instance


class SavTicketPagination(PageNumberPagination):
    """Pagination SAV."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class RamassageRetourView(APIView):
    """SCRUM-112 — Saisie du retour ramassage."""

    permission_classes = [ReturnCheckinPermission]
    serializer_class = RetourRamassageSerializer

    @transaction.atomic
    def patch(self, request, pk, *args, **kwargs):
        """Enregistre les quantités ramassées / SAV / détruites / manquantes."""

        reservation = (
            Reservation.objects.prefetch_related("lignes__part__rentable_info")
            .filter(pk=pk)
            .first()
        )

        if reservation is None:
            return Response(
                {"detail": "Réservation introuvable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated_lines = []
        created_or_updated_tickets = []
        # Même périmètre que le bon de ramassage : un article virtuel n'a rien
        # à faire revenir, donc rien à ventiler ici non plus.
        ramassables = {ligne.pk for ligne in lignes_a_ramasser(reservation)}

        for line_data in serializer.validated_data["lignes"]:
            ligne = line_data["_ligne_instance"]

            if ligne.reservation_id != reservation.pk:
                return Response(
                    {
                        "detail": (
                            "Une ligne fournie ne correspond pas à la réservation."
                        ),
                        "ligne": ligne.pk,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if ligne.pk not in ramassables:
                return Response(
                    {
                        "detail": (
                            "Cette ligne ne se ramasse pas : un article virtuel "
                            "n'a pas d'existence physique."
                        ),
                        "ligne": ligne.pk,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            ligne.quantite_ramassee = line_data.get("quantite_ramassee", 0)
            ligne.quantite_sav = line_data.get("quantite_sav", 0)
            ligne.quantite_detruite = line_data.get("quantite_detruite", 0)
            ligne.quantite_manquante = line_data.get("quantite_manquante", 0)
            ligne.facturer_client = line_data.get("facturer_client", False)
            ligne.commentaire = line_data.get("commentaire", "")
            ligne.quantite_retournee = ligne.quantite_ramassee
            ligne.save()

            # Le registre d'incidents d'abord, l'état de la ligne ensuite : il
            # s'en déduit (cf. retours.py).
            projeter_incidents(
                ligne,
                request.user,
                INCIDENTS_RAMASSAGE,
                facturer=ligne.facturer_client,
            )
            appliquer_etat_retour(ligne)

            sav_ticket = _close_or_update_ticket(
                ligne=ligne,
                type_ticket=TypeSavTicket.REPARATION,
                quantite=ligne.quantite_sav,
                statut_si_quantite=StatutSavTicket.OUVERT,
                user=request.user,
                facturer_client=ligne.facturer_client,
                description=ligne.commentaire,
            )

            destruction_ticket = _close_or_update_ticket(
                ligne=ligne,
                type_ticket=TypeSavTicket.DESTRUCTION,
                quantite=ligne.quantite_detruite,
                statut_si_quantite=StatutSavTicket.DETRUIT,
                user=request.user,
                facturer_client=ligne.facturer_client,
                description=ligne.commentaire,
            )

            updated_lines.append({
                "id": ligne.pk,
                "part": ligne.part_id,
                "quantite_ramassee": ligne.quantite_ramassee,
                "quantite_sav": ligne.quantite_sav,
                "quantite_detruite": ligne.quantite_detruite,
                "quantite_manquante": ligne.quantite_manquante,
                "facturer_client": ligne.facturer_client,
                "etat_retour": ligne.etat_retour,
            })

            for ticket in [sav_ticket, destruction_ticket]:
                if ticket is not None:
                    created_or_updated_tickets.append(ticket.pk)

        reservation.commentaire = serializer.validated_data.get(
            "commentaire",
            reservation.commentaire,
        )

        if reservation.statut == StatutReservation.LIVREE:
            reservation.statut = StatutReservation.RETOURNEE
            reservation.date_retour_reelle = timezone.now()

        reservation.save()

        return Response(
            {
                "reservation": reservation.pk,
                "numero": reservation.numero,
                "statut": reservation.statut,
                "updated_lines": updated_lines,
                "sav_tickets": created_or_updated_tickets,
            },
            status=status.HTTP_200_OK,
        )


class SavTicketListView(generics.ListAPIView):
    """Liste des tickets SAV."""

    permission_classes = [SavPermission]
    serializer_class = SavTicketSerializer
    pagination_class = SavTicketPagination

    def get_queryset(self):
        """Filtre les tickets SAV."""

        queryset = (
            SavTicket.objects.select_related(
                "part",
                "reservation",
                "ligne_reservation",
                "created_by",
                "updated_by",
            )
            .all()
            .order_by("-created_at")
        )

        statut = self.request.query_params.get("statut")
        type_ticket = self.request.query_params.get("type_ticket")
        part = self.request.query_params.get("part")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if statut:
            queryset = queryset.filter(statut=statut)

        if type_ticket:
            queryset = queryset.filter(type_ticket=type_ticket)

        if part and str(part).isdigit():
            queryset = queryset.filter(part_id=int(part))

        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        return queryset


class SavTicketDetailView(generics.RetrieveUpdateAPIView):
    """Détail / édition d'un ticket SAV."""

    permission_classes = [SavPermission]
    serializer_class = SavTicketSerializer

    def get_queryset(self):
        """Queryset tickets SAV."""

        return SavTicket.objects.select_related(
            "part",
            "reservation",
            "ligne_reservation",
            "created_by",
            "updated_by",
        ).all()

    def get_serializer_context(self):
        """Ajoute la requête au serializer."""

        context = super().get_serializer_context()
        context["request"] = self.request

        return context


class DestroyedItemsListView(generics.ListAPIView):
    """Liste des objets détruits, filtrable par période."""

    permission_classes = [SavPermission]
    serializer_class = SavTicketSerializer
    pagination_class = SavTicketPagination

    def get_queryset(self):
        """Retourne les tickets de destruction."""

        queryset = (
            SavTicket.objects.select_related(
                "part",
                "reservation",
                "ligne_reservation",
                "created_by",
                "updated_by",
            )
            .filter(
                type_ticket=TypeSavTicket.DESTRUCTION,
                statut=StatutSavTicket.DETRUIT,
            )
            .order_by("-created_at")
        )

        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        return queryset
