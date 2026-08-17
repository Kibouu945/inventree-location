/** Types de l'API ramassages (`/plugin/inventree-location/ramassages/`). */

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface LieuRamassage {
  id: number;
  nom: string;
  adresse: string;
  latitude: string | null;
  longitude: string | null;
}

export interface RecapVehicule {
  vehicule: string;
  quantite_totale: number;
}

export interface LigneBonRamassage {
  id: number;
  part: number;
  part_nom: string;
  quantite_demandee: number;
  quantite_livree: number;
  quantite_a_ramasser: number;
  quantite_retournee: number;

  quantite_ramassee: number;
  quantite_sav: number;
  quantite_detruite: number;
  quantite_manquante: number;
  facturer_client: boolean;

  etat_retour: string;
  commentaire: string;
}

export interface Ramassage {
  id: number;
  numero: string;
  prestation: number;
  prestation_nom: string;
  manifestation_nom: string;
  demandeur: number;
  demandeur_nom: string;
  statut: string;
  date_ramassage: string | null;
  date_retrait_prevue: string | null;
  date_retour_prevue: string | null;
  lieux: LieuRamassage[];
  nb_objets: number;
  quantite_totale: number;
  recap_par_vehicule: RecapVehicule[];
}

export interface BonRamassageResponse {
  titre: string;
  generated_at: string;
  reservation: Ramassage & {
    lignes: LigneBonRamassage[];
    commentaire: string;
  };
}

export interface RetourRamassageLignePayload {
  ligne: number;
  quantite_ramassee: number;
  quantite_sav: number;
  quantite_detruite: number;
  quantite_manquante: number;
  facturer_client: boolean;
  commentaire: string;
}

export interface RetourRamassagePayload {
  commentaire: string;
  lignes: RetourRamassageLignePayload[];
}

export interface RetourRamassageResponse {
  reservation: number;
  numero: string;
  statut: string;
  updated_lines: Array<{
    id: number;
    part: number;
    quantite_ramassee: number;
    quantite_sav: number;
    quantite_detruite: number;
    quantite_manquante: number;
    facturer_client: boolean;
    etat_retour: string;
  }>;
  sav_tickets: number[];
}