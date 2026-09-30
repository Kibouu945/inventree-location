// Liste des réservations + modal de création/édition.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Chip,
  Group,
  Loader,
  Modal,
  MultiSelect,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { useDebouncedValue } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useCategoryOptions } from '../catalog/useCategoryOptions';
import { FiltreVirtuel, type Virtuel } from '../FiltreVirtuel';

import {
  canArbitrateReservations,
  canCheckinReturns,
  canDeclareRetour,
  canWriteReservations
} from '../roles';
import { EnTeteTriable, useLignesTriees, useTri } from '../TriColonne';
import { ownsKeys, syncOwnedParams } from '../urlState';
import { CheckinForm } from './CheckinForm';
import {
  canArbitrateReservation,
  canCancelReservation,
  transitionErrorMessage
} from './formLogic';
import { ReservationForm } from './ReservationForm';
import { RetourForm } from './RetourForm';
import {
  buildReservationQuery,
  DEFAULT_RESERVATION_FILTERS,
  parseReservationFilters,
  RESERVATION_URL_KEYS,
  type ReservationFiltersState,
  serializeReservationFilters
} from './reservationParams';
import { couleurDuStatut } from './statuts';
import type { Page, Reservation } from './types';

const RESERVATIONS_URL = '/plugin/inventree-location/reservations/';

// Taille de page demandée au serveur (`LimitOffsetPagination`, SCRUM-101).
const PAGE_SIZE = 50;

// Statuts affichables dans le filtre (StatutReservation côté serveur).
const STATUT_OPTIONS = [
  { value: 'brouillon', label: 'Brouillon' },
  { value: 'soumise', label: 'Soumise' },
  { value: 'validee', label: 'Validée' },
  { value: 'refusee', label: 'Refusée' },
  { value: 'livree', label: 'Livrée' },
  { value: 'retournee', label: 'Retournée' },
  { value: 'cloturee', label: 'Clôturée' }
];

interface ModalState {
  open: boolean;
  reservationId?: number;
}

interface RetourModalState {
  open: boolean;
  reservationId?: number;
}

interface CheckinModalState {
  open: boolean;
  reservationId?: number;
}

const ownsReservationKey = ownsKeys(RESERVATION_URL_KEYS);

function syncUrl(filters: ReservationFiltersState) {
  syncOwnedParams(
    ownsReservationKey,
    new URLSearchParams(serializeReservationFilters(filters))
  );
}

function initialFilters(): ReservationFiltersState {
  if (typeof window === 'undefined') {
    return DEFAULT_RESERVATION_FILTERS;
  }

  return parseReservationFilters(window.location.search);
}

/** Écran liste des réservations */
type ColonneBon =
  | 'numero'
  | 'client'
  | 'manifestation'
  | 'prestation'
  | 'retrait'
  | 'retour'
  | 'statut'
  | 'objets';

export function ReservationsList({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const { tri, basculer } = useTri<ColonneBon>();

  // Filtre client du tableau des bons.
  const clientsQuery = useQuery<{
    results: Array<{ id: number; nom: string }>;
  }>(
    {
      queryKey: ['clients-filtre-bons'],
      queryFn: async () => {
        const response = await context.api.get(
          '/plugin/inventree-location/clients/'
        );
        return response.data;
      }
    },
    context.queryClient
  );

  const clientOptions = (clientsQuery.data?.results ?? []).map((c) => ({
    value: String(c.id),
    label: c.nom
  }));
  const [modalState, setModalState] = useState<ModalState>({ open: false });
  //: Annuler est irréversible : aucune transition ne sort de « annulée ».
  const [cancelModal, setCancelModal] = useState<{
    open: boolean;
    reservation?: Reservation;
  }>({ open: false });
  const [checkinModal, setCheckinModal] = useState<CheckinModalState>({
    open: false
  });
  const [retourModal, setRetourModal] = useState<RetourModalState>({
    open: false
  });
  const [filters, setFilters] =
    useState<ReservationFiltersState>(initialFilters);
  const [offset, setOffset] = useState(0);
  const [debouncedSearch] = useDebouncedValue(filters.search, 300);

  const effectiveFilters = useMemo(
    () => ({ ...filters, search: debouncedSearch }),
    [filters, debouncedSearch]
  );

  useEffect(() => {
    syncUrl(effectiveFilters);
    // Changer de filtre remet à la première page : rester à l'offset courant
    // affichait une page vide dès que le nouveau filtre rendait moins de
    setOffset(0);
  }, [effectiveFilters]);

  // La liste est paginée côté serveur depuis SCRUM-101 : sans ces contrôles,
  // le widget affichait les 50 premières réservations sans rien dire des
  const params = {
    ...buildReservationQuery(effectiveFilters),
    limit: String(PAGE_SIZE),
    offset: String(offset)
  };

  const query = useQuery<Reservation[] | Page<Reservation>>(
    {
      queryKey: ['reservations', params],
      queryFn: async () => {
        const response = await context.api.get(RESERVATIONS_URL, {
          params,
          // Clés répétées `statut=a&statut=b` (le backend lit getlist).
          paramsSerializer: { indexes: null }
        });
        return response.data;
      }
    },
    context.queryClient
  );

  const brutes = Array.isArray(query.data)
    ? query.data
    : (query.data?.results ?? []);

  const rows = useLignesTriees(brutes, tri, (r, colonne) => {
    switch (colonne) {
      case 'numero':
        return r.numero;
      case 'client':
        return r.client_nom;
      case 'manifestation':
        return r.manifestation_nom;
      case 'prestation':
        return r.prestation_nom;
      case 'retrait':
        return r.date_retrait_prevue ? new Date(r.date_retrait_prevue) : null;
      case 'retour':
        return r.date_retour_prevue ? new Date(r.date_retour_prevue) : null;
      case 'statut':
        return r.statut;
      case 'objets':
        return r.lignes.length;
    }
  });
  const total = Array.isArray(query.data)
    ? query.data.length
    : (query.data?.count ?? rows.length);
  const hasPrevious = offset > 0;
  const hasNext = offset + rows.length < total;

  // Livreur / magasinier / sav / lecteur : lecture seule (cf. permissions.py).
  const canWrite = canWriteReservations(context);
  const canArbitrate = canArbitrateReservations(context);
  // Le check-in retour est ouvert au magasinier, qui n'arbitre pas : la
  // colonne « Actions » doit donc s'afficher pour lui aussi.
  const canCheckin = canCheckinReturns(context);
  const canRetour = canDeclareRetour(context);
  const showActions = canArbitrate || canCheckin || canRetour;

  // Validation / refus d'une réservation soumise via l'endpoint de transition.
  const transitionMutation = useMutation(
    {
      mutationFn: async ({
        id,
        statut
      }: {
        id: number;
        statut: 'validee' | 'refusee' | 'annulee';
      }) => {
        const response = await context.api.patch(
          `${RESERVATIONS_URL}${id}/transition/`,
          { statut }
        );
        return response.data;
      },
      onSuccess: (_data, variables) => {
        // Une réservation validée entre dans la tournée du livreur et dans les
        // ramassages : sans ça, ces deux listes restaient périmées jusqu'au
        context.queryClient.invalidateQueries({ queryKey: ['reservations'] });
        context.queryClient.invalidateQueries({ queryKey: ['deliveries'] });
        context.queryClient.invalidateQueries({ queryKey: ['ramassages'] });
        const libelles = {
          validee: ['Validée', 'Réservation validée.', 'green'],
          refusee: ['Refusée', 'Réservation refusée.', 'orange'],
          annulee: ['Annulée', 'Réservation annulée.', 'red']
        } as const;
        const [titre, message, couleur] = libelles[variables.statut];

        notifications.show({ title: titre, message, color: couleur });
      },
      onError: (error: unknown) => {
        notifications.show({
          title: 'Action impossible',
          message: transitionErrorMessage(error),
          color: 'red'
        });
      }
    },
    context.queryClient
  );

  // Mêmes options que le catalogue et que le sélecteur d'articles : la même
  // requête était réécrite ici, et deux variantes dégradées existaient
  const categoryOptions = useCategoryOptions(context);

  function updateFilters(patch: Partial<ReservationFiltersState>) {
    setFilters((current) => ({
      ...current,
      ...patch
    }));
  }

  function closeModal() {
    setModalState({ open: false });
  }

  function closeRetourModal() {
    setRetourModal({ open: false });
  }

  function closeCheckinModal() {
    setCheckinModal({ open: false });
  }

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={4} c={context.theme.primaryColor}>
          Réservations
        </Title>
        {canWrite && (
          <Button
            onClick={() =>
              setModalState({ open: true, reservationId: undefined })
            }
          >
            Nouvelle réservation
          </Button>
        )}
      </Group>

      <Group align='flex-end' gap='md' wrap='wrap'>
        <TextInput
          label='Recherche'
          placeholder='Numéro, événement, demandeur…'
          value={filters.search}
          onChange={(event) =>
            updateFilters({ search: event.currentTarget.value })
          }
          w={260}
        />
        <Select
          label='Client'
          placeholder='Tous'
          data={clientOptions}
          value={filters.client}
          onChange={(valeur) => updateFilters({ client: valeur })}
          searchable
          clearable
          w={240}
        />
        <FiltreVirtuel
          value={filters.virtuel as Virtuel}
          onChange={(valeur) => updateFilters({ virtuel: valeur })}
        />
        <MultiSelect
          label='Catégories'
          placeholder='Tous'
          data={categoryOptions}
          value={filters.categories.map(String)}
          onChange={(values) =>
            updateFilters({
              categories: values
                .map((value) => Number.parseInt(value, 10))
                .filter((value) => Number.isInteger(value))
            })
          }
          clearable
          w={240}
        />
        <DatePickerInput
          type='range'
          label='Période'
          placeholder='Retrait — Retour'
          value={filters.dateRange}
          onChange={(value) =>
            updateFilters({
              dateRange: [value[0], value[1]]
            })
          }
          clearable
          w={260}
        />
        <Button
          variant='default'
          onClick={() => setFilters(DEFAULT_RESERVATION_FILTERS)}
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
          Impossible de charger les réservations.
        </Alert>
      )}

      {query.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : rows.length === 0 ? (
        <Text c='dimmed'>Aucune réservation pour le moment.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <EnTeteTriable colonne='numero' tri={tri} onTri={basculer}>
                Réf. réservation
              </EnTeteTriable>
              <EnTeteTriable colonne='client' tri={tri} onTri={basculer}>
                Client
              </EnTeteTriable>
              <EnTeteTriable colonne='manifestation' tri={tri} onTri={basculer}>
                Manifestation
              </EnTeteTriable>
              <EnTeteTriable colonne='prestation' tri={tri} onTri={basculer}>
                Prestation
              </EnTeteTriable>
              <EnTeteTriable colonne='retrait' tri={tri} onTri={basculer}>
                Début prévu
              </EnTeteTriable>
              <EnTeteTriable colonne='retour' tri={tri} onTri={basculer}>
                Retour prévu
              </EnTeteTriable>
              <EnTeteTriable colonne='statut' tri={tri} onTri={basculer}>
                Statut
              </EnTeteTriable>
              <EnTeteTriable
                colonne='objets'
                tri={tri}
                onTri={basculer}
                ta='right'
              >
                Nb objets
              </EnTeteTriable>
              {showActions && <Table.Th>Actions</Table.Th>}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((reservation) => {
              const showCheckinAction =
                canCheckin && reservation.statut === 'livree';
              // Seul un bon livré se déclare : le serveur refuse toute
              // déclaration sur un bon déjà retourné.
              const showRetourAction =
                canRetour && reservation.statut === 'livree';
              const showArbitrageActions =
                canArbitrate && canArbitrateReservation(reservation.statut);
              // Seul levier d'arbitrage sur une réservation déjà validée : sa
              // fiche s'ouvre en lecture seule et rien d'autre n'agit dessus.
              const showCancelAction =
                canWrite && canCancelReservation(reservation.statut);

              return (
                <Table.Tr
                  key={reservation.id}
                  style={{ cursor: 'pointer' }}
                  onClick={() =>
                    setModalState({ open: true, reservationId: reservation.id })
                  }
                >
                  <Table.Td>{reservation.numero}</Table.Td>
                  <Table.Td>{reservation.client_nom || '—'}</Table.Td>
                  <Table.Td>{reservation.manifestation_nom || '—'}</Table.Td>
                  <Table.Td>{reservation.prestation_nom || '—'}</Table.Td>
                  <Table.Td>
                    {reservation.date_retrait_prevue
                      ? new Date(
                          reservation.date_retrait_prevue
                        ).toLocaleString()
                      : '—'}
                  </Table.Td>
                  <Table.Td>
                    {reservation.date_retour_prevue
                      ? new Date(
                          reservation.date_retour_prevue
                        ).toLocaleString()
                      : '—'}
                  </Table.Td>
                  <Table.Td>
                    <Badge color={couleurDuStatut(reservation.statut)}>
                      {reservation.statut}
                    </Badge>
                  </Table.Td>
                  <Table.Td ta='right'>{reservation.lignes.length}</Table.Td>
                  {showActions && (
                    <Table.Td
                      // Les actions ne doivent pas ouvrir la modale de détail.
                      onClick={(event) => event.stopPropagation()}
                      style={{ cursor: 'default' }}
                    >
                      <Group gap='xs' wrap='nowrap'>
                        {showCheckinAction && (
                          <Button
                            size='xs'
                            color='teal'
                            onClick={() =>
                              setCheckinModal({
                                open: true,
                                reservationId: reservation.id
                              })
                            }
                          >
                            Check-in retour
                          </Button>
                        )}
                        {showArbitrageActions && (
                          <>
                            <Button
                              size='xs'
                              color='green'
                              loading={
                                transitionMutation.isPending &&
                                transitionMutation.variables?.id ===
                                  reservation.id &&
                                transitionMutation.variables?.statut ===
                                  'validee'
                              }
                              disabled={transitionMutation.isPending}
                              onClick={() =>
                                transitionMutation.mutate({
                                  id: reservation.id,
                                  statut: 'validee'
                                })
                              }
                            >
                              Valider
                            </Button>
                            <Button
                              size='xs'
                              variant='light'
                              color='red'
                              loading={
                                transitionMutation.isPending &&
                                transitionMutation.variables?.id ===
                                  reservation.id &&
                                transitionMutation.variables?.statut ===
                                  'refusee'
                              }
                              disabled={transitionMutation.isPending}
                              onClick={() =>
                                transitionMutation.mutate({
                                  id: reservation.id,
                                  statut: 'refusee'
                                })
                              }
                            >
                              Refuser
                            </Button>
                          </>
                        )}
                        {showRetourAction && (
                          <Button
                            size='xs'
                            color='grape'
                            onClick={() =>
                              setRetourModal({
                                open: true,
                                reservationId: reservation.id
                              })
                            }
                          >
                            Déclarer le retour
                          </Button>
                        )}
                        {showCancelAction && (
                          <Button
                            size='xs'
                            variant='subtle'
                            color='red'
                            loading={
                              transitionMutation.isPending &&
                              transitionMutation.variables?.id ===
                                reservation.id &&
                              transitionMutation.variables?.statut === 'annulee'
                            }
                            disabled={transitionMutation.isPending}
                            onClick={() =>
                              setCancelModal({
                                open: true,
                                reservation
                              })
                            }
                          >
                            Annuler
                          </Button>
                        )}
                        {!showCheckinAction &&
                          !showRetourAction &&
                          !showArbitrageActions &&
                          !showCancelAction && (
                            <Text c='dimmed' size='sm'>
                              —
                            </Text>
                          )}
                      </Group>
                    </Table.Td>
                  )}
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      )}

      {total > 0 && (
        <Group justify='space-between'>
          <Text size='sm' c='dimmed'>
            {offset + 1}–{offset + rows.length} sur {total}
          </Text>
          <Group gap='xs'>
            <Button
              size='xs'
              variant='default'
              disabled={!hasPrevious}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Précédent
            </Button>
            <Button
              size='xs'
              variant='default'
              disabled={!hasNext}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Suivant
            </Button>
          </Group>
        </Group>
      )}

      <Modal
        closeOnClickOutside={false}
        opened={modalState.open}
        onClose={closeModal}
        size='xl'
        title={
          !canWrite
            ? 'Détail de la réservation'
            : modalState.reservationId
              ? 'Modifier la réservation'
              : 'Nouvelle réservation'
        }
      >
        <ReservationForm
          context={context}
          reservationId={modalState.reservationId}
          readOnly={!canWrite}
          onSaved={closeModal}
        />
      </Modal>

      <Modal
        closeOnClickOutside={false}
        opened={checkinModal.open}
        onClose={closeCheckinModal}
        size='xl'
        title='Check-in retour'
      >
        {checkinModal.reservationId && (
          <CheckinForm
            context={context}
            reservationId={checkinModal.reservationId}
            onSaved={closeCheckinModal}
          />
        )}
      </Modal>

      <Modal
        closeOnClickOutside={false}
        opened={retourModal.open}
        onClose={closeRetourModal}
        size='xl'
        title='Déclarer le retour'
      >
        {retourModal.reservationId && (
          <RetourForm
            context={context}
            reservationId={retourModal.reservationId}
            onSaved={closeRetourModal}
          />
        )}
      </Modal>

      <Modal
        closeOnClickOutside={false}
        opened={cancelModal.open}
        onClose={() => setCancelModal({ open: false })}
        title='Annuler la réservation'
      >
        <Stack gap='md'>
          <Text size='sm'>
            {cancelModal.reservation?.numero} —{' '}
            {cancelModal.reservation?.prestation_nom || 'sans prestation'}.
          </Text>
          <Text size='sm' c='dimmed'>
            Le matériel engagé est libéré et la réservation sort des tournées.
            Aucune transition ne sort de « annulée » : l'opération est
            définitive.
          </Text>

          <Group justify='flex-end'>
            <Button
              variant='default'
              onClick={() => setCancelModal({ open: false })}
            >
              Revenir
            </Button>
            <Button
              color='red'
              loading={transitionMutation.isPending}
              onClick={() => {
                if (cancelModal.reservation) {
                  transitionMutation.mutate({
                    id: cancelModal.reservation.id,
                    statut: 'annulee'
                  });
                }
                setCancelModal({ open: false });
              }}
            >
              Annuler la réservation
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
