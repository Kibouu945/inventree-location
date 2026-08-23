import type { InvenTreePluginContext } from '@inventreedb/ui';
import { describe, expect, it } from 'vitest';

import {
  canCheckinReturns,
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

describe('canCheckinReturns', () => {
  // Miroir de ReturnCheckinPermission.write_roles côté serveur.
  it.each([
    ['admin', true],
    ['gestionnaire', true],
    ['magasinier', true],
    ['organisateur', false],
    ['livreur', false],
    ['sav', false],
    ['lecteur', false]
  ])('%s -> %s', (role, expected) => {
    expect(canCheckinReturns(makeContext({ groups: groups(role) }))).toBe(
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
