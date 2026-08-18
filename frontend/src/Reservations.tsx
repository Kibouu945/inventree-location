// Point d'entrée des réservations (RES-03), rendu comme dashboard item.
import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';

import { ReservationsList } from './reservation/ReservationsList';

/**
 * Fonction appelée par InvenTree pour rendre l'écran réservations.
 */
export function renderInvenTreeLocationReservations(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return <ReservationsList context={context} />;
}
