import { describe, expect, it } from 'vitest';

import type { Delivery } from '../types';

export function computeAvancement(
  fait: number,
  attendu: number
): 'rien' | 'partiel' | 'complet' {
  if (attendu <= 0 || fait <= 0) {
    return 'rien';
  }
  return fait >= attendu ? 'complet' : 'partiel';
}

export function agregerAvancement(
  etats: ('rien' | 'partiel' | 'complet')[]
): 'rien' | 'partiel' | 'complet' {
  if (etats.length === 0 || etats.every((e) => e === 'rien')) {
    return 'rien';
  }
  return etats.every((e) => e === 'complet') ? 'complet' : 'partiel';
}

function makeDelivery(
  id: number,
  quantiteDemandee: number,
  quantiteLivree: number
): Delivery {
  return {
    id,
    numero: `RES-${id}`,
    statut: quantiteLivree >= quantiteDemandee ? 'livree' : 'validee',
    prestation_nom: 'Prestation Test',
    manifestation_nom: 'Manifestation Test',
    client_nom: 'Client Test',
    demandeur_nom: 'Demandeur Test',
    lieu_detail: {
      id: 10,
      nom: 'Lieu Test',
      adresse: '123 rue Test',
      latitude: '48.85',
      longitude: '2.35'
    },
    organisateur_nom: 'Org Test',
    organisateur_telephone: '0102030405',
    date_retrait_prevue: '2026-09-15T10:00:00Z',
    date_retour_prevue: '2026-09-17T18:00:00Z',
    commentaire: '',
    lignes: [
      {
        id: 100 + id,
        part: 50 + id,
        part_name: 'Tente 6P',
        quantite_demandee: quantiteDemandee,
        quantite_livree: quantiteLivree,
        is_virtual: false
      }
    ],
    quantite_totale: quantiteDemandee,
    livreur_assigne: null,
    livreur_assigne_nom: '',
    date_assignation: null,
    etat_livraison: '',
    etat_livraison_display: '',
    livraison_status_logs: []
  };
}

describe('avancement de livraison F6', () => {
  it('calcule l avancement unitaire', () => {
    expect(computeAvancement(0, 10)).toBe('rien');
    expect(computeAvancement(5, 10)).toBe('partiel');
    expect(computeAvancement(10, 10)).toBe('complet');
    expect(computeAvancement(12, 10)).toBe('complet');
  });

  it('agrege l avancement hierarchique', () => {
    expect(agregerAvancement(['rien', 'rien'])).toBe('rien');
    expect(agregerAvancement(['rien', 'complet'])).toBe('partiel');
    expect(agregerAvancement(['partiel', 'complet'])).toBe('partiel');
    expect(agregerAvancement(['complet', 'complet'])).toBe('complet');
  });

  it('gere la structure d une livraison a 4 niveaux', () => {
    const d1 = makeDelivery(1, 10, 0);
    const d2 = makeDelivery(2, 5, 5);

    expect(d1.manifestation_nom).toBe('Manifestation Test');
    expect(d1.prestation_nom).toBe('Prestation Test');
    expect(d1.lignes[0].quantite_demandee).toBe(10);
    expect(d2.statut).toBe('livree');
  });
});
