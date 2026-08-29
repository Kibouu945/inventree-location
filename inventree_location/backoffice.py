"""Back-office utilisateurs et rôles pour SCRUM-108."""

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import generics, permissions, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from . import roles


class BackOfficePermission(permissions.BasePermission):
    """Accès réservé aux superutilisateurs ou au rôle plugin admin."""

    def has_permission(self, request, view) -> bool:
        user = request.user

        if not user or not user.is_authenticated:
            return False

        if getattr(user, "is_superuser", False):
            return True

        return roles.user_has_any_role(user, [roles.ADMIN])


class BackOfficePagination(PageNumberPagination):
    """Pagination commune aux listes back-office (utilisateurs, Parts).

    Déclarée explicitement plutôt que laissée au réglage global : le front
    consomme `count` / `results` et doit pouvoir compter dessus.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class BackOfficeRoleSerializer(serializers.Serializer):
    """Sérialiseur d'un rôle métier exposé au front."""

    name = serializers.CharField()
    label = serializers.CharField()


class BackOfficeUserSerializer(serializers.ModelSerializer):
    """Sérialiseur back-office d'un utilisateur Django + rôles plugin."""

    roles = serializers.ListField(
        child=serializers.ChoiceField(
            choices=[(role, role) for role in roles.ALL_ROLES]
        ),
        required=False,
        allow_empty=True,
    )
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        min_length=6,
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
            "roles",
            "password",
        ]
        read_only_fields = [
            "id",
            "is_staff",
            "is_superuser",
        ]

    def to_representation(self, instance):
        """Expose les rôles plugin à partir des groupes Django."""

        data = super().to_representation(instance)
        data["roles"] = sorted(roles.user_roles(instance))

        return data

    def validate_password(self, value):
        """Applique les validateurs de mot de passe de l'instance InvenTree.

        `min_length` ne suffit pas : le projet hérite des
        `AUTH_PASSWORD_VALIDATORS` de Django / InvenTree (mot de passe courant,
        trop proche du nom d'utilisateur, purement numérique…). Les refuser ici
        évite de créer des comptes que la politique du site rejetterait ensuite.
        """

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
        """Empêche l'admin connecté de se couper lui-même l'accès.

        Se désactiver ou se retirer le rôle `admin` fermerait le back-office à
        son propre auteur — et s'il est le seul admin non superutilisateur,
        plus personne ne peut rouvrir la porte sans passer par le shell.
        """

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

        new_roles = attrs.get("roles")

        if (
            new_roles is not None
            and roles.ADMIN not in set(new_roles)
            and roles.ADMIN in roles.user_roles(self.instance)
        ):
            raise serializers.ValidationError({
                "roles": "Vous ne pouvez pas retirer votre propre rôle admin."
            })

    def _ensure_role_groups(self):
        """Crée les groupes métiers manquants si nécessaire."""

        for role in roles.ALL_ROLES:
            Group.objects.get_or_create(name=role)

    def _apply_roles(self, user, role_names):
        """Remplace uniquement les groupes métier du plugin.

        Les groupes Django hors plugin sont conservés.
        """

        self._ensure_role_groups()

        role_names = set(role_names or [])
        existing_non_plugin_groups = user.groups.exclude(name__in=roles.ALL_ROLES)
        plugin_groups = Group.objects.filter(name__in=role_names)

        user.groups.set(list(existing_non_plugin_groups) + list(plugin_groups))

    def create(self, validated_data):
        """Crée un utilisateur et lui affecte ses rôles."""

        role_names = validated_data.pop("roles", [])
        password = validated_data.pop("password", "")

        user = get_user_model().objects.create_user(
            password=password,
            **validated_data,
        )

        self._apply_roles(user, role_names)

        return user

    def update(self, instance, validated_data):
        """Met à jour l'utilisateur, son état actif et ses rôles."""

        role_names = validated_data.pop("roles", None)
        password = validated_data.pop("password", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        if password:
            instance.set_password(password)

        instance.save()

        if role_names is not None:
            self._apply_roles(instance, role_names)

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
            .objects.prefetch_related("groups")
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
    queryset = get_user_model().objects.prefetch_related("groups").all()


class BackOfficeRoleListView(APIView):
    """Liste des rôles métier disponibles."""

    permission_classes = [BackOfficePermission]

    ROLE_LABELS = {
        roles.ADMIN: "Admin",
        roles.GESTIONNAIRE: "Gestionnaire",
        roles.MAGASINIER: "Magasinier",
        roles.LIVREUR: "Livreur",
        roles.SAV: "SAV",
        roles.ORGANISATEUR: "Organisateur",
        roles.LECTEUR: "Lecteur",
        roles.ACHETEUR: "Acheteur",
    }

    def get(self, request, *args, **kwargs):
        """Retourne les rôles métier disponibles.

        Aucune écriture ici : les groupes sont créés par les migrations
        (`0003_create_role_groups`, `0015_create_acheteur_role_group`) et, en
        dernier recours, à l'affectation des rôles.
        """

        payload = [
            {
                "name": role,
                "label": self.ROLE_LABELS.get(role, role),
            }
            for role in roles.ALL_ROLES
        ]

        serializer = BackOfficeRoleSerializer(payload, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
