// Formulaire de création/édition d'une réservation (RES-03).
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Select,
  Stack,
  Table,
  Text,
  Textarea,
  Title,
  Tooltip
} from '@mantine/core';
import { DateTimePicker } from '@mantine/dates';
import { useForm } from '@mantine/form';
import { useDebouncedValue } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import {
  buildReservationPayload,
  emptyReservationValues,
  enrichLignesFromCatalog,
  isReservationEditable,
  removeLigne,
  reservationToFormValues,
  upsertLigne,
  validateReservationValues
} from './formLogic';
import { PartPicker } from './PartPicker';
import type {
  LieuSummary,
  Page,
  Prestation,
  Reservation,
  ReservationFormValues,
  ReservationStatut,
  UserOption
} from './types';

const RESERVATIONS_URL = '/plugin/inventree-location/reservations/';
const PRESTATIONS_URL = '/plugin/inventree-location/prestations/';
const USERS_URL = '/plugin/inventree-location/users/';
const CATALOG_URL = '/plugin/inventree-location/catalog/';

function userLabel(user: UserOption): string {
  const fullName = `${user.first_name} ${user.last_name}`.trim();
  return fullName ? `${fullName} (${user.username})` : user.username;
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    day: '2-digit',
    month: '2-digit'
  });
}

// US-20 : itinéraire vers le lieu de livraison. On privilégie les coordonnées
// GPS quand elles sont renseignées, sinon on retombe sur l'adresse texte.
function buildGoogleMapsUrl(
  latitude: string | null,
  longitude: string | null,
  address: string
): string {
  if (latitude != null && longitude != null) {
    return `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`;
  }

  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`;
}

function buildApplePlansUrl(
  latitude: string | null,
  longitude: string | null,
  address: string
): string {
  if (latitude != null && longitude != null) {
    return `https://maps.apple.com/?ll=${latitude},${longitude}&q=${encodeURIComponent(
      address || 'Lieu de livraison'
    )}`;
  }

  return `https://maps.apple.com/?q=${encodeURIComponent(address)}`;
}

/** Adresse du lieu de la prestation + raccourcis d'itinéraire (US-20). */
function LieuMapLinks({ lieu }: { lieu: LieuSummary }) {
  const mapSeed = `${lieu.nom} ${lieu.adresse}`.trim();
  const googleUrl = buildGoogleMapsUrl(lieu.latitude, lieu.longitude, mapSeed);
  const appleUrl = buildApplePlansUrl(lieu.latitude, lieu.longitude, mapSeed);

  return (
    <Group justify='space-between' align='center' mt='xs'>
      <Stack gap={0}>
        <Text size='sm'>{lieu.nom}</Text>
        <Text size='xs' c='dimmed'>
          {lieu.adresse || 'Adresse non renseignée'}
        </Text>
      </Stack>

      <Group gap='xs'>
        <Button
          component='a'
          href={googleUrl}
          target='_blank'
          rel='noopener noreferrer'
          size='xs'
          variant='light'
        >
          Google Maps
        </Button>
        <Button
          component='a'
          href={appleUrl}
          target='_blank'
          rel='noopener noreferrer'
          size='xs'
          variant='default'
        >
          Apple Plans
        </Button>
      </Group>
    </Group>
  );
}

/**
 * Clés d'erreur DRF qui ne correspondent à aucun champ du formulaire.
 *
 * `detail` porte les refus non liés à un champ (réservation déjà validée,
 * conflit de stock, permission refusée) ; `conflicts` / `stock` portent les
 * données structurées qui l'accompagnent. Les afficher comme erreurs de champ
 * ne mène nulle part : aucun input ne les rend.
 */
const NON_FIELD_ERROR_KEYS = ['detail', 'non_field_errors'];
const IGNORED_ERROR_KEYS = [...NON_FIELD_ERROR_KEYS, 'conflicts', 'stock'];

function apiErrorData(error: unknown): Record<string, unknown> {
  return (
    (error as { response?: { data?: Record<string, unknown> } })?.response
      ?.data ?? {}
  );
}

function apiErrorFields(error: unknown): Record<string, string> {
  const flattened: Record<string, string> = {};

  for (const [field, messages] of Object.entries(apiErrorData(error))) {
    if (IGNORED_ERROR_KEYS.includes(field)) {
      continue;
    }

    if (typeof messages === 'string') {
      flattened[field] = messages;
    } else if (Array.isArray(messages)) {
      flattened[field] = messages
        .filter((m) => typeof m === 'string')
        .join(' ');
    }
  }

  return flattened;
}

/** Message d'erreur non lié à un champ, tel que renvoyé par le serveur. */
function apiErrorMessage(error: unknown): string | null {
  const data = apiErrorData(error);

  for (const key of NON_FIELD_ERROR_KEYS) {
    const value = data[key];

    if (typeof value === 'string' && value.trim()) {
      return value;
    }

    if (Array.isArray(value)) {
      const joined = value.filter((m) => typeof m === 'string').join(' ');

      if (joined.trim()) {
        return joined;
      }
    }
  }

  return null;
}

/**
 * Formulaire unique de création et d'édition d'une réservation.
 *
 * En édition (`reservationId` fourni), charge la réservation existante et
 * enrichit ses lignes (nom, drapeau virtuel) via le catalogue avant de
 * pré-remplir le formulaire.
 */
export function ReservationForm({
  context,
  reservationId,
  readOnly = false,
  onSaved
}: {
  context: InvenTreePluginContext;
  reservationId?: number;
  /** Masque toute action d'écriture (rôles sans droit — cf. roles.ts). */
  readOnly?: boolean;
  onSaved?: () => void;
}) {
  const isEdit = reservationId != null;

  const form = useForm<ReservationFormValues>({
    initialValues: emptyReservationValues(),
    validate: {}
  });

  const [prestationSearch, setPrestationSearch] = useState('');
  const [debouncedPrestationSearch] = useDebouncedValue(prestationSearch, 300);
  const [userSearch, setUserSearch] = useState('');
  const [debouncedUserSearch] = useDebouncedValue(userSearch, 300);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const existingQuery = useQuery<Reservation>(
    {
      queryKey: ['reservation', reservationId],
      enabled: isEdit,
      queryFn: async () => {
        const response = await context.api.get(
          `${RESERVATIONS_URL}${reservationId}/`
        );
        return response.data as Reservation;
      }
    },
    context.queryClient
  );

  const prestationsQuery = useQuery<Page<Prestation>>(
    {
      queryKey: ['reservation-prestations', debouncedPrestationSearch],
      queryFn: async () => {
        const response = await context.api.get(PRESTATIONS_URL, {
          params: {
            search: debouncedPrestationSearch || undefined,
            page_size: 20
          }
        });
        return response.data as Page<Prestation>;
      }
    },
    context.queryClient
  );

  // La prestation choisie est chargée par son id, indépendamment de la
  // recherche : Mantine recopie le label de l'option dans `searchValue`, et ce
  // label ("nom — manifestation (dates)") ne correspond à aucun résultat côté
  // serveur, qui ne cherche que sur nom / manifestation__nom. Sans cette
  // requête dédiée, l'encart lieu et le tooltip dates disparaissaient dès la
  // sélection. Couvre aussi l'édition, où la prestation peut être hors des 20
  // premiers résultats.
  const selectedPrestationQuery = useQuery<Prestation>(
    {
      queryKey: ['reservation-prestation', form.values.prestation],
      enabled: form.values.prestation != null,
      queryFn: async () => {
        const response = await context.api.get(
          `${PRESTATIONS_URL}${form.values.prestation}/`
        );
        return response.data as Prestation;
      }
    },
    context.queryClient
  );

  const usersQuery = useQuery<Page<UserOption>>(
    {
      queryKey: ['reservation-users', debouncedUserSearch],
      queryFn: async () => {
        const response = await context.api.get(USERS_URL, {
          params: { search: debouncedUserSearch || undefined, page_size: 20 }
        });
        return response.data as Page<UserOption>;
      }
    },
    context.queryClient
  );

  // Pré-remplissage à l'édition : on attend le catalogue pour connaître le
  // nom et le drapeau virtuel des lignes déjà enregistrées.
  useEffect(() => {
    if (!existingQuery.data) {
      return;
    }

    const reservation = existingQuery.data;
    const partIds = reservation.lignes.map((ligne) => ligne.part);

    if (partIds.length === 0) {
      form.setValues(reservationToFormValues(reservation));
      return;
    }

    context.api
      .get(CATALOG_URL, { params: { ids: partIds.join(','), rentable: 'all' } })
      .then((response) => {
        const values = reservationToFormValues(reservation);
        values.lignes = enrichLignesFromCatalog(
          values.lignes,
          response.data.results
        );
        form.setValues(values);
      });
    // form est volontairement absent des deps : ce pré-remplissage ne doit
    // se déclencher qu'au chargement de la réservation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existingQuery.data]);

  const selectedPrestation = useMemo(
    () =>
      selectedPrestationQuery.data?.id === form.values.prestation
        ? selectedPrestationQuery.data
        : null,
    [selectedPrestationQuery.data, form.values.prestation]
  );

  // Une réservation validée (ou au-delà) n'est plus modifiable : lecture seule.
  const locked =
    isEdit &&
    existingQuery.data != null &&
    !isReservationEditable(existingQuery.data.statut);
  const effectiveReadOnly = readOnly || locked;

  const mutation = useMutation(
    {
      mutationFn: async (statut: ReservationStatut) => {
        const payload = buildReservationPayload(form.values, statut);

        const response = isEdit
          ? await context.api.patch(
              `${RESERVATIONS_URL}${reservationId}/`,
              payload
            )
          : await context.api.post(RESERVATIONS_URL, payload);

        return response.data as Reservation;
      },
      onSuccess: (data) => {
        form.clearErrors();
        setSubmitError(null);
        context.queryClient.invalidateQueries({ queryKey: ['reservations'] });
        notifications.show({
          title: 'Enregistré',
          message: `Réservation ${data.numero} enregistrée.`,
          color: 'green'
        });
        onSaved?.();
      },
      onError: (error: unknown) => {
        form.setErrors(apiErrorFields(error));

        // On préfère le motif renvoyé par le serveur au message générique :
        // lui seul dit *pourquoi* (réservation déjà validée, conflit de stock,
        // permission refusée). Conservé aussi dans un encart, la notification
        // disparaissant au bout de quelques secondes.
        const message = apiErrorMessage(error);

        setSubmitError(message);
        notifications.show({
          title: 'Erreur',
          message: message ?? "La réservation n'a pas pu être enregistrée.",
          color: 'red'
        });
      }
    },
    context.queryClient
  );

  function submit(statut: ReservationStatut) {
    const clientErrors = validateReservationValues(
      form.values,
      selectedPrestation,
      statut
    );

    if (Object.keys(clientErrors).length > 0) {
      form.setErrors(clientErrors);
      return;
    }

    mutation.mutate(statut);
  }

  if (isEdit && existingQuery.isLoading) {
    return (
      <Group justify='center' p='xl'>
        <Loader />
      </Group>
    );
  }

  const prestationOption = (prestation: Prestation) => ({
    value: String(prestation.id),
    label: `${prestation.nom} — ${prestation.manifestation_nom} (${shortDate(
      prestation.date_debut
    )}→${shortDate(prestation.date_fin)})`
  });

  const prestationOptions = (prestationsQuery.data?.results ?? []).map(
    prestationOption
  );

  // La prestation choisie doit rester dans les options même quand la recherche
  // courante ne la ramène pas, sinon le Select perd son libellé.
  if (
    selectedPrestation &&
    !prestationOptions.some(
      (option) => option.value === String(selectedPrestation.id)
    )
  ) {
    prestationOptions.unshift(prestationOption(selectedPrestation));
  }

  const userOptions = (usersQuery.data?.results ?? []).map((user) => ({
    value: String(user.id),
    label: userLabel(user)
  }));

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={4} c={context.theme.primaryColor}>
          {isEdit ? 'Modifier la réservation' : 'Nouvelle réservation'}
        </Title>
        {existingQuery.data?.numero && (
          <Badge>{existingQuery.data.numero}</Badge>
        )}
      </Group>

      {effectiveReadOnly && (
        <Alert color='blue' title='Lecture seule'>
          {locked
            ? 'Cette réservation est validée : elle n’est plus modifiable.'
            : 'Votre rôle ne permet pas de modifier cette réservation.'}
        </Alert>
      )}

      {submitError && (
        <Alert color='red' title='Enregistrement refusé'>
          {submitError}
        </Alert>
      )}

      {/* Tooltip sur l'icône, pas sur le Select (le wrapper casse le dropdown). */}
      <Select
        label={
          <Group gap={6} component='span' align='center'>
            <span>Événement / Prestation</span>
            {selectedPrestation && (
              <Tooltip
                multiline
                w={280}
                openDelay={100}
                closeDelay={2000}
                events={{ hover: true, focus: true, touch: true }}
                label={
                  <Stack gap={2}>
                    <Text size='sm' fw={600}>
                      {selectedPrestation.nom} —{' '}
                      {selectedPrestation.manifestation_nom}
                    </Text>
                    <Text size='xs'>
                      Du{' '}
                      {new Date(selectedPrestation.date_debut).toLocaleString()}{' '}
                      au{' '}
                      {new Date(selectedPrestation.date_fin).toLocaleString()}
                    </Text>
                    <Text size='xs'>
                      Lieu : {selectedPrestation.lieu_detail?.nom ?? 'aucun'}
                    </Text>
                    <Text size='xs' c='yellow'>
                      La réservation doit couvrir ces dates.
                    </Text>
                  </Stack>
                }
              >
                <Text component='span' c='blue' style={{ cursor: 'help' }}>
                  ⓘ dates
                </Text>
              </Tooltip>
            )}
          </Group>
        }
        placeholder='Rechercher une prestation…'
        data={prestationOptions}
        searchable
        searchValue={prestationSearch}
        onSearchChange={setPrestationSearch}
        value={
          form.values.prestation != null ? String(form.values.prestation) : null
        }
        onChange={(value) =>
          form.setFieldValue('prestation', value ? Number(value) : null)
        }
        error={form.errors.prestation}
        disabled={effectiveReadOnly}
        required
      />

      {selectedPrestation && (
        <Alert color='gray' title='Événement / Lieu'>
          <Text size='sm'>{selectedPrestation.manifestation_nom}</Text>
          {selectedPrestation.lieu_detail ? (
            <LieuMapLinks lieu={selectedPrestation.lieu_detail} />
          ) : (
            <Text size='sm' c='dimmed'>
              Aucun lieu associé à cette prestation.
            </Text>
          )}
        </Alert>
      )}

      <Select
        label='Demandeur'
        placeholder='Rechercher un utilisateur…'
        data={userOptions}
        searchable
        searchValue={userSearch}
        onSearchChange={setUserSearch}
        value={
          form.values.demandeur != null ? String(form.values.demandeur) : null
        }
        onChange={(value) =>
          form.setFieldValue('demandeur', value ? Number(value) : null)
        }
        error={form.errors.demandeur}
        disabled={effectiveReadOnly}
        required
      />

      <Group grow>
        <DateTimePicker
          label='Date de retrait prévue'
          value={form.values.date_retrait_prevue}
          onChange={(value) =>
            form.setFieldValue(
              'date_retrait_prevue',
              value ? new Date(value) : null
            )
          }
          error={form.errors.date_retrait_prevue}
          disabled={effectiveReadOnly}
          clearable
        />
        <DateTimePicker
          label='Date de retour prévue'
          value={form.values.date_retour_prevue}
          onChange={(value) =>
            form.setFieldValue(
              'date_retour_prevue',
              value ? new Date(value) : null
            )
          }
          error={form.errors.date_retour_prevue}
          disabled={effectiveReadOnly}
          clearable
        />
      </Group>

      <Textarea
        label='Notes'
        placeholder='Commentaire…'
        value={form.values.commentaire}
        onChange={(event) =>
          form.setFieldValue('commentaire', event.currentTarget.value)
        }
        minRows={2}
        disabled={effectiveReadOnly}
      />

      <Title order={5}>Matériel</Title>
      {!effectiveReadOnly && (
        <>
          <PartPicker
            context={context}
            label='Ajouter un article'
            onAdd={(ligne) =>
              form.setFieldValue(
                'lignes',
                upsertLigne(form.values.lignes, ligne)
              )
            }
          />

          <Title order={5}>Article virtuel (obligatoire à la soumission)</Title>
          <PartPicker
            context={context}
            label='Ajouter une prestation (ex: nettoyage)'
            virtualOnly
            onAdd={(ligne) =>
              form.setFieldValue(
                'lignes',
                upsertLigne(form.values.lignes, ligne)
              )
            }
          />
        </>
      )}

      {form.errors.lignes && (
        <Alert color='red' title='Matériel'>
          {form.errors.lignes}
        </Alert>
      )}

      {form.values.lignes.length > 0 && (
        <Table striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Article</Table.Th>
              <Table.Th>Quantité</Table.Th>
              <Table.Th>Type</Table.Th>
              {!effectiveReadOnly && <Table.Th />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {form.values.lignes.map((ligne) => (
              <Table.Tr key={ligne.part}>
                <Table.Td>{ligne.partName}</Table.Td>
                <Table.Td>{ligne.quantiteDemandee}</Table.Td>
                <Table.Td>
                  {ligne.isVirtual ? (
                    <Badge color='orange'>Virtuel</Badge>
                  ) : (
                    <Badge color='green'>Matériel</Badge>
                  )}
                </Table.Td>
                {!effectiveReadOnly && (
                  <Table.Td>
                    <Button
                      size='xs'
                      variant='subtle'
                      color='red'
                      onClick={() =>
                        form.setFieldValue(
                          'lignes',
                          removeLigne(form.values.lignes, ligne.part)
                        )
                      }
                    >
                      Retirer
                    </Button>
                  </Table.Td>
                )}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      {!effectiveReadOnly && (
        <Group justify='flex-end'>
          <Button
            variant='light'
            loading={mutation.isPending}
            onClick={() => submit('brouillon')}
          >
            Enregistrer en brouillon
          </Button>
          <Button
            loading={mutation.isPending}
            onClick={() => submit('soumise')}
          >
            Soumettre
          </Button>
        </Group>
      )}
    </Stack>
  );
}
