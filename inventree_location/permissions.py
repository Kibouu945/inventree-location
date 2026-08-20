"""Permissions DRF basÃ©es sur les rÃ´les (TR-03).

Chaque vue REST dÃ©clare une permission dÃ©rivÃ©e de `RoleBasedPermission` qui
distingue lecture (mÃ©thodes sÃ»res) et Ã©criture. Un superutilisateur passe
toujours ; un utilisateur sans rÃ´le connu est refusÃ©.

Mapping appliquÃ© aux endpoints existants (les actions retours / livraisons /
SAV arriveront avec leurs endpoints aux sprints suivants) :

| Ressource     | Lecture            | Ãcriture                          |
|---------------|--------------------|-----------------------------------|
| Catalogue     | tous les rÃ´les     | admin, gestionnaire               |
| Lieux         | tous les rÃ´les     | admin, gestionnaire               |
| RÃ©servations  | tous les rÃ´les     | admin, gestionnaire, organisateur |
"""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission

from . import roles


class RoleBasedPermission(BasePermission):
    """Autorise la lecture aux `read_roles` et l'Ã©criture aux `write_roles`."""

    #: RÃ´les autorisÃ©s en lecture (mÃ©thodes sÃ»res). Par dÃ©faut : tous.
    read_roles: tuple[str, ...] = roles.ALL_ROLES
    #: RÃ´les autorisÃ©s en Ã©criture. Ã surcharger par ressource.
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
    """Lecture pour tous ; Ã©criture pour admin / gestionnaire / organisateur."""

    write_roles = (roles.ADMIN, roles.GESTIONNAIRE, roles.ORGANISATEUR)


class ManifestationPermission(RoleBasedPermission):
    """Lecture pour tous ; gestion pour admin / gestionnaire / organisateur."""

    write_roles = (roles.ADMIN, roles.GESTIONNAIRE, roles.ORGANISATEUR)


class PrestationPermission(RoleBasedPermission):
    """Lecture pour tous ; gestion pour admin / gestionnaire / organisateur."""

    write_roles = (roles.ADMIN, roles.GESTIONNAIRE, roles.ORGANISATEUR)

class MissingItemPermission(RoleBasedPermission):
    """Déclaration des manquants au retour et facturation client : rôle magasinier."""

    write_roles = (roles.ADMIN, roles.MAGASINIER)
