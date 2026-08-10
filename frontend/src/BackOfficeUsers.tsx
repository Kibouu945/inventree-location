// Point d'entrée SCRUM-108, rendu comme dashboard item.
import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';

import { UsersBackOffice } from './backoffice/UsersBackOffice';

/**
 * Fonction appelée par InvenTree pour rendre le back-office utilisateurs.
 */
export function renderInvenTreeLocationBackOfficeUsers(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return <UsersBackOffice context={context} />;
}