import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Alert, Stack, Tabs, Title } from '@mantine/core';

import { canManageBackOffice } from '../roles';
import { GroupesTab } from './GroupesTab';
import { UsersTab } from './UsersTab';

export function UsersBackOffice({
  context
}: {
  context: InvenTreePluginContext;
}) {
  if (!canManageBackOffice(context)) {
    return (
      <Alert color='red' title='Accès refusé'>
        Cette interface est réservée aux administrateurs du module.
      </Alert>
    );
  }

  return (
    <Stack gap='md'>
      <Title order={4} c={context.theme.primaryColor}>
        Back-office utilisateurs
      </Title>

      <Tabs defaultValue='utilisateurs'>
        <Tabs.List>
          <Tabs.Tab value='utilisateurs'>Utilisateurs</Tabs.Tab>
          <Tabs.Tab value='groupes'>Groupes</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value='utilisateurs' pt='md'>
          <UsersTab context={context} />
        </Tabs.Panel>

        <Tabs.Panel value='groupes' pt='md'>
          <GroupesTab context={context} />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
