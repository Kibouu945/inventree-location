// En-tête de colonne triable, commun aux tableaux de fiches.
// Recette Tassin du 27/09, point 4.2.5 : « si possible faire des colonnes
// triables ».
import { Group, Table, Text, UnstyledButton } from '@mantine/core';
import { useMemo, useState } from 'react';

export type SensTri = 'asc' | 'desc';

export interface EtatTri<C extends string> {
  colonne: C | null;
  sens: SensTri;
}

/** Ce qu'on compare pour une colonne : texte, nombre ou date. */
export type ValeurTri = string | number | Date | null | undefined;

export function useTri<C extends string>(colonneParDefaut: C | null = null) {
  const [tri, setTri] = useState<EtatTri<C>>({
    colonne: colonneParDefaut,
    sens: 'asc'
  });

  /** Un clic trie, un second inverse, un troisième revient à l'ordre naturel. */
  function basculer(colonne: C) {
    setTri((actuel) => {
      if (actuel.colonne !== colonne) {
        return { colonne, sens: 'asc' };
      }

      return actuel.sens === 'asc'
        ? { colonne, sens: 'desc' }
        : { colonne: null, sens: 'asc' };
    });
  }

  return { tri, basculer };
}

function comparer(a: ValeurTri, b: ValeurTri): number {
  if (a instanceof Date && b instanceof Date) {
    return a.getTime() - b.getTime();
  }

  if (typeof a === 'number' && typeof b === 'number') {
    return a - b;
  }

  // `localeCompare` pour que « École » se range avec « Ecole ».
  return String(a).localeCompare(String(b), 'fr', { numeric: true });
}

/** Trie une liste sans la modifier, selon l'état de tri courant. */
export function trier<T, C extends string>(
  lignes: T[],
  tri: EtatTri<C>,
  valeurPour: (ligne: T, colonne: C) => ValeurTri
): T[] {
  if (!tri.colonne) {
    return lignes;
  }

  const colonne = tri.colonne;
  const signe = tri.sens === 'asc' ? 1 : -1;

  return [...lignes].sort((a, b) => {
    const gauche = valeurPour(a, colonne);
    const droite = valeurPour(b, colonne);

    // Les valeurs absentes restent en bas dans les deux sens : le signe ne
    // s'applique qu'à la comparaison de deux valeurs présentes.
    if (gauche == null && droite == null) return 0;
    if (gauche == null) return 1;
    if (droite == null) return -1;

    return signe * comparer(gauche, droite);
  });
}

/** Version mémoïsée, pour ne pas retrier à chaque rendu. */
export function useLignesTriees<T, C extends string>(
  lignes: T[],
  tri: EtatTri<C>,
  valeurPour: (ligne: T, colonne: C) => ValeurTri
): T[] {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => trier(lignes, tri, valeurPour), [lignes, tri]);
}

export function EnTeteTriable<C extends string>({
  colonne,
  tri,
  onTri,
  children,
  ta
}: {
  colonne: C;
  tri: EtatTri<C>;
  onTri: (colonne: C) => void;
  children: React.ReactNode;
  ta?: 'left' | 'right' | 'center';
}) {
  const actif = tri.colonne === colonne;
  const fleche = !actif ? '' : tri.sens === 'asc' ? ' ↑' : ' ↓';

  return (
    <Table.Th ta={ta}>
      <UnstyledButton
        onClick={() => onTri(colonne)}
        aria-label={`Trier par ${String(children)}`}
        w='100%'
      >
        <Group gap={2} justify={ta === 'right' ? 'flex-end' : 'flex-start'}>
          <Text size='sm' fw={600} c={actif ? undefined : 'dimmed'}>
            {children}
            {fleche}
          </Text>
        </Group>
      </UnstyledButton>
    </Table.Th>
  );
}
