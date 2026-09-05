import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';

import { DeliveriesList } from './delivery/DeliveriesList';
import { WidgetScroll } from './WidgetScroll';

export function renderInvenTreeLocationDeliveries(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return (
    <WidgetScroll>
      <DeliveriesList context={context} />
    </WidgetScroll>
  );
}
