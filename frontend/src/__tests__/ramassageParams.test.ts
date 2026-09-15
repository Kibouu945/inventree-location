import { describe, expect, it } from 'vitest';

import {
  buildRamassageQuery,
  DEFAULT_RAMASSAGE_FILTERS,
  parseRamassageFilters,
  RAMASSAGE_PAGE_SIZE,
  serializeRamassageFilters,
  totalRamassagePages
} from '../ramassage/ramassageParams';

describe('ramassageParams', () => {
  it('serialize and parse filters round-trip', () => {
    const filters = {
      search: 'RES-2026',
      lieu: 'Jambville',
      statuts: ['validee', 'livree'],
      dateRange: ['2026-06-01', '2026-06-30'] as [string, string],
      page: 3,
      viewMode: 'hierarchique' as const
    };

    const query = serializeRamassageFilters(filters);

    expect(query).toContain('ram_q=RES-2026');
    expect(query).toContain('ram_lieu=Jambville');
    expect(query).toContain('ram_statut=validee%2Clivree');
    expect(query).toContain('ram_page=3');

    expect(parseRamassageFilters(`?${query}`)).toEqual(filters);
  });

  it('les clés sont préfixées pour ne pas écraser celles des autres widgets', () => {
    const query = serializeRamassageFilters({
      ...DEFAULT_RAMASSAGE_FILTERS,
      statuts: ['validee']
    });

    expect(query).toBe('ram_statut=validee');
  });

  it('build query always carries the pagination', () => {
    expect(buildRamassageQuery(DEFAULT_RAMASSAGE_FILTERS)).toEqual({
      page: '1',
      page_size: String(RAMASSAGE_PAGE_SIZE)
    });

    expect(
      buildRamassageQuery({
        search: '  camp  ',
        lieu: '',
        statuts: ['soumise'],
        dateRange: [null, '2026-08-01'],
        page: 2,
        viewMode: 'hierarchique'
      })
    ).toEqual({
      page: '2',
      page_size: String(RAMASSAGE_PAGE_SIZE),
      search: 'camp',
      statut: ['soumise'],
      date_to: '2026-08-01'
    });
  });

  it('parse tolerates invalid values', () => {
    const parsed = parseRamassageFilters(
      '?ram_statut=&ram_from=&ram_to=2026-08-01&ram_page=0'
    );

    expect(parsed.statuts).toEqual([]);
    expect(parsed.dateRange).toEqual([null, '2026-08-01']);
    expect(parsed.page).toBe(1);
  });

  it('totalRamassagePages ne descend jamais sous une page', () => {
    expect(totalRamassagePages(0)).toBe(1);
    expect(totalRamassagePages(RAMASSAGE_PAGE_SIZE)).toBe(1);
    expect(totalRamassagePages(RAMASSAGE_PAGE_SIZE + 1)).toBe(2);
  });
});
