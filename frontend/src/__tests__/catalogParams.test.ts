import { describe, expect, it } from 'vitest';

import {
  buildCatalogQuery,
  CATALOG_PAGE_SIZE,
  DEFAULT_FILTERS,
  parseFilters,
  serializeFilters,
  totalPages
} from '../catalog/catalogParams';

describe('buildCatalogQuery', () => {
  it('inclut toujours page et page_size', () => {
    const params = buildCatalogQuery(DEFAULT_FILTERS);
    expect(params.page).toBe('1');
    expect(params.page_size).toBe(String(CATALOG_PAGE_SIZE));
  });

  it("n'envoie pas rentable quand louable (défaut)", () => {
    const params = buildCatalogQuery(DEFAULT_FILTERS);
    expect(params.rentable).toBeUndefined();
  });

  it('envoie rentable=all et rentable=false', () => {
    expect(
      buildCatalogQuery({ ...DEFAULT_FILTERS, rentable: 'all' }).rentable
    ).toBe('all');
    expect(
      buildCatalogQuery({ ...DEFAULT_FILTERS, rentable: false }).rentable
    ).toBe('false');
  });

  it('sérialise les catégories en liste séparée par des virgules', () => {
    const params = buildCatalogQuery({
      ...DEFAULT_FILTERS,
      categories: [3, 7]
    });
    expect(params.categories).toBe('3,7');
  });

  it('trim la recherche et omet les valeurs vides', () => {
    expect(buildCatalogQuery({ ...DEFAULT_FILTERS, search: '  ' }).search).toBe(
      undefined
    );
    expect(
      buildCatalogQuery({ ...DEFAULT_FILTERS, search: '  tente ' }).search
    ).toBe('tente');
  });
});

describe('serializeFilters / parseFilters (URL state)', () => {
  it('round-trip conserve les filtres non-défaut', () => {
    const filters = {
      search: 'tente',
      categories: [3, 7],
      rentable: 'all' as const,
      page: 2
    };
    const restored = parseFilters(serializeFilters(filters));
    expect(restored).toEqual(filters);
  });

  it('une query string vide donne les filtres par défaut', () => {
    expect(parseFilters('')).toEqual(DEFAULT_FILTERS);
  });

  it('ignore une page invalide', () => {
    expect(parseFilters('page=0').page).toBe(1);
    expect(parseFilters('page=abc').page).toBe(1);
  });

  it('parse rentable=false', () => {
    expect(parseFilters('rentable=false').rentable).toBe(false);
  });
});

describe('totalPages', () => {
  it('au moins une page même sans résultat', () => {
    expect(totalPages(0)).toBe(1);
  });

  it('arrondit au supérieur', () => {
    expect(totalPages(CATALOG_PAGE_SIZE + 1)).toBe(2);
    expect(totalPages(CATALOG_PAGE_SIZE)).toBe(1);
  });
});
