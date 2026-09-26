import { describe, expect, it } from 'vitest';

import {
  defaultHistogramFilters,
  type HistogramFiltersState,
  parseHistogramFilters,
  serializeHistogramFilters
} from '../histogramParams';

const MAINTENANT = new Date(2026, 8, 14); // lundi 14 septembre 2026

function etat(
  overrides: Partial<HistogramFiltersState> = {}
): HistogramFiltersState {
  return { ...defaultHistogramFilters(MAINTENANT), ...overrides };
}

describe('defaultHistogramFilters', () => {
  it('ouvre sur la semaine du jour, sans article', () => {
    expect(defaultHistogramFilters(MAINTENANT)).toEqual({
      partId: null,
      dateDebut: '2026-09-14',
      preset: 'semaine',
      vue: 'histogramme',
      joursVisibles: []
    });
  });
});

describe('serializeHistogramFilters', () => {
  it("n'écrit rien tant que rien ne change", () => {
    expect(serializeHistogramFilters(etat(), MAINTENANT)).toBe('');
  });

  it('écrit article, période et vue quand ils sortent du défaut', () => {
    const query = serializeHistogramFilters(
      etat({
        partId: '42',
        dateDebut: '2026-10-01',
        preset: 'mois',
        vue: 'tableau',
        joursVisibles: ['5', '6']
      }),
      MAINTENANT
    );

    expect(new URLSearchParams(query).get('hist_part')).toBe('42');
    expect(new URLSearchParams(query).get('hist_from')).toBe('2026-10-01');
    expect(new URLSearchParams(query).get('hist_periode')).toBe('mois');
    expect(new URLSearchParams(query).get('hist_vue')).toBe('tableau');
    expect(new URLSearchParams(query).get('hist_jours')).toBe('5,6');
  });
});

describe('parseHistogramFilters', () => {
  it('relit ce qui vient d’être écrit', () => {
    const depart = etat({
      partId: '7',
      dateDebut: '2026-12-24',
      preset: 'mois',
      vue: 'tableau',
      joursVisibles: ['1', '7']
    });

    expect(
      parseHistogramFilters(
        serializeHistogramFilters(depart, MAINTENANT),
        MAINTENANT
      )
    ).toEqual(depart);
  });

  it('retombe sur les défauts quand la query est vide', () => {
    expect(parseHistogramFilters('', MAINTENANT)).toEqual(
      defaultHistogramFilters(MAINTENANT)
    );
  });

  it('ignore un article qui n’est pas un identifiant', () => {
    expect(parseHistogramFilters('hist_part=../admin', MAINTENANT).partId).toBe(
      null
    );
  });

  it('ignore une date malformée plutôt que de la passer au serveur', () => {
    expect(parseHistogramFilters('hist_from=hier', MAINTENANT).dateDebut).toBe(
      '2026-09-14'
    );
  });

  it('ne retient que les jours ISO, une seule fois chacun', () => {
    expect(
      parseHistogramFilters('hist_jours=1,1,9,0,7,x', MAINTENANT).joursVisibles
    ).toEqual(['1', '7']);
  });

  it('retombe sur la semaine pour une période inconnue', () => {
    expect(
      parseHistogramFilters('hist_periode=trimestre', MAINTENANT).preset
    ).toBe('semaine');
  });
});
