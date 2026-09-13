import { describe, expect, it } from 'vitest';

import {
  type ContactAffichable,
  nomComplet,
  optionsDeContacts
} from '../contactLogic';

function contact(
  overrides: Partial<ContactAffichable> = {}
): ContactAffichable {
  return { id: 1, nom: 'Durand', prenom: 'Paule', actif: true, ...overrides };
}

describe('nomComplet', () => {
  it('assemble le prénom et le nom', () => {
    expect(nomComplet(contact())).toBe('Paule Durand');
  });

  it('ne laisse pas d’espace quand le prénom manque', () => {
    // `prenom` est `blank=True` côté modèle : l'absence est un cas normal.
    expect(nomComplet(contact({ prenom: '' }))).toBe('Durand');
  });
});

describe('optionsDeContacts', () => {
  it('ne propose que les contacts actifs', () => {
    const options = optionsDeContacts([
      contact({ id: 1, nom: 'Durand' }),
      contact({ id: 2, nom: 'Martin', actif: false })
    ]);

    expect(options).toEqual([{ value: '1', label: 'Paule Durand' }]);
  });

  it('garde le contact déjà sélectionné, même désactivé', () => {
    // Sinon, ouvrir une manifestation dont le contact a été désactivé viderait
    // le champ, et l'enregistrement effacerait son interlocuteur.
    const options = optionsDeContacts(
      [
        contact({ id: 1, nom: 'Durand' }),
        contact({ id: 2, nom: 'Martin', actif: false })
      ],
      '2'
    );

    expect(options).toEqual([
      { value: '1', label: 'Paule Durand' },
      { value: '2', label: 'Paule Martin (inactif)' }
    ]);
  });

  it('dit pourquoi ce contact-là est encore proposé', () => {
    const [option] = optionsDeContacts([contact({ actif: false })], '1');

    expect(option.label).toContain('(inactif)');
  });

  it('rend une liste vide plutôt que de planter sans contact', () => {
    expect(optionsDeContacts([])).toEqual([]);
  });
});
