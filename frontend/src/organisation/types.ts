/** Types de l'API organisation (`/manifestations/`, `/prestations/`, `/lieux/`). */

/** Réponse paginée DRF (PageNumberPagination). */
export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export type StatutPrestation =
  | 'brouillon'
  | 'planifiee'
  | 'confirmee'
  | 'livree'
  | 'cloturee'
  | 'annulee';

export type StatutManifestation =
  | 'brouillon'
  | 'planifiee'
  | 'en_cours'
  | 'terminee'
  | 'annulee';

/** Manifestation telle que renvoyée par l'API (`ManifestationSerializer`). */
export interface Manifestation {
  id: number;
  nom: string;
  description: string;
  date_debut: string;
  date_fin: string;
  statut: StatutManifestation | string;
  // Statut réel : en_cours / terminée sont dérivés des dates côté serveur.
  statut_effectif: StatutManifestation | string;
  couleur: string;
  pourcent_remise_globale: string;
  client: number;
  contact: number | null;
  // Clé conservée : la source est le contact référent, à défaut le client.
  organisateur_nom: string;
  prestations_count: number;
  created_at: string;
  updated_at: string;
}

/** Client (`ClientSerializer`). */
export interface Client {
  id: number;
  nom: string;
  adresse: string;
  email: string | null;
  telephone: string;
  type_client: string;
  siret: string;
  actif: boolean;
}

/** Contact d'un client (`ContactSerializer`). */
export interface Contact {
  id: number;
  client: number;
  nom: string;
  prenom: string;
  nom_complet: string;
  email: string | null;
  telephone: string;
  actif: boolean;
}

/** Lieu géolocalisé autonome (`LieuSerializer`). */
export interface Lieu {
  id: number;
  nom: string;
  description: string;
  adresse: string;
  latitude: string | null;
  longitude: string | null;
  capacite: number | null;
  created_at: string;
  updated_at: string;
}

/** Ligne d'article d'une prestation (`LignePrestationSerializer`). */
export interface LignePrestation {
  id?: number;
  part: number;
  part_name?: string;
  quantite: number;
  commentaire?: string;
}

/** Article manipulé par le formulaire prestation (avant envoi API). */
export interface PrestationArticle {
  part: number;
  partName: string;
  quantite: number;
}

/** Prestation telle que renvoyée par l'API (`PrestationSerializer`). */
export interface Prestation {
  id: number;
  nom: string;
  date_debut: string;
  date_fin: string;
  description: string;
  statut: StatutPrestation | string;
  modifie_apres_devis: boolean;
  manifestation: number;
  manifestation_nom: string;
  lieu: number | null;
  lieu_detail: Lieu | null;
  lignes: LignePrestation[];
  created_at: string;
  updated_at: string;
}

/** Ligne de disponibilité renvoyée par le calcul de stock (STK-01). */
export interface StockLine {
  part_id: number;
  part_name: string;
  requested: number;
  total_stock: number;
  reserved: number;
  available: number;
  missing: number;
  shortage: boolean;
}

export interface StockResult {
  has_shortage: boolean;
  lines: StockLine[];
}

/** Extrait le message d'erreur DRF le plus parlant d'une exception API. */
export function apiErrorMessage(error: unknown, fallback: string): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data;

  if (typeof data === 'string') {
    return data;
  }

  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>;

    if (typeof record.detail === 'string') {
      return record.detail;
    }

    const parts: string[] = [];

    for (const [field, messages] of Object.entries(record)) {
      const text = Array.isArray(messages)
        ? messages.join(' ')
        : String(messages);
      parts.push(`${field}: ${text}`);
    }

    if (parts.length > 0) {
      return parts.join(' — ');
    }
  }

  return fallback;
}
