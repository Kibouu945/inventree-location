// Nature d'un article du catalogue, en un badge.
import { Badge } from '@mantine/core';

export function PartKindBadge({
  isVirtual,
  consommable,
  rentable
}: {
  isVirtual?: boolean;
  consommable?: boolean;
  rentable?: boolean;
}) {
  if (isVirtual) {
    return <Badge color='violet'>Service</Badge>;
  }

  if (consommable) {
    return <Badge color='orange'>Consommable</Badge>;
  }

  if (rentable) {
    return <Badge color='green'>Louable</Badge>;
  }

  return <Badge color='gray'>Non-louable</Badge>;
}
