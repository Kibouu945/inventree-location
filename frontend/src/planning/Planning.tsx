// Écran « Planning » — la maquette du cahier des charges : les manifestations
// étalées sur les jours, leur couleur, leur statut, et au survol la fiche avec
// le client, l'interlocuteur, le volume et l'avancement des livraisons.
//
// Pas de bibliothèque de Gantt : une grille CSS suffit, et la vue
// chronologique de FullCalendar est payante. L'ancien écran (calendrier
// mensuel des réservations) reste disponible sous l'onglet Réservations.
import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Group,
  HoverCard,
  Loader,
  SegmentedControl,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
  UnstyledButton
} from '@mantine/core';
import {
  IconCalendarDue,
  IconChevronLeft,
  IconChevronRight
} from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { ownsKeys, syncOwnedParams } from '../urlState';
import {
  barres,
  bornes,
  COULEUR_STATUT,
  colonnes as colonnesDeLaFenetre,
  contientAujourdhui,
  decaler,
  ECHELLES,
  etatDepuisUrl,
  fenetreParDefaut,
  jourDe,
  LARGEUR_COLONNE,
  libelleLivraison,
  libellePeriode,
  libelleStatut,
  PLANNING_URL_KEYS,
  urlDuPlanning
} from './planningLogic';
import type {
  EchellePlanning,
  FenetrePlanning,
  ManifestationPlanning,
  VuePlanning
} from './types';

const MANIFESTATIONS_URL = '/plugin/inventree-location/manifestations/';

/** Largeur de la colonne des noms, à gauche de la grille. */
const LARGEUR_NOMS = 190;

interface Page<T> {
  count: number;
  results: T[];
}

/** Fiche détaillée, au survol d'une barre ou d'une ligne de la liste. */
function Fiche({
  manifestation,
  children
}: {
  manifestation: ManifestationPlanning;
  children: React.ReactNode;
}) {
  const etat = manifestation.etat_livraison;

  return (
    <HoverCard width={300} shadow='md' openDelay={180} withinPortal>
      <HoverCard.Target>{children}</HoverCard.Target>

      <HoverCard.Dropdown>
        <Stack gap={6}>
          <Group gap='xs' justify='space-between'>
            <Text fw={700} size='sm'>
              {manifestation.nom}
            </Text>
            <Badge
              size='sm'
              color={COULEUR_STATUT[manifestation.statut_effectif] || 'gray'}
            >
              {libelleStatut(manifestation.statut_effectif)}
            </Badge>
          </Group>

          <Text size='xs' c='dimmed'>
            {jourDe(manifestation.date_debut)} →{' '}
            {jourDe(manifestation.date_fin)}
          </Text>

          <Text size='sm'>{manifestation.client_nom || '—'}</Text>

          <Text size='xs'>
            {manifestation.organisateur_nom || '—'}
            {manifestation.contact_telephone
              ? ` · ${manifestation.contact_telephone}`
              : ''}
          </Text>

          <Group gap='xs'>
            <Badge size='sm' variant='light'>
              {manifestation.quantite_totale} objet
              {manifestation.quantite_totale > 1 ? 's' : ''}
            </Badge>
            <Badge size='sm' variant='light'>
              {manifestation.prestations_count} prestation
              {manifestation.prestations_count > 1 ? 's' : ''}
            </Badge>
            <Badge
              size='sm'
              variant='light'
              color={etat.a_livrer === 0 && etat.bons > 0 ? 'green' : 'orange'}
            >
              {libelleLivraison(manifestation)}
            </Badge>
          </Group>
        </Stack>
      </HoverCard.Dropdown>
    </HoverCard>
  );
}

export function Planning({ context }: { context: InvenTreePluginContext }) {
  const initial = useMemo(
    () =>
      etatDepuisUrl(
        typeof window === 'undefined' ? '' : window.location.search
      ),
    []
  );

  const [vue, setVue] = useState<VuePlanning>(initial.vue);
  const [fenetre, setFenetre] = useState<FenetrePlanning>(initial.fenetre);

  // Les clés du planning et elles seules : le tableau de bord partage sa query
  // string entre tous les widgets montés.
  useEffect(() => {
    syncOwnedParams(ownsKeys(PLANNING_URL_KEYS), urlDuPlanning(vue, fenetre));
  }, [vue, fenetre]);

  const grille = useMemo(() => colonnesDeLaFenetre(fenetre), [fenetre]);
  const fenetreServeur = useMemo(() => bornes(fenetre), [fenetre]);

  // La fenêtre borne la requête : sur une vue à l'année, demander « le futur »
  // laisserait vides des mois pourtant affichés.
  const query = useQuery<Page<ManifestationPlanning>>(
    {
      queryKey: [
        'planning-manifestations',
        fenetreServeur.from,
        fenetreServeur.to
      ],
      queryFn: async () => {
        const response = await context.api.get(MANIFESTATIONS_URL, {
          params: { ...fenetreServeur, page_size: 100 }
        });

        return response.data;
      }
    },
    context.queryClient
  );

  const manifestations = query.data?.results ?? [];
  const placees = useMemo(
    () => barres(manifestations, grille),
    [manifestations, grille]
  );

  const largeurColonne = LARGEUR_COLONNE[fenetre.echelle];
  const largeurGrille = grille.length * largeurColonne;

  return (
    <Stack gap='md'>
      <Group justify='space-between' align='center'>
        <Group gap='sm' align='baseline'>
          <Title order={4} c={context.theme.primaryColor}>
            Planning
          </Title>
          <Text size='sm' c='dimmed'>
            {libellePeriode(fenetre)}
          </Text>
        </Group>

        <Group gap='xs'>
          <SegmentedControl
            size='xs'
            value={fenetre.echelle}
            onChange={(valeur) =>
              setFenetre(fenetreParDefaut(valeur as EchellePlanning))
            }
            data={ECHELLES}
          />

          <Tooltip label='Période précédente'>
            <ActionIcon
              variant='default'
              onClick={() => setFenetre((f) => decaler(f, -1))}
              aria-label='Reculer'
            >
              <IconChevronLeft size={16} />
            </ActionIcon>
          </Tooltip>

          <Tooltip label="Revenir à aujourd'hui">
            <ActionIcon
              variant='default'
              onClick={() => setFenetre((f) => fenetreParDefaut(f.echelle))}
              aria-label="Aujourd'hui"
            >
              <IconCalendarDue size={16} />
            </ActionIcon>
          </Tooltip>

          <Tooltip label='Période suivante'>
            <ActionIcon
              variant='default'
              onClick={() => setFenetre((f) => decaler(f, 1))}
              aria-label='Avancer'
            >
              <IconChevronRight size={16} />
            </ActionIcon>
          </Tooltip>

          <SegmentedControl
            size='xs'
            value={vue}
            onChange={(valeur) => setVue(valeur as VuePlanning)}
            data={[
              { label: 'Planning', value: 'gantt' },
              { label: 'Liste', value: 'liste' }
            ]}
          />
        </Group>
      </Group>

      {query.isError && (
        <Alert color='red' title='Planning indisponible'>
          Impossible de charger les manifestations.
        </Alert>
      )}

      {query.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : vue === 'liste' ? (
        <PlanningListe barres={placees} />
      ) : (
        <Box style={{ overflowX: 'auto' }}>
          <Box style={{ minWidth: LARGEUR_NOMS + largeurGrille }}>
            <Group gap={0} align='stretch' wrap='nowrap'>
              <Box w={LARGEUR_NOMS} />

              {grille.map((colonne) => (
                <Box
                  key={colonne.debut}
                  w={largeurColonne}
                  style={{
                    textAlign: 'center',
                    borderLeft: '1px solid var(--mantine-color-gray-3)',
                    background: contientAujourdhui(colonne)
                      ? 'var(--mantine-color-blue-0)'
                      : colonne.weekend
                        ? 'var(--mantine-color-gray-1)'
                        : undefined
                  }}
                >
                  <Text size='9px' c='dimmed' style={{ lineHeight: 1.6 }}>
                    {colonne.libelle}
                  </Text>
                </Box>
              ))}
            </Group>

            {placees.length === 0 ? (
              <Text c='dimmed' size='sm' p='md'>
                Aucune manifestation sur cette période.
              </Text>
            ) : (
              <Stack gap={4} mt={4}>
                {placees.map((barre) => (
                  <Group
                    key={barre.manifestation.id}
                    gap={0}
                    align='center'
                    wrap='nowrap'
                  >
                    <Box w={LARGEUR_NOMS} pr='xs'>
                      <Text
                        size='xs'
                        truncate='end'
                        title={barre.manifestation.nom}
                      >
                        {barre.manifestation.nom}
                      </Text>
                      <Text size='9px' c='dimmed' truncate='end'>
                        {barre.manifestation.client_nom}
                      </Text>
                    </Box>

                    <Box
                      style={{
                        position: 'relative',
                        width: largeurGrille,
                        height: 26
                      }}
                    >
                      {grille.map((colonne, index) => (
                        <Box
                          key={colonne.debut}
                          style={{
                            position: 'absolute',
                            left: index * largeurColonne,
                            top: 0,
                            bottom: 0,
                            width: largeurColonne,
                            borderLeft: '1px solid var(--mantine-color-gray-2)',
                            background: contientAujourdhui(colonne)
                              ? 'var(--mantine-color-blue-0)'
                              : colonne.weekend
                                ? 'var(--mantine-color-gray-0)'
                                : undefined
                          }}
                        />
                      ))}

                      <Fiche manifestation={barre.manifestation}>
                        <UnstyledButton
                          style={{
                            position: 'absolute',
                            left: (barre.colonne - 1) * largeurColonne + 2,
                            width: barre.largeur * largeurColonne - 4,
                            top: 3,
                            height: 20,
                            background:
                              barre.manifestation.couleur || '#868e96',
                            color: '#fff',
                            borderRadius: 4,
                            paddingInline: 6,
                            // Le rognage se voit : bord droit quand la
                            // manifestation continue après la fenêtre.
                            borderLeft: barre.deborde_avant
                              ? '3px dotted #fff'
                              : undefined,
                            borderRight: barre.deborde_apres
                              ? '3px dotted #fff'
                              : undefined
                          }}
                        >
                          <Text size='10px' truncate='end' c='#fff'>
                            {barre.manifestation.quantite_totale} obj ·{' '}
                            {libelleLivraison(barre.manifestation)}
                          </Text>
                        </UnstyledButton>
                      </Fiche>
                    </Box>
                  </Group>
                ))}
              </Stack>
            )}
          </Box>
        </Box>
      )}

      <Text size='xs' c='dimmed'>
        {placees.length} manifestation(s) sur la période · survolez une barre
        pour le contact et l'avancement
      </Text>
    </Stack>
  );
}

/** La même période, en liste — la bascule de la maquette. */
function PlanningListe({
  barres: placees
}: {
  barres: ReturnType<typeof barres>;
}) {
  if (placees.length === 0) {
    return (
      <Text c='dimmed' size='sm'>
        Aucune manifestation sur cette période.
      </Text>
    );
  }

  return (
    <Table striped highlightOnHover>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Manifestation</Table.Th>
          <Table.Th>Client</Table.Th>
          <Table.Th>Période</Table.Th>
          <Table.Th>Contact</Table.Th>
          <Table.Th>Objets</Table.Th>
          <Table.Th>Livraisons</Table.Th>
          <Table.Th>Statut</Table.Th>
        </Table.Tr>
      </Table.Thead>

      <Table.Tbody>
        {placees.map(({ manifestation }) => (
          <Table.Tr key={manifestation.id}>
            <Table.Td>
              <Group gap={6} wrap='nowrap'>
                <Box
                  w={10}
                  h={10}
                  style={{
                    borderRadius: 2,
                    background: manifestation.couleur || '#868e96'
                  }}
                />
                <Fiche manifestation={manifestation}>
                  <Text size='sm' fw={600}>
                    {manifestation.nom}
                  </Text>
                </Fiche>
              </Group>
            </Table.Td>

            <Table.Td>{manifestation.client_nom || '—'}</Table.Td>

            <Table.Td>
              <Text size='xs'>
                {jourDe(manifestation.date_debut)} →{' '}
                {jourDe(manifestation.date_fin)}
              </Text>
            </Table.Td>

            <Table.Td>
              <Text size='xs'>{manifestation.organisateur_nom || '—'}</Text>
              <Text size='9px' c='dimmed'>
                {manifestation.contact_telephone || '—'}
              </Text>
            </Table.Td>

            <Table.Td>{manifestation.quantite_totale}</Table.Td>

            <Table.Td>{libelleLivraison(manifestation)}</Table.Td>

            <Table.Td>
              <Badge
                size='sm'
                color={COULEUR_STATUT[manifestation.statut_effectif] || 'gray'}
              >
                {libelleStatut(manifestation.statut_effectif)}
              </Badge>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}
