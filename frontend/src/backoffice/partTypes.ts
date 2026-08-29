/** Types de l'API SCRUM-111 back-office Parts. */

export type { Page } from './types';

export interface BackOfficePart {
  id: number;
  NOI: string;
  name: string;
  description: string;
  link: string;
  active: boolean;
  salable: boolean;
  virtual: boolean;
  pack: boolean;
  /** Stock physique louable selon InvenTree — lecture seule. */
  stock_total: number;
  is_rentable: boolean;
  consommable: boolean;
  seuil_alerte_bas: number | null;
  seuil_alerte_haut: number | null;
  /** Coupe les alertes de seuil sans effacer les seuils (CDC V06). */
  alertes_desactivees: boolean;
}

export interface BackOfficePartFormValues {
  NOI: string;
  name: string;
  description: string;
  link: string;
  active: boolean;
  salable: boolean;
  virtual: boolean;
  is_rentable: boolean;
  consommable: boolean;
  seuil_alerte_bas: number | null;
  seuil_alerte_haut: number | null;
  alertes_desactivees: boolean;
  /** Quantité à mettre en stock : crée un StockItem InvenTree. */
  stock_initial: number;
}
