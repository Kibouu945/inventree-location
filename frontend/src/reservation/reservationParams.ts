export interface ReservationFiltersState {
  search: string;
  statuts: string[];
  categories: number[];
  dateRange: [string | null, string | null];
}

export const DEFAULT_RESERVATION_FILTERS: ReservationFiltersState = {
  search: '',
  statuts: [],
  categories: [],
  dateRange: [null, null]
};

export function buildReservationQuery(
  filters: ReservationFiltersState
): Record<string, string | string[]> {
  const params: Record<string, string | string[]> = {};

  if (filters.search.trim()) {
    params.search = filters.search.trim();
  }

  if (filters.statuts.length > 0) {
    params.statut = filters.statuts;
  }

  if (filters.categories.length > 0) {
    params.categories = filters.categories.join(',');
  }

  if (filters.dateRange[0]) {
    params.date_from = filters.dateRange[0];
  }

  if (filters.dateRange[1]) {
    params.date_to = filters.dateRange[1];
  }

  return params;
}

/**
 * Clés d'URL du widget Réservations.
 *
 * Préfixées : le widget Catalogue est monté sur le même dashboard et possède
 * déjà `q` / `cat` / `rentable` / `page`, avec un sens différent (catégorie de
 * Part vs catégorie des lignes de réservation). Sans préfixe, les deux widgets
 * s'écrasent et se contaminent.
 */
export const RESERVATION_URL_KEYS = [
  'resa_q',
  'resa_statut',
  'resa_cat',
  'resa_from',
  'resa_to'
];

export function serializeReservationFilters(
  filters: ReservationFiltersState
): string {
  const search = new URLSearchParams();

  if (filters.search.trim()) {
    search.set('resa_q', filters.search.trim());
  }

  if (filters.statuts.length > 0) {
    search.set('resa_statut', filters.statuts.join(','));
  }

  if (filters.categories.length > 0) {
    search.set('resa_cat', filters.categories.join(','));
  }

  if (filters.dateRange[0]) {
    search.set('resa_from', filters.dateRange[0]);
  }

  if (filters.dateRange[1]) {
    search.set('resa_to', filters.dateRange[1]);
  }

  return search.toString();
}

function parseIntList(value: string | null): number[] {
  if (!value) {
    return [];
  }

  const seen = new Set<number>();

  for (const entry of value.split(',')) {
    const parsed = Number.parseInt(entry, 10);

    if (Number.isInteger(parsed)) {
      seen.add(parsed);
    }
  }

  return Array.from(seen);
}

function parseStringList(value: string | null): string[] {
  if (!value) {
    return [];
  }

  const seen = new Set<string>();

  for (const entry of value.split(',')) {
    const normalized = entry.trim();

    if (normalized) {
      seen.add(normalized);
    }
  }

  return Array.from(seen);
}

export function parseReservationFilters(
  query: string
): ReservationFiltersState {
  const search = new URLSearchParams(query);
  const from = search.get('resa_from');
  const to = search.get('resa_to');

  return {
    search: search.get('resa_q') ?? '',
    statuts: parseStringList(search.get('resa_statut')),
    categories: parseIntList(search.get('resa_cat')),
    dateRange: [from || null, to || null]
  };
}
