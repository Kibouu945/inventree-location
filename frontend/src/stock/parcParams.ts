// État d'URL de l'écran « État du parc », clés `parc_`.
// Mêmes règles que `ramassageParams.ts` : la query string est partagée entre
// widgets, chacun n'écrit que ses propres clés.

import { pageCount, parseStringList } from '../urlState';

export interface ParcFiltersState {
  search: string;
  categories: string[];
  /** N'afficher que les lignes qui méritent l'œil du magasinier. */
  alerteSeule: boolean;
  page: number;
}

export const PARC_PAGE_SIZE = 25;

export const DEFAULT_PARC_FILTERS: ParcFiltersState = {
  search: '',
  categories: [],
  alerteSeule: false,
  page: 1
};

export const PARC_URL_KEYS = ['parc_q', 'parc_cat', 'parc_alerte', 'parc_page'];

/** Paramètres envoyés au serveur. */
export function buildParcQuery(
  filters: ParcFiltersState
): Record<string, string> {
  const params: Record<string, string> = {
    page: String(filters.page),
    page_size: String(PARC_PAGE_SIZE)
  };

  if (filters.search.trim()) {
    params.search = filters.search.trim();
  }

  if (filters.categories.length > 0) {
    params.categories = filters.categories.join(',');
  }

  if (filters.alerteSeule) {
    params.alerte = '1';
  }

  return params;
}

export function serializeParcFilters(filters: ParcFiltersState): string {
  const search = new URLSearchParams();

  if (filters.search.trim()) {
    search.set('parc_q', filters.search.trim());
  }

  if (filters.categories.length > 0) {
    search.set('parc_cat', filters.categories.join(','));
  }

  if (filters.alerteSeule) {
    search.set('parc_alerte', '1');
  }

  if (filters.page !== DEFAULT_PARC_FILTERS.page) {
    search.set('parc_page', String(filters.page));
  }

  return search.toString();
}

export function parseParcFilters(query: string): ParcFiltersState {
  const search = new URLSearchParams(query);
  const page = Number.parseInt(search.get('parc_page') ?? '1', 10);

  return {
    search: search.get('parc_q') ?? '',
    categories: parseStringList(search.get('parc_cat')),
    alerteSeule: search.get('parc_alerte') === '1',
    page: Number.isInteger(page) && page > 0 ? page : 1
  };
}

/** Nombre total de pages pour un compte donné. */
export function totalParcPages(count: number): number {
  return pageCount(count, PARC_PAGE_SIZE);
}

/** Ce que dit un motif d'alerte au magasinier, en clair. */
export function libelleMotif(motif: string): string {
  if (motif === 'sous_seuil') {
    return 'Sous le seuil d’alerte';
  }

  if (motif === 'sorti_au_dela_du_parc') {
    return 'Sorti au-delà du parc';
  }

  return motif;
}
