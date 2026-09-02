// CRUD des prestations : lieu unique, articles + quantités et stock temps réel
// (ORG-01 / ORG-02 / RES-09 / STK-01).
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  ActionIcon,
  Alert,
  Button,
  Group,
  Loader,
  Modal,
  NumberInput,
  Select,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  Title
} from '@mantine/core';
import { DateTimePicker } from '@mantine/dates';
import { useDebouncedValue } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { canWriteOrganisation } from '../roles';
import {
  apiErrorMessage,
  type Manifestation,
  type Page,
  type Prestation,
  type PrestationArticle,
  type StockResult
} from './types';

const PRESTATIONS_URL = '/plugin/inventree-location/prestations/';
const STOCK_PREVIEW_URL =
  '/plugin/inventree-location/prestations/stock-preview/';
const MANIFESTATIONS_URL = '/plugin/inventree-location/manifestations/';
const LIEUX_URL = '/plugin/inventree-location/lieux/';
const CATALOG_URL = '/plugin/inventree-location/catalog/';

interface FormState {
  nom: string;
  description: string;
  manifestation: string | null;
  lieu: string | null;
  date_debut: Date | null;
  date_fin: Date | null;
  articles: PrestationArticle[];
}

function emptyState(): FormState {
  return {
    nom: '',
    description: '',
    manifestation: null,
    lieu: null,
    date_debut: null,
    date_fin: null,
    articles: []
  };
}

/** Sélecteur d'un article du catalogue + quantité. */
function ArticleAdder({
  context,
  onAdd
}: {
  context: InvenTreePluginContext;
  onAdd: (article: PrestationArticle) => void;
}) {
  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [quantite, setQuantite] = useState<number>(1);

  const query = useQuery<{ results: Array<{ id: number; name: string }> }>(
    {
      queryKey: ['prestation-part-search', debouncedSearch],
      queryFn: async () => {
        const response = await context.api.get(CATALOG_URL, {
          params: {
            search: debouncedSearch || undefined,
            rentable: 'all',
            page_size: 20
          }
        });
        return response.data;
      }
    },
    context.queryClient
  );

  const results = query.data?.results ?? [];
  const options = results.map((part) => ({
    value: String(part.id),
    label: part.name
  }));
  const selected = results.find((part) => String(part.id) === selectedId);

  return (
    <Group align='flex-end' gap='sm' wrap='wrap'>
      <Select
        label='Article'
        placeholder='Rechercher…'
        data={options}
        searchable
        searchValue={search}
        onSearchChange={setSearch}
        value={selectedId}
        onChange={setSelectedId}
        nothingFoundMessage={query.isFetching ? 'Recherche…' : 'Aucun résultat'}
        w={260}
      />
      <NumberInput
        label='Quantité'
        min={1}
        value={quantite}
        onChange={(value) => setQuantite(Number(value) || 1)}
        w={100}
      />
      <Button
        disabled={!selected || quantite < 1}
        onClick={() => {
          if (!selected) {
            return;
          }
          onAdd({ part: selected.id, partName: selected.name, quantite });
          setSelectedId(null);
          setSearch('');
          setQuantite(1);
        }}
      >
        Ajouter
      </Button>
    </Group>
  );
}

export function PrestationsTab({
  context
}: {
  context: InvenTreePluginContext;
}) {
  const canWrite = canWriteOrganisation(context);

  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [state, setState] = useState<FormState>(emptyState());
  const [stock, setStock] = useState<StockResult | null>(null);

  const listQuery = useQuery<Prestation[] | Page<Prestation>>(
    {
      queryKey: ['prestations', debouncedSearch],
      queryFn: async () => {
        const response = await context.api.get(PRESTATIONS_URL, {
          params: debouncedSearch ? { search: debouncedSearch } : {}
        });
        return response.data;
      }
    },
    context.queryClient
  );

  const manifestationsQuery = useQuery<{ results: Manifestation[] }>(
    {
      queryKey: ['manifestations-select'],
      queryFn: async () => {
        const response = await context.api.get(MANIFESTATIONS_URL);
        return response.data;
      }
    },
    context.queryClient
  );

  const lieuxQuery = useQuery<{ results: Array<{ id: number; nom: string }> }>(
    {
      queryKey: ['lieux-select'],
      queryFn: async () => {
        const response = await context.api.get(LIEUX_URL);
        return response.data;
      }
    },
    context.queryClient
  );

  const rows = Array.isArray(listQuery.data)
    ? listQuery.data
    : (listQuery.data?.results ?? []);

  const manifestationOptions = (manifestationsQuery.data?.results ?? []).map(
    (m) => ({ value: String(m.id), label: m.nom })
  );
  const lieuOptions = (lieuxQuery.data?.results ?? []).map((l) => ({
    value: String(l.id),
    label: l.nom
  }));

  // STK-01 — disponibilité recalculée (debounced) à chaque changement de dates
  // ou d'articles, avant sauvegarde.
  const [debouncedState] = useDebouncedValue(state, 500);

  useEffect(() => {
    const { date_debut, date_fin, articles } = debouncedState;

    if (!date_debut || !date_fin || articles.length === 0) {
      setStock(null);
      return;
    }

    let cancelled = false;

    context.api
      .post(
        STOCK_PREVIEW_URL,
        {
          date_debut: date_debut.toISOString(),
          date_fin: date_fin.toISOString(),
          exclude_prestation: editId ?? undefined,
          lignes: articles.map((article) => ({
            part: article.part,
            quantite: article.quantite
          }))
        },
        // 409 = pénurie : ce n'est pas une erreur réseau, on lit quand même.
        { validateStatus: (status: number) => status < 500 }
      )
      .then((response) => {
        if (!cancelled) {
          setStock(response.data as StockResult);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStock(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [debouncedState, context.api, editId]);

  const hasShortage = stock?.has_shortage ?? false;

  const mutation = useMutation(
    {
      mutationFn: async () => {
        const payload = {
          nom: state.nom,
          description: state.description,
          manifestation: state.manifestation
            ? Number(state.manifestation)
            : null,
          lieu: state.lieu ? Number(state.lieu) : null,
          date_debut: state.date_debut?.toISOString(),
          date_fin: state.date_fin?.toISOString(),
          lignes: state.articles.map((article) => ({
            part: article.part,
            quantite: article.quantite
          }))
        };

        if (editId != null) {
          const response = await context.api.patch(
            `${PRESTATIONS_URL}${editId}/`,
            payload
          );
          return response.data;
        }

        const response = await context.api.post(PRESTATIONS_URL, payload);
        return response.data;
      },
      onSuccess: () => {
        notifications.show({
          color: 'green',
          message:
            editId != null ? 'Prestation mise à jour.' : 'Prestation créée.'
        });
        context.queryClient.invalidateQueries({ queryKey: ['prestations'] });
        setModalOpen(false);
      },
      onError: (error) => {
        notifications.show({
          color: 'red',
          title: 'Erreur',
          message: apiErrorMessage(error, "Échec de l'enregistrement.")
        });
      }
    },
    context.queryClient
  );

  function openCreate() {
    setEditId(null);
    setState(emptyState());
    setStock(null);
    setModalOpen(true);
  }

  function openEdit(prestation: Prestation) {
    setEditId(prestation.id);
    setState({
      nom: prestation.nom,
      description: prestation.description,
      manifestation: String(prestation.manifestation),
      lieu: prestation.lieu != null ? String(prestation.lieu) : null,
      date_debut: new Date(prestation.date_debut),
      date_fin: new Date(prestation.date_fin),
      articles: prestation.lignes.map((ligne) => ({
        part: ligne.part,
        partName: ligne.part_name ?? `#${ligne.part}`,
        quantite: ligne.quantite
      }))
    });
    setStock(null);
    setModalOpen(true);
  }

  /**
   * Écrit un champ du formulaire depuis une valeur **déjà lue**.
   *
   * React remet `event.currentTarget` à `null` dès la fin du gestionnaire.
   * Lire `event.currentTarget.value` *à l'intérieur* d'un updater
   * `setState((s) => …)` marche donc par accident : tant que React évalue
   * l'updater tout de suite (cas de la première frappe, chemin « eager »), la
   * valeur est encore là ; dès qu'il le diffère, le callback lit `null.value`
   * et le widget Organisation entier tombe en « Error rendering component ».
   * C'est le plantage remonté par le client le 02/09/2026 sur la saisie du nom
   * d'une prestation, reproductible dès la deuxième frappe sur InvenTree 1.5.
   * Toujours capturer la valeur dans le gestionnaire, jamais dans l'updater.
   */
  function setField<K extends keyof FormState>(field: K, value: FormState[K]) {
    setState((current) => ({ ...current, [field]: value }));
  }

  function addArticle(article: PrestationArticle) {
    setState((current) => {
      const existing = current.articles.find((a) => a.part === article.part);
      const articles = existing
        ? current.articles.map((a) =>
            a.part === article.part
              ? { ...a, quantite: a.quantite + article.quantite }
              : a
          )
        : [...current.articles, article];
      return { ...current, articles };
    });
  }

  function removeArticle(partId: number) {
    setState((current) => ({
      ...current,
      articles: current.articles.filter((a) => a.part !== partId)
    }));
  }

  const canSubmit = useMemo(
    () =>
      Boolean(
        state.nom &&
          state.manifestation &&
          state.date_debut &&
          state.date_fin &&
          !hasShortage
      ),
    [state, hasShortage]
  );

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={5}>Prestations</Title>
        {canWrite && <Button onClick={openCreate}>Nouvelle prestation</Button>}
      </Group>

      <TextInput
        label='Recherche'
        placeholder='Nom de la prestation ou manifestation…'
        value={search}
        onChange={(event) => setSearch(event.currentTarget.value)}
        w={320}
      />

      {listQuery.isError && (
        <Alert color='red' title='Erreur'>
          Impossible de charger les prestations.
        </Alert>
      )}

      {listQuery.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : rows.length === 0 ? (
        <Text c='dimmed'>Aucune prestation pour le moment.</Text>
      ) : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Nom</Table.Th>
              <Table.Th>Manifestation</Table.Th>
              <Table.Th>Lieu</Table.Th>
              <Table.Th>Début</Table.Th>
              <Table.Th>Articles</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((prestation) => (
              <Table.Tr
                key={prestation.id}
                style={{ cursor: canWrite ? 'pointer' : 'default' }}
                onClick={() => canWrite && openEdit(prestation)}
              >
                <Table.Td>{prestation.nom}</Table.Td>
                <Table.Td>{prestation.manifestation_nom}</Table.Td>
                <Table.Td>{prestation.lieu_detail?.nom ?? '—'}</Table.Td>
                <Table.Td>
                  {new Date(prestation.date_debut).toLocaleString()}
                </Table.Td>
                <Table.Td>{prestation.lignes.length}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Modal
        opened={modalOpen}
        onClose={() => setModalOpen(false)}
        size='xl'
        title={
          editId != null ? 'Modifier la prestation' : 'Nouvelle prestation'
        }
      >
        <Stack gap='sm'>
          <TextInput
            label='Nom'
            required
            value={state.nom}
            onChange={(event) => setField('nom', event.currentTarget.value)}
          />
          <Group grow>
            <Select
              label='Manifestation'
              required
              data={manifestationOptions}
              searchable
              value={state.manifestation}
              onChange={(value) => setField('manifestation', value)}
            />
            <Select
              label='Lieu'
              data={lieuOptions}
              searchable
              clearable
              value={state.lieu}
              onChange={(value) => setField('lieu', value)}
            />
          </Group>
          <Group grow>
            <DateTimePicker
              label='Date de début'
              required
              value={state.date_debut}
              onChange={(value) =>
                setField('date_debut', value ? new Date(value) : null)
              }
            />
            <DateTimePicker
              label='Date de fin'
              required
              value={state.date_fin}
              onChange={(value) =>
                setField('date_fin', value ? new Date(value) : null)
              }
            />
          </Group>
          <Textarea
            label='Description'
            autosize
            minRows={2}
            value={state.description}
            onChange={(event) =>
              setField('description', event.currentTarget.value)
            }
          />

          <Title order={6}>Articles (RES-09)</Title>
          <ArticleAdder context={context} onAdd={addArticle} />

          {state.articles.length > 0 && (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Article</Table.Th>
                  <Table.Th>Quantité</Table.Th>
                  <Table.Th>Disponible</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {state.articles.map((article) => {
                  const stockLine = stock?.lines.find(
                    (line) => line.part_id === article.part
                  );
                  return (
                    <Table.Tr key={article.part}>
                      <Table.Td>{article.partName}</Table.Td>
                      <Table.Td>
                        <NumberInput
                          min={1}
                          value={article.quantite}
                          onChange={(value) =>
                            setState((s) => ({
                              ...s,
                              articles: s.articles.map((a) =>
                                a.part === article.part
                                  ? { ...a, quantite: Number(value) || 1 }
                                  : a
                              )
                            }))
                          }
                          w={90}
                        />
                      </Table.Td>
                      <Table.Td>
                        {stockLine ? (
                          <Text
                            size='sm'
                            c={stockLine.shortage ? 'red' : 'green'}
                          >
                            {stockLine.available} / {stockLine.total_stock}
                            {stockLine.shortage
                              ? ` (manque ${stockLine.missing})`
                              : ''}
                          </Text>
                        ) : (
                          <Text size='sm' c='dimmed'>
                            —
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        <ActionIcon
                          color='red'
                          variant='subtle'
                          onClick={() => removeArticle(article.part)}
                          aria-label='Retirer'
                        >
                          ✕
                        </ActionIcon>
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          )}

          {hasShortage && (
            <Alert color='red' title='Stock insuffisant'>
              Certains articles dépassent le stock disponible sur la période. La
              prestation ne peut pas être enregistrée tant que le conflit n'est
              pas résolu (réduire les quantités ou changer la période).
            </Alert>
          )}

          <Group justify='flex-end'>
            <Button variant='default' onClick={() => setModalOpen(false)}>
              Annuler
            </Button>
            <Button
              onClick={() => mutation.mutate()}
              loading={mutation.isPending}
              disabled={!canSubmit}
            >
              Enregistrer
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
