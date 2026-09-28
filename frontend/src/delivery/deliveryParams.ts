export type DeliveryViewMode =
  | 'hierarchique'
  | 'liste'
  | 'calendrier'
  | 'carte';

export type DeliveryHorizon = 'jour' | 'avenir' | 'tout';

export interface DeliveryFiltersState {
  horizon: DeliveryHorizon;
  dateRange: [string | null, string | null];
  statuts: string[];
  lieux: number[];
  /** Filtre « Virtuel » du point 4.8.1 : `oui`, `non`, ou `null` pour tous. */
  virtuel: string | null;
  viewMode: DeliveryViewMode;
  ordre: string[];
}

export const DEFAULT_DELIVERY_FILTERS: DeliveryFiltersState = {
  horizon: 'jour',
  dateRange: [null, null],
  statuts: [],
  lieux: [],
  // « L'option Non est positionnée par défaut » (4.8.1) : une tournée sert à
  // sortir du matériel, un bon de service seul n'a rien à y faire.
  virtuel: 'non',
  viewMode: 'hierarchique',
  ordre: []
};

/**
 * Le serveur compare à la journée entière dans son propre fuseau
 * (`Europe/Paris`, cf. `_borne_journee`) : envoyer une date nue plutôt qu'un
 */
export function aujourdhuiIso(maintenant: Date = new Date()): string {
  const mois = String(maintenant.getMonth() + 1).padStart(2, '0');
  const jour = String(maintenant.getDate()).padStart(2, '0');
  return `${maintenant.getFullYear()}-${mois}-${jour}`;
}

export function buildDeliveryQuery(
  filters: DeliveryFiltersState,
  aujourdhui: string = aujourdhuiIso()
): Record<string, string | string[]> {
  const params: Record<string, string | string[]> = {};

  if (filters.statuts.length > 0) {
    params.statut = filters.statuts;
  }

  if (filters.lieux.length > 0) {
    params.lieu = filters.lieux.map(String);
  }

  if (filters.virtuel) {
    params.virtuel = filters.virtuel;
  }

  const [debut, fin] = filters.dateRange;

  // Une période saisie à la main l'emporte : l'horizon n'est qu'un raccourci.
  if (debut || fin) {
    if (debut) {
      params.date_from = debut;
    }
    if (fin) {
      params.date_to = fin;
    }

    return params;
  }

  // `date_from` filtre sur la date de retour, `date_to` sur celle de retrait :
  // borner les deux à aujourd'hui garde les tournées *en cours* ce jour-là, y
  if (filters.horizon === 'jour') {
    params.date_from = aujourdhui;
    params.date_to = aujourdhui;
  } else if (filters.horizon === 'avenir') {
    params.date_from = aujourdhui;
  }

  return params;
}

/** Clés d'URL du widget Livraisons. */
export const DELIVERY_URL_KEYS = [
  'livr_from',
  'livr_to',
  'livr_horizon',
  'livr_statut',
  'livr_lieu',
  'livr_virtuel',
  'livr_view',
  'livr_ordre'
];

function isHorizon(value: string | null): value is DeliveryHorizon {
  return value === 'jour' || value === 'avenir' || value === 'tout';
}

/** `tous` lève le défaut, une valeur inconnue le rétablit. */
function parseVirtuel(value: string | null): string | null {
  if (value === 'oui' || value === 'non') {
    return value;
  }

  if (value === 'tous') {
    return null;
  }

  return DEFAULT_DELIVERY_FILTERS.virtuel;
}

function isViewMode(value: string | null): value is DeliveryViewMode {
  return (
    value === 'hierarchique' ||
    value === 'liste' ||
    value === 'calendrier' ||
    value === 'carte'
  );
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

  // L'horizon est écrit dès qu'il n'est plus le défaut, y compris « tout » :
  // sans cela, « voir toutes les livraisons » redeviendrait « aujourd'hui » au
  if (filters.horizon !== DEFAULT_DELIVERY_FILTERS.horizon) {
    search.set('livr_horizon', filters.horizon);
  }

  // Le défaut étant « non », c'est « tous » qu'il faut écrire pour survivre à
  // un rechargement : sans marqueur, l'absence de clé ramènerait « non ».
  if (filters.virtuel !== DEFAULT_DELIVERY_FILTERS.virtuel) {
    search.set('livr_virtuel', filters.virtuel ?? 'tous');
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
  const horizon = search.get('livr_horizon');

  return {
    horizon: isHorizon(horizon) ? horizon : DEFAULT_DELIVERY_FILTERS.horizon,
    dateRange: [from || null, to || null],
    statuts: parseStringList(search.get('livr_statut')),
    lieux: parseIntList(search.get('livr_lieu')),
    virtuel: parseVirtuel(search.get('livr_virtuel')),
    viewMode: isViewMode(view) ? view : DEFAULT_DELIVERY_FILTERS.viewMode,
    ordre: parseStringList(search.get('livr_ordre'))
  };
}

/**
 * Retire les articles virtuels des bons quand le filtre est sur « non »
 * (point 4.8.1 : « ne pas afficher les articles virtuels »). On les retire des
 * données, pas seulement de l'affichage : un service ne se charge pas dans un
 * camion, l'exiger dans le « tout est chargé » empêcherait de clore un bon.
 */
export function sansArticlesVirtuels<
  T extends { lignes: { is_virtual: boolean }[] }
>(bons: T[], virtuel: string | null): T[] {
  if (virtuel !== 'non') {
    return bons;
  }

  return bons.map((bon) => ({
    ...bon,
    lignes: bon.lignes.filter((ligne) => !ligne.is_virtual)
  }));
}
