import { describe, expect, it } from 'vitest';

import { finSuivantLeDebut } from '../DateTimeField';

const j = (iso: string) => new Date(iso);

describe('finSuivantLeDebut', () => {
  it('cale la fin sur le lendemain quand elle est vide', () => {
    const fin = finSuivantLeDebut(j('2026-10-20T08:00:00'), null);

    expect(fin?.toISOString()).toBe(j('2026-10-21T08:00:00').toISOString());
  });

  it("garde l'heure du début", () => {
    const fin = finSuivantLeDebut(j('2026-10-20T14:30:00'), null);

    expect(fin?.getHours()).toBe(14);
    expect(fin?.getMinutes()).toBe(30);
  });

  it('ne touche pas à une fin déjà postérieure', () => {
    const choisie = j('2026-10-25T18:00:00');
    const fin = finSuivantLeDebut(j('2026-10-20T08:00:00'), choisie);

    expect(fin).toBe(choisie);
  });

  it('rattrape une fin devenue antérieure au début', () => {
    const fin = finSuivantLeDebut(
      j('2026-10-20T08:00:00'),
      j('2026-10-15T08:00:00')
    );

    expect(fin?.toISOString()).toBe(j('2026-10-21T08:00:00').toISOString());
  });

  it('rattrape une fin égale au début', () => {
    const debut = j('2026-10-20T08:00:00');
    const fin = finSuivantLeDebut(debut, j('2026-10-20T08:00:00'));

    expect(fin?.getTime()).toBeGreaterThan(debut.getTime());
  });

  it('laisse la fin intacte tant que le début est vide', () => {
    const choisie = j('2026-10-25T18:00:00');

    expect(finSuivantLeDebut(null, choisie)).toBe(choisie);
  });

  it('franchit un changement de mois', () => {
    const fin = finSuivantLeDebut(j('2026-10-31T09:00:00'), null);

    expect(fin?.getMonth()).toBe(10); // novembre
    expect(fin?.getDate()).toBe(1);
  });
});
