// RBAC métier côté front — miroir de inventree_location/roles.py & permissions.py.
import type { InvenTreePluginContext } from '@inventreedb/ui';

export const ADMIN = 'admin';
export const GESTIONNAIRE = 'gestionnaire';
export const MAGASINIER = 'magasinier';
export const LIVREUR = 'livreur';
export const SAV = 'sav';
export const ORGANISATEUR = 'organisateur';
export const LECTEUR = 'lecteur';
export const ACHETEUR = 'acheteur';

export const RESERVATION_WRITE_ROLES = [ADMIN, GESTIONNAIRE, ORGANISATEUR];
export const CATALOG_WRITE_ROLES = [ADMIN, GESTIONNAIRE];
export const ORGANISATION_WRITE_ROLES = [ADMIN, GESTIONNAIRE, ORGANISATEUR];
// Arbitrage (valider / refuser) : gestionnaire + admin seulement.
export const RESERVATION_ARBITRAGE_ROLES = [ADMIN, GESTIONNAIRE];
// Retours (check-in comme déclaration) : magasinier + admin, miroir strict de
// `ReturnCheckinPermission` et `PrestationRetourPermission`. Distinct de
// l'arbitrage : le magasinier traite les retours mais ne valide pas les
// réservations, et le gestionnaire fait l'inverse.
export const RETURN_CHECKIN_ROLES = [ADMIN, MAGASINIER];
export const RESERVATION_RETOUR_ROLES = [ADMIN, MAGASINIER];
// Back-office (utilisateurs, articles) : administrateur seulement.
export const BACKOFFICE_ROLES = [ADMIN];

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

export function isSuperuser(context: InvenTreePluginContext): boolean {
  if (context.user?.isSuperuser?.()) {
    return true;
  }

  return Boolean(context.user?.getUser?.()?.is_superuser);
}

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

export function canWriteReservations(context: InvenTreePluginContext): boolean {
  return hasAnyRole(context, RESERVATION_WRITE_ROLES);
}

/** Peut valider / refuser une réservation (admin, gestionnaire). */
export function canArbitrateReservations(
  context: InvenTreePluginContext
): boolean {
  return hasAnyRole(context, RESERVATION_ARBITRAGE_ROLES);
}

/** Peut pointer le retour d'une réservation livrée (admin, magasinier). */
export function canCheckinReturns(context: InvenTreePluginContext): boolean {
  return hasAnyRole(context, RETURN_CHECKIN_ROLES);
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

/** Peut accéder aux back-offices utilisateurs et articles (admin). */
export function canManageBackOffice(context: InvenTreePluginContext): boolean {
  return hasAnyRole(context, BACKOFFICE_ROLES);
}
