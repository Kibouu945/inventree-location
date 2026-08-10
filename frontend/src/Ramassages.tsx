// Point d'entrée SCRUM-89, rendu comme dashboard item.
import {
  checkPluginVersion,
  type InvenTreePluginContext
} from '@inventreedb/ui';

import { RamassagesList } from './ramassage/RamassagesList';

/**
 * Fonction appelée par InvenTree pour rendre l'écran ramassages.
 */
export function renderInvenTreeLocationRamassages(
  context: InvenTreePluginContext
) {
  checkPluginVersion(context);
  return <RamassagesList context={context} />;
}