// Point d'entrée des réservations (RES-03), rendu comme dashboard item.
import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';

import { ReservationsList } from './reservation/ReservationsList';
import { WidgetScroll } from './WidgetScroll';

/**
 * Fonction appelée par InvenTree pour rendre l'écran réservations.
 */
export function renderInvenTreeLocationReservations(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return (
    <WidgetScroll locale={context.locale}>
      <ReservationsList context={context} />
    </WidgetScroll>
  );
}
