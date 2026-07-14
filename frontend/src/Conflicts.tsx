import {
    checkPluginVersion,
    type InvenTreePluginContext
} from '@inventreedb/ui';

import { ConflictsList } from './conflicts/ConflictsList';

export function renderInvenTreeLocationConflicts(
    context: InvenTreePluginContext
) {
    checkPluginVersion(context);
    return <ConflictsList context={context} />;
}
