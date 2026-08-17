// SCRUM-89 + SCRUM-112 — Liste des ramassages, bon imprimable et saisie retour.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Group,
  Loader,
  Modal,
  MultiSelect,
  NumberInput,
  Stack,
  Table,
  Text,
  Textarea,
  TextInput,
  Title
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { useDebouncedValue } from '@mantine/hooks';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import type { Page, Ramassage } from './types';

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

interface LigneBonRamassage112 {
  id: number;
  part: number;
  part_nom: string;
  quantite_demandee: number;
  quantite_livree: number;
  quantite_a_ramasser: number;
  quantite_retournee: number;
  quantite_ramassee: number;
  quantite_sav: number;
  quantite_detruite: number;
  quantite_manquante: number;
  facturer_client: boolean;
  etat_retour: string;
  commentaire: string;
}

interface BonRamassageResponse112 {
  titre: string;
  generated_at: string;
  reservation: Ramassage & {
    lignes: LigneBonRamassage112[];
    commentaire: string;
  };
}

interface RetourLineForm {
  ligne: number;
  partNom: string;
  quantiteAttendue: number;
  quantite_ramassee: number;
  quantite_sav: number;
  quantite_detruite: number;
  quantite_manquante: number;
  facturer_client: boolean;
  commentaire: string;
}

interface RetourRamassagePayload {
  commentaire: string;
  lignes: Array<{
    ligne: number;
    quantite_ramassee: number;
    quantite_sav: number;
    quantite_detruite: number;
    quantite_manquante: number;
    facturer_client: boolean;
    commentaire: string;
  }>;
}

interface RetourRamassageResponse {
  reservation: number;
  numero: string;
  statut: string;
  updated_lines: Array<{
    id: number;
    part: number;
    quantite_ramassee: number;
    quantite_sav: number;
    quantite_detruite: number;
    quantite_manquante: number;
    facturer_client: boolean;
    etat_retour: string;
  }>;
  sav_tickets: number[];
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

function numberValue(value: string | number | null | undefined): number {
  if (typeof value === 'number') {
    return Number.isNaN(value) ? 0 : value;
  }

  const parsed = Number(value);

  return Number.isNaN(parsed) ? 0 : parsed;
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
  if (!ramassage.lieux || ramassage.lieux.length === 0) {
    return '—';
  }

  return ramassage.lieux
    .map((lieu) => lieu.nom || lieu.adresse)
    .filter(Boolean)
    .join(', ');
}

function lineExpectedQuantity(ligne: LigneBonRamassage112): number {
  return (
    ligne.quantite_a_ramasser ||
    ligne.quantite_livree ||
    ligne.quantite_demandee ||
    0
  );
}

function lineFormFromBon(ligne: LigneBonRamassage112): RetourLineForm {
  return {
    ligne: ligne.id,
    partNom: ligne.part_nom,
    quantiteAttendue: lineExpectedQuantity(ligne),
    quantite_ramassee:
      ligne.quantite_ramassee ||
      ligne.quantite_retournee ||
      0,
    quantite_sav: ligne.quantite_sav || 0,
    quantite_detruite: ligne.quantite_detruite || 0,
    quantite_manquante: ligne.quantite_manquante || 0,
    facturer_client: Boolean(ligne.facturer_client),
    commentaire: ligne.commentaire || ''
  };
}

function totalRetour(line: RetourLineForm): number {
  return (
    line.quantite_ramassee +
    line.quantite_sav +
    line.quantite_detruite +
    line.quantite_manquante
  );
}

function retourPayload(
  lines: RetourLineForm[],
  commentaire: string
): RetourRamassagePayload {
  return {
    commentaire,
    lignes: lines.map((line) => ({
      ligne: line.ligne,
      quantite_ramassee: line.quantite_ramassee,
      quantite_sav: line.quantite_sav,
      quantite_detruite: line.quantite_detruite,
      quantite_manquante: line.quantite_manquante,
      facturer_client: line.facturer_client,
      commentaire: line.commentaire
    }))
  };
}

function BonRamassageContent({
  bon,
  retourLines,
  onChangeLine,
  commentaireRetour,
  onChangeCommentaireRetour,
  onSaveRetour,
  isSaving,
  saveError,
  saveSuccess
}: {
  bon: BonRamassageResponse112;
  retourLines: RetourLineForm[];
  onChangeLine: (index: number, patch: Partial<RetourLineForm>) => void;
  commentaireRetour: string;
  onChangeCommentaireRetour: (value: string) => void;
  onSaveRetour: () => void;
  isSaving: boolean;
  saveError: string;
  saveSuccess: string;
}) {
  const reservation = bon.reservation;

  const hasInvalidLines = retourLines.some(
    (line) => totalRetour(line) > line.quantiteAttendue
  );

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
          <Table.Tr>
            <Table.Th>Statut</Table.Th>
            <Table.Td>
              <Badge color={STATUT_COLORS[reservation.statut] ?? 'gray'}>
                {reservation.statut}
              </Badge>
            </Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>

      <Title order={5}>Retour terrain</Title>

      <Alert color='blue' title='SCRUM-112 — stock réel'>
        Au ramassage, renseigner pour chaque article les quantités ramassées en bon
        état, envoyées au SAV, détruites ou manquantes. Les quantités SAV,
        détruites et manquantes sortent du stock réellement disponible.
      </Alert>

      {saveError && (
        <Alert color='red' title='Erreur retour'>
          {saveError}
        </Alert>
      )}

      {saveSuccess && (
        <Alert color='green' title='Retour enregistré'>
          {saveSuccess}
        </Alert>
      )}

      <Table striped withTableBorder>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Article</Table.Th>
            <Table.Th>À ramasser</Table.Th>
            <Table.Th>Ramassée OK</Table.Th>
            <Table.Th>SAV</Table.Th>
            <Table.Th>Détruite</Table.Th>
            <Table.Th>Manquante</Table.Th>
            <Table.Th>Facturer</Table.Th>
            <Table.Th>Commentaire</Table.Th>
            <Table.Th>Total saisi</Table.Th>
          </Table.Tr>
        </Table.Thead>

        <Table.Tbody>
          {retourLines.map((line, index) => {
            const total = totalRetour(line);
            const invalid = total > line.quantiteAttendue;

            return (
              <Table.Tr key={line.ligne}>
                <Table.Td>
                  <Text fw={500}>{line.partNom}</Text>
                </Table.Td>

                <Table.Td>{line.quantiteAttendue}</Table.Td>

                <Table.Td>
                  <NumberInput
                    min={0}
                    value={line.quantite_ramassee}
                    onChange={(value) =>
                      onChangeLine(index, {
                        quantite_ramassee: numberValue(value)
                      })
                    }
                    w={90}
                  />
                </Table.Td>

                <Table.Td>
                  <NumberInput
                    min={0}
                    value={line.quantite_sav}
                    onChange={(value) =>
                      onChangeLine(index, {
                        quantite_sav: numberValue(value)
                      })
                    }
                    w={90}
                  />
                </Table.Td>

                <Table.Td>
                  <NumberInput
                    min={0}
                    value={line.quantite_detruite}
                    onChange={(value) =>
                      onChangeLine(index, {
                        quantite_detruite: numberValue(value)
                      })
                    }
                    w={90}
                  />
                </Table.Td>

                <Table.Td>
                  <NumberInput
                    min={0}
                    value={line.quantite_manquante}
                    onChange={(value) =>
                      onChangeLine(index, {
                        quantite_manquante: numberValue(value)
                      })
                    }
                    w={90}
                  />
                </Table.Td>

                <Table.Td>
                  <Checkbox
                    checked={line.facturer_client}
                    onChange={(event) =>
                      onChangeLine(index, {
                        facturer_client: event.currentTarget.checked
                      })
                    }
                  />
                </Table.Td>

                <Table.Td>
                  <Textarea
                    autosize
                    minRows={1}
                    value={line.commentaire}
                    onChange={(event) =>
                      onChangeLine(index, {
                        commentaire: event.currentTarget.value
                      })
                    }
                    placeholder='État, casse, remarque…'
                    w={220}
                  />
                </Table.Td>

                <Table.Td>
                  <Badge color={invalid ? 'red' : 'green'}>
                    {total} / {line.quantiteAttendue}
                  </Badge>
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Table>

      {hasInvalidLines && (
        <Alert color='red' title='Quantités invalides'>
          Une ou plusieurs lignes dépassent la quantité à ramasser. Corrige les
          quantités avant d’enregistrer le retour.
        </Alert>
      )}

      <Textarea
        label='Commentaire global du retour'
        value={commentaireRetour}
        onChange={(event) => onChangeCommentaireRetour(event.currentTarget.value)}
        placeholder='Ex : retour terrain saisi par le livreur, contrôle magasinier à prévoir…'
        autosize
        minRows={2}
      />

      <Group justify='space-between'>
        <Button variant='default' onClick={() => window.print()}>
          Imprimer
        </Button>

        <Button
          onClick={onSaveRetour}
          loading={isSaving}
          disabled={hasInvalidLines || retourLines.length === 0}
        >
          Enregistrer le retour
        </Button>
      </Group>

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
          <Title order={5}>Commentaire réservation</Title>
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
  const [retourLines, setRetourLines] = useState<RetourLineForm[]>([]);
  const [commentaireRetour, setCommentaireRetour] = useState('');
  const [isSavingRetour, setIsSavingRetour] = useState(false);
  const [saveRetourError, setSaveRetourError] = useState('');
  const [saveRetourSuccess, setSaveRetourSuccess] = useState('');

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

  const bonQuery = useQuery<BonRamassageResponse112>(
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

  useEffect(() => {
    if (!bonQuery.data) {
      return;
    }

    setRetourLines(bonQuery.data.reservation.lignes.map(lineFormFromBon));
    setCommentaireRetour(bonQuery.data.reservation.commentaire || '');
    setSaveRetourError('');
    setSaveRetourSuccess('');
  }, [bonQuery.data]);

  const rows = Array.isArray(query.data)
    ? query.data
    : (query.data?.results ?? []);

  function updateRetourLine(index: number, patch: Partial<RetourLineForm>) {
    setRetourLines((currentLines) =>
      currentLines.map((line, currentIndex) =>
        currentIndex === index ? { ...line, ...patch } : line
      )
    );
  }

  async function saveRetour() {
    if (!bonModal.reservationId) {
      return;
    }

    setIsSavingRetour(true);
    setSaveRetourError('');
    setSaveRetourSuccess('');

    try {
      const payload = retourPayload(retourLines, commentaireRetour);

      const response = await context.api.patch(
        `${RAMASSAGES_URL}${bonModal.reservationId}/retour/`,
        payload
      );

      const data = response.data as RetourRamassageResponse;

      setSaveRetourSuccess(
        `Retour enregistré pour ${data.numero}. Statut : ${data.statut}. Tickets SAV : ${data.sav_tickets.length}.`
      );

      await bonQuery.refetch();
      await query.refetch();
    } catch (error: any) {
      const detail =
        error?.response?.data?.detail ||
        JSON.stringify(error?.response?.data || error?.message || error);

      setSaveRetourError(detail);
    } finally {
      setIsSavingRetour(false);
    }
  }

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
              <Table.Th>Retour</Table.Th>
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
                    Voir / retour
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
        size='100%'
        title='Bon de ramassage / retour terrain'
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
          <BonRamassageContent
            bon={bonQuery.data}
            retourLines={retourLines}
            onChangeLine={updateRetourLine}
            commentaireRetour={commentaireRetour}
            onChangeCommentaireRetour={setCommentaireRetour}
            onSaveRetour={saveRetour}
            isSaving={isSavingRetour}
            saveError={saveRetourError}
            saveSuccess={saveRetourSuccess}
          />
        ) : null}
      </Modal>
    </Stack>
  );
}