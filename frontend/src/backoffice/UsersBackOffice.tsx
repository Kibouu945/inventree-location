import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Alert, Stack, Tabs, Title } from '@mantine/core';

import { canManageBackOffice, canManageClients } from '../roles';
import { ClientsTab } from './ClientsTab';
import { ContactsTab } from './ContactsTab';
import { UsersTab } from './UsersTab';

export function UsersBackOffice({
  context
}: {
  context: InvenTreePluginContext;
}) {
  // Deux publics pour un même écran : l'admin y gère les comptes, le
  // gestionnaire n'y tient que son fichier clients. On masque l'onglet plutôt
  // que de le laisser buter sur un 403.
  const gereLesComptes = canManageBackOffice(context);

  if (!canManageClients(context)) {
    return (
      <Alert color='red' title='Accès refusé'>
        Cette interface est réservée aux administrateurs et aux gestionnaires.
      </Alert>
    );
  }

  return (
    <Stack gap='md'>
      <Title order={4} c={context.theme.primaryColor}>
        {gereLesComptes ? 'Back-office utilisateurs' : 'Clients et contacts'}
      </Title>

      <Tabs defaultValue={gereLesComptes ? 'utilisateurs' : 'clients'}>
        <Tabs.List>
          {gereLesComptes && (
            <Tabs.Tab value='utilisateurs'>Utilisateurs</Tabs.Tab>
          )}
          <Tabs.Tab value='clients'>Clients</Tabs.Tab>
          <Tabs.Tab value='contacts'>Contacts</Tabs.Tab>
        </Tabs.List>

        {gereLesComptes && (
          <Tabs.Panel value='utilisateurs' pt='md'>
            <UsersTab context={context} />
          </Tabs.Panel>
        )}

        <Tabs.Panel value='clients' pt='md'>
          <ClientsTab context={context} />
        </Tabs.Panel>

        <Tabs.Panel value='contacts' pt='md'>
          <ContactsTab context={context} />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
