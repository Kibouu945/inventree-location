import { describe, expect, it } from 'vitest';

import { type Desactivable, optionsActives } from '../optionsActives';

interface Client extends Desactivable {
  nom: string;
}

function client(overrides: Partial<Client> = {}): Client {
  return { id: 1, nom: 'École des beaux-arts', actif: true, ...overrides };
}

const nom = (c: Client) => c.nom;

describe('optionsActives', () => {
  it('propose ce qui est en service', () => {
    expect(optionsActives([client()], nom)).toEqual([
      { value: '1', label: 'École des beaux-arts' }
    ]);
  });

  it('écarte ce qui est désactivé', () => {
    expect(optionsActives([client({ actif: false })], nom)).toEqual([]);
  });

  it('garde le désactivé quand c’est lui qui est déjà choisi', () => {
    // Sans cette exception, rouvrir une manifestation dont le client a été
    // désactivé viderait le champ, et l'enregistrement effacerait le lien.
    expect(optionsActives([client({ actif: false })], nom, '1')).toEqual([
      { value: '1', label: 'École des beaux-arts (inactif)' }
    ]);
  });

  it('rend une liste vide plutôt que de planter sans élément', () => {
    expect(optionsActives([], nom)).toEqual([]);
  });

  it('ne garde pas un autre désactivé que celui choisi', () => {
    const elements = [
      client({ id: 1, actif: false }),
      client({ id: 2, nom: 'Mairie d’Évreux', actif: false })
    ];

    expect(optionsActives(elements, nom, '1').map((o) => o.value)).toEqual([
      '1'
    ]);
  });
});
