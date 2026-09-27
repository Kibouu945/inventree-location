import { describe, expect, it } from 'vitest';

import {
  buildReservationQuery,
  DEFAULT_RESERVATION_FILTERS,
  parseReservationFilters,
  serializeReservationFilters
} from '../reservation/reservationParams';

describe('reservationParams', () => {
  it('serialize and parse filters round-trip', () => {
    const query = serializeReservationFilters({
      search: 'camp',
      statuts: ['soumise', 'validee'],
      categories: [3, 7],
      client: null,
      dateRange: ['2026-06-01', '2026-06-02']
    });

    expect(query).toContain('resa_q=camp');
    expect(query).toContain('resa_statut=soumise%2Cvalidee');
    expect(query).toContain('resa_cat=3%2C7');

    const parsed = parseReservationFilters(`?${query}`);

    expect(parsed).toEqual({
      search: 'camp',
      statuts: ['soumise', 'validee'],
      categories: [3, 7],
      client: null,
      dateRange: ['2026-06-01', '2026-06-02']
    });
  });

  it('build query includes only meaningful filters', () => {
    expect(buildReservationQuery(DEFAULT_RESERVATION_FILTERS)).toEqual({});

    expect(
      buildReservationQuery({
        search: 'abc',
        statuts: ['brouillon'],
        categories: [4],
        client: null,
        dateRange: ['2026-01-01', null]
      })
    ).toEqual({
      search: 'abc',
      statut: ['brouillon'],
      categories: '4',
      date_from: '2026-01-01'
    });
  });

  it('parse tolerates invalid values', () => {
    const parsed = parseReservationFilters(
      '?resa_cat=2,abc,2&resa_statut=&resa_from=&resa_to=2026-08-01'
    );

    expect(parsed.categories).toEqual([2]);
    expect(parsed.statuts).toEqual([]);
    expect(parsed.dateRange).toEqual([null, '2026-08-01']);
  });
  it('garde le filtre client dans l’URL et la requête', () => {
    const filtres = { ...DEFAULT_RESERVATION_FILTERS, client: '12' };

    expect(buildReservationQuery(filtres)).toEqual({ client: '12' });

    const query = serializeReservationFilters(filtres);
    expect(query).toContain('resa_client=12');
    expect(parseReservationFilters(`?${query}`).client).toBe('12');
  });
});
