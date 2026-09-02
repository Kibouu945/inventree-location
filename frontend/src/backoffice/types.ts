/** Types de l'API back-office : utilisateurs, rôles et groupes. */

/** Réponse paginée DRF, commune aux listes back-office. */
export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface BackOfficeRole {
  name: string;
  label: string;
}

export interface BackOfficeUser {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  roles: string[];
  /** Porté par le `Profile`, imprimé sur le bon de livraison. */
  telephone: string;
  groupe: number | null;
  groupe_nom: string;
}

export interface BackOfficeUserFormValues {
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  is_active: boolean;
  roles: string[];
  telephone: string;
  /** `Select` Mantine travaille en chaîne : converti en entier à l'envoi. */
  groupe: string | null;
}

export interface BackOfficeGroupe {
  id: number;
  nom: string;
  code: string;
  adresse: string;
  membres: number;
}

export interface BackOfficeGroupeFormValues {
  nom: string;
  code: string;
  adresse: string;
}
