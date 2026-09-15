// Point d'entrée du widget « Alertes stock », rendu comme dashboard item.
//
// L'écran lui-même vit dans `stock/StockAlertsList` : il est aussi monté comme
// onglet dans les postes, et ne peut donc pas dépendre au runtime des globales
// qu'InvenTree ne fournit qu'aux widgets.
import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';

import { StockAlertsList } from './stock/StockAlertsList';
import { WidgetScroll } from './WidgetScroll';

export function renderInvenTreeLocationDashboardItem(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return (
    <WidgetScroll locale={context.locale}>
      <StockAlertsList context={context} />
    </WidgetScroll>
  );
}
