export type DeliveryViewMode = 'liste' | 'calendrier' | 'carte';

export interface DeliveryFiltersState {
  dateRange: [string | null, string | null];
  statuts: string[];
  lieux: number[];
  viewMode: DeliveryViewMode;
  /**
   * Ordre de passage de la tournée (LIV-04), clés `l<id>` / `r<id>`.
   *
   * Vide = ordre chronologique. Il vit dans l'URL comme les filtres : la
   * tournée survit au rechargement et se partage par simple lien, sans table
   * d'ordre côté serveur.
   */
  ordre: string[];
}

export const DEFAULT_DELIVERY_FILTERS: DeliveryFiltersState = {
  dateRange: [null, null],
  statuts: [],
  lieux: [],
  viewMode: 'liste',
  ordre: []
};

export function buildDeliveryQuery(
  filters: DeliveryFiltersState
): Record<string, string | string[]> {
  const params: Record<string, string | string[]> = {};

  if (filters.statuts.length > 0) {
    params.statut = filters.statuts;
  }

  if (filters.lieux.length > 0) {
    params.lieu = filters.lieux.map(String);
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
 * Clés d'URL du widget Livraisons.
 *
 * Préfixées : plusieurs widgets partagent la même URL de dashboard (cf.
 * `reservationParams.ts` / `urlState.ts`).
 */
export const DELIVERY_URL_KEYS = [
  'livr_from',
  'livr_to',
  'livr_statut',
  'livr_lieu',
  'livr_view',
  'livr_ordre'
];

function isViewMode(value: string | null): value is DeliveryViewMode {
  return value === 'liste' || value === 'calendrier' || value === 'carte';
}

export function serializeDeliveryFilters(
  filters: DeliveryFiltersState
): string {
  const search = new URLSearchParams();

  if (filters.statuts.length > 0) {
    search.set('livr_statut', filters.statuts.join(','));
  }

  if (filters.lieux.length > 0) {
    search.set('livr_lieu', filters.lieux.join(','));
  }

  if (filters.dateRange[0]) {
    search.set('livr_from', filters.dateRange[0]);
  }

  if (filters.dateRange[1]) {
    search.set('livr_to', filters.dateRange[1]);
  }

  if (filters.viewMode !== DEFAULT_DELIVERY_FILTERS.viewMode) {
    search.set('livr_view', filters.viewMode);
  }

  if (filters.ordre.length > 0) {
    search.set('livr_ordre', filters.ordre.join(','));
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

export function parseDeliveryFilters(query: string): DeliveryFiltersState {
  const search = new URLSearchParams(query);
  const from = search.get('livr_from');
  const to = search.get('livr_to');
  const view = search.get('livr_view');

  return {
    dateRange: [from || null, to || null],
    statuts: parseStringList(search.get('livr_statut')),
    lieux: parseIntList(search.get('livr_lieu')),
    viewMode: isViewMode(view) ? view : DEFAULT_DELIVERY_FILTERS.viewMode,
    ordre: parseStringList(search.get('livr_ordre'))
  };
}
