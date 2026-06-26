/**
 * Logique pure de l'écran catalogue (CAT-02 / CAT-03).
 *
 * Isolée des composants React pour être testable sans rendu :
 * - état des filtres <-> query string (URL state)
 * - construction des paramètres envoyés à l'API `/catalog/`
 */

export interface CatalogFiltersState {
  /** Recherche plein-texte (nom, description, IPN). */
  search: string;
  /** Identifiants de catégories sélectionnés. */
  categories: number[];
  /** Drapeau louable : true = louable uniquement, false = non-louable, 'all' = tout. */
  rentable: boolean | 'all';
  /** Page courante (1-based). */
  page: number;
}

export const DEFAULT_FILTERS: CatalogFiltersState = {
  search: '',
  categories: [],
  rentable: true,
  page: 1
};

/** Taille de page du catalogue (alignée sur le backend, CAT-02). */
export const CATALOG_PAGE_SIZE = 50;

/**
 * Construit les query params envoyés à l'API catalogue à partir des filtres.
 * N'inclut que les paramètres significatifs (pas de clés vides).
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

  return params;
}

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
  if (filters.page !== 1) {
    search.set('page', String(filters.page));
  }

  return search.toString();
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
    page: Number.isInteger(pageRaw) && pageRaw > 0 ? pageRaw : 1
  };
}

/** Nombre total de pages pour un compte donné. */
export function totalPages(count: number): number {
  return Math.max(1, Math.ceil(count / CATALOG_PAGE_SIZE));
}
