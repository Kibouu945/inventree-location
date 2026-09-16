import { describe, expect, it } from 'vitest';

import { type ClientAffichable, optionsDeClients } from '../clientLogic';

function client(overrides: Partial<ClientAffichable> = {}): ClientAffichable {
  return { id: 1, nom: 'Jambville', actif: true, ...overrides };
}

describe('optionsDeClients', () => {
  it('ne propose que les clients actifs', () => {
    const options = optionsDeClients([
      client({ id: 1, nom: 'Jambville' }),
      client({ id: 2, nom: 'Autre maison', actif: false })
    ]);

    expect(options).toEqual([{ value: '1', label: 'Jambville' }]);
  });

  it('garde le client déjà sélectionné, même désactivé', () => {
    // Sinon, ouvrir une manifestation dont le client a été désactivé viderait
    // le champ, et l'enregistrement effacerait son client.
    const options = optionsDeClients(
      [
        client({ id: 1, nom: 'Jambville' }),
        client({ id: 2, nom: 'Autre maison', actif: false })
      ],
      '2'
    );

    expect(options).toEqual([
      { value: '1', label: 'Jambville' },
      { value: '2', label: 'Autre maison (inactif)' }
    ]);
  });

  it('dit pourquoi ce client-là est encore proposé', () => {
    const [option] = optionsDeClients([client({ actif: false })], '1');

    expect(option.label).toContain('(inactif)');
  });

  it('rend une liste vide plutôt que de planter sans client', () => {
    expect(optionsDeClients([])).toEqual([]);
  });
});
