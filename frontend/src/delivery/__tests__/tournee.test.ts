import { describe, expect, it } from 'vitest';

import type { Ramassage } from '../../ramassage/types';
import {
  appliquerOrdre,
  compterSansCoordonnees,
  construireItineraireUrl,
  construireStops,
  deplacerStop,
  distanceKm,
  distanceTotaleKm,
  dureeEstimeeMin,
  formaterDuree,
  MAX_WAYPOINTS_MAPS,
  optimiserOrdre,
  serialiserOrdre,
  stopsHorsItineraire,
  type TourneeStop
} from '../tournee';
import type { Delivery } from '../types';

function livraison(
  id: number,
  latitude: string | null,
  longitude: string | null,
  heure: string | null
): Delivery {
  return {
    id,
    numero: `RES-${id}`,
    statut: 'validee',
    prestation_nom: 'Prestation',
    demandeur_nom: 'Alice',
    lieu_detail:
      latitude === null && longitude === null
        ? null
        : {
            id: 100 + id,
            nom: `Lieu ${id}`,
            adresse: `${id} rue du Test`,
            latitude,
            longitude
          },
    organisateur_nom: 'Org',
    organisateur_telephone: '',
    date_retrait_prevue: heure,
    date_retour_prevue: null,
    commentaire: '',
    lignes: [],
    quantite_totale: 3
  };
}

function ramassage(
  id: number,
  latitude: string | null,
  longitude: string | null,
  heure: string | null,
  statut = 'livree'
): Ramassage {
  return {
    id,
    numero: `RES-${id}`,
    prestation: 1,
    prestation_nom: 'Prestation',
    manifestation_nom: 'Camp',
    demandeur: 1,
    demandeur_nom: 'Alice',
    statut,
    date_ramassage: null,
    date_retrait_prevue: null,
    date_retour_prevue: heure,
    lieu:
      latitude === null
        ? null
        : {
            id: 200 + id,
            nom: `Lieu R${id}`,
            adresse: `${id} avenue du Test`,
            latitude,
            longitude
          },
    nb_objets: 2,
    quantite_totale: 5,
    recap_par_vehicule: []
  };
}

/** Arrêt nu, pour les calculs géométriques. */
function stop(key: string, latitude: number, longitude: number): TourneeStop {
  return {
    key,
    kind: 'livraison',
    id: Number.parseInt(key.slice(1), 10),
    numero: key,
    prestationNom: '',
    lieuNom: key,
    adresse: '',
    latitude,
    longitude,
    heure: null,
    quantite: 0
  };
}

describe('construireStops', () => {
  it('mélange livraisons et ramassages dans l’ordre chronologique', () => {
    const stops = construireStops(
      [livraison(1, '48.85', '2.35', '2026-06-02T10:00:00Z')],
      [ramassage(2, '48.87', '2.33', '2026-06-02T08:00:00Z')]
    );

    expect(stops.map((entry) => entry.key)).toEqual(['r2', 'l1']);
    expect(stops[0].kind).toBe('ramassage');
    expect(stops[1].kind).toBe('livraison');
  });

  it('écarte ce qui n’a pas de coordonnées GPS', () => {
    const deliveries = [
      livraison(1, '48.85', '2.35', null),
      livraison(2, null, null, null)
    ];
    const ramassages = [ramassage(3, null, null, null)];

    expect(construireStops(deliveries, ramassages)).toHaveLength(1);
    expect(compterSansCoordonnees(deliveries, ramassages)).toBe(2);
  });

  it('ne retient comme ramassage que ce qui est effectivement sur place', () => {
    const ramassages = [
      ramassage(3, '48.85', '2.35', null, 'retournee'),
      ramassage(4, '48.85', '2.35', null, 'livree'),
      ramassage(5, '48.85', '2.35', null, 'validee')
    ];

    expect(construireStops([], ramassages).map((s) => s.key)).toEqual(['r4']);
    // Un ramassage hors périmètre n’est pas « perdu faute de GPS ».
    expect(compterSansCoordonnees([], ramassages)).toBe(0);
  });

  it('écarte une livraison déjà livrée', () => {
    const livree = livraison(6, '48.85', '2.35', null);
    livree.statut = 'livree';

    expect(construireStops([livree], [])).toHaveLength(0);
    expect(compterSansCoordonnees([livree], [])).toBe(0);
  });

  it('range les arrêts sans horaire en fin de tournée', () => {
    const stops = construireStops(
      [
        livraison(1, '48.85', '2.35', null),
        livraison(2, '48.85', '2.35', '2026-06-02T10:00:00Z')
      ],
      []
    );

    expect(stops.map((entry) => entry.key)).toEqual(['l2', 'l1']);
  });
});

describe('distances', () => {
  it('mesure une distance connue à quelques kilomètres près', () => {
    // Paris (Notre-Dame) → Lyon (Bellecour) : ~392 km à vol d'oiseau.
    const paris = stop('l1', 48.853, 2.349);
    const lyon = stop('l2', 45.757, 4.832);

    expect(distanceKm(paris, lyon)).toBeGreaterThan(385);
    expect(distanceKm(paris, lyon)).toBeLessThan(400);
  });

  it('additionne les segments successifs', () => {
    const stops = [
      stop('l1', 48.0, 2.0),
      stop('l2', 48.1, 2.0),
      stop('l3', 48.2, 2.0)
    ];

    expect(distanceTotaleKm(stops)).toBeCloseTo(
      distanceKm(stops[0], stops[1]) + distanceKm(stops[1], stops[2]),
      6
    );
  });

  it('compte le temps passé sur place dans la durée estimée', () => {
    const unique = [stop('l1', 48.0, 2.0)];

    // Aucun trajet, mais un arrêt à desservir.
    expect(dureeEstimeeMin(unique)).toBe(15);
    expect(dureeEstimeeMin([])).toBe(0);
  });
});

describe('optimiserOrdre', () => {
  it('passe au plus proche voisin depuis le premier arrêt', () => {
    const stops = [
      stop('l1', 48.0, 2.0),
      stop('l2', 49.0, 2.0),
      stop('l3', 48.1, 2.0)
    ];

    const optimise = optimiserOrdre(stops);

    expect(optimise.map((entry) => entry.key)).toEqual(['l1', 'l3', 'l2']);
    expect(distanceTotaleKm(optimise)).toBeLessThan(distanceTotaleKm(stops));
  });

  it('ne touche pas une tournée trop courte pour être réordonnée', () => {
    const stops = [stop('l1', 48.0, 2.0), stop('l2', 49.0, 2.0)];

    expect(optimiserOrdre(stops).map((entry) => entry.key)).toEqual([
      'l1',
      'l2'
    ]);
  });
});

describe('ordre mémorisé', () => {
  it('fait l’aller-retour avec la sérialisation URL', () => {
    const stops = [stop('l1', 48.0, 2.0), stop('r2', 48.1, 2.0)];
    const ordre = serialiserOrdre([stops[1], stops[0]]).split(',');

    expect(ordre).toEqual(['r2', 'l1']);
    expect(appliquerOrdre(stops, ordre).map((entry) => entry.key)).toEqual([
      'r2',
      'l1'
    ]);
  });

  it('ignore une clé disparue et ajoute un arrêt neuf à la fin', () => {
    const stops = [stop('l1', 48.0, 2.0), stop('l3', 48.2, 2.0)];

    expect(
      appliquerOrdre(stops, ['l3', 'l2']).map((entry) => entry.key)
    ).toEqual(['l3', 'l1']);
  });

  it('rend l’ordre chronologique quand aucun ordre n’est mémorisé', () => {
    const stops = [stop('l1', 48.0, 2.0), stop('l2', 48.2, 2.0)];

    expect(appliquerOrdre(stops, []).map((entry) => entry.key)).toEqual([
      'l1',
      'l2'
    ]);
  });
});

describe('deplacerStop', () => {
  const stops = [
    stop('l1', 48.0, 2.0),
    stop('l2', 48.1, 2.0),
    stop('l3', 48.2, 2.0)
  ];

  it('échange deux arrêts voisins', () => {
    expect(deplacerStop(stops, 1, -1).map((entry) => entry.key)).toEqual([
      'l2',
      'l1',
      'l3'
    ]);
    expect(deplacerStop(stops, 1, 1).map((entry) => entry.key)).toEqual([
      'l1',
      'l3',
      'l2'
    ]);
  });

  it('ne sort pas des bornes', () => {
    expect(deplacerStop(stops, 0, -1)).toBe(stops);
    expect(deplacerStop(stops, 2, 1)).toBe(stops);
  });
});

describe('construireItineraireUrl', () => {
  it('ne renvoie rien sans arrêt', () => {
    expect(construireItineraireUrl([])).toBeNull();
  });

  it('vise directement la destination quand il n’y a qu’un arrêt', () => {
    const url = construireItineraireUrl([stop('l1', 48.0, 2.0)]) as string;

    expect(url).toContain('destination=48%2C2');
    expect(url).not.toContain('origin=');
    expect(url).not.toContain('waypoints=');
  });

  it('place les arrêts intermédiaires en waypoints', () => {
    const url = construireItineraireUrl([
      stop('l1', 48.0, 2.0),
      stop('l2', 48.1, 2.1),
      stop('l3', 48.2, 2.2)
    ]) as string;

    expect(url).toContain('origin=48%2C2');
    expect(url).toContain('destination=48.2%2C2.2');
    expect(url).toContain('waypoints=48.1%2C2.1');
    expect(url).toContain('travelmode=driving');
  });

  it('tronque au-delà de la limite Google Maps et l’annonce', () => {
    const stops = Array.from({ length: MAX_WAYPOINTS_MAPS + 5 }, (_, index) =>
      stop(`l${index}`, 48 + index / 100, 2)
    );

    const url = construireItineraireUrl(stops) as string;
    const waypoints = new URL(url).searchParams.get('waypoints') as string;

    expect(waypoints.split('|')).toHaveLength(MAX_WAYPOINTS_MAPS);
    expect(stopsHorsItineraire(stops)).toBe(3);
    expect(stopsHorsItineraire(stops.slice(0, 4))).toBe(0);
  });
});

describe('formaterDuree', () => {
  it('affiche les minutes puis les heures', () => {
    expect(formaterDuree(40)).toBe('40 min');
    expect(formaterDuree(60)).toBe('1 h');
    expect(formaterDuree(85)).toBe('1 h 25');
  });
});
