// Point d'entrée « Organisation » (ORG-01), rendu comme dashboard item.
import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';

import { OrganisationPanel } from './organisation/OrganisationPanel';
import { WidgetScroll } from './WidgetScroll';

/**
 * Fonction appelée par InvenTree pour rendre l'écran de gestion des
 * manifestations, prestations et lieux.
 */
export function renderInvenTreeLocationOrganisation(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return (
    <WidgetScroll>
      <OrganisationPanel context={context} />
    </WidgetScroll>
  );
}
