/** Points d'entrée et pagination communs aux écrans back-office. */

const BASE = '/plugin/inventree-location/backoffice';

export const USERS_URL = `${BASE}/users/`;
export const ROLES_URL = `${BASE}/roles/`;
export const GROUPES_URL = `${BASE}/groupes/`;
export const PARTS_URL = `${BASE}/parts/`;

/** Doit rester aligné sur `BackOfficePagination.page_size` côté serveur. */
export const PAGE_SIZE = 20;

/** Paramètres de requête d'une liste paginée, recherche incluse si non vide. */
export function listParams(
  page: number,
  search: string
): Record<string, string> {
  const params: Record<string, string> = {
    page: String(page),
    page_size: String(PAGE_SIZE)
  };

  if (search.trim()) {
    params.search = search.trim();
  }

  return params;
}

/** Nombre de pages pour un total d'éléments. */
export function pageCount(total: number): number {
  return Math.max(1, Math.ceil(total / PAGE_SIZE));
}
