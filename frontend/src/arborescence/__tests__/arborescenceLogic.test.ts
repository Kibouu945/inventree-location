import { describe, expect, it } from 'vitest';

import { clientsDuReperage, filtresManifestations } from '../arborescenceLogic';

describe('filtresManifestations', () => {
  it('ne filtre rien quand on ne demande rien', () => {
    // « Tout » et une recherche vide valent l'absence de paramètre : envoyer
    // `search=` ferait chercher la chaîne vide côté serveur.
    expect(filtresManifestations('', 'tout')).toEqual({});
  });

  it('porte la recherche, débarrassée de ses espaces', () => {
    expect(filtresManifestations('  Gala  ', 'tout')).toEqual({
      search: 'Gala'
    });
  });

  it('ignore une recherche qui n’est que des espaces', () => {
    expect(filtresManifestations('   ', 'tout')).toEqual({});
  });

  it('porte la période quand elle en est une', () => {
    expect(filtresManifestations('', 'futur')).toEqual({ periode: 'futur' });
    expect(filtresManifestations('', 'passe')).toEqual({ periode: 'passe' });
  });

  it('restreint à un client quand on le nomme', () => {
    expect(filtresManifestations('', 'tout', 7)).toEqual({ client: '7' });
  });

  it('donne au dépliage les filtres du repérage, plus son client', () => {
    // La garantie qui compte : un client remonté par la recherche doit
    // retrouver au moins une manifestation en s'ouvrant. Si les deux appels
    // filtraient différemment, il s'ouvrirait sur du vide.
    const reperage = filtresManifestations('Gala', 'futur');
    const depliage = filtresManifestations('Gala', 'futur', 3);

    expect(depliage).toEqual({ ...reperage, client: '3' });
  });
});

describe('clientsDuReperage', () => {
  it('ne rend rien quand la recherche ne trouve rien', () => {
    expect(clientsDuReperage([])).toEqual(new Set());
  });

  it('remonte le client de chaque manifestation trouvée', () => {
    expect(clientsDuReperage([{ client: 4 }, { client: 9 }])).toEqual(
      new Set([4, 9])
    );
  });

  it('ne compte qu’une fois un client qui en porte plusieurs', () => {
    expect(clientsDuReperage([{ client: 4 }, { client: 4 }])).toEqual(
      new Set([4])
    );
  });
});
