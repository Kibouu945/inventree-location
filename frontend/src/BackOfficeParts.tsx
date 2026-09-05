// Point d'entrée SCRUM-111, rendu comme dashboard item.
import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';

import { PartsBackOffice } from './backoffice/PartsBackOffice';
import { WidgetScroll } from './WidgetScroll';

/**
 * Fonction appelée par InvenTree pour rendre le back-office Parts.
 */
export function renderInvenTreeLocationBackOfficeParts(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return (
    <WidgetScroll>
      <PartsBackOffice context={context} />
    </WidgetScroll>
  );
}
