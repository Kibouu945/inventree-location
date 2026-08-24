import type { InvenTreePluginContext } from '@inventreedb/ui';
import { describe, expect, it } from 'vitest';

import {
  canArbitrateReservations,
  canDeclareRetour,
  canWriteCatalog,
  canWriteReservations,
  hasAnyRole,
  isSuperuser,
  userRoles
} from '../roles';

// Fabrique un contexte minimal imitant le store user d'InvenTree :
// les données sont derrière getUser(), groups est [{ pk, name }].
function makeContext({
  groups = [],
  is_superuser = false
}: {
  groups?: Array<{ pk: number; name: string }> | null;
  is_superuser?: boolean;
} = {}): InvenTreePluginContext {
  const user = { groups, is_superuser };
  return {
    user: {
      getUser: () => user,
      isSuperuser: () => is_superuser
    }
  } as unknown as InvenTreePluginContext;
}

const groups = (...names: string[]) =>
  names.map((name, index) => ({ pk: index + 1, name }));

describe('userRoles', () => {
  it('extrait les noms de groupes depuis getUser()', () => {
    const ctx = makeContext({ groups: groups('gestionnaire', 'lecteur') });
    expect(userRoles(ctx)).toEqual(['gestionnaire', 'lecteur']);
  });

  it('renvoie [] quand groups est null ou absent', () => {
    expect(userRoles(makeContext({ groups: null }))).toEqual([]);
    expect(userRoles({} as InvenTreePluginContext)).toEqual([]);
  });
});

describe('isSuperuser', () => {
  it('détecte le superutilisateur', () => {
    expect(isSuperuser(makeContext({ is_superuser: true }))).toBe(true);
    expect(isSuperuser(makeContext({ is_superuser: false }))).toBe(false);
  });
});

describe('hasAnyRole', () => {
  it('vrai si un rôle correspond', () => {
    const ctx = makeContext({ groups: groups('livreur') });
    expect(hasAnyRole(ctx, ['livreur', 'sav'])).toBe(true);
    expect(hasAnyRole(ctx, ['admin'])).toBe(false);
  });

  it('le superutilisateur passe toujours', () => {
    const ctx = makeContext({ is_superuser: true });
    expect(hasAnyRole(ctx, ['admin'])).toBe(true);
  });
});

describe('canWriteReservations', () => {
  it.each([
    ['admin', true],
    ['gestionnaire', true],
    ['organisateur', true],
    ['magasinier', false],
    ['livreur', false],
    ['sav', false],
    ['lecteur', false]
  ])('%s -> %s', (role, expected) => {
    expect(canWriteReservations(makeContext({ groups: groups(role) }))).toBe(
      expected
    );
  });
});

describe('canWriteCatalog', () => {
  it.each([
    ['admin', true],
    ['gestionnaire', true],
    ['organisateur', false],
    ['magasinier', false],
    ['livreur', false],
    ['lecteur', false]
  ])('%s -> %s', (role, expected) => {
    expect(canWriteCatalog(makeContext({ groups: groups(role) }))).toBe(
      expected
    );
  });
});

// Le retour et l'arbitrage ne se recouvrent pas : le magasinier déclare les
// retours sans arbitrer, le gestionnaire arbitre sans déclarer. Le bouton
// « Déclarer le retour » vivait dans la colonne d'arbitrage, donc invisible
// pour sa propre persona.
describe('canDeclareRetour', () => {
  it('ouvert au magasinier et à l’admin', () => {
    expect(
      canDeclareRetour(makeContext({ groups: groups('magasinier') }))
    ).toBe(true);
    expect(canDeclareRetour(makeContext({ groups: groups('admin') }))).toBe(
      true
    );
  });

  it('fermé au gestionnaire, qui n’arbitre que les réservations', () => {
    const ctx = makeContext({ groups: groups('gestionnaire') });
    expect(canDeclareRetour(ctx)).toBe(false);
    expect(canArbitrateReservations(ctx)).toBe(true);
  });

  it('le magasinier n’arbitre pas', () => {
    const ctx = makeContext({ groups: groups('magasinier') });
    expect(canArbitrateReservations(ctx)).toBe(false);
  });
});
