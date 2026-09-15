import { describe, expect, it } from 'vitest';

import { apiErrorMessage } from '../backoffice/apiError';

const FALLBACK = 'Impossible d’enregistrer.';

describe('apiErrorMessage', () => {
  it('aplatit les erreurs de champ DRF', () => {
    const error = {
      response: {
        data: { password: ['Ce mot de passe est trop courant.'] }
      }
    };

    expect(apiErrorMessage(error, FALLBACK)).toBe(
      'Ce mot de passe est trop courant.'
    );
  });

  it('concatène plusieurs messages', () => {
    const error = {
      response: {
        data: {
          lignes: ['Objet non actif.', 'Objet non louable.'],
          detail: 'Requête invalide.'
        }
      }
    };

    expect(apiErrorMessage(error, FALLBACK)).toBe(
      'Objet non actif. Objet non louable. Requête invalide.'
    );
  });

  it('accepte une réponse texte', () => {
    expect(apiErrorMessage({ response: { data: 'Boum' } }, FALLBACK)).toBe(
      'Boum'
    );
  });

  it('retombe sur le message par défaut sans réponse exploitable', () => {
    expect(apiErrorMessage(new Error('réseau'), FALLBACK)).toBe(FALLBACK);
    expect(apiErrorMessage({ response: { data: {} } }, FALLBACK)).toBe(
      FALLBACK
    );
    expect(apiErrorMessage(undefined, FALLBACK)).toBe(FALLBACK);
  });
});
