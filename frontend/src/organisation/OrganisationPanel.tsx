// Conteneur à onglets pour la gestion manifestation / prestation / lieu (ORG-01).
import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Stack, Tabs, Title } from '@mantine/core';

import { LieuxTab } from './LieuxTab';
import { ManifestationsTab } from './ManifestationsTab';
import { PrestationsTab } from './PrestationsTab';

export function OrganisationPanel({
  context
}: {
  context: InvenTreePluginContext;
}) {
  return (
    <Stack gap='md'>
      <Title order={4} c={context.theme.primaryColor}>
        Organisation
      </Title>

      <Tabs defaultValue='manifestations'>
        <Tabs.List>
          <Tabs.Tab value='manifestations'>Manifestations</Tabs.Tab>
          <Tabs.Tab value='prestations'>Prestations</Tabs.Tab>
          <Tabs.Tab value='lieux'>Lieux</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value='manifestations' pt='md'>
          <ManifestationsTab context={context} />
        </Tabs.Panel>
        <Tabs.Panel value='prestations' pt='md'>
          <PrestationsTab context={context} />
        </Tabs.Panel>
        <Tabs.Panel value='lieux' pt='md'>
          <LieuxTab context={context} />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
