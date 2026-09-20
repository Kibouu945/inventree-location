import { describe, expect, it } from 'vitest';

import {
  deduireManquant,
  quantiteAttendue
} from '../RamassagesHierarchicalTable';
import type { LigneBonRamassage } from '../types';

describe('regles R31, R32, R33 du ramassage F7', () => {
  it('R31 et R32 : le manquant se deduit uniquement si le lieu est complet', () => {
    const attendu = 10;
    const ramassee = 6;
    const sav = 1;
    const detruite = 1;

    expect(deduireManquant(attendu, ramassee, sav, detruite, false)).toBe(0);
    expect(deduireManquant(attendu, ramassee, sav, detruite, true)).toBe(2);
  });

  it('R32 : rien n est declare perdu tant que le lieu n est pas termine', () => {
    expect(deduireManquant(10, 0, 0, 0, false)).toBe(0);
    expect(deduireManquant(10, 4, 0, 0, false)).toBe(0);
  });

  it('R33 : aucun plafond au ramassage (surplus legitime)', () => {
    const attendu = 10;
    const ramassee = 12;
    const sav = 1;
    const detruite = 0;

    expect(deduireManquant(attendu, ramassee, sav, detruite, true)).toBe(0);
  });

  it('quantite attendue priorise a_ramasser puis livree puis demandee', () => {
    const ligne1: LigneBonRamassage = {
      id: 1,
      part: 10,
      part_nom: 'Tente',
      quantite_demandee: 8,
      quantite_livree: 6,
      quantite_a_ramasser: 6,
      quantite_retournee: 0,
      quantite_ramassee: 0,
      quantite_sav: 0,
      quantite_detruite: 0,
      quantite_manquante: 0,
      facturer_client: false,
      etat_retour: '',
      commentaire: ''
    };

    expect(quantiteAttendue(ligne1)).toBe(6);
  });
});
