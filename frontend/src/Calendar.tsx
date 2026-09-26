// Point d'entrée du calendrier des réservations (DIS-01), rendu comme
// dashboard item.
import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';

import { ReservationCalendar } from './reservation/ReservationCalendar';
import { WidgetScroll } from './WidgetScroll';

/** Fonction appelée par InvenTree pour rendre l'écran calendrier. */
export function renderInvenTreeLocationCalendar(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return (
    <WidgetScroll locale={context.locale}>
      <ReservationCalendar context={context} />
    </WidgetScroll>
  );
}
