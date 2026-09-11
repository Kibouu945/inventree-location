import { describe, expect, it } from 'vitest';

import {
  barres,
  decaler,
  estWeekEnd,
  etatDepuisUrl,
  jourDe,
  joursDeLaFenetre,
  libelleLivraison,
  libelleStatut,
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

const FENETRE: FenetrePlanning = { debut: '2026-09-14', jours: 7 };

describe('jourDe', () => {
  it('garde le jour et jette l’heure', () => {
    expect(jourDe('2026-09-14 09:00')).toBe('2026-09-14');
  });

  it('tolère une valeur absente', () => {
    expect(jourDe('')).toBe('');
  });
});

describe('joursDeLaFenetre', () => {
  it('rend les jours du premier au dernier inclus', () => {
    expect(joursDeLaFenetre({ debut: '2026-09-14', jours: 3 })).toEqual([
      '2026-09-14',
      '2026-09-15',
      '2026-09-16'
    ]);
  });

  it('franchit un changement de mois', () => {
    expect(joursDeLaFenetre({ debut: '2026-09-30', jours: 2 })).toEqual([
      '2026-09-30',
      '2026-10-01'
    ]);
  });

  // Le 25 octobre 2026, la France repasse à l'heure d'hiver : une arithmétique
  // en heure locale sauterait ou doublerait un jour. On calcule en UTC.
  it('franchit le changement d’heure sans perdre un jour', () => {
    expect(joursDeLaFenetre({ debut: '2026-10-24', jours: 4 })).toEqual([
      '2026-10-24',
      '2026-10-25',
      '2026-10-26',
      '2026-10-27'
    ]);
  });
});

describe('decaler', () => {
  it('avance et recule la fenêtre', () => {
    expect(decaler(FENETRE, 7).debut).toBe('2026-09-21');
    expect(decaler(FENETRE, -7).debut).toBe('2026-09-07');
  });
});

describe('placer', () => {
  it('place une manifestation entièrement dans la fenêtre', () => {
    const barre = placer(manifestation(), FENETRE);

    expect(barre).toMatchObject({
      colonne: 1,
      largeur: 3,
      deborde_avant: false,
      deborde_apres: false
    });
  });

  it('rogne celle qui commence avant, sans l’écarter', () => {
    const barre = placer(
      manifestation({ date_debut: '2026-09-10 08:00' }),
      FENETRE
    );

    expect(barre).toMatchObject({
      colonne: 1,
      largeur: 3,
      deborde_avant: true,
      deborde_apres: false
    });
  });

  it('rogne celle qui finit après', () => {
    const barre = placer(
      manifestation({ date_fin: '2026-09-30 18:00' }),
      FENETRE
    );

    expect(barre).toMatchObject({ largeur: 7, deborde_apres: true });
  });

  it('écarte celle qui est entièrement hors fenêtre', () => {
    expect(
      placer(
        manifestation({
          date_debut: '2026-08-01 08:00',
          date_fin: '2026-08-03 18:00'
        }),
        FENETRE
      )
    ).toBeNull();
  });

  it('donne une largeur de 1 à une manifestation d’un seul jour', () => {
    const barre = placer(
      manifestation({
        date_debut: '2026-09-15 09:00',
        date_fin: '2026-09-15 23:00'
      }),
      FENETRE
    );

    expect(barre).toMatchObject({ colonne: 2, largeur: 1 });
  });

  it('survit à une date de fin absente', () => {
    const barre = placer(manifestation({ date_fin: '' }), FENETRE);

    expect(barre).toMatchObject({ colonne: 1, largeur: 1 });
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
      FENETRE
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
      FENETRE
    );

    expect(rendues).toHaveLength(1);
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
  it('fait l’aller-retour', () => {
    const params = urlDuPlanning('liste', { debut: '2026-09-14', jours: 30 });

    expect(etatDepuisUrl(params.toString())).toEqual({
      vue: 'liste',
      fenetre: { debut: '2026-09-14', jours: 30 }
    });
  });

  it('n’écrit pas la largeur quand elle est celle par défaut', () => {
    const params = urlDuPlanning('gantt', { debut: '2026-09-14', jours: 21 });

    expect(params.has('plan_jours')).toBe(false);
  });

  it('se rabat sur aujourd’hui quand l’URL est illisible', () => {
    const etat = etatDepuisUrl(
      'plan_debut=hier&plan_jours=-4',
      new Date('2026-09-14T10:00:00Z')
    );

    expect(etat.fenetre).toEqual({ debut: '2026-09-14', jours: 21 });
    expect(etat.vue).toBe('gantt');
  });

  it('préfixe toutes ses clés', () => {
    const params = urlDuPlanning('gantt', { debut: '2026-09-14', jours: 30 });

    for (const cle of params.keys()) {
      expect(cle.startsWith('plan_')).toBe(true);
    }
  });
});
