import { describe, expect, it } from 'vitest';

import {
  ajouterJours,
  aujourdhui,
  borneDePeriode,
  filtrerJoursVisibles,
  type HistogramDay,
  hauteurBarrePourcent,
  jourIso
} from '../histogramLogic';

function jour(overrides: Partial<HistogramDay> = {}): HistogramDay {
  return {
    date: '2026-09-14',
    total_stock: 10,
    reserved: 0,
    available: 10,
    occupation_rate: 0,
    tension_level: 'green',
    ...overrides
  };
}

describe('ajouterJours', () => {
  it('avance de plusieurs jours en UTC, sans dérive de fuseau', () => {
    expect(ajouterJours('2026-09-14', 3)).toBe('2026-09-17');
  });

  it('traverse le changement d’heure d’octobre 2026 sans sauter de jour', () => {
    expect(ajouterJours('2026-10-24', 1)).toBe('2026-10-25');
    expect(ajouterJours('2026-10-25', 1)).toBe('2026-10-26');
  });
});

describe('aujourdhui', () => {
  it('formate la date locale en AAAA-MM-JJ', () => {
    expect(aujourdhui(new Date(2026, 8, 5))).toBe('2026-09-05');
  });

  it('complète les mois et jours à un chiffre', () => {
    expect(aujourdhui(new Date(2026, 0, 2))).toBe('2026-01-02');
  });
});

describe('borneDePeriode', () => {
  it('couvre sept jours pour le préréglage semaine', () => {
    expect(borneDePeriode('2026-09-14', 'semaine')).toBe('2026-09-20');
  });

  it('couvre le mois calendaire complet pour le préréglage mois', () => {
    expect(borneDePeriode('2026-09-01', 'mois')).toBe('2026-09-30');
  });

  it('gère un mois de 31 jours démarrant en cours de mois', () => {
    expect(borneDePeriode('2026-07-15', 'mois')).toBe('2026-07-31');
  });

  it('gère février en année non bissextile', () => {
    expect(borneDePeriode('2027-02-01', 'mois')).toBe('2027-02-28');
  });
});

describe('jourIso', () => {
  it('rend 1 pour un lundi', () => {
    expect(jourIso('2026-09-14')).toBe(1);
  });

  it('rend 7 pour un dimanche, pas 0', () => {
    expect(jourIso('2026-09-20')).toBe(7);
  });

  it('rend 5 pour un vendredi', () => {
    expect(jourIso('2026-09-18')).toBe(5);
  });
});

describe('filtrerJoursVisibles', () => {
  const semaine: HistogramDay[] = [
    jour({ date: '2026-09-14' }),
    jour({ date: '2026-09-18' }),
    jour({ date: '2026-09-19' }),
    jour({ date: '2026-09-20' })
  ];

  it('ne garde que les jours de semaine ISO demandés', () => {
    const resultat = filtrerJoursVisibles(semaine, [5, 6, 7]);
    expect(resultat.map((j) => j.date)).toEqual([
      '2026-09-18',
      '2026-09-19',
      '2026-09-20'
    ]);
  });

  it('renvoie tout quand le filtre est vide', () => {
    expect(filtrerJoursVisibles(semaine, [])).toHaveLength(4);
  });

  it('renvoie tout quand le filtre est absent', () => {
    expect(filtrerJoursVisibles(semaine, null)).toHaveLength(4);
  });
});

describe('hauteurBarrePourcent', () => {
  it('rend 100 quand tout le stock est disponible', () => {
    expect(hauteurBarrePourcent(jour({ available: 10, total_stock: 10 }))).toBe(
      100
    );
  });

  it('rend 0 quand rien n’est disponible', () => {
    expect(hauteurBarrePourcent(jour({ available: 0, total_stock: 10 }))).toBe(
      0
    );
  });

  it('rend un pourcentage proportionnel', () => {
    expect(hauteurBarrePourcent(jour({ available: 3, total_stock: 10 }))).toBe(
      30
    );
  });

  it('reste borné à 0 même si le disponible est négatif (sur-réservation)', () => {
    expect(hauteurBarrePourcent(jour({ available: -2, total_stock: 10 }))).toBe(
      0
    );
  });

  it('rend 0 pour un stock total nul plutôt qu’une division infinie', () => {
    expect(hauteurBarrePourcent(jour({ available: 0, total_stock: 0 }))).toBe(
      0
    );
  });
});
