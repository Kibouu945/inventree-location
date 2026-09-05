// Point d'entrée SCRUM-108, rendu comme dashboard item.
import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';

import { UsersBackOffice } from './backoffice/UsersBackOffice';
import { WidgetScroll } from './WidgetScroll';

/**
 * Fonction appelée par InvenTree pour rendre le back-office utilisateurs.
 */
export function renderInvenTreeLocationBackOfficeUsers(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return (
    <WidgetScroll>
      <UsersBackOffice context={context} />
    </WidgetScroll>
  );
}
