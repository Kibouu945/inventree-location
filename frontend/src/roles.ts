// RBAC métier côté front — miroir de inventree_location/roles.py & permissions.py.
//
// La visibilité des actions (boutons créer / soumettre / éditer) est pilotée par
// les 7 groupes métier, PAS par is_staff. Le backend reste la source d'autorité
// (les endpoints renvoient 403) ; ce module ne fait que masquer l'UI en amont.
import type { InvenTreePluginContext } from '@inventreedb/ui';

export const ADMIN = 'admin';
export const GESTIONNAIRE = 'gestionnaire';
export const MAGASINIER = 'magasinier';
export const LIVREUR = 'livreur';
export const SAV = 'sav';
export const ORGANISATEUR = 'organisateur';
export const LECTEUR = 'lecteur';

// Rôles autorisés en écriture, alignés sur permissions.py.
export const RESERVATION_WRITE_ROLES = [ADMIN, GESTIONNAIRE, ORGANISATEUR];
export const CATALOG_WRITE_ROLES = [ADMIN, GESTIONNAIRE];
export const ORGANISATION_WRITE_ROLES = [ADMIN, GESTIONNAIRE, ORGANISATEUR];
// Arbitrage (valider / refuser) : gestionnaire + admin seulement.
export const RESERVATION_ARBITRAGE_ROLES = [ADMIN, GESTIONNAIRE];
// Déclaration du retour d'une prestation : magasinier + admin, miroir de
// `PrestationRetourPermission`. Distinct de l'arbitrage : le magasinier
// déclare les retours mais ne valide pas les réservations, et le
// gestionnaire fait l'inverse.
export const RESERVATION_RETOUR_ROLES = [ADMIN, MAGASINIER];

/**
 * Rôles (noms de groupes) de l'utilisateur courant.
 *
 * `context.user` est le store InvenTree (`UserStateProps`) : les données sont
 * derrière `getUser()`, et `groups` est un tableau d'objets `{ pk, name }`.
 */
export function userRoles(context: InvenTreePluginContext): string[] {
  const groups = context.user?.getUser?.()?.groups;

  if (!Array.isArray(groups)) {
    return [];
  }

  return groups
    .map((group) =>
      typeof group === 'string'
        ? group
        : String((group as { name?: unknown })?.name ?? '')
    )
    .filter(Boolean);
}

/** Vrai si l'utilisateur courant est superutilisateur. */
export function isSuperuser(context: InvenTreePluginContext): boolean {
  if (context.user?.isSuperuser?.()) {
    return true;
  }

  return Boolean(context.user?.getUser?.()?.is_superuser);
}

/** Vrai si l'utilisateur possède au moins un des rôles fournis (superuser inclus). */
export function hasAnyRole(
  context: InvenTreePluginContext,
  roles: string[]
): boolean {
  if (isSuperuser(context)) {
    return true;
  }

  const owned = userRoles(context);
  return owned.some((role) => roles.includes(role));
}

/** Peut créer / éditer une réservation (admin, gestionnaire, organisateur). */
export function canWriteReservations(context: InvenTreePluginContext): boolean {
  return hasAnyRole(context, RESERVATION_WRITE_ROLES);
}

/** Peut valider / refuser une réservation (admin, gestionnaire). */
export function canArbitrateReservations(
  context: InvenTreePluginContext
): boolean {
  return hasAnyRole(context, RESERVATION_ARBITRAGE_ROLES);
}

/** Peut déclarer le retour d'une prestation (admin, magasinier). */
export function canDeclareRetour(context: InvenTreePluginContext): boolean {
  return hasAnyRole(context, RESERVATION_RETOUR_ROLES);
}

/** Peut modifier les drapeaux du catalogue (admin, gestionnaire). */
export function canWriteCatalog(context: InvenTreePluginContext): boolean {
  return hasAnyRole(context, CATALOG_WRITE_ROLES);
}

/** Peut gérer manifestations / prestations / lieux (admin, gestionnaire, organisateur). */
export function canWriteOrganisation(context: InvenTreePluginContext): boolean {
  return hasAnyRole(context, ORGANISATION_WRITE_ROLES);
}
