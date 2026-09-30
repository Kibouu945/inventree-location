import { describe, expect, it } from 'vitest';

import {
  buildParcQuery,
  DEFAULT_PARC_FILTERS,
  libelleMotif,
  type ParcFiltersState,
  parseParcFilters,
  serializeParcFilters,
  totalParcPages
} from '../parcParams';

const filtres = (patch: Partial<ParcFiltersState> = {}): ParcFiltersState => ({
  ...DEFAULT_PARC_FILTERS,
  ...patch
});

describe('la requête envoyée au serveur', () => {
  it('porte toujours la page et sa taille', () => {
    expect(buildParcQuery(filtres())).toEqual({ page: '1', page_size: '25' });
  });

  it('ignore une recherche qui n’est que des espaces', () => {
    expect(buildParcQuery(filtres({ search: '   ' }))).not.toHaveProperty(
      'search'
    );
  });

  it('joint les catégories par des virgules', () => {
    expect(buildParcQuery(filtres({ categories: ['3', '7'] })).categories).toBe(
      '3,7'
    );
  });

  it('ne demande les alertes que si on les a demandées', () => {
    expect(buildParcQuery(filtres())).not.toHaveProperty('alerte');
    expect(buildParcQuery(filtres({ alerteSeule: true })).alerte).toBe('1');
  });
});

describe('l’état d’URL', () => {
  it('n’écrit rien quand rien n’est filtré', () => {
    expect(serializeParcFilters(filtres())).toBe('');
  });

  it('fait l’aller-retour sans rien perdre', () => {
    const avant = filtres({
      search: 'banc',
      categories: ['3', '7'],
      alerteSeule: true,
      page: 4
    });

    expect(parseParcFilters(serializeParcFilters(avant))).toEqual(avant);
  });

  it('ne garde pas deux fois la même catégorie', () => {
    expect(parseParcFilters('parc_cat=3,3,7').categories).toEqual(['3', '7']);
  });

  it('retombe sur la première page devant une valeur absurde', () => {
    expect(parseParcFilters('parc_page=0').page).toBe(1);
    expect(parseParcFilters('parc_page=-2').page).toBe(1);
    expect(parseParcFilters('parc_page=abc').page).toBe(1);
  });

  it('ignore les clés des autres widgets', () => {
    /* La query string est partagée : lire celle du voisin fausserait le filtre. */
    expect(parseParcFilters('ram_q=camp&hist_part=2')).toEqual(
      DEFAULT_PARC_FILTERS
    );
  });
});

describe('la pagination', () => {
  it('garde une page même sans résultat', () => {
    expect(totalParcPages(0)).toBe(1);
  });

  it('compte la page entamée', () => {
    expect(totalParcPages(25)).toBe(1);
    expect(totalParcPages(26)).toBe(2);
  });
});

describe('les motifs d’alerte', () => {
  it('se disent en clair', () => {
    expect(libelleMotif('sous_seuil')).toBe('Sous le seuil d’alerte');
    expect(libelleMotif('sorti_au_dela_du_parc')).toBe('Sorti au-delà du parc');
  });

  it('laisse passer un motif inconnu plutôt que de l’avaler', () => {
    expect(libelleMotif('motif_futur')).toBe('motif_futur');
  });
});
