// CRUD des prestations : lieu unique, articles + quantités et stock temps réel
// (ORG-01 / ORG-02 / RES-09 / STK-01).
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Modal,
  MultiSelect,
  NumberInput,
  SegmentedControl,
  Select,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  Title,
  Tooltip
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { useDebouncedValue } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { buildCatalogQuery } from '../catalog/catalogParams';
import { PartKindBadge } from '../catalog/PartKindBadge';
import type { CatalogPage } from '../catalog/types';
import { useCategoryOptions } from '../catalog/useCategoryOptions';
import {
  DateTimeField,
  finSuivantLeDebut,
  reprendreLesDates
} from '../DateTimeField';
import { FiltreVirtuel, type Virtuel } from '../FiltreVirtuel';

import { canWriteOrganisation } from '../roles';
import { EnTeteTriable, useLignesTriees, useTri } from '../TriColonne';
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

// Taille de la liste déroulante d'articles.
const TAILLE_LISTE_ARTICLES = 30;

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
  const [categories, setCategories] = useState<number[]>([]);
  const [rentable, setRentable] = useState<boolean | 'all'>(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [quantite, setQuantite] = useState<number>(1);

  const categoryOptions = useCategoryOptions(context);

  // Mêmes paramètres que l'écran catalogue, aux deux réglages près qui sont
  // propres à une liste déroulante : la taille de page, et l'exclusion des
  const params = {
    ...buildCatalogQuery({
      search: debouncedSearch,
      categories,
      rentable,
      // La disponibilité affichée ici est celle du jour : la période de la
      // prestation n'est pas forcément saisie quand on ajoute les articles, et
      dateDebut: null,
      dateFin: null,
      page: 1
    }),
    page_size: String(TAILLE_LISTE_ARTICLES),
    active: 'true'
  };

  const query = useQuery<CatalogPage>(
    {
      queryKey: ['prestation-part-search', params],
      queryFn: async () => {
        const response = await context.api.get(CATALOG_URL, { params });
        return response.data as CatalogPage;
      }
    },
    context.queryClient
  );

  const results = query.data?.results ?? [];
  const total = query.data?.count ?? 0;
  const tronque = total > results.length;

  const options = results.map((part) => ({
    value: String(part.id),
    label: part.name
  }));
  const parById = new Map(results.map((part) => [String(part.id), part]));
  const selected = selectedId ? parById.get(selectedId) : undefined;

  // Un article non louable ne peut pas entrer dans une prestation. Le message
  // dit lequel et pourquoi, plutôt que de griser un bouton sans explication.
  const refus =
    selected && !selected.rentable
      ? `« ${selected.name} » n'est pas louable : il ne peut pas être réservé.`
      : null;

  return (
    <Stack gap='xs'>
      <Group align='flex-end' gap='sm' wrap='wrap'>
        <Select
          label='Article'
          placeholder='Nom, description, référence…'
          data={options}
          searchable
          searchValue={search}
          onSearchChange={setSearch}
          value={selectedId}
          onChange={setSelectedId}
          renderOption={({ option }) => {
            const part = parById.get(option.value);

            return (
              <Group gap='xs' justify='space-between' w='100%' wrap='nowrap'>
                <Text size='sm' truncate>
                  {option.label}
                </Text>
                <PartKindBadge
                  isVirtual={part?.is_virtual}
                  consommable={part?.consommable}
                  rentable={part?.rentable}
                />
              </Group>
            );
          }}
          nothingFoundMessage={
            query.isFetching ? 'Recherche…' : 'Aucun résultat'
          }
          w={280}
        />
        <MultiSelect
          label='Catégories'
          placeholder='Toutes'
          data={categoryOptions}
          value={categories.map(String)}
          onChange={(values) =>
            setCategories(values.map((value) => Number(value)))
          }
          clearable
          searchable
          w={220}
        />
        <SegmentedControl
          value={String(rentable)}
          onChange={(value) =>
            setRentable(value === 'all' ? 'all' : value === 'true')
          }
          data={[
            { label: 'Louable', value: 'true' },
            { label: 'Non-louable', value: 'false' },
            { label: 'Tout', value: 'all' }
          ]}
        />
        <NumberInput
          label='Quantité'
          min={1}
          value={quantite}
          onChange={(value) => setQuantite(Number(value) || 1)}
          w={100}
        />
        <Button
          disabled={!selected || quantite < 1 || refus != null}
          onClick={() => {
            if (!selected || refus) {
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

      {refus && (
        <Text size='xs' c='red'>
          {refus}
        </Text>
      )}

      {tronque && !refus && (
        <Text size='xs' c='dimmed'>
          {total} articles correspondent, {results.length} affichés — affinez la
          recherche ou choisissez une catégorie.
        </Text>
      )}
    </Stack>
  );
}

type ColonnePresta =
  | 'client'
  | 'manifestation'
  | 'nom'
  | 'debut'
  | 'lieu'
  | 'articles';

export function PrestationsTab({
  context,
  manifestationFiltre
}: {
  context: InvenTreePluginContext;
  /** Manifestation sur laquelle arriver préfiltré (point 4.2.5.1). */
  manifestationFiltre?: { id: number; nom: string } | null;
}) {
  const canWrite = canWriteOrganisation(context);
  const { tri, basculer } = useTri<ColonnePresta>();
  // Le filtre hérité de l'onglet Manifestations se retire d'un clic.
  const [filtreLeve, setFiltreLeve] = useState(false);
  // Filtre par période, demandé sur les deux onglets (point 4.2.5).
  const [periode, setPeriode] = useState<[string | null, string | null]>([
    null,
    null
  ]);

  // Point 4.5.1 : masquer les prestations qui ne portent que des services.
  const [virtuel, setVirtuel] = useState<Virtuel>(null);

  const [search, setSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [modalOpen, setModalOpen] = useState(false);
  // 4.6.1 : les dates suivent la manifestation tant qu'on n'y a pas touché.
  const [datesSaisies, setDatesSaisies] = useState(false);
  const [articlesOuverts, setArticlesOuverts] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [state, setState] = useState<FormState>(emptyState());
  const [stock, setStock] = useState<StockResult | null>(null);

  const listQuery = useQuery<Prestation[] | Page<Prestation>>(
    {
      queryKey: ['prestations', debouncedSearch, periode, virtuel],
      queryFn: async () => {
        const params: Record<string, string> = {};

        if (debouncedSearch) {
          params.search = debouncedSearch;
        }

        if (periode[0]) {
          params.from = periode[0];
        }

        if (periode[1]) {
          params.to = periode[1];
        }

        if (virtuel) {
          params.virtuel = virtuel;
        }

        const response = await context.api.get(PRESTATIONS_URL, { params });
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

  const brutes = Array.isArray(listQuery.data)
    ? listQuery.data
    : (listQuery.data?.results ?? []);

  // Le clic sur le nombre de prestations d'une manifestation arrive ici.
  const filtreActif = manifestationFiltre && !filtreLeve;
  const filtrees = filtreActif
    ? brutes.filter((p) => p.manifestation === manifestationFiltre.id)
    : brutes;

  const rows = useLignesTriees(filtrees, tri, (p, colonne) => {
    switch (colonne) {
      case 'client':
        return p.client_nom;
      case 'manifestation':
        return p.manifestation_nom;
      case 'nom':
        return p.nom;
      case 'debut':
        return new Date(p.date_debut);
      case 'lieu':
        return p.lieu_detail?.nom;
      case 'articles':
        return p.lignes.length;
    }
  });

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
    setDatesSaisies(false);
    setStock(null);
    // Création : on ne demande pas le matériel d'entrée de jeu. Nommer la
    // prestation, la rattacher et la dater suffit à l'enregistrer.
    setArticlesOuverts(false);
    setModalOpen(true);
  }

  function openEdit(prestation: Prestation) {
    setEditId(prestation.id);
    // Modification : les dates existent, elles ne se recalculent pas.
    setDatesSaisies(true);
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
    // Édition : masquer une liste déjà saisie la ferait passer pour perdue.
    setArticlesOuverts(prestation.lignes.length > 0);
    setModalOpen(true);
  }

  /** Rattache la prestation, et lui passe les dates de la manifestation. */
  function choisirManifestation(value: string | null) {
    const porteuse = (manifestationsQuery.data?.results ?? []).find(
      (m) => String(m.id) === value
    );

    setState((current) => ({
      ...current,
      manifestation: value,
      ...reprendreLesDates(porteuse, current, datesSaisies)
    }));
  }

  /** Écrit un champ du formulaire depuis une valeur **déjà lue**. */
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

  // La pénurie de stock ne fait plus partie des conditions d'enregistrement.
  const canSubmit = useMemo(
    () =>
      Boolean(
        state.nom && state.manifestation && state.date_debut && state.date_fin
      ),
    [state]
  );

  return (
    <Stack gap='md'>
      <Group justify='space-between'>
        <Title order={5}>Prestations</Title>
        {canWrite && <Button onClick={openCreate}>Nouvelle prestation</Button>}
      </Group>

      <Group align='flex-end' gap='md'>
        <TextInput
          label='Recherche'
          placeholder='Nom de la prestation ou manifestation…'
          value={search}
          onChange={(event) => setSearch(event.currentTarget.value)}
          w={320}
        />

        <DatePickerInput
          type='range'
          label='Période'
          placeholder='Toutes les dates'
          value={periode}
          onChange={setPeriode}
          clearable
          w={280}
        />

        <FiltreVirtuel value={virtuel} onChange={setVirtuel} />
      </Group>

      {filtreActif && (
        <Group>
          <Badge
            size='lg'
            variant='light'
            rightSection={
              <ActionIcon
                size='xs'
                variant='transparent'
                aria-label='Retirer le filtre'
                onClick={() => setFiltreLeve(true)}
              >
                ×
              </ActionIcon>
            }
          >
            Manifestation : {manifestationFiltre.nom}
          </Badge>
        </Group>
      )}

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
              <EnTeteTriable colonne='client' tri={tri} onTri={basculer}>
                Client
              </EnTeteTriable>
              <EnTeteTriable colonne='manifestation' tri={tri} onTri={basculer}>
                Manifestation
              </EnTeteTriable>
              <EnTeteTriable colonne='nom' tri={tri} onTri={basculer}>
                Prestation
              </EnTeteTriable>
              <EnTeteTriable colonne='debut' tri={tri} onTri={basculer}>
                Début
              </EnTeteTriable>
              <EnTeteTriable colonne='lieu' tri={tri} onTri={basculer}>
                Lieu
              </EnTeteTriable>
              <EnTeteTriable
                colonne='articles'
                tri={tri}
                onTri={basculer}
                ta='right'
              >
                Articles
              </EnTeteTriable>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((prestation) => (
              <Table.Tr
                key={prestation.id}
                style={{ cursor: canWrite ? 'pointer' : 'default' }}
                onClick={() => canWrite && openEdit(prestation)}
              >
                <Table.Td>{prestation.client_nom ?? '—'}</Table.Td>
                <Table.Td>{prestation.manifestation_nom}</Table.Td>
                <Table.Td>{prestation.nom}</Table.Td>
                <Table.Td>
                  {new Date(prestation.date_debut).toLocaleString()}
                </Table.Td>
                <Table.Td>{prestation.lieu_detail?.nom ?? '—'}</Table.Td>
                <Table.Td ta='right'>{prestation.lignes.length}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Modal
        closeOnClickOutside={false}
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
              onChange={(value) => choisirManifestation(value)}
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
            <DateTimeField
              label='Date de début'
              required
              value={state.date_debut}
              onChange={(value) => {
                setDatesSaisies(true);
                const debut = value ? new Date(value) : null;
                setField('date_debut', debut);
                setField('date_fin', finSuivantLeDebut(debut, state.date_fin));
              }}
            />
            <DateTimeField
              label='Date de fin'
              required
              minDate={state.date_debut ?? undefined}
              value={state.date_fin}
              onChange={(value) => {
                setDatesSaisies(true);
                setField('date_fin', value ? new Date(value) : null);
              }}
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

          {/* Le prévisionnel matériel, replié tant qu'on n'y touche pas.
           *
           * Revue interne du 07/09/2026 : la liste d'articles a été jugée
           * redondante avec celle de la réservation, au point d'être
           * proposée à la suppression. Elle ne l'est plus — la réservation
           * reprend désormais celle de la prestation (recette Tassin,
           * remarque 15) : on saisit une fois, ici. La supprimer coûterait
           * la moitié « prévision » du moteur de stock, donc toute
           * anticipation de tension avant qu'une réservation existe, et
           * irait contre le CDC (« une prestation nécessite au moins une
           * liste d'objets avec une quantité pour chacun »).
           *
           * Reste le grief de fond, qui est juste : le formulaire est long.
           * La section s'ouvre donc à la demande, et d'elle-même dès qu'une
           * prestation en édition porte déjà des articles. */}
          {/* Le `onClick` ne vit que sur le bouton. Posé aussi sur le `Group`,
              il partait deux fois par remontée d'événement : la section
              s'ouvrait et se refermait dans le même clic. */}
          <Group justify='space-between'>
            <Title order={6}>
              Articles{' '}
              {state.articles.length > 0 && `(${state.articles.length})`}
            </Title>
            <Button
              variant='subtle'
              size='compact-sm'
              onClick={() => setArticlesOuverts((ouvert) => !ouvert)}
            >
              {articlesOuverts ? 'Masquer' : 'Renseigner le matériel'}
            </Button>
          </Group>

          {/* Rendu conditionnel plutôt que `<Collapse>` : `@mantine/core` est
              externalisé vers l'hôte (cf. `vite.config.ts`), et son `Collapse`
              y restait fermé malgré `in={true}` — la mesure de hauteur ne se
              faisait pas. On ne cherchait qu'à raccourcir le formulaire, pas à
              l'animer ; démonter la section évite en prime la requête
              catalogue de `ArticleAdder` tant qu'on ne s'en sert pas. */}
          {articlesOuverts && (
            <Stack gap='sm'>
              <Text size='xs' c='dimmed'>
                Le prévisionnel de la prestation. Les réservations rattachées le
                reprennent automatiquement — inutile de le ressaisir.
              </Text>
              <ArticleAdder context={context} onAdd={addArticle} />

              {state.articles.length > 0 && (
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Article</Table.Th>
                      <Table.Th>Quantité</Table.Th>
                      {/* « Sous le libellé "disponible" il y a deux chiffres, à
                      quoi correspondent-ils ? » (recette du 07/09/2026,
                      remarque 7). C'était `available / total_stock` : le libre
                      sur la période, puis le parc possédé — et l'ordre se lit
                      à l'envers de la convention « N sur M ». */}
                      <Table.Th>Disponible / parc</Table.Th>
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
                              <Tooltip
                                multiline
                                w={260}
                                label={`${stockLine.available} disponible(s) sur la période, sur un parc de ${stockLine.total_stock}. Le reste est déjà engagé par d'autres prestations ou réservations.`}
                              >
                                <Text
                                  size='sm'
                                  c={stockLine.shortage ? 'orange' : 'green'}
                                >
                                  {stockLine.available} sur{' '}
                                  {stockLine.total_stock}
                                  {stockLine.shortage
                                    ? ` — il manque ${stockLine.missing}`
                                    : ''}
                                </Text>
                              </Tooltip>
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
            </Stack>
          )}

          {hasShortage && (
            <Alert color='orange' title='Stock insuffisant sur la période'>
              Certains articles dépassent le stock disponible. La prestation
              reste enregistrable — le prévisionnel peut légitimement précéder
              l'arbitrage : réduire les quantités, changer la période, ou
              retenir un article équivalent. En revanche une réservation portant
              cette pénurie ne pourra pas être validée tant qu'elle n'est pas
              levée, et elle entrera alors au registre des conflits.
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
