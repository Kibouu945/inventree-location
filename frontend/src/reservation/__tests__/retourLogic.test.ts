import { describe, expect, it } from 'vitest';

import {
  computeStatutRetour,
  normalizeRetourErrors,
  validateRetourLignes
} from '../retourLogic';

function makeLigne(
  overrides: Partial<Parameters<typeof computeStatutRetour>[0][number]> = {}
) {
  return {
    id: 1,
    quantite_demandee: 5,
    quantite_rendue: 0,
    ...overrides
  };
}

describe('computeStatutRetour', () => {
  it('is "aucun" when nothing has been returned', () => {
    expect(computeStatutRetour([makeLigne({ quantite_rendue: 0 })])).toBe(
      'aucun'
    );
  });

  it('is "partiel" when some but not all quantity has been returned', () => {
    expect(
      computeStatutRetour([
        makeLigne({ id: 1, quantite_demandee: 5, quantite_rendue: 2 }),
        makeLigne({ id: 2, quantite_demandee: 10, quantite_rendue: 0 })
      ])
    ).toBe('partiel');
  });

  it('is "complet" when every line matches its requested quantity', () => {
    expect(
      computeStatutRetour([
        makeLigne({ id: 1, quantite_demandee: 5, quantite_rendue: 5 }),
        makeLigne({ id: 2, quantite_demandee: 10, quantite_rendue: 10 })
      ])
    ).toBe('complet');
  });

  it('ignores an empty set of lines', () => {
    expect(computeStatutRetour([])).toBe('aucun');
  });
});

describe('validateRetourLignes', () => {
  it('returns no error for valid quantities', () => {
    expect(
      validateRetourLignes([
        makeLigne({ id: 1, quantite_demandee: 5, quantite_rendue: 3 })
      ])
    ).toEqual({});
  });

  it('flags a negative quantity', () => {
    const errors = validateRetourLignes([
      makeLigne({ id: 1, quantite_rendue: -1 })
    ]);
    expect(errors[1]).toBeDefined();
  });

  it('flags a quantity exceeding the requested amount', () => {
    const errors = validateRetourLignes([
      makeLigne({ id: 2, quantite_demandee: 5, quantite_rendue: 6 })
    ]);
    expect(errors[2]).toBeDefined();
  });
});

describe('normalizeRetourErrors', () => {
  const envoyees = [
    makeLigne({ id: 7, quantite_demandee: 5, quantite_rendue: 5 }),
    makeLigne({ id: 9, quantite_demandee: 3, quantite_rendue: 1 })
  ];

  it('keys the server object form by line id', () => {
    const errors = normalizeRetourErrors(
      { lignes: { '9': 'Quantité trop grande.' } },
      envoyees
    );
    expect(errors[9]).toBe('Quantité trop grande.');
  });

  it('maps the DRF list form back onto the submitted line ids', () => {
    // DRF aligne la liste sur l'ordre envoyé : le 2e objet vise la ligne 9.
    const errors = normalizeRetourErrors(
      { lignes: [{}, { quantite_rendue: ['Nombre entier valide requis.'] }] },
      envoyees
    );
    expect(errors[7]).toBeUndefined();
    expect(errors[9]).toBe('Nombre entier valide requis.');
  });

  it('flattens several messages for the same line into one string', () => {
    const errors = normalizeRetourErrors(
      { lignes: [{ quantite_rendue: ['Trop grand.', 'Non entier.'] }] },
      envoyees
    );
    expect(errors[7]).toBe('Trop grand. Non entier.');
  });

  it('returns nothing for a payload without usable lines', () => {
    expect(normalizeRetourErrors(null, envoyees)).toEqual({});
    expect(normalizeRetourErrors({ detail: 'Conflit.' }, envoyees)).toEqual({});
  });
});
