// Point d'entrée du widget « Alertes stock », rendu comme dashboard item.
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
