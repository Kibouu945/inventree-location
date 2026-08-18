/** Types de l'API réservation (`/plugin/inventree-location/reservations/`,
 * `/prestations/`, `/users/`, `/catalog/`). */

export interface UserOption {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
}

export interface LieuSummary {
  id: number;
  nom: string;
  adresse: string;
  // DRF sérialise les DecimalField en chaîne (cf. organisation/types.ts).
  latitude: string | null;
  longitude: string | null;
}

export interface Prestation {
  id: number;
  nom: string;
  date_debut: string;
  date_fin: string;
  manifestation: number;
  manifestation_nom: string;
  // ORG-02 : une prestation se déroule sur un seul lieu géolocalisé.
  lieu: number | null;
  lieu_detail: LieuSummary | null;
}

/** Réponse paginée DRF (PageNumberPagination). */
export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export type ReservationStatut = 'brouillon' | 'soumise';

/** Ligne de matériel telle que manipulée par le formulaire (avant envoi API). */
export interface LigneReservationLine {
  part: number;
  partName: string;
  quantiteDemandee: number;
  isVirtual: boolean;
}

/** Payload envoyé à l'API pour une ligne (`LigneReservationSerializer`). */
export interface LigneReservationPayload {
  part: number;
  quantite_demandee: number;
}

/** Valeurs manipulées par le formulaire Mantine (`useForm`). */
export interface ReservationFormValues {
  prestation: number | null;
  demandeur: number | null;
  date_retrait_prevue: Date | null;
  date_retour_prevue: Date | null;
  commentaire: string;
  lignes: LigneReservationLine[];
}

/** Réservation telle que renvoyée par l'API (`ReservationSerializer`). */
export interface Reservation {
  id: number;
  numero: string;
  prestation: number;
  prestation_nom: string;
  demandeur: number;
  demandeur_nom: string;
  validateur: number | null;
  statut: ReservationStatut | string;
  forced: boolean;
  date_demande: string;
  date_retrait_prevue: string | null;
  date_retour_prevue: string | null;
  date_retrait_reelle: string | null;
  date_retour_reelle: string | null;
  commentaire: string;
  lignes: Array<{
    id: number;
    part: number;
    quantite_demandee: number;
    quantite_livree: number;
    quantite_retournee: number;
    etat_retour: string;
    commentaire: string;
  }>;
  created_at: string;
  updated_at: string;
}
