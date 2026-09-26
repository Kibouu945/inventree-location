// État d'URL de l'écran : mêmes règles que `ramassageParams.ts`, clés `hist_`.
import type { PeriodePreset } from './histogramLogic';
import { aujourdhui } from './histogramLogic';

export type HistogramVue = 'histogramme' | 'tableau';

export interface HistogramFiltersState {
  partId: string | null;
  /** AAAA-MM-JJ. */
  dateDebut: string;
  preset: PeriodePreset;
  vue: HistogramVue;
  /** Jours ISO (1 = lundi … 7 = dimanche) ; vide = tous. */
  joursVisibles: string[];
}

export const HISTOGRAM_URL_KEYS = [
  'hist_part',
  'hist_from',
  'hist_periode',
  'hist_vue',
  'hist_jours'
];

export function defaultHistogramFilters(
  maintenant: Date = new Date()
): HistogramFiltersState {
  return {
    partId: null,
    dateDebut: aujourdhui(maintenant),
    preset: 'semaine',
    vue: 'histogramme',
    joursVisibles: []
  };
}

function parseJours(value: string | null): string[] {
  if (!value) {
    return [];
  }

  const retenus: string[] = [];

  for (const entree of value.split(',')) {
    const jour = entree.trim();

    if (/^[1-7]$/.test(jour) && !retenus.includes(jour)) {
      retenus.push(jour);
    }
  }

  return retenus;
}

function parseDate(value: string | null, defaut: string): string {
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : defaut;
}

export function parseHistogramFilters(
  query: string,
  maintenant: Date = new Date()
): HistogramFiltersState {
  const search = new URLSearchParams(query);
  const defauts = defaultHistogramFilters(maintenant);
  const part = search.get('hist_part');

  return {
    partId: part && /^\d+$/.test(part) ? part : null,
    dateDebut: parseDate(search.get('hist_from'), defauts.dateDebut),
    preset: search.get('hist_periode') === 'mois' ? 'mois' : 'semaine',
    vue: search.get('hist_vue') === 'tableau' ? 'tableau' : 'histogramme',
    joursVisibles: parseJours(search.get('hist_jours'))
  };
}

export function serializeHistogramFilters(
  filters: HistogramFiltersState,
  maintenant: Date = new Date()
): string {
  const search = new URLSearchParams();
  const defauts = defaultHistogramFilters(maintenant);

  if (filters.partId) {
    search.set('hist_part', filters.partId);
  }

  if (filters.dateDebut !== defauts.dateDebut) {
    search.set('hist_from', filters.dateDebut);
  }

  if (filters.preset !== defauts.preset) {
    search.set('hist_periode', filters.preset);
  }

  if (filters.vue !== defauts.vue) {
    search.set('hist_vue', filters.vue);
  }

  if (filters.joursVisibles.length > 0) {
    search.set('hist_jours', filters.joursVisibles.join(','));
  }

  return search.toString();
}
