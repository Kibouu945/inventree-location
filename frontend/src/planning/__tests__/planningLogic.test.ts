import { describe, expect, it } from 'vitest';

import {
  barres,
  bornes,
  colonnes,
  contientAujourdhui,
  debutDeLaFenetre,
  decaler,
  estWeekEnd,
  etatDepuisUrl,
  fenetreParDefaut,
  jourDe,
  joursDuMois,
  libelleLivraison,
  libellePeriode,
  libelleStatut,
  lundiDeLaSemaine,
  placer,
  urlDuPlanning
} from '../planningLogic';
import type { FenetrePlanning, ManifestationPlanning } from '../types';

function manifestation(
  overrides: Partial<ManifestationPlanning> = {}
): ManifestationPlanning {
  return {
    id: 1,
    nom: 'Camp d’été',
    date_debut: '2026-09-14 09:00',
    date_fin: '2026-09-16 19:00',
    statut: 'planifiee',
    statut_effectif: 'planifiee',
    couleur: '#be185d',
    client_nom: 'Pionniers de Mantes',
    organisateur_nom: 'Paule Durand',
    contact_telephone: '0611223344',
    quantite_totale: 24,
    etat_livraison: { bons: 2, livres: 1, a_livrer: 1 },
    prestations_count: 2,
    ...overrides
  };
}

// Le 16 septembre 2026 est un mercredi : sa semaine court du 14 au 20.
const SEMAINE: FenetrePlanning = { echelle: 'semaine', ancre: '2026-09-16' };
const MOIS: FenetrePlanning = { echelle: 'mois', ancre: '2026-09-16' };
const ANNEE: FenetrePlanning = { echelle: 'annee', ancre: '2026-09-16' };

describe('jourDe', () => {
  it('garde le jour et jette l’heure', () => {
    expect(jourDe('2026-09-14 09:00')).toBe('2026-09-14');
  });

  it('tolère une valeur absente', () => {
    expect(jourDe('')).toBe('');
  });
});

describe('alignement de la fenêtre', () => {
  it('la semaine commence le lundi, quel que soit le jour d’ancrage', () => {
    expect(lundiDeLaSemaine('2026-09-16')).toBe('2026-09-14');
    expect(lundiDeLaSemaine('2026-09-20')).toBe('2026-09-14');
    expect(debutDeLaFenetre(SEMAINE)).toBe('2026-09-14');
  });

  it('le mois commence le premier', () => {
    expect(debutDeLaFenetre(MOIS)).toBe('2026-09-01');
  });

  it('l’année commence au 1er janvier', () => {
    expect(debutDeLaFenetre(ANNEE)).toBe('2026-01-01');
  });

  it('se rabat sur aujourd’hui quand l’ancre est illisible', () => {
    expect(debutDeLaFenetre({ echelle: 'mois', ancre: 'hier' })).toMatch(
      /^\d{4}-\d{2}-\d{2}$/
    );
  });
});

describe('colonnes', () => {
  it('la semaine en fait sept, du lundi au dimanche', () => {
    const grille = colonnes(SEMAINE);

    expect(grille).toHaveLength(7);
    expect(grille[0].debut).toBe('2026-09-14');
    expect(grille[6].fin).toBe('2026-09-20');
    expect(grille[5].weekend).toBe(true);
    expect(grille[6].weekend).toBe(true);
  });

  it('le mois en fait autant que le mois a de jours', () => {
    expect(colonnes(MOIS)).toHaveLength(30);
    expect(colonnes({ echelle: 'mois', ancre: '2026-02-10' })).toHaveLength(28);
    // 2028 est bissextile : une grille figée à 31 colonnes afficherait des
    // jours fantômes, une grille figée à 28 en perdrait un.
    expect(colonnes({ echelle: 'mois', ancre: '2028-02-10' })).toHaveLength(29);
  });

  it('l’année en fait douze, un par mois', () => {
    const grille = colonnes(ANNEE);

    expect(grille).toHaveLength(12);
    expect(grille[0]).toMatchObject({ debut: '2026-01-01', fin: '2026-01-31' });
    expect(grille[11]).toMatchObject({
      debut: '2026-12-01',
      fin: '2026-12-31'
    });
  });

  it('franchit le changement d’heure sans perdre un jour', () => {
    // La France repasse à l'heure d'hiver le 25 octobre 2026 : une
    // arithmétique en heure locale y saute ou double un jour.
    const grille = colonnes({ echelle: 'mois', ancre: '2026-10-01' });

    expect(grille).toHaveLength(31);
    expect(grille[24].debut).toBe('2026-10-25');
    expect(grille[30].debut).toBe('2026-10-31');
  });
});

describe('joursDuMois', () => {
  it('connaît les mois courts et les années bissextiles', () => {
    expect(joursDuMois('2026-02-10')).toBe(28);
    expect(joursDuMois('2028-02-10')).toBe(29);
    expect(joursDuMois('2026-04-10')).toBe(30);
    expect(joursDuMois('2026-12-10')).toBe(31);
  });
});

describe('decaler', () => {
  it('avance et recule d’une semaine entière', () => {
    expect(debutDeLaFenetre(decaler(SEMAINE, 1))).toBe('2026-09-21');
    expect(debutDeLaFenetre(decaler(SEMAINE, -1))).toBe('2026-09-07');
  });

  it('avance et recule d’un mois entier', () => {
    expect(debutDeLaFenetre(decaler(MOIS, 1))).toBe('2026-10-01');
    expect(debutDeLaFenetre(decaler(MOIS, -1))).toBe('2026-08-01');
  });

  it('franchit le passage d’une année à l’autre', () => {
    const decembre: FenetrePlanning = { echelle: 'mois', ancre: '2026-12-15' };

    expect(debutDeLaFenetre(decaler(decembre, 1))).toBe('2027-01-01');
  });

  it('avance et recule d’une année entière', () => {
    expect(debutDeLaFenetre(decaler(ANNEE, 1))).toBe('2027-01-01');
    expect(debutDeLaFenetre(decaler(ANNEE, -1))).toBe('2025-01-01');
  });
});

describe('bornes envoyées au serveur', () => {
  it('couvrent exactement la période affichée', () => {
    expect(bornes(SEMAINE)).toEqual({ from: '2026-09-14', to: '2026-09-20' });
    expect(bornes(MOIS)).toEqual({ from: '2026-09-01', to: '2026-09-30' });
    expect(bornes(ANNEE)).toEqual({ from: '2026-01-01', to: '2026-12-31' });
  });
});

describe('placer', () => {
  it('place une manifestation dans la semaine', () => {
    // Du lundi 14 au mercredi 16 : première colonne, trois jours.
    expect(placer(manifestation(), colonnes(SEMAINE))).toMatchObject({
      colonne: 1,
      largeur: 3,
      deborde_avant: false,
      deborde_apres: false
    });
  });

  it('rogne celle qui commence avant, sans l’écarter', () => {
    expect(
      placer(
        manifestation({ date_debut: '2026-09-10 08:00' }),
        colonnes(SEMAINE)
      )
    ).toMatchObject({ colonne: 1, largeur: 3, deborde_avant: true });
  });

  it('rogne celle qui finit après', () => {
    expect(
      placer(manifestation({ date_fin: '2026-10-30 18:00' }), colonnes(SEMAINE))
    ).toMatchObject({ largeur: 7, deborde_apres: true });
  });

  it('écarte celle qui est entièrement hors fenêtre', () => {
    expect(
      placer(
        manifestation({
          date_debut: '2026-08-01 08:00',
          date_fin: '2026-08-03 18:00'
        }),
        colonnes(SEMAINE)
      )
    ).toBeNull();
  });

  it('tient sur une seule colonne à l’échelle de l’année', () => {
    // Trois jours de septembre : un mois, pas trois colonnes.
    expect(placer(manifestation(), colonnes(ANNEE))).toMatchObject({
      colonne: 9,
      largeur: 1
    });
  });

  it('couvre plusieurs mois quand elle les traverse', () => {
    expect(
      placer(
        manifestation({
          date_debut: '2026-09-28 09:00',
          date_fin: '2026-11-02 18:00'
        }),
        colonnes(ANNEE)
      )
    ).toMatchObject({ colonne: 9, largeur: 3 });
  });

  it('donne une largeur de 1 à une manifestation d’un seul jour', () => {
    expect(
      placer(
        manifestation({
          date_debut: '2026-09-15 09:00',
          date_fin: '2026-09-15 23:00'
        }),
        colonnes(SEMAINE)
      )
    ).toMatchObject({ colonne: 2, largeur: 1 });
  });

  it('survit à une date de fin absente', () => {
    expect(
      placer(manifestation({ date_fin: '' }), colonnes(SEMAINE))
    ).toMatchObject({ colonne: 1, largeur: 1 });
  });
});

describe('barres', () => {
  it('trie par colonne puis par nom, quel que soit l’ordre reçu', () => {
    const rendues = barres(
      [
        manifestation({ id: 3, nom: 'Zoulou', date_debut: '2026-09-15 09:00' }),
        manifestation({ id: 2, nom: 'Bravo', date_debut: '2026-09-14 09:00' }),
        manifestation({ id: 1, nom: 'Alpha', date_debut: '2026-09-15 09:00' })
      ],
      colonnes(SEMAINE)
    );

    expect(rendues.map((barre) => barre.manifestation.nom)).toEqual([
      'Bravo',
      'Alpha',
      'Zoulou'
    ]);
  });

  it('laisse de côté ce qui ne paraît pas dans la fenêtre', () => {
    const rendues = barres(
      [
        manifestation(),
        manifestation({
          id: 2,
          date_debut: '2020-01-01 09:00',
          date_fin: '2020-01-02 09:00'
        })
      ],
      colonnes(SEMAINE)
    );

    expect(rendues).toHaveLength(1);
  });
});

describe('libellePeriode', () => {
  it('nomme la semaine par ses bornes', () => {
    expect(libellePeriode(SEMAINE)).toContain('14 sept.');
    expect(libellePeriode(SEMAINE)).toContain('2026');
  });

  it('nomme le mois et l’année', () => {
    expect(libellePeriode(MOIS)).toBe('Septembre 2026');
  });

  it('nomme l’année par son seul millésime', () => {
    expect(libellePeriode(ANNEE)).toBe('2026');
  });
});

describe('contientAujourdhui', () => {
  it('reconnaît la colonne du jour, au jour comme au mois', () => {
    const jour = {
      debut: '2026-09-16',
      fin: '2026-09-16',
      libelle: '',
      weekend: false
    };
    const mois = {
      debut: '2026-09-01',
      fin: '2026-09-30',
      libelle: '',
      weekend: false
    };

    expect(contientAujourdhui(jour, '2026-09-16')).toBe(true);
    expect(contientAujourdhui(jour, '2026-09-17')).toBe(false);
    expect(contientAujourdhui(mois, '2026-09-16')).toBe(true);
  });
});

describe('estWeekEnd', () => {
  it('reconnaît samedi et dimanche', () => {
    expect(estWeekEnd('2026-09-19')).toBe(true);
    expect(estWeekEnd('2026-09-20')).toBe(true);
    expect(estWeekEnd('2026-09-21')).toBe(false);
  });
});

describe('libelleLivraison', () => {
  it('rend l’avancement', () => {
    expect(libelleLivraison(manifestation())).toBe('1/2 livré');
  });

  it('accorde le pluriel', () => {
    expect(
      libelleLivraison(
        manifestation({ etat_livraison: { bons: 5, livres: 2, a_livrer: 3 } })
      )
    ).toBe('2/5 livrés');
  });

  it('dit qu’il n’y a aucun bon plutôt que 0/0', () => {
    expect(
      libelleLivraison(
        manifestation({ etat_livraison: { bons: 0, livres: 0, a_livrer: 0 } })
      )
    ).toBe('aucun bon');
  });
});

describe('libelleStatut', () => {
  it('traduit les codes du serveur', () => {
    expect(libelleStatut('en_cours')).toBe('En cours');
    expect(libelleStatut('planifiee')).toBe('Planifiée');
  });

  it('rend le code tel quel s’il est inconnu, jamais une case vide', () => {
    expect(libelleStatut('inattendu')).toBe('inattendu');
  });
});

describe('état d’URL', () => {
  it('fait l’aller-retour sur les trois échelles', () => {
    for (const fenetre of [SEMAINE, MOIS, ANNEE]) {
      const relu = etatDepuisUrl(urlDuPlanning('liste', fenetre).toString());

      expect(relu.vue).toBe('liste');
      expect(relu.fenetre.echelle).toBe(fenetre.echelle);
      expect(debutDeLaFenetre(relu.fenetre)).toBe(debutDeLaFenetre(fenetre));
    }
  });

  it('se rabat sur le mois courant quand l’URL est illisible', () => {
    const etat = etatDepuisUrl(
      'plan_echelle=trimestre&plan_date=hier',
      new Date('2026-09-16T10:00:00Z')
    );

    expect(etat.fenetre.echelle).toBe('mois');
    expect(etat.vue).toBe('gantt');
    expect(debutDeLaFenetre(etat.fenetre)).toBe('2026-09-01');
  });

  it('préfixe toutes ses clés', () => {
    for (const cle of urlDuPlanning('gantt', MOIS).keys()) {
      expect(cle.startsWith('plan_')).toBe(true);
    }
  });
});

describe('fenetreParDefaut', () => {
  it('ancre la période sur aujourd’hui', () => {
    const fenetre = fenetreParDefaut('mois', new Date('2026-09-16T10:00:00Z'));

    expect(debutDeLaFenetre(fenetre)).toBe('2026-09-01');
  });
});
