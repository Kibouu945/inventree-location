/** Types de l'API SCRUM-108 back-office utilisateurs. */

/** Réponse paginée DRF, commune aux deux listes back-office. */
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
}

export interface BackOfficeUserFormValues {
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  is_active: boolean;
  roles: string[];
}
