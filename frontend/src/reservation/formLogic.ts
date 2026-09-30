/** Logique pure du formulaire de réservation (RES-03). */

import { HEURE_PAR_DEFAUT } from '../DateTimeField';
import type {
  LigneReservationLine,
  Prestation,
  Reservation,
  ReservationFormValues,
  ReservationStatut
} from './types';

/** Formate une date en « JJ/MM », en UTC pour rester stable quel que soit le
 * fuseau d'exécution (tests compris). */
function formatDayMonth(date: Date): string {
  const day = String(date.getUTCDate()).padStart(2, '0');
  const month = String(date.getUTCMonth() + 1).padStart(2, '0');
  return `${day}/${month}`;
}

export function emptyReservationValues(): ReservationFormValues {
  return {
    prestation: null,
    demandeur: null,
    date_retrait_prevue: null,
    date_retour_prevue: null,
    commentaire: '',
    lignes: []
  };
}

/** Pose une heure « HH:mm » sur le jour d'une date, sans toucher au jour. */
function auMemeJourA(date: Date, heure: string): Date {
  const [h, m] = heure.split(':').map(Number);
  const resultat = new Date(date);
  resultat.setHours(h, m ?? 0, 0, 0);
  return resultat;
}

/** Valeurs reprises de la prestation pour une réservation neuve. */
export function prestationDefaults(
  prestation: Prestation
): Pick<
  ReservationFormValues,
  'date_retrait_prevue' | 'date_retour_prevue' | 'lignes'
> {
  const debut = new Date(prestation.date_debut);
  const fin = new Date(prestation.date_fin);

  const retraitA8h = auMemeJourA(debut, HEURE_PAR_DEFAUT);
  const retourA8h = auMemeJourA(fin, HEURE_PAR_DEFAUT);

  return {
    date_retrait_prevue: retraitA8h <= debut ? retraitA8h : debut,
    date_retour_prevue: retourA8h >= fin ? retourA8h : fin,
    // `isVirtual` est laissé à faux : c'est `enrichLignesFromCatalog` qui
    // tranche, une fois le catalogue résolu.
    lignes: (prestation.lignes ?? []).map((ligne) => ({
      part: ligne.part,
      partName: ligne.part_name,
      quantiteDemandee: ligne.quantite,
      isVirtual: false
    }))
  };
}

export interface ReservationFormErrors {
  [key: string]: string | undefined;
  prestation?: string;
  demandeur?: string;
  date_retrait_prevue?: string;
  date_retour_prevue?: string;
  lignes?: string;
}

/** Valide les valeurs du formulaire pour un statut donné. */
export function validateReservationValues(
  values: ReservationFormValues,
  prestation: Prestation | null,
  statut: ReservationStatut
): ReservationFormErrors {
  const errors: ReservationFormErrors = {};

  if (!values.prestation) {
    errors.prestation = 'La prestation est obligatoire.';
  }
  if (!values.demandeur) {
    errors.demandeur = 'Le demandeur est obligatoire.';
  }

  if (statut === 'brouillon') {
    return errors;
  }

  const { date_retrait_prevue: retrait, date_retour_prevue: retour } = values;

  if (!retrait) {
    errors.date_retrait_prevue =
      'La date de retrait est obligatoire pour soumettre la réservation.';
  }
  if (!retour) {
    errors.date_retour_prevue =
      'La date de retour est obligatoire pour soumettre la réservation.';
  }

  if (retrait && retour) {
    if (retrait > retour) {
      errors.date_retour_prevue =
        'La date de retour doit être postérieure ou égale à la date de retrait.';
    } else if (prestation) {
      const debut = new Date(prestation.date_debut);
      const fin = new Date(prestation.date_fin);
      const couvreDebut = retrait <= debut;
      const couvreFin = retour >= fin;

      if (!couvreDebut || !couvreFin) {
        const message =
          'La période de réservation doit couvrir les dates du ' +
          `${formatDayMonth(debut)} au ${formatDayMonth(fin)}.`;

        if (!couvreDebut) {
          errors.date_retrait_prevue = message;
        }
        if (!couvreFin) {
          errors.date_retour_prevue = message;
        }
      }
    }
  }

  if (values.lignes.length === 0) {
    errors.lignes =
      'Au moins une ligne de matériel est obligatoire pour soumettre la réservation.';
  } else if (!values.lignes.some((ligne) => ligne.isVirtual)) {
    errors.lignes =
      'Au moins un article virtuel (ex: prestation de nettoyage) est obligatoire pour soumettre la réservation.';
  }

  return errors;
}

/** Construit le payload API à partir des valeurs du formulaire. */
export function buildReservationPayload(
  values: ReservationFormValues,
  statut: ReservationStatut
) {
  return {
    prestation: values.prestation,
    demandeur: values.demandeur,
    statut,
    date_retrait_prevue: values.date_retrait_prevue
      ? values.date_retrait_prevue.toISOString()
      : null,
    date_retour_prevue: values.date_retour_prevue
      ? values.date_retour_prevue.toISOString()
      : null,
    commentaire: values.commentaire,
    lignes: values.lignes.map((ligne) => ({
      part: ligne.part,
      quantite_demandee: ligne.quantiteDemandee
    }))
  };
}

/** Ajoute ou remplace une ligne de matériel (une seule ligne par part). */
export function upsertLigne(
  lignes: LigneReservationLine[],
  ligne: LigneReservationLine
): LigneReservationLine[] {
  const withoutExisting = lignes.filter(
    (existing) => existing.part !== ligne.part
  );
  return [...withoutExisting, ligne];
}

export function removeLigne(
  lignes: LigneReservationLine[],
  part: number
): LigneReservationLine[] {
  return lignes.filter((ligne) => ligne.part !== part);
}

/** (édition). */
export function reservationToFormValues(
  reservation: Reservation
): ReservationFormValues {
  return {
    prestation: reservation.prestation,
    demandeur: reservation.demandeur,
    date_retrait_prevue: reservation.date_retrait_prevue
      ? new Date(reservation.date_retrait_prevue)
      : null,
    date_retour_prevue: reservation.date_retour_prevue
      ? new Date(reservation.date_retour_prevue)
      : null,
    commentaire: reservation.commentaire,
    lignes: reservation.lignes.map((ligne) => ({
      part: ligne.part,
      partName: `Article #${ligne.part}`,
      quantiteDemandee: ligne.quantite_demandee,
      isVirtual: false
    }))
  };
}

interface CatalogPartInfo {
  id: number;
  name: string;
  is_virtual: boolean;
}

/** Complète le nom et le drapeau `is_virtual` des lignes à partir du
 * catalogue (résultat de `/catalog/?ids=...`). */
export function enrichLignesFromCatalog(
  lignes: LigneReservationLine[],
  catalogParts: CatalogPartInfo[]
): LigneReservationLine[] {
  const byId = new Map(catalogParts.map((part) => [part.id, part]));

  return lignes.map((ligne) => {
    const info = byId.get(ligne.part);

    if (!info) {
      return ligne;
    }

    return { ...ligne, partName: info.name, isVirtual: info.is_virtual };
  });
}

/** Vrai si la réservation attend un arbitrage (seul « soumise » l'ouvre). */
export function canArbitrateReservation(statut: string): boolean {
  return statut === 'soumise';
}

/** Statuts depuis lesquels `VALID_TRANSITIONS` autorise encore l'annulation. */
const STATUTS_ANNULABLES = [
  'brouillon',
  'soumise',
  'validee',
  'livree',
  'retournee'
];

/**
 * C'est le seul levier d'arbitrage sur une réservation déjà validée : la fiche
 * s'ouvre alors en lecture seule et aucune autre action n'existe.
 */
export function canCancelReservation(statut: string): boolean {
  return STATUTS_ANNULABLES.includes(statut);
}

/**
 * Le message était figé sur « validée » alors que `isReservationEditable`
 * verrouille tout ce qui n'est ni brouillon ni soumise : une réservation
 * annulée ou refusée s'annonçait donc comme validée.
 */
export function readOnlyReason(statut: string): string {
  const raisons: Record<string, string> = {
    validee: 'Cette réservation est validée : elle n’est plus modifiable.',
    livree: 'Cette réservation est livrée : elle n’est plus modifiable.',
    retournee: 'Cette réservation est retournée : elle n’est plus modifiable.',
    cloturee: 'Cette réservation est clôturée : elle n’est plus modifiable.',
    refusee: 'Cette réservation a été refusée : elle n’est plus modifiable.',
    annulee: 'Cette réservation a été annulée : elle n’est plus modifiable.'
  };

  return raisons[statut] ?? 'Cette réservation n’est plus modifiable.';
}

/** Vrai tant que la réservation est modifiable (avant validation). */
export function isReservationEditable(statut: string): boolean {
  return statut === 'brouillon' || statut === 'soumise';
}

/** Message d'une transition ratée : le `detail` backend, sinon un générique. */
export function transitionErrorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;

  return typeof detail === 'string'
    ? detail
    : "Le statut n'a pas pu être changé.";
}

/** Option de `Select` : {value, label} tels que Mantine les attend. */
export interface OptionSelect {
  value: string;
  label: string;
}

/**
 * Garantit que la valeur déjà choisie figure dans la liste : les options
 * viennent d'une recherche paginée qui ne la contient pas forcément, et
 * Mantine afficherait alors un champ vide sur un formulaire de modification.
 */
export function avecOptionCourante(
  options: OptionSelect[],
  value: string | null,
  label: string | null | undefined
): OptionSelect[] {
  if (!value || !label || options.some((option) => option.value === value)) {
    return options;
  }

  return [{ value, label }, ...options];
}

/**
 * Terme à envoyer au serveur pour un `Select` searchable. Mantine recopie le
 * libellé de l'option choisie dans le champ de recherche : le renvoyer tel quel
 * ne ramènerait que cette option, et la liste se réduirait à ce qu'on vient de
 * choisir. On ne cherche donc que sur une saisie qui diffère du libellé retenu.
 */
export function rechercheServeur(
  saisie: string,
  libelleChoisi: string | null | undefined
): string | undefined {
  const terme = saisie.trim();

  if (!terme || terme === libelleChoisi) {
    return undefined;
  }

  return terme;
}

/** Conflit de stock sur un article, tel que le serveur le rend. */
export interface ConflitArticle {
  part_id: number;
  part_name: string;
  requested_quantity: number;
  available_quantity: number;
  missing_quantity: number;
}

/**
 * Les conflits rangés par article, pour marquer les lignes du tableau : le
 * client veut voir sur *quel* article porte le blocage, pas seulement qu'il y
 * en a un (recette).
 */
export function conflitsParArticle(
  conflits: ConflitArticle[] | undefined | null
): Record<number, ConflitArticle> {
  const parArticle: Record<number, ConflitArticle> = {};

  for (const conflit of conflits ?? []) {
    parArticle[conflit.part_id] = conflit;
  }

  return parArticle;
}

/** Ligne du calcul de disponibilité « avant enregistrement » (STK-01). */
export interface LignePreviewStock {
  part_id: number;
  part_name: string;
  requested: number;
  available: number;
  missing: number;
  shortage: boolean;
}

/**
 * Ramène les lignes en pénurie du calcul « avant enregistrement » au format
 * des conflits : les deux chemins alimentent le même indicateur, un
 * bon tout neuf n'a pas encore d'identifiant à donner au point d'entrée
 * `conflicts`.
 */
export function conflitsDuPreview(
  lignes: LignePreviewStock[] | undefined | null
): ConflitArticle[] {
  return (lignes ?? [])
    .filter((ligne) => ligne.shortage)
    .map((ligne) => ({
      part_id: ligne.part_id,
      part_name: ligne.part_name,
      requested_quantity: ligne.requested,
      available_quantity: ligne.available,
      missing_quantity: ligne.missing
    }));
}
