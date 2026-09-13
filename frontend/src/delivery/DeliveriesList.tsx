// Écran "Tournées livreur" : livraisons à effectuer, filtrables par date /
// lieu / statut, avec bascule liste / calendrier / carte et bon de livraison
// imprimable par ligne.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Chip,
  Group,
  Loader,
  MultiSelect,
  SegmentedControl,
  Stack,
  Table,
  Text,
  Title
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import type { Page, Ramassage } from '../ramassage/types';
import { canMarquerLivree, hasAnyRole, LIVREUR } from '../roles';
import { ownsKeys, syncOwnedParams } from '../urlState';
import { DeliveryCalendar } from './DeliveryCalendar';
import { DeliveryNote } from './DeliveryNote';
import { DeliveryStatusForm } from './DeliveryStatusForm';
import {
  buildDeliveryQuery,
  DEFAULT_DELIVERY_FILTERS,
  DELIVERY_URL_KEYS,
  type DeliveryFiltersState,
  parseDeliveryFilters,
  serializeDeliveryFilters
} from './deliveryParams';
import { TourneeView } from './TourneeView';
import type { Delivery } from './types';

const DELIVERIES_URL = '/plugin/inventree-location/deliveries/';
const LIEUX_URL = '/plugin/inventree-location/lieux/';
const RAMASSAGES_URL = '/plugin/inventree-location/ramassages/';

/** Plafond de `LieuPagination` côté serveur : au-delà, on le signale. */
const MAX_RAMASSAGES_TOURNEE = 100;

const STATUT_COLORS: Record<string, string> = {
  validee: 'green',
  livree: 'teal'
};

const STATUT_OPTIONS = [
  { value: 'validee', label: 'À livrer (validée)' },
  { value: 'livree', label: 'Livrée' }
];

const VIEW_OPTIONS = [
  { value: 'liste', label: 'Liste' },
  { value: 'calendrier', label: 'Calendrier' },
  { value: 'carte', label: 'Tournée' }
];

interface LieuOption {
  id: number;
  nom: string;
}

function apiErrorDetail(error: unknown): string {
  const data = (error as { response?: { data?: { detail?: string } } })
    ?.response?.data;
  return data?.detail ?? 'Action impossible.';
}

const ownsDeliveryKey = ownsKeys(DELIVERY_URL_KEYS);

function syncUrl(filters: DeliveryFiltersState) {
  syncOwnedParams(
    ownsDeliveryKey,
    new URLSearchParams(serializeDeliveryFilters(filters))
  );
}

function initialFilters(): DeliveryFiltersState {
  if (typeof window === 'undefined') {
    return DEFAULT_DELIVERY_FILTERS;
  }

  return parseDeliveryFilters(window.location.search);
}

export function DeliveriesList({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const [filters, setFilters] = useState<DeliveryFiltersState>(initialFilters);
  const [noteDelivery, setNoteDelivery] = useState<Delivery | null>(null);
  const [statusDelivery, setStatusDelivery] = useState<Delivery | null>(null);

  const isLivreur = hasAnyRole(context, [LIVREUR]);
  const currentUserId = context.user?.userId?.();

  useEffect(() => {
    syncUrl(filters);
  }, [filters]);

  const params = buildDeliveryQuery(filters);

  const query = useQuery<Delivery[]>(
    {
      queryKey: ['deliveries', params],
      queryFn: async () => {
        const response = await context.api.get(DELIVERIES_URL, {
          params,
          // Clés répétées `statut=a&statut=b` (le backend lit getlist).
          paramsSerializer: { indexes: null }
        });
        return response.data as Delivery[];
      },
      // Le pool commun (US-18) change sous l'action d'autres livreurs : sans
      // ça, une livraison relâchée par un livreur reste invisible pour les
      // autres tant qu'ils ne rechargent pas la page à la main.
      refetchInterval: 15000,
      refetchOnWindowFocus: true
    },
    context.queryClient
  );

  const acceptMutation = useMutation(
    {
      mutationFn: async (deliveryId: number) => {
        const response = await context.api.post(
          `${DELIVERIES_URL}${deliveryId}/accepter/`
        );
        return response.data;
      },
      onSuccess: () => {
        context.queryClient.invalidateQueries({ queryKey: ['deliveries'] });
        notifications.show({
          title: 'Livraison acceptée',
          message: 'Cette livraison vous est désormais assignée.',
          color: 'green'
        });
      },
      onError: (error: unknown) => {
        // Course perdue (livraison prise entre-temps) : la vue est stale,
        // on la resynchronise plutôt que de laisser le bouton « Accepter »
        // réapparaître comme si de rien n'était.
        context.queryClient.invalidateQueries({ queryKey: ['deliveries'] });
        notifications.show({
          title: 'Action impossible',
          message: apiErrorDetail(error),
          color: 'red'
        });
      }
    },
    context.queryClient
  );

  const releaseMutation = useMutation(
    {
      mutationFn: async (deliveryId: number) => {
        const response = await context.api.delete(
          `${DELIVERIES_URL}${deliveryId}/accepter/`
        );
        return response.data;
      },
      onSuccess: () => {
        context.queryClient.invalidateQueries({ queryKey: ['deliveries'] });
      },
      onError: (error: unknown) => {
        notifications.show({
          title: 'Action impossible',
          message: apiErrorDetail(error),
          color: 'red'
        });
      }
    },
    context.queryClient
  );

  const peutMarquerLivree = canMarquerLivree(context);

  const livrerMutation = useMutation(
    {
      mutationFn: async (id: number) => {
        const response = await context.api.post(
          `${DELIVERIES_URL}${id}/livrer/`
        );
        return response.data;
      },
      onSuccess: () => {
        // La réservation quitte « à livrer » : les deux listes changent.
        context.queryClient.invalidateQueries({ queryKey: ['deliveries'] });
        context.queryClient.invalidateQueries({ queryKey: ['reservations'] });
        context.queryClient.invalidateQueries({ queryKey: ['ramassages'] });
        // Une réservation livrée devient un ramassage à venir.
        context.queryClient.invalidateQueries({
          queryKey: ['tournee-ramassages']
        });
        notifications.show({
          title: 'Livrée',
          message: 'Réservation marquée livrée.',
          color: 'green'
        });
      },
      onError: () => {
        notifications.show({
          title: 'Action impossible',
          message: "La réservation n'a pas pu être marquée livrée.",
          color: 'red'
        });
      }
    },
    context.queryClient
  );

  const lieuxQuery = useQuery<
    { id: number; nom: string }[] | { results: LieuOption[] }
  >(
    {
      queryKey: ['delivery-lieu-options'],
      queryFn: async () => {
        const response = await context.api.get(LIEUX_URL, {
          params: { page_size: 100 }
        });
        return response.data;
      }
    },
    context.queryClient
  );

  // La tournée mélange dépose et reprise : les ramassages ne sont chargés que
  // pour cette vue, et l'API les filtre par nom de lieu là où les livraisons
  // le font par id — on retombe donc sur un filtrage client par id.
  const ramassagesQuery = useQuery<Page<Ramassage>>(
    {
      queryKey: ['tournee-ramassages', params.date_from, params.date_to],
      enabled: filters.viewMode === 'carte',
      queryFn: async () => {
        const response = await context.api.get(RAMASSAGES_URL, {
          params: {
            page_size: MAX_RAMASSAGES_TOURNEE,
            ...(params.date_from ? { date_from: params.date_from } : {}),
            ...(params.date_to ? { date_to: params.date_to } : {})
          }
        });
        return response.data as Page<Ramassage>;
      }
    },
    context.queryClient
  );

  const ramassages = useMemo(() => {
    const resultats = ramassagesQuery.data?.results ?? [];

    if (filters.lieux.length === 0) {
      return resultats;
    }

    const retenus = new Set(filters.lieux);

    return resultats.filter(
      (ramassage) => ramassage.lieu && retenus.has(ramassage.lieu.id)
    );
  }, [ramassagesQuery.data, filters.lieux]);

  const ramassagesTronques =
    (ramassagesQuery.data?.count ?? 0) >
    (ramassagesQuery.data?.results.length ?? 0);

  const lieuOptions = useMemo(() => {
    const payload = lieuxQuery.data;

    if (!payload) {
      return [];
    }

    const lieux = Array.isArray(payload) ? payload : payload.results;

    return lieux.map((lieu) => ({ value: String(lieu.id), label: lieu.nom }));
  }, [lieuxQuery.data]);

  const rows = query.data ?? [];

  function updateFilters(patch: Partial<DeliveryFiltersState>) {
    setFilters((current) => ({ ...current, ...patch }));
  }

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={4} c={context.theme.primaryColor}>
          Tournées livreur
        </Title>
        <SegmentedControl
          value={filters.viewMode}
          onChange={(value) =>
            updateFilters({
              viewMode: value as DeliveryFiltersState['viewMode']
            })
          }
          data={VIEW_OPTIONS}
        />
      </Group>

      <Group align='flex-end' gap='md' wrap='wrap'>
        {/* Le livreur ouvre son écran sur sa journée, pas sur l'historique
            complet (revue interne du 07/09/2026). Choisir un horizon efface
            la période libre, et inversement : les deux répondent à la même
            question, les cumuler ne voudrait rien dire. */}
        <Stack gap={4}>
          <Text size='sm' fw={500}>
            Quand
          </Text>
          <SegmentedControl
            value={
              filters.dateRange[0] || filters.dateRange[1]
                ? ''
                : filters.horizon
            }
            onChange={(value) =>
              updateFilters({
                horizon: value as DeliveryFiltersState['horizon'],
                dateRange: [null, null]
              })
            }
            data={[
              { label: "Aujourd'hui", value: 'jour' },
              { label: 'À venir', value: 'avenir' },
              { label: 'Tout', value: 'tout' }
            ]}
          />
        </Stack>
        <DatePickerInput
          type='range'
          label='Période précise'
          placeholder='Toute autre période'
          value={filters.dateRange}
          onChange={(value) =>
            updateFilters({
              dateRange: [value[0], value[1]],
              // Une période choisie remplace l'horizon plutôt que de s'y
              // ajouter : sinon « Aujourd'hui » resterait allumé sur une
              // liste qui montre le mois prochain.
              horizon:
                value[0] || value[1] ? 'tout' : DEFAULT_DELIVERY_FILTERS.horizon
            })
          }
          clearable
          valueFormat='DD/MM/YYYY'
          w={240}
        />
        <MultiSelect
          label='Lieu'
          placeholder='Tous'
          data={lieuOptions}
          value={filters.lieux.map(String)}
          onChange={(values) =>
            updateFilters({
              lieux: values
                .map((value) => Number.parseInt(value, 10))
                .filter((value) => Number.isInteger(value))
            })
          }
          clearable
          w={240}
        />
        <Button
          variant='default'
          onClick={() => setFilters(DEFAULT_DELIVERY_FILTERS)}
        >
          Reset filtres
        </Button>
      </Group>

      <Stack gap={6}>
        <Text size='sm' fw={500}>
          Statuts
        </Text>
        <Chip.Group
          multiple
          value={filters.statuts}
          onChange={(values) => updateFilters({ statuts: values })}
        >
          <Group gap='xs' wrap='wrap'>
            {STATUT_OPTIONS.map((option) => (
              <Chip key={option.value} value={option.value}>
                {option.label}
              </Chip>
            ))}
          </Group>
        </Chip.Group>
      </Stack>

      {query.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger les livraisons.
        </Alert>
      )}

      {query.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : filters.viewMode === 'carte' ? (
        <Stack gap='sm'>
          {ramassagesQuery.isError && (
            <Alert color='yellow' variant='light'>
              Les ramassages n'ont pas pu être chargés : la tournée ne montre
              que les livraisons.
            </Alert>
          )}

          {ramassagesTronques && (
            <Alert color='yellow' variant='light'>
              Plus de {MAX_RAMASSAGES_TOURNEE} ramassages sur cette période :
              seuls les {MAX_RAMASSAGES_TOURNEE} premiers sont dans la tournée.
              Resserrez la période.
            </Alert>
          )}

          <TourneeView
            deliveries={rows}
            ramassages={ramassages}
            ordre={filters.ordre}
            onOrdreChange={(ordre) => updateFilters({ ordre })}
          />
        </Stack>
      ) : rows.length === 0 ? (
        <Text c='dimmed'>Aucune livraison sur cette période.</Text>
      ) : filters.viewMode === 'calendrier' ? (
        <DeliveryCalendar
          deliveries={rows}
          onSelectDay={(day) => updateFilters({ dateRange: [day, day] })}
        />
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Numéro</Table.Th>
              <Table.Th>Horaire prévu</Table.Th>
              <Table.Th>Prestation</Table.Th>
              <Table.Th>Lieu</Table.Th>
              <Table.Th>Organisateur</Table.Th>
              <Table.Th>Quantité totale</Table.Th>
              <Table.Th>Statut</Table.Th>
              <Table.Th>Assignation</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((delivery) => {
              const isMine = delivery.livreur_assigne === currentUserId;

              return (
                <Table.Tr key={delivery.id}>
                  <Table.Td>{delivery.numero}</Table.Td>
                  <Table.Td>
                    {delivery.date_retrait_prevue
                      ? new Date(delivery.date_retrait_prevue).toLocaleString()
                      : '—'}
                  </Table.Td>
                  <Table.Td>{delivery.prestation_nom || '—'}</Table.Td>
                  <Table.Td>{delivery.lieu_detail?.nom ?? '—'}</Table.Td>
                  <Table.Td>{delivery.organisateur_nom || '—'}</Table.Td>
                  <Table.Td>{delivery.quantite_totale}</Table.Td>
                  <Table.Td>
                    <Badge color={STATUT_COLORS[delivery.statut] ?? 'gray'}>
                      {delivery.statut}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    {delivery.livreur_assigne == null ? (
                      <Text size='sm' c='dimmed'>
                        Non assignée
                      </Text>
                    ) : (
                      <Stack gap={2}>
                        <Text size='sm'>
                          {isMine ? 'Moi' : delivery.livreur_assigne_nom}
                        </Text>
                        <Text size='xs' c='dimmed'>
                          {delivery.etat_livraison_display}
                        </Text>
                      </Stack>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Group gap='xs' wrap='nowrap'>
                      {/* Une réservation déjà livrée n'a plus rien à prendre
                          en charge : sans ce garde, le bouton s'affichait et
                          le serveur répondait 409. */}
                      {isLivreur &&
                        delivery.statut === 'validee' &&
                        delivery.livreur_assigne == null && (
                          <Button
                            size='xs'
                            loading={
                              acceptMutation.isPending &&
                              acceptMutation.variables === delivery.id
                            }
                            onClick={() => acceptMutation.mutate(delivery.id)}
                          >
                            Accepter
                          </Button>
                        )}
                      {isMine && delivery.etat_livraison === 'assignee' && (
                        <Button
                          size='xs'
                          variant='default'
                          loading={
                            releaseMutation.isPending &&
                            releaseMutation.variables === delivery.id
                          }
                          onClick={() => releaseMutation.mutate(delivery.id)}
                        >
                          Relâcher
                        </Button>
                      )}
                      {isMine &&
                        (delivery.etat_livraison === 'assignee' ||
                          delivery.etat_livraison === 'en_cours') && (
                          <Button
                            size='xs'
                            variant='light'
                            onClick={() => setStatusDelivery(delivery)}
                          >
                            Changer l'état
                          </Button>
                        )}
                      <Button
                        size='xs'
                        variant='light'
                        onClick={() => setNoteDelivery(delivery)}
                      >
                        Détails / Imprimer
                      </Button>

                      {peutMarquerLivree && delivery.statut === 'validee' && (
                        <Button
                          size='xs'
                          variant='outline'
                          color='green'
                          loading={
                            livrerMutation.isPending &&
                            livrerMutation.variables === delivery.id
                          }
                          onClick={() => livrerMutation.mutate(delivery.id)}
                        >
                          Marquer livrée
                        </Button>
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      )}

      <DeliveryNote
        delivery={noteDelivery}
        onClose={() => setNoteDelivery(null)}
      />
      <DeliveryStatusForm
        context={context}
        delivery={statusDelivery}
        onClose={() => setStatusDelivery(null)}
      />
    </Stack>
  );
}
