"""Back-office utilisateurs et rôles"""

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import generics, permissions, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from . import profiles, roles
from .doublons import clients_proches
from .models import Client, Contact
from .serializers import _user_label


class BackOfficePermission(permissions.BasePermission):
    """Accès réservé aux superutilisateurs ou au rôle plugin admin."""

    def has_permission(self, request, view) -> bool:
        user = request.user

        if not user or not user.is_authenticated:
            return False

        if getattr(user, "is_superuser", False):
            return True

        return roles.user_has_any_role(user, [roles.ADMIN])


class ClientDeskPermission(BackOfficePermission):
    """Fichier clients : l'admin, et le gestionnaire dont c'est le métier."""

    def has_permission(self, request, view) -> bool:
        user = request.user

        if not user or not user.is_authenticated:
            return False

        if super().has_permission(request, view):
            return True

        return roles.user_has_any_role(user, [roles.GESTIONNAIRE])


class BackOfficePagination(PageNumberPagination):
    """Pagination commune aux listes back-office (utilisateurs, Parts)."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class BackOfficeRoleSerializer(serializers.Serializer):
    """Sérialiseur d'un rôle métier exposé au front."""

    name = serializers.CharField()
    label = serializers.CharField()


class BackOfficeUserSerializer(serializers.ModelSerializer):
    """Sérialiseur back-office d'un utilisateur Django + rôles plugin."""

    # Un acteur interne porte **un** rôle (décision du 09/09/2026), d'où un
    # champ simple et non une liste.
    role = serializers.ChoiceField(
        choices=[(role, role) for role in roles.ALL_ROLES],
        required=False,
        allow_null=True,
    )
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        min_length=6,
    )
    telephone = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = get_user_model()
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "is_active",
            "is_staff",
            "is_superuser",
            "role",
            "password",
            "telephone",
        ]
        read_only_fields = [
            "id",
            "is_staff",
            "is_superuser",
        ]

    def to_representation(self, instance):
        """Expose les rôles plugin et les champs portés par le `Profile`."""

        data = super().to_representation(instance)

        # Un seul rôle, mais `user_roles` renvoie un ensemble : un groupe Django
        # hors plugin peut traîner, et un compte neuf n'en a aucun.
        proprietes = sorted(roles.user_roles(instance))
        data["role"] = proprietes[0] if proprietes else None

        profile = profiles.user_profile(instance)
        data["telephone"] = profile.telephone if profile else ""

        return data

    def validate_password(self, value):
        """Applique les validateurs de mot de passe de l'instance InvenTree."""

        if not value:
            return value

        try:
            password_validation.validate_password(value)
        except DjangoValidationError as error:
            raise serializers.ValidationError(list(error.messages)) from None

        return value

    def validate(self, attrs):
        """Mot de passe obligatoire à la création, et pas d'auto-verrouillage."""

        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({
                "password": "Le mot de passe est obligatoire à la création."
            })

        self._reject_self_lockout(attrs)

        return attrs

    def _reject_self_lockout(self, attrs):
        """Empêche l'admin connecté de se couper lui-même l'accès."""

        request = self.context.get("request")
        current_user = getattr(request, "user", None)

        if (
            self.instance is None
            or current_user is None
            or current_user.pk != self.instance.pk
        ):
            return

        if attrs.get("is_active") is False:
            raise serializers.ValidationError({
                "is_active": "Vous ne pouvez pas désactiver votre propre compte."
            })

        if (
            "role" in self.initial_data
            and attrs.get("role") != roles.ADMIN
            and roles.ADMIN in roles.user_roles(self.instance)
        ):
            raise serializers.ValidationError({
                "role": "Vous ne pouvez pas retirer votre propre rôle admin."
            })

    def _ensure_role_groups(self):
        """Crée les groupes métiers manquants si nécessaire."""

        for role in roles.ALL_ROLES:
            Group.objects.get_or_create(name=role)

    def _apply_role(self, user, role_name):
        """Pose **le** rôle métier, en conservant les groupes hors plugin."""

        self._ensure_role_groups()

        hors_plugin = list(user.groups.exclude(name__in=roles.ALL_ROLES))
        metier = list(Group.objects.filter(name=role_name)) if role_name else []

        user.groups.set(hors_plugin + metier)

    def _pop_profile_fields(self, validated_data):
        """Sort les champs portés par le `Profile`, pas par le `User`."""

        return {
            name: validated_data.pop(name)
            for name in ("telephone",)
            if name in validated_data
        }

    def create(self, validated_data):
        """Crée un utilisateur, son profil et lui affecte ses rôles."""

        role_name = validated_data.pop("role", None)
        password = validated_data.pop("password", "")
        profile_fields = self._pop_profile_fields(validated_data)

        user = get_user_model().objects.create_user(
            password=password,
            **validated_data,
        )

        self._apply_role(user, role_name)
        profiles.update_user_profile(user, profile_fields)

        return user

    def update(self, instance, validated_data):
        """Met à jour l'utilisateur, son profil, son état actif et ses rôles."""

        role_name = validated_data.pop("role", None)
        password = validated_data.pop("password", None)
        profile_fields = self._pop_profile_fields(validated_data)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        if password:
            instance.set_password(password)

        instance.save()

        if "role" in self.initial_data:
            self._apply_role(instance, role_name)

        profiles.update_user_profile(instance, profile_fields)

        return instance


class BackOfficeUserListCreateView(generics.ListCreateAPIView):
    """Liste et création des utilisateurs depuis le back-office."""

    permission_classes = [BackOfficePermission]
    serializer_class = BackOfficeUserSerializer
    pagination_class = BackOfficePagination

    def get_queryset(self):
        """Retourne les utilisateurs filtrables par recherche."""

        queryset = (
            get_user_model()
            .objects.select_related("location_profile")
            .prefetch_related("groups")
            .all()
            .order_by("username")
        )

        search = self.request.query_params.get("search", "").strip()

        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
            )

        return queryset


class BackOfficeUserDetailView(generics.RetrieveUpdateAPIView):
    """Lecture / modification d'un utilisateur depuis le back-office."""

    permission_classes = [BackOfficePermission]
    serializer_class = BackOfficeUserSerializer
    queryset = (
        get_user_model()
        .objects.select_related("location_profile")
        .prefetch_related("groups")
        .all()
    )


class BackOfficeClientSerializer(serializers.ModelSerializer):
    """CRUD d'un client, réservé au back-office."""

    contacts = serializers.SerializerMethodField()
    gestionnaire_nom = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "id",
            "nom",
            "adresse",
            "email",
            "telephone",
            "type_client",
            "siret",
            "gestionnaire",
            "gestionnaire_nom",
            "actif",
            "contacts",
        ]

    def get_contacts(self, obj) -> int:
        """Nombre de contacts."""

        return Contact.objects.filter(client=obj.pk).count()

    def get_gestionnaire_nom(self, obj) -> str:
        """Nom du gestionnaire référent, pour l'afficher sans second appel."""

        return _user_label(obj.gestionnaire)

    def validate_nom(self, valeur):
        """Refuse un nom qui désigne visiblement un client déjà enregistré.

        `nom` est unique, mais « Mairie de vertou » passait à côté de
        « Mairie de Vertou » : le fichier client se dédoublait sans que
        personne ne s'en aperçoive. Recette Tassin du 27/09.
        """

        deja = Client.objects.all()

        # En modification, un client ne se ressemble pas à lui-même.
        if self.instance is not None:
            deja = deja.exclude(pk=self.instance.pk)

        proches = clients_proches(valeur, deja)

        if proches:
            noms = ", ".join(f"« {c.nom} »" for c in proches[:3])
            raise serializers.ValidationError(
                f"Ce client existe déjà sous le nom {noms}. "
                "Reprenez la fiche existante, ou précisez ce nom s'il s'agit "
                "bien d'un autre client."
            )

        return valeur


class BackOfficeClientListCreateView(generics.ListCreateAPIView):
    """Liste et création des clients."""

    permission_classes = [ClientDeskPermission]
    serializer_class = BackOfficeClientSerializer
    pagination_class = BackOfficePagination

    def get_queryset(self):
        queryset = Client.objects.all().order_by("nom")

        search = self.request.query_params.get("search", "").strip()

        if search:
            queryset = queryset.filter(
                Q(nom__icontains=search) | Q(email__icontains=search)
            )

        return queryset


class BackOfficeClientDetailView(generics.RetrieveUpdateAPIView):
    """Lecture / modification d'un client."""

    permission_classes = [ClientDeskPermission]
    serializer_class = BackOfficeClientSerializer

    def get_queryset(self):
        """Évalué par requête : un queryset de classe casserait l'import."""

        return Client.objects.all()


class BackOfficeContactSerializer(serializers.ModelSerializer):
    """CRUD d'un contact."""

    client_nom = serializers.CharField(source="client.nom", read_only=True)

    class Meta:
        model = Contact
        fields = [
            "id",
            "client",
            "client_nom",
            "nom",
            "prenom",
            "email",
            "telephone",
            "actif",
        ]


class BackOfficeContactListCreateView(generics.ListCreateAPIView):
    """Liste et création des contacts, filtrables par client."""

    permission_classes = [ClientDeskPermission]
    serializer_class = BackOfficeContactSerializer
    pagination_class = BackOfficePagination

    def get_queryset(self):
        queryset = Contact.objects.select_related("client").order_by(
            "client", "nom", "prenom"
        )

        client = self.request.query_params.get("client")

        if client:
            queryset = queryset.filter(client_id=client)

        search = self.request.query_params.get("search", "").strip()

        if search:
            queryset = queryset.filter(
                Q(nom__icontains=search)
                | Q(prenom__icontains=search)
                | Q(email__icontains=search)
            )

        return queryset


class BackOfficeContactDetailView(generics.RetrieveUpdateAPIView):
    """Lecture / modification d'un contact."""

    permission_classes = [ClientDeskPermission]
    serializer_class = BackOfficeContactSerializer

    def get_queryset(self):
        return Contact.objects.select_related("client")


class BackOfficeRoleListView(APIView):
    """Liste des rôles métier disponibles."""

    permission_classes = [BackOfficePermission]

    ROLE_LABELS = {
        roles.ADMIN: "Admin",
        roles.GESTIONNAIRE: "Gestionnaire",
        roles.MAGASINIER: "Magasinier",
        roles.LIVREUR: "Livreur",
        roles.SAV: "SAV",
        roles.LECTEUR: "Lecteur",
        roles.ACHETEUR: "Acheteur",
    }

    def get(self, request, *args, **kwargs):
        """Retourne les rôles métier disponibles."""

        payload = [
            {
                "name": role,
                "label": self.ROLE_LABELS.get(role, role),
            }
            for role in roles.ALL_ROLES
        ]

        serializer = BackOfficeRoleSerializer(payload, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
