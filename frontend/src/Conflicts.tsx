import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';

import { ConflictsList } from './conflicts/ConflictsList';
import { WidgetScroll } from './WidgetScroll';

export function renderInvenTreeLocationConflicts(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return (
    <WidgetScroll locale={context.locale}>
      <ConflictsList context={context} />
    </WidgetScroll>
  );
}
