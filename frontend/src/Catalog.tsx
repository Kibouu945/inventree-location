// Point d'entrée du catalogue (CAT-02 / CAT-03), rendu comme dashboard item.
import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';

import { CatalogList } from './catalog/CatalogList';
import { WidgetScroll } from './WidgetScroll';

/** Fonction appelée par InvenTree pour rendre l'écran catalogue. */
export function renderInvenTreeLocationCatalog(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return (
    <WidgetScroll locale={context.locale}>
      <CatalogList context={context} />
    </WidgetScroll>
  );
}
