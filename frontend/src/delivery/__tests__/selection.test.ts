import { describe, expect, it } from 'vitest';

import { messageBonPartiel, trierLaSelection } from '../selection';
import type { Delivery, DeliveryLigne } from '../types';

function ligne(id: number): DeliveryLigne {
  return {
    id,
    part: id,
    part_name: `Article ${id}`,
    quantite_demandee: 2,
    is_virtual: false
  };
}

function bon(id: number, lignes: number[], statut = 'validee'): Delivery {
  return {
    id,
    numero: `RES-2026-000${id}`,
    statut,
    lignes: lignes.map(ligne)
  } as unknown as Delivery;
}

describe('trierLaSelection', () => {
  it('envoie un bon coché en entier', () => {
    const cochees = new Set([1, 2]);
    const selection = trierLaSelection([bon(1, [1, 2])], (l) =>
      cochees.has(l.id)
    );

    expect(selection).toEqual({ complets: [1], partiels: [] });
  });

  it('garde de côté un bon coché en partie, et le nomme', () => {
    const cochees = new Set([1, 2, 3]);
    const selection = trierLaSelection([bon(3, [1, 2, 3, 4, 5])], (l) =>
      cochees.has(l.id)
    );

    expect(selection.complets).toEqual([]);
    expect(selection.partiels).toEqual([
      { numero: 'RES-2026-0003', coches: 3, total: 5 }
    ]);
  });

  it("ignore un bon dont rien n'est coché, et un bon déjà livré", () => {
    const cochees = new Set([3]);
    const selection = trierLaSelection(
      [bon(1, [1, 2]), bon(2, [3], 'livree')],
      (l) => cochees.has(l.id)
    );

    expect(selection).toEqual({ complets: [], partiels: [] });
  });
});

describe('messageBonPartiel', () => {
  it('dit ce qui est coché et quoi faire', () => {
    expect(
      messageBonPartiel({ numero: 'RES-2026-0003', coches: 3, total: 5 })
    ).toBe(
      "RES-2026-0003 : 3 articles sur 5 cochés. Un bon se livre en entier : cochez tous ses articles pour l'envoyer."
    );
  });

  it('accorde au singulier', () => {
    expect(
      messageBonPartiel({ numero: 'RES-2026-0001', coches: 1, total: 4 })
    ).toMatch(/^RES-2026-0001 : 1 article sur 4 coché\./);
  });
});
