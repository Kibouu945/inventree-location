/** Types de l'API SCRUM-111 back-office Parts. */

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

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
  stock_total_inventree: number;
  is_rentable: boolean;
  consommable: boolean;
  stock_total: number;
  seuil_alerte_bas: number | null;
  seuil_alerte_haut: number | null;
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
  stock_total: number;
  seuil_alerte_bas: number | null;
  seuil_alerte_haut: number | null;
  alertes_desactivees: boolean;
  stock_initial: number;
}
