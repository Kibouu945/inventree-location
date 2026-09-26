import { describe, expect, it } from 'vitest';

import {
  ajouterJours,
  aujourdhui,
  borneDePeriode,
  capitaliser,
  classeDeTension,
  estWeekEnd,
  etiquetteColonne,
  filtrerJoursVisibles,
  graduations,
  type HistogramDay,
  hauteurRemplissagePourcent,
  jourIso,
  jourLePlusTendu,
  libelleJourLong,
  libelleJournees,
  resumeTension
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

  it('gère février en année bissextile', () => {
    expect(borneDePeriode('2028-02-01', 'mois')).toBe('2028-02-29');
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

describe('classeDeTension', () => {
  it('range les cinq niveaux du serveur en trois classes affichables', () => {
    expect(classeDeTension('green')).toBe('disponible');
    expect(classeDeTension('blue')).toBe('disponible');
    expect(classeDeTension('yellow')).toBe('tendu');
    expect(classeDeTension('orange')).toBe('tendu');
    expect(classeDeTension('red')).toBe('complet');
  });
});

describe('hauteurRemplissagePourcent', () => {
  it('remplit la colonne à hauteur de ce qui est engagé', () => {
    expect(
      hauteurRemplissagePourcent(jour({ reserved: 3, total_stock: 10 }))
    ).toBe(30);
  });

  it('rend une colonne pleine quand tout est engagé — le cas qu’on cherche', () => {
    expect(
      hauteurRemplissagePourcent(jour({ reserved: 10, total_stock: 10 }))
    ).toBe(100);
  });

  it('laisse la colonne vide quand rien n’est engagé', () => {
    expect(
      hauteurRemplissagePourcent(jour({ reserved: 0, total_stock: 10 }))
    ).toBe(0);
  });

  it('plafonne la sur-réservation à 100, sans déborder de la piste', () => {
    expect(
      hauteurRemplissagePourcent(jour({ reserved: 14, total_stock: 10 }))
    ).toBe(100);
  });

  it('rend une colonne pleine pour un stock nul déjà engagé', () => {
    expect(
      hauteurRemplissagePourcent(jour({ reserved: 2, total_stock: 0 }))
    ).toBe(100);
  });

  it('rend 0 pour un stock nul et rien d’engagé, sans division infinie', () => {
    expect(
      hauteurRemplissagePourcent(jour({ reserved: 0, total_stock: 0 }))
    ).toBe(0);
  });
});

describe('estWeekEnd', () => {
  it('reconnaît samedi et dimanche', () => {
    expect(estWeekEnd('2026-09-19')).toBe(true);
    expect(estWeekEnd('2026-09-20')).toBe(true);
  });

  it('laisse le lundi en semaine', () => {
    expect(estWeekEnd('2026-09-14')).toBe(false);
  });
});

describe('etiquetteColonne', () => {
  it('rend le quantième et le jour abrégé, sans dérive de fuseau', () => {
    expect(etiquetteColonne('2026-09-20')).toEqual({
      numero: '20',
      semaine: 'dim.'
    });
  });
});

describe('capitaliser', () => {
  it('ne relève que la première lettre, le mois reste en bas de casse', () => {
    expect(capitaliser('dimanche 20 septembre 2026')).toBe(
      'Dimanche 20 septembre 2026'
    );
  });

  it('supporte la chaîne vide', () => {
    expect(capitaliser('')).toBe('');
  });
});

describe('libelleJourLong', () => {
  it('écrit la date en toutes lettres', () => {
    expect(libelleJourLong('2026-09-20')).toBe('dimanche 20 septembre 2026');
  });
});

describe('graduations', () => {
  it('donne zéro, la moitié et le total quand la moitié tombe juste', () => {
    expect(graduations(80)).toEqual([0, 40, 80]);
  });

  it('s’en tient à zéro et au total quand la moitié serait décimale', () => {
    expect(graduations(15)).toEqual([0, 15]);
  });

  it('rend la seule graduation zéro pour un stock nul', () => {
    expect(graduations(0)).toEqual([0]);
  });
});

describe('resumeTension', () => {
  it('compte les journées par classe', () => {
    const periode = [
      jour({ date: '2026-09-18', tension_level: 'green' }),
      jour({ date: '2026-09-19', tension_level: 'yellow' }),
      jour({ date: '2026-09-20', tension_level: 'red' }),
      jour({ date: '2026-09-21', tension_level: 'orange' })
    ];

    expect(resumeTension(periode)).toEqual({
      disponible: 1,
      tendu: 2,
      complet: 1
    });
  });
});

describe('libelleJournees', () => {
  it('accorde au féminin, puisqu’on compte des journées', () => {
    expect(libelleJournees('complet', 2)).toBe('journées complètes');
    expect(libelleJournees('tendu', 3)).toBe('journées tendues');
    expect(libelleJournees('disponible', 4)).toBe('journées disponibles');
  });

  it('reste au singulier à zéro et à un', () => {
    expect(libelleJournees('tendu', 0)).toBe('journée tendue');
    expect(libelleJournees('complet', 1)).toBe('journée complète');
  });
});

describe('jourLePlusTendu', () => {
  it('retient la journée la plus occupée', () => {
    const periode = [
      jour({ date: '2026-09-18', reserved: 2, occupation_rate: 20 }),
      jour({ date: '2026-09-20', reserved: 9, occupation_rate: 90 }),
      jour({ date: '2026-09-21', reserved: 5, occupation_rate: 50 })
    ];

    expect(jourLePlusTendu(periode)?.date).toBe('2026-09-20');
  });

  it('tranche à égalité par la première rencontrée', () => {
    const periode = [
      jour({ date: '2026-09-18', reserved: 5, occupation_rate: 50 }),
      jour({ date: '2026-09-19', reserved: 5, occupation_rate: 50 })
    ];

    expect(jourLePlusTendu(periode)?.date).toBe('2026-09-18');
  });

  it('n’étiquette rien quand la période n’engage rien', () => {
    expect(jourLePlusTendu([jour({ reserved: 0 })])).toBe(null);
  });

  it('n’étiquette rien sur une période vide', () => {
    expect(jourLePlusTendu([])).toBe(null);
  });
});
