/** Points d'entrée et pagination communs aux écrans back-office. */

const BASE = "/plugin/inventree-location/backoffice";

export const USERS_URL = `${BASE}/users/`;
export const ROLES_URL = `${BASE}/roles/`;
export const CLIENTS_URL = `${BASE}/clients/`;
export const CONTACTS_URL = `${BASE}/contacts/`;
export const PARTS_URL = `${BASE}/parts/`;

/**
 * Photo d'un objet : endpoint distinct du formulaire.
 *
 * Le formulaire reste en JSON ; y glisser un fichier imposerait du multipart à
 * tous les champs, où un booléen devient « true » et un entier nul une chaîne
 * vide. POST pour déposer, DELETE pour retirer.
 */
export function partImageUrl(partId: number): string {
	return `${PARTS_URL}${partId}/image/`;
}

/** Doit rester aligné sur `BackOfficePagination.page_size` côté serveur. */
export const PAGE_SIZE = 20;

/** Paramètres de requête d'une liste paginée, recherche incluse si non vide. */
export function listParams(
	page: number,
	search: string,
): Record<string, string> {
	const params: Record<string, string> = {
		page: String(page),
		page_size: String(PAGE_SIZE),
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
