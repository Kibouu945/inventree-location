/** Types de l'API catalogue (`/plugin/inventree-location/catalog/`). */

export interface CatalogPart {
  id: number;
  name: string;
  description: string;
  IPN: string | null;
  active: boolean;
  category: number | null;
  category_name: string | null;
  stock_available: number;
  image_url: string | null;
  rentable: boolean;
  consommable: boolean;
}

/** Réponse paginée DRF (PageNumberPagination). */
export interface CatalogPage {
  count: number;
  next: string | null;
  previous: string | null;
  results: CatalogPart[];
}
