"""Back-office utilisateurs et rôles pour SCRUM-108."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import generics, permissions, serializers, status
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

    def validate(self, attrs):
        """Le mot de passe est obligatoire à la création."""

        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({
                "password": "Le mot de passe est obligatoire à la création."
            })

        return attrs

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
            queryset = (
                queryset.filter(username__icontains=search)
                | queryset.filter(first_name__icontains=search)
                | queryset.filter(last_name__icontains=search)
                | queryset.filter(email__icontains=search)
            )

        return queryset.distinct()


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
        """Retourne les rôles disponibles et crée les groupes s'ils manquent."""

        for role in roles.ALL_ROLES:
            Group.objects.get_or_create(name=role)

        payload = [
            {
                "name": role,
                "label": self.ROLE_LABELS.get(role, role),
            }
            for role in roles.ALL_ROLES
        ]

        serializer = BackOfficeRoleSerializer(payload, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)
