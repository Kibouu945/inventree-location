/** Envoi groupé des livraisons : un bon ne part que si tous ses articles sont cochés. */
import type { Delivery, DeliveryLigne } from './types';

export interface BonCocheEnPartie {
  numero: string;
  coches: number;
  total: number;
}

export interface SelectionDeLivraison {
  /** Les bons à envoyer, cochés en entier. */
  complets: number[];
  /** Les bons laissés de côté, à signaler au livreur. */
  partiels: BonCocheEnPartie[];
}

export function trierLaSelection(
  deliveries: Delivery[],
  estCochee: (ligne: DeliveryLigne) => boolean
): SelectionDeLivraison {
  const complets: number[] = [];
  const partiels: BonCocheEnPartie[] = [];

  for (const bon of deliveries) {
    if (bon.statut !== 'validee' || bon.lignes.length === 0) {
      continue;
    }

    const coches = bon.lignes.filter(estCochee).length;

    if (coches === bon.lignes.length) {
      complets.push(bon.id);
    } else if (coches > 0) {
      partiels.push({ numero: bon.numero, coches, total: bon.lignes.length });
    }
  }

  return { complets, partiels };
}

export function messageBonPartiel({
  numero,
  coches,
  total
}: BonCocheEnPartie): string {
  const articles = coches > 1 ? 'articles' : 'article';
  const cochés = coches > 1 ? 'cochés' : 'coché';

  return (
    `${numero} : ${coches} ${articles} sur ${total} ${cochés}. ` +
    "Un bon se livre en entier : cochez tous ses articles pour l'envoyer."
  );
}
