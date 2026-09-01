/** Types de l'API tournée livreur (`/plugin/inventree-location/deliveries/`). */
import type { LieuSummary } from '../reservation/types';

export interface DeliveryLigne {
  id: number;
  part: number;
  part_name: string;
  quantite_demandee: number;
  /** Un service : listé à part sur le bon, hors du total à charger. */
  is_virtual: boolean;
}

/** Livraison telle que renvoyée par l'API (`DeliverySerializer`). */
export interface Delivery {
  id: number;
  numero: string;
  statut: string;
  prestation_nom: string;
  demandeur_nom: string;
  lieu_detail: LieuSummary | null;
  organisateur_nom: string;
  organisateur_telephone: string;
  date_retrait_prevue: string | null;
  date_retour_prevue: string | null;
  commentaire: string;
  lignes: DeliveryLigne[];
  quantite_totale: number;
}
