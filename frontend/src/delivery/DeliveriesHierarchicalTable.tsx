import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Checkbox,
  FileInput,
  Group,
  Image,
  Modal,
  NumberInput,
  SegmentedControl,
  Stack,
  Text,
  Tooltip,
  UnstyledButton
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconCamera,
  IconCheck,
  IconChevronDown,
  IconChevronRight,
  IconMinus,
  IconPlus,
  IconUpload
} from '@tabler/icons-react';
import { useMemo, useState } from 'react';

import type { Delivery, DeliveryLigne } from './types';

export type DeliveryAvancementFilter =
  | 'tous'
  | 'a_faire'
  | 'partiel'
  | 'complet';

const FOND = {
  manifestation: 'var(--mantine-color-gray-3)',
  prestation: 'var(--mantine-color-blue-1)',
  bon: 'var(--mantine-color-red-0)',
  article: 'var(--mantine-color-yellow-0)'
};

type Avancement = 'rien' | 'partiel' | 'complet';

function computeAvancement(fait: number, attendu: number): Avancement {
  if (attendu <= 0 || fait <= 0) {
    return 'rien';
  }
  return fait >= attendu ? 'complet' : 'partiel';
}

function agregerAvancement(etats: Avancement[]): Avancement {
  if (etats.length === 0 || etats.every((e) => e === 'rien')) {
    return 'rien';
  }
  return etats.every((e) => e === 'complet') ? 'complet' : 'partiel';
}

function Pastille({
  lettre,
  etat,
  libelle
}: {
  lettre: 'L' | 'R';
  etat: Avancement;
  libelle: string;
}) {
  if (etat === 'rien') {
    return (
      <Tooltip label={`${libelle} : à faire`}>
        <Badge
          circle
          variant='outline'
          color='gray'
          styles={{ label: { fontSize: 10 } }}
        >
          {lettre}
        </Badge>
      </Tooltip>
    );
  }

  const couleur =
    etat === 'complet' ? (lettre === 'R' ? 'grape' : 'green') : 'yellow';

  return (
    <Tooltip label={`${libelle} : ${etat}`}>
      <Badge circle color={couleur} styles={{ label: { fontSize: 10 } }}>
        {lettre}
      </Badge>
    </Tooltip>
  );
}

function Chevron({ ouvert }: { ouvert: boolean }) {
  return ouvert ? (
    <IconChevronDown size={16} />
  ) : (
    <IconChevronRight size={16} />
  );
}

function Ligne({
  fond,
  indentation,
  children
}: {
  fond: string;
  indentation: number;
  children: React.ReactNode;
}) {
  return (
    <Box
      style={{
        background: fond,
        marginLeft: indentation,
        borderRadius: 4,
        marginBottom: 3
      }}
      px='sm'
      py={6}
    >
      {children}
    </Box>
  );
}

interface LigneState {
  quantiteLivree: number;
  validee: boolean;
  photoUrl: string | null;
}

export function DeliveriesHierarchicalTable({
  context: _context,
  deliveries,
  onLivrerReservations,
  onOpenNote
}: {
  context?: InvenTreePluginContext;
  deliveries: Delivery[];
  onLivrerReservations: (reservationIds: number[]) => Promise<void>;
  onOpenNote?: (delivery: Delivery) => void;
}) {
  const [filterAvancement, setFilterAvancement] =
    useState<DeliveryAvancementFilter>('tous');
  const [ouverts, setOuverts] = useState<Set<string>>(new Set());
  const [lignesState, setLignesState] = useState<Record<number, LigneState>>(
    {}
  );
  const [photoModal, setPhotoModal] = useState<{
    ligneId: number;
    partName: string;
  } | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);

  function getLigneState(
    ligne: DeliveryLigne,
    isDelivered: boolean
  ): LigneState {
    const existing = lignesState[ligne.id];
    if (existing) {
      return existing;
    }
    const defaultLivree = isDelivered
      ? ligne.quantite_demandee
      : (ligne.quantite_livree ?? 0);
    return {
      quantiteLivree: defaultLivree,
      validee: isDelivered,
      photoUrl: null
    };
  }

  function setLigneState(ligneId: number, patch: Partial<LigneState>) {
    setLignesState((prev) => {
      const current = prev[ligneId] ?? {
        quantiteLivree: 0,
        validee: false,
        photoUrl: null
      };
      return {
        ...prev,
        [ligneId]: { ...current, ...patch }
      };
    });
  }

  function toggleOuvert(cle: string) {
    setOuverts((prev) => {
      const next = new Set(prev);
      if (next.has(cle)) {
        next.delete(cle);
      } else {
        next.add(cle);
      }
      return next;
    });
  }

  const hierarchicalData = useMemo(() => {
    const manifestationsMap = new Map<
      string,
      {
        nom: string;
        clientNom: string;
        prestationsMap: Map<
          string,
          {
            nom: string;
            lieuNom: string;
            dateRetrait: string | null;
            bons: Delivery[];
          }
        >;
      }
    >();

    for (const d of deliveries) {
      const manifNom =
        d.manifestation_nom ||
        d.prestation_nom ||
        d.lieu_detail?.nom ||
        'Manifestation générale';
      const prestNom = d.prestation_nom || 'Prestation standard';

      if (!manifestationsMap.has(manifNom)) {
        manifestationsMap.set(manifNom, {
          nom: manifNom,
          clientNom: d.client_nom || '',
          prestationsMap: new Map()
        });
      }
      const manif = manifestationsMap.get(manifNom)!;
      if (!manif.prestationsMap.has(prestNom)) {
        manif.prestationsMap.set(prestNom, {
          nom: prestNom,
          lieuNom: d.lieu_detail?.nom || d.lieu_detail?.adresse || '—',
          dateRetrait: d.date_retrait_prevue,
          bons: []
        });
      }
      manif.prestationsMap.get(prestNom)?.bons.push(d);
    }

    return Array.from(manifestationsMap.values()).map((manif) => ({
      nom: manif.nom,
      clientNom: manif.clientNom,
      prestations: Array.from(manif.prestationsMap.values()).map((prest) => ({
        nom: prest.nom,
        lieuNom: prest.lieuNom,
        dateRetrait: prest.dateRetrait,
        bons: prest.bons
      }))
    }));
  }, [deliveries]);

  const filteredHierarchy = useMemo(() => {
    if (filterAvancement === 'tous') {
      return hierarchicalData;
    }

    return hierarchicalData
      .map((manif) => {
        const filteredPrestations = manif.prestations
          .map((prest) => {
            const filteredBons = prest.bons.filter((bon) => {
              const isDelivered = bon.statut === 'livree';
              const etats = bon.lignes.map((l) => {
                const state = getLigneState(l, isDelivered);
                return computeAvancement(
                  state.quantiteLivree,
                  l.quantite_demandee
                );
              });
              const bonAvancement = agregerAvancement(etats);

              if (filterAvancement === 'a_faire') {
                return bonAvancement === 'rien';
              }
              if (filterAvancement === 'partiel') {
                return bonAvancement === 'partiel';
              }
              if (filterAvancement === 'complet') {
                return bonAvancement === 'complet';
              }
              return true;
            });

            return { ...prest, bons: filteredBons };
          })
          .filter((prest) => prest.bons.length > 0);

        return { ...manif, prestations: filteredPrestations };
      })
      .filter((manif) => manif.prestations.length > 0);
  }, [hierarchicalData, filterAvancement, getLigneState]);

  const allSelectedReservations = useMemo(() => {
    const selected = new Set<number>();
    for (const d of deliveries) {
      if (d.statut === 'validee') {
        const isAllLinesChecked =
          d.lignes.length > 0 &&
          d.lignes.every((l) => getLigneState(l, false).validee);
        if (isAllLinesChecked) {
          selected.add(d.id);
        }
      }
    }
    return Array.from(selected);
  }, [deliveries, getLigneState]);

  async function handleBatchSubmit() {
    if (allSelectedReservations.length === 0) {
      notifications.show({
        title: 'Aucune sélection',
        message: 'Cochez au moins une ligne ou prestation validée à envoyer.',
        color: 'orange'
      });
      return;
    }

    setBatchLoading(true);
    try {
      await onLivrerReservations(allSelectedReservations);
      notifications.show({
        title: 'Envoi groupé réussi',
        message: `${allSelectedReservations.length} réservation(s) marquée(s) livrée(s).`,
        color: 'green'
      });
    } catch {
      notifications.show({
        title: 'Erreur',
        message: "Échec lors de l'envoi groupé des livraisons.",
        color: 'red'
      });
    } finally {
      setBatchLoading(false);
    }
  }

  function handlePrestationCheck(prestBons: Delivery[], checked: boolean) {
    for (const bon of prestBons) {
      for (const ligne of bon.lignes) {
        setLigneState(ligne.id, {
          validee: checked,
          quantiteLivree: checked ? ligne.quantite_demandee : 0
        });
      }
    }
  }

  function handleBonCheck(bon: Delivery, checked: boolean) {
    for (const ligne of bon.lignes) {
      setLigneState(ligne.id, {
        validee: checked,
        quantiteLivree: checked ? ligne.quantite_demandee : 0
      });
    }
  }

  return (
    <Stack gap='sm'>
      <Group justify='space-between' align='center' wrap='wrap'>
        <Group gap='xs'>
          <Text size='sm' fw={500}>
            Filtre avancement :
          </Text>
          <SegmentedControl
            size='xs'
            value={filterAvancement}
            onChange={(val) =>
              setFilterAvancement(val as DeliveryAvancementFilter)
            }
            data={[
              { label: 'Tous', value: 'tous' },
              { label: 'À faire', value: 'a_faire' },
              { label: 'Partiel', value: 'partiel' },
              { label: 'Complet', value: 'complet' }
            ]}
          />
        </Group>

        <Group gap='xs'>
          <Button
            size='xs'
            color='green'
            leftSection={<IconCheck size={14} />}
            loading={batchLoading}
            onClick={handleBatchSubmit}
          >
            Envoi groupé ({allSelectedReservations.length})
          </Button>
        </Group>
      </Group>

      {filteredHierarchy.length === 0 ? (
        <Text c='dimmed' size='sm'>
          Aucune livraison ne correspond aux critères.
        </Text>
      ) : (
        <Stack gap={4}>
          {filteredHierarchy.map((manif) => {
            const manifKey = `manif-${manif.nom}`;
            const manifOuvert = ouverts.has(manifKey);

            const allManifLignes: { l: DeliveryLigne; deliv: Delivery }[] = [];
            for (const p of manif.prestations) {
              for (const b of p.bons) {
                for (const l of b.lignes) {
                  allManifLignes.push({ l, deliv: b });
                }
              }
            }

            const manifEtat = agregerAvancement(
              allManifLignes.map(({ l, deliv }) => {
                const st = getLigneState(l, deliv.statut === 'livree');
                return computeAvancement(
                  st.quantiteLivree,
                  l.quantite_demandee
                );
              })
            );

            return (
              <Box key={manifKey}>
                <Ligne fond={FOND.manifestation} indentation={0}>
                  <Group justify='space-between' wrap='nowrap'>
                    <UnstyledButton onClick={() => toggleOuvert(manifKey)}>
                      <Group gap='xs' wrap='nowrap'>
                        <Chevron ouvert={manifOuvert} />
                        <Text size='sm' fw={700}>
                          {manif.nom}
                        </Text>
                        {manif.clientNom && (
                          <Text size='xs' c='dimmed'>
                            · Client : {manif.clientNom}
                          </Text>
                        )}
                        <Text size='xs' c='dimmed'>
                          ({manif.prestations.length} prestation
                          {manif.prestations.length > 1 ? 's' : ''})
                        </Text>
                      </Group>
                    </UnstyledButton>
                    <Group gap='xs' wrap='nowrap'>
                      <Pastille
                        lettre='L'
                        etat={manifEtat}
                        libelle='Livraison'
                      />
                    </Group>
                  </Group>
                </Ligne>

                {manifOuvert &&
                  manif.prestations.map((prest) => {
                    const prestKey = `prest-${manif.nom}-${prest.nom}`;
                    const prestOuvert = ouverts.has(prestKey);

                    const prestLignes: {
                      l: DeliveryLigne;
                      deliv: Delivery;
                    }[] = [];
                    for (const b of prest.bons) {
                      for (const l of b.lignes) {
                        prestLignes.push({ l, deliv: b });
                      }
                    }

                    const prestEtat = agregerAvancement(
                      prestLignes.map(({ l, deliv }) => {
                        const st = getLigneState(l, deliv.statut === 'livree');
                        return computeAvancement(
                          st.quantiteLivree,
                          l.quantite_demandee
                        );
                      })
                    );

                    const isPrestAllChecked =
                      prestLignes.length > 0 &&
                      prestLignes.every(
                        ({ l, deliv }) =>
                          getLigneState(l, deliv.statut === 'livree').validee
                      );

                    return (
                      <Box key={prestKey}>
                        <Ligne fond={FOND.prestation} indentation={24}>
                          <Group justify='space-between' wrap='nowrap'>
                            <Group gap='xs' wrap='nowrap'>
                              <Checkbox
                                size='xs'
                                aria-label={`Valider prestation ${prest.nom}`}
                                checked={isPrestAllChecked}
                                onChange={(e) =>
                                  handlePrestationCheck(
                                    prest.bons,
                                    e.currentTarget.checked
                                  )
                                }
                              />
                              <UnstyledButton
                                onClick={() => toggleOuvert(prestKey)}
                              >
                                <Group gap='xs' wrap='nowrap'>
                                  <Chevron ouvert={prestOuvert} />
                                  <Text size='sm' fw={600}>
                                    {prest.nom}
                                  </Text>
                                  <Text size='xs' c='dimmed'>
                                    Lieu : {prest.lieuNom}
                                  </Text>
                                </Group>
                              </UnstyledButton>
                            </Group>
                            <Group gap='xs' wrap='nowrap'>
                              <Pastille
                                lettre='L'
                                etat={prestEtat}
                                libelle='Livraison'
                              />
                            </Group>
                          </Group>
                        </Ligne>

                        {prestOuvert &&
                          prest.bons.map((bon) => {
                            const bonKey = `bon-${bon.id}`;
                            const bonOuvert = ouverts.has(bonKey);
                            const isDelivered = bon.statut === 'livree';

                            const bonEtat = agregerAvancement(
                              bon.lignes.map((l) => {
                                const st = getLigneState(l, isDelivered);
                                return computeAvancement(
                                  st.quantiteLivree,
                                  l.quantite_demandee
                                );
                              })
                            );

                            const isBonAllChecked =
                              bon.lignes.length > 0 &&
                              bon.lignes.every(
                                (l) => getLigneState(l, isDelivered).validee
                              );

                            return (
                              <Box key={bonKey}>
                                <Ligne fond={FOND.bon} indentation={48}>
                                  <Group justify='space-between' wrap='nowrap'>
                                    <Group gap='xs' wrap='nowrap'>
                                      <Checkbox
                                        size='xs'
                                        aria-label={`Valider bon ${bon.numero}`}
                                        checked={isBonAllChecked}
                                        onChange={(e) =>
                                          handleBonCheck(
                                            bon,
                                            e.currentTarget.checked
                                          )
                                        }
                                      />
                                      <UnstyledButton
                                        onClick={() => toggleOuvert(bonKey)}
                                      >
                                        <Group gap='xs' wrap='nowrap'>
                                          <Chevron ouvert={bonOuvert} />
                                          <Text size='sm' fw={600}>
                                            Bon {bon.numero}
                                          </Text>
                                          <Badge
                                            size='xs'
                                            color={
                                              isDelivered ? 'teal' : 'green'
                                            }
                                          >
                                            {bon.statut}
                                          </Badge>
                                          <Text size='xs' c='dimmed'>
                                            {bon.lignes.length} article
                                            {bon.lignes.length > 1 ? 's' : ''}
                                          </Text>
                                        </Group>
                                      </UnstyledButton>
                                    </Group>
                                    <Group gap='xs' wrap='nowrap'>
                                      {onOpenNote && (
                                        <Button
                                          size='compact-xs'
                                          variant='light'
                                          onClick={() => onOpenNote(bon)}
                                        >
                                          Détails
                                        </Button>
                                      )}
                                      <Pastille
                                        lettre='L'
                                        etat={bonEtat}
                                        libelle='Livraison'
                                      />
                                    </Group>
                                  </Group>
                                </Ligne>

                                {bonOuvert &&
                                  bon.lignes.map((ligne) => {
                                    const st = getLigneState(
                                      ligne,
                                      isDelivered
                                    );
                                    const restante = Math.max(
                                      0,
                                      ligne.quantite_demandee -
                                        st.quantiteLivree
                                    );
                                    const ligneEtat = computeAvancement(
                                      st.quantiteLivree,
                                      ligne.quantite_demandee
                                    );

                                    return (
                                      <Ligne
                                        key={ligne.id}
                                        fond={FOND.article}
                                        indentation={72}
                                      >
                                        <Group
                                          justify='space-between'
                                          wrap='nowrap'
                                        >
                                          <Group gap='xs' wrap='nowrap'>
                                            <Checkbox
                                              size='xs'
                                              aria-label={`Valider ligne ${ligne.part_name}`}
                                              checked={st.validee}
                                              onChange={(e) => {
                                                const checked =
                                                  e.currentTarget.checked;
                                                setLigneState(ligne.id, {
                                                  validee: checked,
                                                  quantiteLivree: checked
                                                    ? ligne.quantite_demandee
                                                    : st.quantiteLivree
                                                });
                                              }}
                                            />
                                            <Box>
                                              <Text size='sm' fw={600}>
                                                {ligne.part_name}
                                              </Text>
                                              <Text size='xs' c='dimmed'>
                                                ID: {ligne.part}
                                              </Text>
                                            </Box>
                                          </Group>

                                          <Group gap='md' wrap='nowrap'>
                                            <Text size='xs'>
                                              Demandée :{' '}
                                              <b>{ligne.quantite_demandee}</b>
                                            </Text>

                                            <Group gap={4} wrap='nowrap'>
                                              <Text size='xs'>Livrée :</Text>
                                              <ActionIcon
                                                size='xs'
                                                variant='default'
                                                disabled={
                                                  st.quantiteLivree <= 0
                                                }
                                                onClick={() => {
                                                  const n = Math.max(
                                                    0,
                                                    st.quantiteLivree - 1
                                                  );
                                                  setLigneState(ligne.id, {
                                                    quantiteLivree: n,
                                                    validee:
                                                      n >=
                                                      ligne.quantite_demandee
                                                  });
                                                }}
                                              >
                                                <IconMinus size={10} />
                                              </ActionIcon>
                                              <NumberInput
                                                size='xs'
                                                w={60}
                                                min={0}
                                                max={ligne.quantite_demandee}
                                                value={st.quantiteLivree}
                                                onChange={(val) => {
                                                  const n =
                                                    typeof val === 'number'
                                                      ? val
                                                      : Number(val) || 0;
                                                  setLigneState(ligne.id, {
                                                    quantiteLivree: n,
                                                    validee:
                                                      n >=
                                                      ligne.quantite_demandee
                                                  });
                                                }}
                                              />
                                              <ActionIcon
                                                size='xs'
                                                variant='default'
                                                disabled={
                                                  st.quantiteLivree >=
                                                  ligne.quantite_demandee
                                                }
                                                onClick={() => {
                                                  const n =
                                                    st.quantiteLivree + 1;
                                                  setLigneState(ligne.id, {
                                                    quantiteLivree: n,
                                                    validee:
                                                      n >=
                                                      ligne.quantite_demandee
                                                  });
                                                }}
                                              >
                                                <IconPlus size={10} />
                                              </ActionIcon>
                                            </Group>

                                            <Text size='xs'>
                                              Restante : <b>{restante}</b>
                                            </Text>

                                            <Tooltip
                                              label={
                                                st.photoUrl
                                                  ? 'Photo jointe'
                                                  : 'Prendre ou joindre une photo'
                                              }
                                            >
                                              <ActionIcon
                                                size='sm'
                                                variant={
                                                  st.photoUrl
                                                    ? 'filled'
                                                    : 'light'
                                                }
                                                color={
                                                  st.photoUrl ? 'blue' : 'gray'
                                                }
                                                onClick={() =>
                                                  setPhotoModal({
                                                    ligneId: ligne.id,
                                                    partName: ligne.part_name
                                                  })
                                                }
                                              >
                                                <IconCamera size={14} />
                                              </ActionIcon>
                                            </Tooltip>

                                            <Pastille
                                              lettre='L'
                                              etat={ligneEtat}
                                              libelle='Livraison'
                                            />
                                          </Group>
                                        </Group>
                                      </Ligne>
                                    );
                                  })}
                              </Box>
                            );
                          })}
                      </Box>
                    );
                  })}
              </Box>
            );
          })}
        </Stack>
      )}

      <Modal
        closeOnClickOutside={false}
        opened={photoModal !== null}
        onClose={() => setPhotoModal(null)}
        title={`Photo de livraison — ${photoModal?.partName ?? ''}`}
      >
        {photoModal && (
          <Stack gap='md'>
            {lignesState[photoModal.ligneId]?.photoUrl ? (
              <Box>
                <Image
                  src={lignesState[photoModal.ligneId]?.photoUrl}
                  alt='Preuve de livraison'
                  radius='md'
                  mah={300}
                  fit='contain'
                />
                <Button
                  mt='xs'
                  color='red'
                  variant='subtle'
                  size='xs'
                  onClick={() =>
                    setLigneState(photoModal.ligneId, { photoUrl: null })
                  }
                >
                  Supprimer la photo
                </Button>
              </Box>
            ) : (
              <FileInput
                label='Joindre une photo'
                placeholder='Sélectionner un fichier image'
                accept='image/*'
                leftSection={<IconUpload size={14} />}
                onChange={(file) => {
                  if (file) {
                    const reader = new FileReader();
                    reader.onload = () => {
                      setLigneState(photoModal.ligneId, {
                        photoUrl: reader.result as string
                      });
                    };
                    reader.readAsDataURL(file);
                  }
                }}
              />
            )}
            <Group justify='flex-end'>
              <Button size='xs' onClick={() => setPhotoModal(null)}>
                Fermer
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </Stack>
  );
}
