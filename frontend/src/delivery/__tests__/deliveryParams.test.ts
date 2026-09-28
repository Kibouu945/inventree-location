import { describe, expect, it } from 'vitest';

import {
  aujourdhuiIso,
  buildDeliveryQuery,
  DEFAULT_DELIVERY_FILTERS,
  parseDeliveryFilters,
  sansArticlesVirtuels,
  serializeDeliveryFilters
} from '../deliveryParams';

const AUJOURDHUI = '2026-09-08';

describe('horizon de la tournée', () => {
  it('par défaut, borne la tournée à la journée', () => {
    // Revue interne du 07/09/2026 : le livreur ouvrait son écran sur toutes
    // les livraisons, passées comprises.
    expect(DEFAULT_DELIVERY_FILTERS.horizon).toBe('jour');

    const params = buildDeliveryQuery(DEFAULT_DELIVERY_FILTERS, AUJOURDHUI);

    expect(params.date_from).toBe(AUJOURDHUI);
    expect(params.date_to).toBe(AUJOURDHUI);
  });

  it('« à venir » n’a pas de borne haute', () => {
    const params = buildDeliveryQuery(
      { ...DEFAULT_DELIVERY_FILTERS, horizon: 'avenir' },
      AUJOURDHUI
    );

    expect(params.date_from).toBe(AUJOURDHUI);
    expect(params.date_to).toBeUndefined();
  });

  it('« tout » ne borne rien', () => {
    const params = buildDeliveryQuery(
      { ...DEFAULT_DELIVERY_FILTERS, horizon: 'tout' },
      AUJOURDHUI
    );

    expect(params.date_from).toBeUndefined();
    expect(params.date_to).toBeUndefined();
  });

  it('une période saisie l’emporte sur l’horizon', () => {
    const params = buildDeliveryQuery(
      {
        ...DEFAULT_DELIVERY_FILTERS,
        horizon: 'jour',
        dateRange: ['2026-10-01', '2026-10-05']
      },
      AUJOURDHUI
    );

    expect(params.date_from).toBe('2026-10-01');
    expect(params.date_to).toBe('2026-10-05');
  });

  it('une borne libre seule ne réintroduit pas la journée', () => {
    // Sinon « à partir du 1er octobre » se serait vu ajouter un date_to à
    // aujourd'hui, et n'aurait plus rien rendu.
    const params = buildDeliveryQuery(
      { ...DEFAULT_DELIVERY_FILTERS, dateRange: ['2026-10-01', null] },
      AUJOURDHUI
    );

    expect(params.date_from).toBe('2026-10-01');
    expect(params.date_to).toBeUndefined();
  });
});

describe('horizon dans l’URL', () => {
  it('« tout » survit au rechargement', () => {
    // Une absence de clé vaut défaut : sans écrire « tout », le livreur qui
    // demande à voir l'historique retomberait sur sa journée en rechargeant.
    const filtres = { ...DEFAULT_DELIVERY_FILTERS, horizon: 'tout' as const };
    const restaure = parseDeliveryFilters(serializeDeliveryFilters(filtres));

    expect(restaure.horizon).toBe('tout');
  });

  it('n’écrit pas l’horizon par défaut', () => {
    expect(serializeDeliveryFilters(DEFAULT_DELIVERY_FILTERS)).not.toContain(
      'livr_horizon'
    );
  });

  it('retombe sur le défaut devant une valeur inconnue', () => {
    expect(parseDeliveryFilters('livr_horizon=hier').horizon).toBe('jour');
    expect(parseDeliveryFilters('').horizon).toBe('jour');
  });
});

describe('aujourdhuiIso', () => {
  it('formate en AAAA-MM-JJ local, sans décalage de fuseau', () => {
    // 23h30 heure locale : un passage par toISOString() aurait basculé au
    // lendemain en UTC et vidé la tournée du soir.
    expect(aujourdhuiIso(new Date(2026, 8, 8, 23, 30))).toBe('2026-09-08');
    expect(aujourdhuiIso(new Date(2026, 0, 1, 0, 5))).toBe('2026-01-01');
  });
});

describe('filtre Virtuel des livraisons (4.8.1)', () => {
  it('écarte les bons de service par défaut', () => {
    expect(DEFAULT_DELIVERY_FILTERS.virtuel).toBe('non');
    expect(buildDeliveryQuery(DEFAULT_DELIVERY_FILTERS).virtuel).toBe('non');
  });

  it('n’envoie rien quand on demande tous les bons', () => {
    const filtres = { ...DEFAULT_DELIVERY_FILTERS, virtuel: null };
    expect(buildDeliveryQuery(filtres).virtuel).toBeUndefined();
  });

  it('n’écrit pas le défaut dans l’URL', () => {
    expect(serializeDeliveryFilters(DEFAULT_DELIVERY_FILTERS)).not.toContain(
      'livr_virtuel'
    );
  });

  it('écrit « tous » pour que le défaut ne revienne pas au rechargement', () => {
    const query = serializeDeliveryFilters({
      ...DEFAULT_DELIVERY_FILTERS,
      virtuel: null
    });
    expect(query).toContain('livr_virtuel=tous');
    expect(parseDeliveryFilters(query).virtuel).toBeNull();
  });

  it('relit oui et non, et retombe sur le défaut sinon', () => {
    expect(parseDeliveryFilters('livr_virtuel=oui').virtuel).toBe('oui');
    expect(parseDeliveryFilters('livr_virtuel=non').virtuel).toBe('non');
    expect(parseDeliveryFilters('livr_virtuel=zzz').virtuel).toBe('non');
    expect(parseDeliveryFilters('').virtuel).toBe('non');
  });
});

describe('sansArticlesVirtuels', () => {
  const bons = () => [
    {
      id: 1,
      lignes: [
        { is_virtual: false, part: 1 },
        { is_virtual: true, part: 2 }
      ]
    },
    { id: 2, lignes: [{ is_virtual: false, part: 3 }] }
  ];

  it('retire les lignes de service sous « non »', () => {
    const filtres = sansArticlesVirtuels(bons(), 'non');
    expect(filtres[0].lignes).toHaveLength(1);
    expect(filtres[0].lignes[0].part).toBe(1);
    expect(filtres[1].lignes).toHaveLength(1);
  });

  it('ne touche à rien sous « oui » ou « tous »', () => {
    const originaux = bons();
    expect(sansArticlesVirtuels(originaux, 'oui')).toBe(originaux);
    expect(sansArticlesVirtuels(originaux, null)).toBe(originaux);
  });
});
