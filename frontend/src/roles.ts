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

export function canWriteCatalog(context: InvenTreePluginContext): boolean {
  return hasAnyRole(context, CATALOG_WRITE_ROLES);
}

export function canManageBackOffice(context: InvenTreePluginContext): boolean {
  return hasAnyRole(context, BACKOFFICE_ROLES);
}