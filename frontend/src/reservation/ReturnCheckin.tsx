// Check-in retour (SCRUM-96) : marquer une ligne « manquant » (ou « cassé »),
// commentaire libre et option « facturer au client ». Alimente le rapport de pertes.
import type { InvenTreePluginContext } from "@inventreedb/ui";
import {
    Alert,
    Badge,
    Button,
    Group,
    Loader,
    Modal,
    NumberInput,
    Stack,
    Switch,
    Table,
    Text,
    Textarea,
    Title
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import type {
    Reservation,
    ReturnIncident,
    ReturnIncidentPayload,
    ReturnIncidentType,
    ReturnLossReport
} from "./types";

const INCIDENTS_URL = "/plugin/inventree-location/returns/incidents/";
const LOSS_REPORT_URL = "/plugin/inventree-location/returns/loss-report/";

function incidentLabel(type: ReturnIncidentType): string {
    return type === "missing" ? "Manquant" : "Cassé";
}

/**
 * Modale de déclaration d'un incident de retour pour une ligne.
 * Le magasinier choisit le type (manquant / cassé), saisit un commentaire
 * libre et active l'option « facturer au client ».
 */
function IncidentModal({
    context,
    reservation,
    line,
    opened,
    onClose,
    onSaved
}: {
    context: InvenTreePluginContext;
    reservation: Reservation;
    line: Reservation["lignes"][number];
    opened: boolean;
    onClose: () => void;
    onSaved: () => void;
}) {
    const [type, setType] = useState<ReturnIncidentType>("missing");
    const [qty, setQty] = useState<number>(line.quantite_livree || 1);
    const [comment, setComment] = useState("");
    const [billClient, setBillClient] = useState(false);

    useEffect(() => {
        if (opened) {
            setType("missing");
            setQty(line.quantite_livree || 1);
            setComment("");
            setBillClient(false);
        }
    }, [opened, line]);

    const maxQty = line.quantite_livree || line.quantite_demandee;

    const mutation = useMutation(
        {
            mutationFn: async (payload: ReturnIncidentPayload) => {
                const response = await context.api.post(INCIDENTS_URL, payload);
                return response.data as ReturnIncident;
            },
            onSuccess: () => {
                context.queryClient.invalidateQueries({ queryKey: ["return-incidents"] });
                context.queryClient.invalidateQueries({
                    queryKey: ["return-loss-report"]
                });
                context.queryClient.invalidateQueries({ queryKey: ["reservations"] });
                notifications.show({
                    title: "Incident signalé",
                    message: `Incident signalé pour la ligne #${line.id}.`,
                    color: type === "missing" ? "orange" : "red"
                });
                onSaved();
                onClose();
            },
            onError: () => {
                notifications.show({
                    title: "Erreur",
                    message: "L'incident n'a pas pu être enregistré.",
                    color: "red"
                });
            }
        },
        context.queryClient
    );

    function submit() {
        if (qty <= 0) {
            notifications.show({
                title: "Erreur",
                message: "Quantité invalide.",
                color: "red"
            });
            return;
        }

        mutation.mutate({
            line: line.id,
            type,
            qty,
            comment,
            bill_client: billClient
        });
    }

    return (
        <Modal
            opened={opened}
            onClose={onClose}
            title={`Incident — ligne #${line.id}`}
            size="md"
        >
            <Stack gap="md">
                <Text size="sm">
                    Réservation {reservation.numero} — quantité disponible : {maxQty}
                </Text>

                <Group grow>
                    <Button
                        variant={type === "missing" ? "filled" : "light"}
                        color={type === "missing" ? "orange" : "gray"}
                        onClick={() => setType("missing")}
                    >
                        Manquant
                    </Button>
                    <Button
                        variant={type === "broken" ? "filled" : "light"}
                        color={type === "broken" ? "red" : "gray"}
                        onClick={() => setType("broken")}
                    >
                        Cassé
                    </Button>
                </Group>

                <NumberInput
                    label="Quantité"
                    min={1}
                    max={maxQty}
                    value={qty}
                    onChange={(value) => setQty(Number(value) || 0)}
                    required
                />

                <Textarea
                    label="Commentaire"
                    placeholder="Commentaire libre…"
                    value={comment}
                    onChange={(event) => setComment(event.currentTarget.value)}
                    minRows={3}
                />

                <Switch
                    label="Facturer au client"
                    checked={billClient}
                    onChange={(event) => setBillClient(event.currentTarget.checked)}
                />

                <Group justify="flex-end">
                    <Button variant="light" onClick={onClose}>
                        Annuler
                    </Button>
                    <Button
                        color={type === "missing" ? "orange" : "red"}
                        loading={mutation.isPending}
                        onClick={submit}
                    >
                        Signaler {incidentLabel(type).toLowerCase()}
                    </Button>
                </Group>
            </Stack>
        </Modal>
    );
}

/**
 * Encart de check-in retour affiché dans la modale de détail d'une réservation.
 * Liste les incidents déjà signalés + le rapport de pertes agrégé, et permet
 * au magasinier de déclarer une ligne manquante ou cassée.
 */
export function ReturnCheckin({
    context,
    reservation
}: {
    context: InvenTreePluginContext;
    reservation: Reservation;
}) {
    const [incidentLine, setIncidentLine] = useState<
        Reservation["lignes"][number] | null
    >(null);
    const [opened, { open, close }] = useDisclosure(false);

    const incidentsQuery = useQuery<ReturnIncident[]>(
        {
            queryKey: ["return-incidents", reservation.id],
            queryFn: async () => {
                const response = await context.api.get(INCIDENTS_URL, {
                    params: { reservation: reservation.id, page_size: 100 }
                });
                return (Array.isArray(response.data) ? response.data : response.data.results) as ReturnIncident[];
            }
        },
        context.queryClient
    );

    const lossReportQuery = useQuery<ReturnLossReport>(
        {
            queryKey: ["return-loss-report", reservation.id],
            queryFn: async () => {
                const response = await context.api.get(LOSS_REPORT_URL, {
                    params: { reservation: reservation.id }
                });
                return response.data as ReturnLossReport;
            }
        },
        context.queryClient
    );

    const incidents = incidentsQuery.data ?? [];
    const report = lossReportQuery.data;

    const incidentsByLine = useMemo(() => {
        const map = new Map<number, ReturnIncident[]>();
        for (const incident of incidents) {
            const entries = map.get(incident.line) ?? [];
            entries.push(incident);
            map.set(incident.line, entries);
        }
        return map;
    }, [incidents]);

    function openIncident(line: Reservation["lignes"][number]) {
        setIncidentLine(line);
        open();
    }

    const reportPending = lossReportQuery.isLoading;

    return (
        <Stack gap="md" mt="md">
            <Group justify="space-between">
                <Title order={5}>Retour — manquants & cassés</Title>
            </Group>

            <Table striped>
                <Table.Thead>
                    <Table.Tr>
                        <Table.Th>Ligne</Table.Th>
                        <Table.Th>Qté</Table.Th>
                        <Table.Th>État</Table.Th>
                        <Table.Th>Commentaire</Table.Th>
                        <Table.Th />
                    </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                    {reservation.lignes.map((line) => {
                        const lineIncidents = incidentsByLine.get(line.id) ?? [];
                        const latest = lineIncidents[0];
                        const partName = `Article #${line.part}`;

                        return (
                            <Table.Tr key={line.id}>
                                <Table.Td>{partName}</Table.Td>
                                <Table.Td>
                                    {line.quantite_livree || line.quantite_demandee}
                                </Table.Td>
                                <Table.Td>
                                    {latest ? (
                                        <Badge color={latest.type === "missing" ? "orange" : "red"}>
                                            {incidentLabel(latest.type)}
                                            {latest.bill_client ? " · facturé" : ""}
                                        </Badge>
                                    ) : (
                                        <Text c="dimmed" size="sm">
                                            —
                                        </Text>
                                    )}
                                </Table.Td>
                                <Table.Td>
                                    {latest ? (
                                        <Text size="sm" lineClamp={1}>
                                            {latest.comment || "—"}
                                        </Text>
                                    ) : (
                                        <Text c="dimmed" size="sm">
                                            —
                                        </Text>
                                    )}
                                </Table.Td>
                                <Table.Td>
                                    <Button
                                        size="xs"
                                        variant="light"
                                        color="orange"
                                        onClick={() => openIncident(line)}
                                    >
                                        Manquant
                                    </Button>
                                </Table.Td>
                            </Table.Tr>
                        );
                    })}
                </Table.Tbody>
            </Table>

            {reportPending ? (
                <Group justify="center" p="md">
                    <Loader size="sm" />
                </Group>
            ) : report ? (
                <Alert color="red" title="Rapport de pertes">
                    <Group gap="xl">
                        <Stack gap={0}>
                            <Text size="sm" fw={600}>
                                Manquants
                            </Text>
                            <Text size="xl" fw={700}>
                                {report.total_missing}
                            </Text>
                        </Stack>
                        <Stack gap={0}>
                            <Text size="sm" fw={600}>
                                Cassés
                            </Text>
                            <Text size="xl" fw={700}>
                                {report.total_broken}
                            </Text>
                        </Stack>
                        <Stack gap={0}>
                            <Text size="sm" fw={600}>
                                Facturé au client
                            </Text>
                            <Text size="xl" fw={700}>
                                {report.total_billed}
                            </Text>
                        </Stack>
                    </Group>
                </Alert>
            ) : null}

            {incidentLine && (
                <IncidentModal
                    context={context}
                    reservation={reservation}
                    line={incidentLine}
                    opened={opened}
                    onClose={close}
                    onSaved={() => {
                        context.queryClient.invalidateQueries({
                            queryKey: ["return-incidents"]
                        });
                    }}
                />
            )}
        </Stack>
    );
}