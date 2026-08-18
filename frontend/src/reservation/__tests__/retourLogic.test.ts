import { describe, expect, it } from 'vitest';

import {
  computeStatutRetour,
  isRetourValid,
  validateRetourLignes
} from '../retourLogic';

function makeLigne(overrides: Partial<Parameters<typeof computeStatutRetour>[0][number]> = {}) {
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

describe('isRetourValid', () => {
  it('is true when all lines are within bounds', () => {
    expect(
      isRetourValid([
        makeLigne({ id: 1, quantite_demandee: 5, quantite_rendue: 5 }),
        makeLigne({ id: 2, quantite_demandee: 3, quantite_rendue: 0 })
      ])
    ).toBe(true);
  });

  it('is false when at least one line is out of bounds', () => {
    expect(
      isRetourValid([makeLigne({ id: 1, quantite_demandee: 5, quantite_rendue: 9 })])
    ).toBe(false);
  });
});
