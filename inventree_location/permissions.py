"""Permissions DRF basées sur les rôles (TR-03).

Chaque vue REST déclare une permission dérivée de `RoleBasedPermission` qui
distingue lecture (méthodes sûres) et écriture. Un superutilisateur passe
toujours ; un utilisateur sans rôle connu est refusé.

Mapping appliqué aux endpoints existants (les actions retours / livraisons /
SAV arriveront avec leurs endpoints aux sprints suivants) :

| Ressource     | Lecture            | Écriture                          |
|---------------|--------------------|-----------------------------------|
| Catalogue     | tous les rôles     | admin, gestionnaire               |
| Lieux         | tous les rôles     | admin, gestionnaire               |
| Réservations  | tous les rôles     | admin, gestionnaire, organisateur |
"""

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
    """Lecture pour tous ; écriture pour admin / gestionnaire / organisateur."""

    write_roles = (roles.ADMIN, roles.GESTIONNAIRE, roles.ORGANISATEUR)


class ManifestationPermission(RoleBasedPermission):
    """Lecture pour tous ; gestion pour admin / gestionnaire / organisateur."""

    write_roles = (roles.ADMIN, roles.GESTIONNAIRE, roles.ORGANISATEUR)


class PrestationPermission(RoleBasedPermission):
    """Lecture pour tous ; gestion pour admin / gestionnaire / organisateur."""

    write_roles = (roles.ADMIN, roles.GESTIONNAIRE, roles.ORGANISATEUR)


class ReturnCheckinPermission(RoleBasedPermission):
    """Check-in retour ligne par ligne (OK / manquant / cassé) : rôle magasinier."""

    write_roles = (roles.ADMIN, roles.MAGASINIER)
