/** Logique pure de l'écran catalogue (CAT-02 / CAT-03). */

import { pageCount } from '../urlState';

export interface CatalogFiltersState {
  /** Recherche plein-texte (nom, description, IPN). */
  search: string;
  /** Identifiants de catégories sélectionnés. */
  categories: number[];
  /** Drapeau louable : true = louable uniquement, false = non-louable, 'all' = tout. */
  rentable: boolean | 'all';
  /** Période sur laquelle juger la disponibilité, au format `AAAA-MM-JJ`. */
  dateDebut: string | null;
  dateFin: string | null;
  /** Page courante (1-based). */
  page: number;
}

export const DEFAULT_FILTERS: CatalogFiltersState = {
  search: '',
  categories: [],
  rentable: true,
  dateDebut: null,
  dateFin: null,
  page: 1
};

/** Taille de page du catalogue (alignée sur le backend, CAT-02). */
export const CATALOG_PAGE_SIZE = 50;

/**
 * Construit les query params envoyés à l'API catalogue à partir des filtres.
 */
export function buildCatalogQuery(
  filters: CatalogFiltersState
): Record<string, string> {
  const params: Record<string, string> = {
    page: String(filters.page),
    page_size: String(CATALOG_PAGE_SIZE)
  };

  if (filters.search.trim()) {
    params.search = filters.search.trim();
  }

  if (filters.categories.length > 0) {
    params.categories = filters.categories.join(',');
  }

  // rentable=true est le défaut backend ; on ne l'envoie que si non-défaut.
  if (filters.rentable === 'all') {
    params.rentable = 'all';
  } else if (filters.rentable === false) {
    params.rentable = 'false';
  }

  // Une borne seule est légitime : « à partir du 10 » se calcule, le serveur
  // complète l'autre avec la journée courante.
  if (filters.dateDebut) {
    params.date_debut = filters.dateDebut;
  }
  if (filters.dateFin) {
    params.date_fin = filters.dateFin;
  }

  return params;
}

/** Clés d'URL du widget Catalogue. */
export const CATALOG_URL_KEYS = ['q', 'cat', 'rentable', 'du', 'au', 'page'];

/** Sérialise l'état des filtres en query string pour l'URL (CAT-03). */
export function serializeFilters(filters: CatalogFiltersState): string {
  const search = new URLSearchParams();

  if (filters.search.trim()) {
    search.set('q', filters.search.trim());
  }
  if (filters.categories.length > 0) {
    search.set('cat', filters.categories.join(','));
  }
  if (filters.rentable !== DEFAULT_FILTERS.rentable) {
    search.set('rentable', String(filters.rentable));
  }
  if (filters.dateDebut) {
    search.set('du', filters.dateDebut);
  }
  if (filters.dateFin) {
    search.set('au', filters.dateFin);
  }
  if (filters.page !== 1) {
    search.set('page', String(filters.page));
  }

  return search.toString();
}

/** pas partir au serveur : il répondrait 400 et le widget afficherait une */
function parseIsoDate(value: string | null): string | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return null;
  }

  return Number.isNaN(new Date(value).getTime()) ? null : value;
}

/** Parse une query string en état de filtres (tolérant aux valeurs absentes). */
export function parseFilters(query: string): CatalogFiltersState {
  const search = new URLSearchParams(query);

  const categories = (search.get('cat') ?? '')
    .split(',')
    .map((value) => Number.parseInt(value, 10))
    .filter((value) => Number.isInteger(value));

  const rentableRaw = search.get('rentable');
  let rentable: boolean | 'all' = DEFAULT_FILTERS.rentable;
  if (rentableRaw === 'all') {
    rentable = 'all';
  } else if (rentableRaw === 'false') {
    rentable = false;
  } else if (rentableRaw === 'true') {
    rentable = true;
  }

  const pageRaw = Number.parseInt(search.get('page') ?? '1', 10);

  return {
    search: search.get('q') ?? '',
    categories,
    rentable,
    dateDebut: parseIsoDate(search.get('du')),
    dateFin: parseIsoDate(search.get('au')),
    page: Number.isInteger(pageRaw) && pageRaw > 0 ? pageRaw : 1
  };
}

/** `2026-09-10` → `10/09/2026`. */
function enFrancais(iso: string): string {
  const [annee, mois, jour] = iso.split('-');
  return `${jour}/${mois}/${annee}`;
}

/** En-tête de la colonne de disponibilité, selon la période demandée. */
export function libelleColonneDisponibilite(
  dateDebut: string | null,
  dateFin: string | null
): string {
  if (!dateDebut && !dateFin) {
    return "Disponible aujourd'hui";
  }

  if (dateDebut && dateFin) {
    return dateDebut === dateFin
      ? `Disponible le ${enFrancais(dateDebut)}`
      : `Disponible du ${enFrancais(dateDebut)} au ${enFrancais(dateFin)}`;
  }

  // Une seule borne : le serveur complète l'autre avec aujourd'hui. On le dit
  // plutôt que d'afficher une plage dont une extrémité serait devinée.
  return dateDebut
    ? `Disponible à partir du ${enFrancais(dateDebut)}`
    : `Disponible jusqu'au ${enFrancais(dateFin as string)}`;
}

/** Nombre total de pages pour un compte donné. */
export function totalPages(count: number): number {
  return pageCount(count, CATALOG_PAGE_SIZE);
}
