import { describe, expect, it } from 'vitest';

import { type EtatTri, trier } from '../TriColonne';

type Colonne = 'nom' | 'nombre' | 'date';

interface Ligne {
  nom: string | null;
  nombre: number | null;
  date: Date | null;
}

const ligne = (over: Partial<Ligne> = {}): Ligne => ({
  nom: 'a',
  nombre: 0,
  date: null,
  ...over
});

const valeurPour = (l: Ligne, c: Colonne) => l[c];
const tri = (colonne: Colonne | null, sens: 'asc' | 'desc' = 'asc') =>
  ({ colonne, sens }) as EtatTri<Colonne>;

describe('trier', () => {
  it('laisse la liste intacte sans colonne active', () => {
    const lignes = [ligne({ nom: 'b' }), ligne({ nom: 'a' })];

    expect(trier(lignes, tri(null), valeurPour)).toBe(lignes);
  });

  it('ne modifie pas la liste reçue', () => {
    const lignes = [ligne({ nom: 'b' }), ligne({ nom: 'a' })];
    trier(lignes, tri('nom'), valeurPour);

    expect(lignes[0].nom).toBe('b');
  });

  it('trie le texte en ordre croissant', () => {
    const lignes = [ligne({ nom: 'Zoé' }), ligne({ nom: 'Alice' })];

    expect(trier(lignes, tri('nom'), valeurPour).map((l) => l.nom)).toEqual([
      'Alice',
      'Zoé'
    ]);
  });

  it('inverse en ordre décroissant', () => {
    const lignes = [ligne({ nom: 'Alice' }), ligne({ nom: 'Zoé' })];

    expect(
      trier(lignes, tri('nom', 'desc'), valeurPour).map((l) => l.nom)
    ).toEqual(['Zoé', 'Alice']);
  });

  it('ignore les accents et la casse', () => {
    const lignes = [ligne({ nom: 'Zoé' }), ligne({ nom: 'École' })];

    expect(trier(lignes, tri('nom'), valeurPour).map((l) => l.nom)).toEqual([
      'École',
      'Zoé'
    ]);
  });

  it('compare les nombres comme des nombres', () => {
    const lignes = [
      ligne({ nombre: 10 }),
      ligne({ nombre: 9 }),
      ligne({ nombre: 100 })
    ];

    expect(
      trier(lignes, tri('nombre'), valeurPour).map((l) => l.nombre)
    ).toEqual([9, 10, 100]);
  });

  it('compare les dates chronologiquement', () => {
    const lignes = [
      ligne({ date: new Date('2026-12-01') }),
      ligne({ date: new Date('2026-01-15') })
    ];

    expect(
      trier(lignes, tri('date'), valeurPour).map((l) => l.date?.getMonth())
    ).toEqual([0, 11]);
  });

  it('renvoie les valeurs absentes en bas, même en décroissant', () => {
    const lignes = [
      ligne({ nom: null }),
      ligne({ nom: 'Alice' }),
      ligne({ nom: 'Zoé' })
    ];

    expect(
      trier(lignes, tri('nom', 'desc'), valeurPour).map((l) => l.nom)
    ).toEqual(['Zoé', 'Alice', null]);
  });
});
