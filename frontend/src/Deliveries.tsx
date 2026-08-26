import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';

import { DeliveriesList } from './delivery/DeliveriesList';

export function renderInvenTreeLocationDeliveries(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return <DeliveriesList context={context} />;
}
