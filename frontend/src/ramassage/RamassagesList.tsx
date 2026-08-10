// SCRUM-89 — Liste des ramassages + bon imprimable.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Modal,
  MultiSelect,
  Stack,
  Table,
  Text,
  TextInput,
  Title
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { useDebouncedValue } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import type { BonRamassageResponse, Page, Ramassage } from './types';

const RAMASSAGES_URL = '/plugin/inventree-location/ramassages/';

const STATUT_COLORS: Record<string, string> = {
  brouillon: 'gray',
  soumise: 'blue',
  validee: 'green',
  refusee: 'red',
  annulee: 'red',
  livree: 'teal',
  retournee: 'grape',
  cloturee: 'dark'
};

const STATUT_OPTIONS = [
  { value: 'brouillon', label: 'Brouillon' },
  { value: 'soumise', label: 'Soumise' },
  { value: 'validee', label: 'Validée' },
  { value: 'livree', label: 'Livrée' },
  { value: 'retournee', label: 'Retournée' }
];

interface BonModalState {
  open: boolean;
  reservationId?: number;
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return '—';
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function buildQuery(
  search: string,
  lieu: string,
  statuts: string[],
  dateRange: [string | null, string | null]
): Record<string, string | string[]> {
  const params: Record<string, string | string[]> = {};

  if (search.trim()) {
    params.search = search.trim();
  }

  if (lieu.trim()) {
    params.lieu = lieu.trim();
  }

  if (statuts.length > 0) {
    params.statut = statuts;
  }

  if (dateRange[0]) {
    params.date_from = dateRange[0];
  }

  if (dateRange[1]) {
    params.date_to = dateRange[1];
  }

  return params;
}

function lieuLabel(ramassage: Ramassage): string {
  const lieu = ramassage.lieu;

  if (!lieu) {
    return '—';
  }

  return lieu.nom || lieu.adresse || '—';
}

function BonRamassageContent({ bon }: { bon: BonRamassageResponse }) {
  const reservation = bon.reservation;

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={4}>{bon.titre}</Title>
        <Text size='sm' c='dimmed'>
          Généré le {formatDateTime(bon.generated_at)}
        </Text>
      </Group>

      <Table withTableBorder withColumnBorders>
        <Table.Tbody>
          <Table.Tr>
            <Table.Th>Numéro</Table.Th>
            <Table.Td>{reservation.numero}</Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Th>Manifestation</Table.Th>
            <Table.Td>{reservation.manifestation_nom || '—'}</Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Th>Prestation</Table.Th>
            <Table.Td>{reservation.prestation_nom || '—'}</Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Th>Demandeur</Table.Th>
            <Table.Td>{reservation.demandeur_nom || '—'}</Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Th>Date de ramassage</Table.Th>
            <Table.Td>{formatDateTime(reservation.date_ramassage)}</Table.Td>
          </Table.Tr>
          <Table.Tr>
            <Table.Th>Lieu</Table.Th>
            <Table.Td>{lieuLabel(reservation)}</Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>

      <Title order={5}>Matériel à ramasser</Title>

      <Table striped withTableBorder>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Article</Table.Th>
            <Table.Th>Demandée</Table.Th>
            <Table.Th>Livrée</Table.Th>
            <Table.Th>À ramasser</Table.Th>
            <Table.Th>Retournée</Table.Th>
            <Table.Th>État retour</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {reservation.lignes.map((ligne) => (
            <Table.Tr key={`${ligne.part}-${ligne.part_nom}`}>
              <Table.Td>{ligne.part_nom}</Table.Td>
              <Table.Td>{ligne.quantite_demandee}</Table.Td>
              <Table.Td>{ligne.quantite_livree}</Table.Td>
              <Table.Td>{ligne.quantite_a_ramasser}</Table.Td>
              <Table.Td>{ligne.quantite_retournee}</Table.Td>
              <Table.Td>{ligne.etat_retour || '—'}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      <Title order={5}>Récapitulatif par véhicule</Title>

      <Table striped withTableBorder>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Véhicule</Table.Th>
            <Table.Th>Quantité totale</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {reservation.recap_par_vehicule.map((recap) => (
            <Table.Tr key={recap.vehicule}>
              <Table.Td>{recap.vehicule}</Table.Td>
              <Table.Td>{recap.quantite_totale}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      {reservation.commentaire && (
        <>
          <Title order={5}>Commentaire</Title>
          <Text>{reservation.commentaire}</Text>
        </>
      )}
    </Stack>
  );
}

export function RamassagesList({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);

  const [lieu, setLieu] = useState('');
  const [debouncedLieu] = useDebouncedValue(lieu, 300);

  const [statuts, setStatuts] = useState<string[]>([]);
  const [dateRange, setDateRange] = useState<[string | null, string | null]>([
    null,
    null
  ]);

  const [bonModal, setBonModal] = useState<BonModalState>({ open: false });

  const params = buildQuery(debouncedSearch, debouncedLieu, statuts, dateRange);

  const query = useQuery<Ramassage[] | Page<Ramassage>>(
    {
      queryKey: ['ramassages', params],
      queryFn: async () => {
        const response = await context.api.get(RAMASSAGES_URL, { params });
        return response.data;
      }
    },
    context.queryClient
  );

  const bonQuery = useQuery<BonRamassageResponse>(
    {
      queryKey: ['bon-ramassage', bonModal.reservationId],
      enabled: bonModal.open && Boolean(bonModal.reservationId),
      queryFn: async () => {
        const response = await context.api.get(
          `${RAMASSAGES_URL}${bonModal.reservationId}/bon/`
        );

        return response.data;
      }
    },
    context.queryClient
  );

  const rows = Array.isArray(query.data)
    ? query.data
    : (query.data?.results ?? []);

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={4} c={context.theme.primaryColor}>
          Mes ramassages
        </Title>
      </Group>

      <Group align='flex-end' gap='md' wrap='wrap'>
        <TextInput
          label='Recherche'
          placeholder='Numéro, prestation, demandeur…'
          value={search}
          onChange={(event) => setSearch(event.currentTarget.value)}
          w={260}
        />

        <TextInput
          label='Lieu'
          placeholder='Nom ou adresse du lieu'
          value={lieu}
          onChange={(event) => setLieu(event.currentTarget.value)}
          w={240}
        />

        <MultiSelect
          label='Statut'
          placeholder='Tous'
          data={STATUT_OPTIONS}
          value={statuts}
          onChange={setStatuts}
          clearable
          w={240}
        />

        <DatePickerInput
          type='range'
          label='Date de ramassage'
          placeholder='Du — au'
          value={dateRange}
          onChange={setDateRange}
          clearable
          w={260}
        />
      </Group>

      {query.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger les ramassages.
        </Alert>
      )}

      {query.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : rows.length === 0 ? (
        <Text c='dimmed'>Aucun ramassage à afficher.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Numéro</Table.Th>
              <Table.Th>Demandeur</Table.Th>
              <Table.Th>Prestation</Table.Th>
              <Table.Th>Lieu</Table.Th>
              <Table.Th>Date ramassage</Table.Th>
              <Table.Th>Statut</Table.Th>
              <Table.Th>Qté totale</Table.Th>
              <Table.Th>Bon</Table.Th>
            </Table.Tr>
          </Table.Thead>

          <Table.Tbody>
            {rows.map((ramassage) => (
              <Table.Tr key={ramassage.id}>
                <Table.Td>{ramassage.numero}</Table.Td>
                <Table.Td>{ramassage.demandeur_nom || '—'}</Table.Td>
                <Table.Td>{ramassage.prestation_nom || '—'}</Table.Td>
                <Table.Td>{lieuLabel(ramassage)}</Table.Td>
                <Table.Td>{formatDateTime(ramassage.date_ramassage)}</Table.Td>
                <Table.Td>
                  <Badge color={STATUT_COLORS[ramassage.statut] ?? 'gray'}>
                    {ramassage.statut}
                  </Badge>
                </Table.Td>
                <Table.Td>{ramassage.quantite_totale}</Table.Td>
                <Table.Td>
                  <Button
                    size='xs'
                    variant='light'
                    onClick={() =>
                      setBonModal({
                        open: true,
                        reservationId: ramassage.id
                      })
                    }
                  >
                    Voir / imprimer
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Modal
        opened={bonModal.open}
        onClose={() => setBonModal({ open: false })}
        size='xl'
        title='Bon de ramassage'
      >
        {bonQuery.isLoading ? (
          <Group justify='center' p='xl'>
            <Loader />
          </Group>
        ) : bonQuery.isError ? (
          <Alert color='red' title='Erreur'>
            Impossible de charger le bon de ramassage.
          </Alert>
        ) : bonQuery.data ? (
          <Stack gap='md'>
            <Group justify='flex-end'>
              <Button onClick={() => window.print()}>Imprimer</Button>
            </Group>

            <BonRamassageContent bon={bonQuery.data} />
          </Stack>
        ) : null}
      </Modal>
    </Stack>
  );
}
