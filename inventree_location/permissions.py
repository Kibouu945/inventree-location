"""Permissions DRF basées sur les rôles (TR-03)."""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from . import roles


class RoleBasedPermission(BasePermission):
    """Autorise la lecture aux `read_roles` et l'écriture aux `write_roles`."""

    #: Rôles autorisés en lecture (méthodes sûres). Par défaut : tous.
    read_roles: tuple[str, ...] = roles.ALL_ROLES
    #: Rôles autorisés en écriture. À surcharger par ressource.
    write_roles: tuple[str, ...] = (roles.ADMIN,)

    def has_permission(self, request, view) -> bool:
        user = request.user

        if not user or not user.is_authenticated:
            return False

        allowed = (
            self.read_roles if request.method in SAFE_METHODS else self.write_roles
        )

        return roles.user_has_any_role(user, allowed)


class CatalogPermission(RoleBasedPermission):
    """Lecture pour tous ; gestion du drapeau louable pour admin / gestionnaire."""

    write_roles = (roles.ADMIN, roles.GESTIONNAIRE)


class LieuPermission(RoleBasedPermission):
    """Lecture pour tous ; gestion des lieux pour admin / gestionnaire."""

    write_roles = (roles.ADMIN, roles.GESTIONNAIRE)


class ReservationPermission(RoleBasedPermission):
    """Lecture pour tous ; écriture pour admin / gestionnaire."""

    write_roles = (roles.ADMIN, roles.GESTIONNAIRE)


class ManifestationPermission(RoleBasedPermission):
    """Lecture pour tous ; gestion pour admin / gestionnaire."""

    write_roles = (roles.ADMIN, roles.GESTIONNAIRE)


class PrestationPermission(RoleBasedPermission):
    """Lecture pour tous ; gestion pour admin / gestionnaire."""

    write_roles = (roles.ADMIN, roles.GESTIONNAIRE)


class DeliveryPermission(RoleBasedPermission):
    """Lecture pour tous (dont livreur) ; aucune écriture ouverte cette itération."""

    write_roles = (roles.ADMIN, roles.GESTIONNAIRE)


class MarquerLivreePermission(RoleBasedPermission):
    """Marquer une réservation livrée : celui qui livre, plus l'encadrement."""

    write_roles = (roles.ADMIN, roles.GESTIONNAIRE, roles.LIVREUR)


class DeliveryAssignationPermission(RoleBasedPermission):
    """Prendre, relâcher et faire avancer une livraison : le livreur, plus"""

    write_roles = (roles.ADMIN, roles.GESTIONNAIRE, roles.LIVREUR)


class ReturnCheckinPermission(RoleBasedPermission):
    """Check-in retour ligne par ligne (OK / manquant / cassé) : rôle magasinier."""

    write_roles = (roles.ADMIN, roles.MAGASINIER)


class PrestationRetourPermission(RoleBasedPermission):
    """Déclaration du retour d'une prestation (SCRUM-95) : rôle magasinier."""

    write_roles = (roles.ADMIN, roles.MAGASINIER)


class SavPermission(RoleBasedPermission):
    """Tickets SAV et objets détruits (SCRUM-112) : rôle sav."""

    write_roles = (roles.ADMIN, roles.SAV)
