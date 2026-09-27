import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Alert, Stack, Tabs, Title } from '@mantine/core';

import { useState } from 'react';

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
  // gestionnaire n'y tient que son fichier clients.
  const gereLesComptes = canManageBackOffice(context);

  const [onglet, setOnglet] = useState<string | null>(
    gereLesComptes ? 'utilisateurs' : 'clients'
  );
  // Client tout juste créé : l'onglet Contacts ouvre son premier
  // interlocuteur, client déjà choisi (point 4.4.1).
  const [clientAEnchainer, setClientAEnchainer] = useState<{
    id: number;
    nom: string;
  } | null>(null);

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

      <Tabs value={onglet} onChange={setOnglet}>
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
          <ClientsTab
            context={context}
            onClientCree={(client) => {
              setClientAEnchainer(client);
              setOnglet('contacts');
            }}
          />
        </Tabs.Panel>

        <Tabs.Panel value='contacts' pt='md'>
          <ContactsTab
            context={context}
            clientAEnchainer={clientAEnchainer}
            onEnchainementFait={() => setClientAEnchainer(null)}
          />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
