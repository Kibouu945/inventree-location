// Écran « Planning » — la maquette du cahier des charges : les manifestations
// étalées sur les jours, leur couleur, leur statut, et au survol la fiche avec
// le client, l'interlocuteur, le volume et l'avancement des livraisons.
//
// La maquette et la recette du 11/09 demandent **une ligne par prestation**.
// La barre de la manifestation est conservée et se déplie sur ses prestations :
// on garde la vue d'ensemble — couleur, volume total, avancement — tout en
// donnant le détail, là où descendre sec d'un cran l'aurait perdue.
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
import { useElementSize } from '@mantine/hooks';
import {
  IconCalendarDue,
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
  IconLayoutNavbarCollapse,
  IconLayoutNavbarExpand
} from '@tabler/icons-react';
import { useQuery } from '@tanstack/react-query';
import { Fragment, useEffect, useMemo, useState } from 'react';

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
  HAUTEUR,
  jourDe,
  LARGEUR_NOMS,
  largeurDeColonne,
  libelleLivraison,
  libellePeriode,
  libelleStatut,
  PLANNING_URL_KEYS,
  parManifestation,
  urlDuPlanning
} from './planningLogic';
import type {
  Barre,
  EchellePlanning,
  FenetrePlanning,
  LignePlanning,
  ManifestationPlanning,
  PrestationPlanning,
  VuePlanning
} from './types';

const MANIFESTATIONS_URL = '/plugin/inventree-location/manifestations/';
const PRESTATIONS_URL = '/plugin/inventree-location/prestations/';

/** Plafond de la pagination serveur (`LieuPagination.max_page_size`). */
const PAGE_MAX = 100;

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

/** Fiche d'une prestation, au survol de sa sous-ligne. */
function FichePrestation({
  prestation,
  children
}: {
  prestation: PrestationPlanning;
  children: React.ReactNode;
}) {
  return (
    <HoverCard width={280} shadow='md' openDelay={180} withinPortal>
      <HoverCard.Target>{children}</HoverCard.Target>

      <HoverCard.Dropdown>
        <Stack gap={6}>
          <Text fw={700} size='sm'>
            {prestation.nom}
          </Text>

          <Text size='xs' c='dimmed'>
            {jourDe(prestation.date_debut)} → {jourDe(prestation.date_fin)}
          </Text>

          <Text size='sm'>
            {prestation.lieu_detail?.nom || 'Lieu à définir'}
          </Text>

          <Group gap='xs'>
            <Badge size='sm' variant='light'>
              {prestation.quantite_totale} objet
              {prestation.quantite_totale > 1 ? 's' : ''}
            </Badge>
            <Badge size='sm' variant='light'>
              {libelleLivraison(prestation)}
            </Badge>
          </Group>
        </Stack>
      </HoverCard.Dropdown>
    </HoverCard>
  );
}

/** Le fond d'une ligne : les colonnes de la grille, week-ends et jour courant.
 *
 * Une piste par ligne et non un fond unique derrière toutes : les lignes se
 * déplient et se replient, leur nombre change, et un fond absolu devrait être
 * redimensionné à la main à chaque bascule.
 */
function Piste({
  grille,
  largeurColonne,
  hauteur,
  children
}: {
  grille: ReturnType<typeof colonnesDeLaFenetre>;
  largeurColonne: number;
  hauteur: number;
  children: React.ReactNode;
}) {
  return (
    <Box
      style={{
        position: 'relative',
        width: grille.length * largeurColonne,
        height: hauteur
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

      {children}
    </Box>
  );
}

/** Position et largeur d'une barre dans la piste, en pixels. */
function geometrie(barre: Barre<LignePlanning>, largeurColonne: number) {
  return {
    left: (barre.colonne - 1) * largeurColonne + 2,
    width: barre.largeur * largeurColonne - 4,
    // Le rognage se voit : bord pointillé quand le sujet continue au-delà.
    borderLeft: barre.deborde_avant ? '3px dotted #fff' : undefined,
    borderRight: barre.deborde_apres ? '3px dotted #fff' : undefined
  };
}

/** Le chevron de dépliage d'une manifestation.
 *
 * Désactivé — et non caché — quand la manifestation n'a aucune prestation dans
 * la période : la colonne des noms garde son alignement, et le survol dit
 * pourquoi il ne se passe rien.
 */
function Deplier({
  ouverte,
  sousLignes,
  onClick
}: {
  ouverte: boolean;
  sousLignes: number;
  onClick: () => void;
}) {
  const vide = sousLignes === 0;

  return (
    <Tooltip
      label={
        vide
          ? 'Aucune prestation sur cette période'
          : ouverte
            ? 'Replier les prestations'
            : `Déplier ${sousLignes} prestation${sousLignes > 1 ? 's' : ''}`
      }
    >
      <ActionIcon
        size='xs'
        variant='subtle'
        color='gray'
        disabled={vide}
        onClick={onClick}
        aria-label={ouverte ? 'Replier' : 'Déplier'}
      >
        {ouverte ? (
          <IconChevronDown size={14} />
        ) : (
          <IconChevronRight size={14} />
        )}
      </ActionIcon>
    </Tooltip>
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
  const [ouvertes, setOuvertes] = useState<Set<number>>(initial.ouvertes);

  // Les clés du planning et elles seules : le tableau de bord partage sa query
  // string entre tous les widgets montés.
  useEffect(() => {
    syncOwnedParams(
      ownsKeys(PLANNING_URL_KEYS),
      urlDuPlanning(vue, fenetre, ouvertes)
    );
  }, [vue, fenetre, ouvertes]);

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
          params: { ...fenetreServeur, page_size: PAGE_MAX }
        });

        return response.data;
      }
    },
    context.queryClient
  );

  // Les prestations de la **fenêtre**, en une requête, et non celles de chaque
  // manifestation au dépliage : déplier devient instantané, et le nombre de
  // requêtes ne dépend plus du nombre de lignes ouvertes.
  const prestationsQuery = useQuery<Page<PrestationPlanning>>(
    {
      queryKey: [
        'planning-prestations',
        fenetreServeur.from,
        fenetreServeur.to
      ],
      queryFn: async () => {
        const response = await context.api.get(PRESTATIONS_URL, {
          params: { ...fenetreServeur, page_size: PAGE_MAX }
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

  const prestations = prestationsQuery.data?.results ?? [];
  const sousLignes = useMemo(
    () => parManifestation(prestations),
    [prestations]
  );

  // Ce qui est réellement montrable : une prestation ne s'affiche que sous la
  // barre de sa manifestation. Les dates d'une prestation sont bornées par
  // celles de sa manifestation — mais par le sérialiseur seulement, pas par la
  // base : une donnée écrite hors API peut déborder, et compter ici les
  // prestations chargées plutôt que les prestations placées annoncerait des
  // lignes que personne ne peut voir.
  const prestationsAffichees = placees.reduce(
    (total, barre) => total + (sousLignes.get(barre.sujet.id)?.length ?? 0),
    0
  );

  // Ce que la pagination a laissé de côté. Le dire plutôt que de l'afficher en
  // silence : un planning amputé se lit comme un planning vide.
  const prestationsTronquees =
    (prestationsQuery.data?.count ?? 0) - prestations.length;

  const basculer = (id: number) =>
    setOuvertes((precedent) => {
      const suivant = new Set(precedent);
      suivant.has(id) ? suivant.delete(id) : suivant.add(id);
      return suivant;
    });

  // La grille occupe la largeur du panneau : le planning est posé dans un
  // poste de travail dont la largeur dépend de l'écran, et une grille figée y
  // laissait un tiers de vide à droite.
  const { ref: cadre, width: largeurCadre } = useElementSize();
  const largeurColonne = largeurDeColonne(
    fenetre.echelle,
    grille.length,
    largeurCadre - LARGEUR_NOMS
  );
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

          <Tooltip
            label={
              ouvertes.size > 0
                ? 'Replier toutes les manifestations'
                : 'Déplier toutes les manifestations'
            }
          >
            <ActionIcon
              variant='default'
              onClick={() =>
                setOuvertes(
                  ouvertes.size > 0 ? new Set() : new Set(sousLignes.keys())
                )
              }
              aria-label={ouvertes.size > 0 ? 'Tout replier' : 'Tout déplier'}
            >
              {ouvertes.size > 0 ? (
                <IconLayoutNavbarCollapse size={16} />
              ) : (
                <IconLayoutNavbarExpand size={16} />
              )}
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

      {prestationsQuery.isError && (
        <Alert color='orange' title='Prestations indisponibles'>
          Les manifestations s'affichent, mais leur détail n'a pas pu être
          chargé.
        </Alert>
      )}

      {query.isLoading ? (
        <Group justify='center' p='xl'>
          <Loader />
        </Group>
      ) : vue === 'liste' ? (
        <PlanningListe
          barres={placees}
          sousLignes={sousLignes}
          ouvertes={ouvertes}
          onBasculer={basculer}
        />
      ) : (
        <Box ref={cadre} style={{ overflowX: 'auto' }}>
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
                  <Text size='10px' c='dimmed' style={{ lineHeight: 1.8 }}>
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
                {placees.map((barre) => {
                  const manifestation = barre.sujet;
                  const prestationsDeLaBarre =
                    sousLignes.get(manifestation.id) ?? [];
                  const ouverte = ouvertes.has(manifestation.id);
                  const hors =
                    manifestation.prestations_count -
                    prestationsDeLaBarre.length;

                  return (
                    <Box key={manifestation.id}>
                      <Group gap={0} align='center' wrap='nowrap'>
                        <Group
                          w={LARGEUR_NOMS}
                          pr='xs'
                          gap={4}
                          wrap='nowrap'
                          align='center'
                        >
                          <Deplier
                            ouverte={ouverte}
                            sousLignes={prestationsDeLaBarre.length}
                            onClick={() => basculer(manifestation.id)}
                          />

                          <Box style={{ minWidth: 0, flex: 1 }}>
                            <Text
                              size='sm'
                              fw={600}
                              truncate='end'
                              title={manifestation.nom}
                            >
                              {manifestation.nom}
                            </Text>
                            <Text size='xs' c='dimmed' truncate='end'>
                              {manifestation.client_nom}
                            </Text>
                          </Box>
                        </Group>

                        <Piste
                          grille={grille}
                          largeurColonne={largeurColonne}
                          hauteur={HAUTEUR.ligne}
                        >
                          <Fiche manifestation={manifestation}>
                            <UnstyledButton
                              style={{
                                position: 'absolute',
                                top: (HAUTEUR.ligne - HAUTEUR.barre) / 2,
                                height: HAUTEUR.barre,
                                background: manifestation.couleur || '#868e96',
                                color: '#fff',
                                borderRadius: 4,
                                paddingInline: 6,
                                ...geometrie(barre, largeurColonne)
                              }}
                            >
                              <Text size='xs' truncate='end' c='#fff'>
                                {manifestation.quantite_totale} obj ·{' '}
                                {libelleLivraison(manifestation)}
                              </Text>
                            </UnstyledButton>
                          </Fiche>
                        </Piste>
                      </Group>

                      {ouverte &&
                        barres(prestationsDeLaBarre, grille).map(
                          (sousBarre) => (
                            <Group
                              key={sousBarre.sujet.id}
                              gap={0}
                              align='center'
                              wrap='nowrap'
                            >
                              <Box w={LARGEUR_NOMS} pr='xs' pl={28}>
                                <Text
                                  size='xs'
                                  truncate='end'
                                  title={sousBarre.sujet.nom}
                                >
                                  {sousBarre.sujet.nom}
                                </Text>
                                <Text size='10px' c='dimmed' truncate='end'>
                                  {sousBarre.sujet.lieu_detail?.nom ||
                                    'Lieu à définir'}
                                </Text>
                              </Box>

                              <Piste
                                grille={grille}
                                largeurColonne={largeurColonne}
                                hauteur={HAUTEUR.sousLigne}
                              >
                                <FichePrestation prestation={sousBarre.sujet}>
                                  <UnstyledButton
                                    style={{
                                      position: 'absolute',
                                      top:
                                        (HAUTEUR.sousLigne -
                                          HAUTEUR.sousBarre) /
                                        2,
                                      height: HAUTEUR.sousBarre,
                                      // La couleur de la manifestation, en
                                      // plus clair : la sous-ligne se rattache
                                      // à l'œil à sa barre.
                                      background:
                                        manifestation.couleur || '#868e96',
                                      opacity: 0.55,
                                      color: '#fff',
                                      borderRadius: 3,
                                      paddingInline: 5,
                                      ...geometrie(sousBarre, largeurColonne)
                                    }}
                                  >
                                    <Text size='10px' truncate='end' c='#fff'>
                                      {sousBarre.sujet.quantite_totale} obj
                                    </Text>
                                  </UnstyledButton>
                                </FichePrestation>
                              </Piste>
                            </Group>
                          )
                        )}

                      {ouverte && hors > 0 && (
                        <Text size='10px' c='dimmed' pl={28}>
                          {hors} prestation{hors > 1 ? 's' : ''} hors de la
                          période
                        </Text>
                      )}
                    </Box>
                  );
                })}
              </Stack>
            )}
          </Box>
        </Box>
      )}

      <Text size='xs' c='dimmed'>
        {placees.length} manifestation(s) et {prestationsAffichees}{' '}
        prestation(s) sur la période · survolez une barre pour le contact et
        l'avancement
        {prestationsTronquees > 0
          ? ` · ${prestationsTronquees} prestation(s) non affichée(s), affinez la période`
          : ''}
      </Text>
    </Stack>
  );
}

/** La même période, en liste — la bascule de la maquette. */
function PlanningListe({
  barres: placees,
  sousLignes,
  ouvertes,
  onBasculer
}: {
  barres: Barre<ManifestationPlanning>[];
  sousLignes: Map<number, PrestationPlanning[]>;
  ouvertes: Set<number>;
  onBasculer: (id: number) => void;
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
          <Table.Th w={32} />
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
        {placees.map(({ sujet: manifestation }) => {
          const prestations = sousLignes.get(manifestation.id) ?? [];
          const ouverte = ouvertes.has(manifestation.id);

          return (
            <Fragment key={manifestation.id}>
              <Table.Tr>
                <Table.Td>
                  <Deplier
                    ouverte={ouverte}
                    sousLignes={prestations.length}
                    onClick={() => onBasculer(manifestation.id)}
                  />
                </Table.Td>

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
                    color={
                      COULEUR_STATUT[manifestation.statut_effectif] || 'gray'
                    }
                  >
                    {libelleStatut(manifestation.statut_effectif)}
                  </Badge>
                </Table.Td>
              </Table.Tr>

              {ouverte &&
                prestations.map((prestation) => (
                  <Table.Tr key={prestation.id}>
                    <Table.Td />
                    <Table.Td pl={28}>
                      <Text size='xs'>{prestation.nom}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size='xs' c='dimmed'>
                        {prestation.lieu_detail?.nom || 'Lieu à définir'}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size='xs'>
                        {jourDe(prestation.date_debut)} →{' '}
                        {jourDe(prestation.date_fin)}
                      </Text>
                    </Table.Td>
                    <Table.Td />
                    <Table.Td>{prestation.quantite_totale}</Table.Td>
                    <Table.Td>{libelleLivraison(prestation)}</Table.Td>
                    <Table.Td />
                  </Table.Tr>
                ))}
            </Fragment>
          );
        })}
      </Table.Tbody>
    </Table>
  );
}
