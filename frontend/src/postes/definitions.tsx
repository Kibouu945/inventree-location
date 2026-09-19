// Définition des postes : quels écrans, pour quels rôles.
//
// Un poste est l'écran unique d'un métier, à la place de l'empilement de
// widgets refusé en revue du 09/09/2026. Les écrans sont **chargés
// paresseusement** : sans ça le bundle embarquerait FullCalendar et Leaflet
// pour un livreur qui n'ouvre ni planning ni carte.
//
// Cette table double `pages.POSTES` côté serveur, comme `roles.ts` double
// `roles.py` : le serveur refuse, le client évite de proposer. À garder aligné.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  IconAlertTriangle,
  IconBellExclamation,
  IconBox,
  IconCalendarEvent,
  IconCalendarMonth,
  IconListSearch,
  IconPackageImport,
  IconSitemap,
  IconTruckDelivery,
  IconUsers,
  IconUsersGroup
} from '@tabler/icons-react';
import { lazy, type ReactNode } from 'react';

import {
  ACHETEUR,
  ADMIN,
  GESTIONNAIRE,
  LECTEUR,
  LIVREUR,
  MAGASINIER,
  userRoles
} from '../roles';

const Arborescence = lazy(() =>
  import('../arborescence/Arborescence').then((m) => ({
    default: m.Arborescence
  }))
);
const CatalogList = lazy(() =>
  import('../catalog/CatalogList').then((m) => ({ default: m.CatalogList }))
);
const ConflictsList = lazy(() =>
  import('../conflicts/ConflictsList').then((m) => ({
    default: m.ConflictsList
  }))
);
const DeliveriesList = lazy(() =>
  import('../delivery/DeliveriesList').then((m) => ({
    default: m.DeliveriesList
  }))
);
const OrganisationPanel = lazy(() =>
  import('../organisation/OrganisationPanel').then((m) => ({
    default: m.OrganisationPanel
  }))
);
const PartsBackOffice = lazy(() =>
  import('../backoffice/PartsBackOffice').then((m) => ({
    default: m.PartsBackOffice
  }))
);
const RamassagesList = lazy(() =>
  import('../ramassage/RamassagesList').then((m) => ({
    default: m.RamassagesList
  }))
);
const Planning = lazy(() =>
  import('../planning/Planning').then((m) => ({ default: m.Planning }))
);
const ReservationsList = lazy(() =>
  import('../reservation/ReservationsList').then((m) => ({
    default: m.ReservationsList
  }))
);
const StockAlerts = lazy(() =>
  import('../stock/StockAlertsList').then((m) => ({
    default: m.StockAlertsList
  }))
);
const UsersBackOffice = lazy(() =>
  import('../backoffice/UsersBackOffice').then((m) => ({
    default: m.UsersBackOffice
  }))
);

export interface OngletDefinition {
  value: string;
  label: string;
  icon: ReactNode;
  render: (context: InvenTreePluginContext) => ReactNode;
}

export interface PosteDefinition {
  titre: string;
  roles: string[];
  onglets: OngletDefinition[];
}

/** Taille d'icône des panneaux natifs. */
const TAILLE_ICONE = 18;

function onglet(
  value: string,
  label: string,
  Icone: React.ComponentType<{ size?: number }>,
  Composant: React.ComponentType<{ context: InvenTreePluginContext }>
): OngletDefinition {
  return {
    value,
    label,
    icon: <Icone size={TAILLE_ICONE} />,
    render: (context) => <Composant context={context} />
  };
}

// L'arborescence de la maquette, premier écran du gestionnaire.
const MANIFESTATIONS = onglet(
  'manifestations',
  'Manifestations',
  IconSitemap,
  Arborescence
);

// La saisie : les formulaires vivent ici, pas dans l'arborescence.
const FICHES = onglet('fiches', 'Fiches', IconUsers, OrganisationPanel);
const RESERVATIONS = onglet(
  'reservations',
  'Réservations',
  IconCalendarEvent,
  ReservationsList
);
// La maquette du CDC : manifestations étalées sur les jours, fiche au survol.
// L'ancien calendrier mensuel des réservations est remplacé — il montrait les
// bons, pas les manifestations, et ni volume ni avancement.
const PLANNING = onglet('planning', 'Planning', IconCalendarMonth, Planning);
// Le fichier clients. Même écran que le back-office de l'admin, qui masque de
// lui-même l'onglet Utilisateurs à qui ne gère pas les comptes.
const CLIENTS = onglet('clients', 'Clients', IconUsersGroup, UsersBackOffice);
const CATALOGUE = onglet('catalogue', 'Catalogue', IconListSearch, CatalogList);
const CONFLITS = onglet(
  'conflits',
  'Conflits',
  IconAlertTriangle,
  ConflictsList
);
const ALERTES = onglet(
  'alertes',
  'Alertes stock',
  IconBellExclamation,
  StockAlerts
);
const LIVRAISONS = onglet(
  'livraisons',
  'Livraisons',
  IconTruckDelivery,
  DeliveriesList
);
const RAMASSAGES = onglet(
  'ramassages',
  'Ramassages',
  IconPackageImport,
  RamassagesList
);

//: Ordre = journée de travail du métier. Le premier écran est celui qu'on doit
//: voir en arrivant.
export const POSTES: Record<string, PosteDefinition> = {
  gestionnaire: {
    titre: 'Poste gestionnaire client',
    roles: [ADMIN, GESTIONNAIRE],
    // Devis, Factures et Histogramme (CDC §95-101) manquent : leurs écrans
    // n'existent pas, on ne pose pas d'onglet vide.
    onglets: [
      MANIFESTATIONS,
      CLIENTS,
      PLANNING,
      FICHES,
      RESERVATIONS,
      CATALOGUE,
      CONFLITS,
      ALERTES
    ]
  },
  magasinier: {
    titre: 'Poste magasinier',
    roles: [ADMIN, MAGASINIER],
    // Le catalogue reste faute d'écran stock dédié : c'est le seul qui donne
    // l'état article par article.
    onglets: [RAMASSAGES, CATALOGUE, ALERTES, RESERVATIONS]
  },
  livreur: {
    titre: 'Poste livreur',
    roles: [ADMIN, LIVREUR],
    onglets: [LIVRAISONS, RAMASSAGES]
  },
  acheteur: {
    titre: 'Poste acheteur',
    roles: [ADMIN, ACHETEUR],
    // Les commandes fournisseurs passent par les écrans natifs.
    onglets: [ALERTES, CATALOGUE]
  },
  lecteur: {
    titre: 'Poste lecture',
    roles: [ADMIN, LECTEUR],
    onglets: [PLANNING, RESERVATIONS, CATALOGUE, CONFLITS]
  },
  admin: {
    titre: 'Poste administration',
    roles: [ADMIN],
    // « Voit tout mais ne travaille pas au quotidien » : les utilisateurs
    // d'abord.
    onglets: [
      onglet('utilisateurs', 'Utilisateurs', IconUsersGroup, UsersBackOffice),
      onglet('articles', 'Articles', IconBox, PartsBackOffice),
      MANIFESTATIONS,
      PLANNING,
      FICHES,
      RESERVATIONS,
      LIVRAISONS,
      RAMASSAGES,
      CONFLITS,
      ALERTES
    ]
  }
};

/**
 * Le poste de l'utilisateur courant, ou `null` sans rôle métier.
 *
 * **Un seul** poste : règle « un acteur interne, un rôle ». L'admin a le poste
 * complet ; un superutilisateur est traité comme un admin.
 */
export function posteDeLUtilisateur(
  context: InvenTreePluginContext
): { cle: string; definition: PosteDefinition } | null {
  if (context.user?.isSuperuser?.()) {
    return { cle: 'admin', definition: POSTES.admin };
  }

  const mesRoles = new Set(userRoles(context));

  // L'admin d'abord : poste complet même si un autre rôle traîne.
  if (mesRoles.has(ADMIN)) {
    return { cle: 'admin', definition: POSTES.admin };
  }

  const trouve = Object.entries(POSTES).find(
    ([cle, definition]) =>
      cle !== 'admin' && definition.roles.some((r) => mesRoles.has(r))
  );

  return trouve ? { cle: trouve[0], definition: trouve[1] } : null;
}
