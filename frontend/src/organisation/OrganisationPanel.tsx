// Conteneur à onglets pour la gestion manifestation / prestation / lieu (ORG-01).
import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Stack, Tabs, Title } from '@mantine/core';
import { useState } from 'react';

import { LieuxTab } from './LieuxTab';
import { ManifestationsTab } from './ManifestationsTab';
import { PrestationsTab } from './PrestationsTab';

export function OrganisationPanel({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const [onglet, setOnglet] = useState<string | null>('manifestations');
  // Le clic sur le nombre de prestations d'une manifestation bascule d'onglet
  // en emportant le filtre (point 4.2.5.1).
  const [manifestationFiltre, setManifestationFiltre] = useState<{
    id: number;
    nom: string;
  } | null>(null);

  return (
    <Stack gap='md'>
      <Title order={4} c={context.theme.primaryColor}>
        Organisation
      </Title>

      <Tabs
        value={onglet}
        onChange={(valeur) => {
          setOnglet(valeur);
          // Changer d'onglet à la main efface le filtre hérité.
          if (valeur !== 'prestations') {
            setManifestationFiltre(null);
          }
        }}
      >
        <Tabs.List>
          <Tabs.Tab value='manifestations'>Manifestations</Tabs.Tab>
          <Tabs.Tab value='prestations'>Prestations</Tabs.Tab>
          <Tabs.Tab value='lieux'>Lieux</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value='manifestations' pt='md'>
          <ManifestationsTab
            context={context}
            onVoirPrestations={(manifestation) => {
              setManifestationFiltre({
                id: manifestation.id,
                nom: manifestation.nom
              });
              setOnglet('prestations');
            }}
          />
        </Tabs.Panel>
        <Tabs.Panel value='prestations' pt='md'>
          <PrestationsTab
            context={context}
            manifestationFiltre={manifestationFiltre}
          />
        </Tabs.Panel>
        <Tabs.Panel value='lieux' pt='md'>
          <LieuxTab context={context} />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  );
}
