// Écran « Alertes stock » (US-09), partagé par le widget de dashboard et par
// l'onglet du même nom des postes.
//
// Extrait de `Dashboard.tsx`, qui importe `checkPluginVersion` au runtime :
// externalisé pour les widgets, ce paquet est embarqué ailleurs et tire
// `@lingui` sans `i18n` initialisé. Règle : un composant réutilisé par un poste
// n'importe d'`@inventreedb/ui` que des **types**.
import type { InvenTreePluginContext } from "@inventreedb/ui";
import {
	Alert,
	Badge,
	Button,
	Group,
	Loader,
	Stack,
	Table,
	Text,
	Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery } from "@tanstack/react-query";

const STOCK_ALERTS_URL = "/plugin/inventree-location/alerts/stock/";

interface StockAlertItem {
	part_id: number;
	part_name: string;
	consommable: boolean;
	stock_available: number;
	stock_total: number;
	seuil_alerte_bas: number | null;
	seuil_alerte_haut: number | null;
	projected_reserved_quantity: number;
	projected_occupation_rate: number;
	reasons: Array<{
		type: string;
		message: string;
	}>;
}

interface StockAlertResponse {
	count: number;
	email_sent: boolean;
	alerts: StockAlertItem[];
}

/**
 * Render a custom dashboard item with the provided context
 * Refer to the InvenTree documentation for the context interface
 * https://docs.inventree.org/en/stable/extend/plugins/ui/#plugin-context
 */
export function StockAlertsList({
	context,
}: {
	context: InvenTreePluginContext;
}) {
	const query = useQuery<StockAlertResponse>(
		{
			queryKey: ["stock-alerts"],
			queryFn: async () => {
				const response = await context.api.get(STOCK_ALERTS_URL);
				return response.data as StockAlertResponse;
			},
		},
		context.queryClient,
	);

	const notifyMutation = useMutation(
		{
			mutationFn: async () => {
				const response = await context.api.get(STOCK_ALERTS_URL, {
					params: { notify: 1 },
				});
				return response.data as StockAlertResponse;
			},
			onSuccess: (data) => {
				if (data.email_sent) {
					notifications.show({
						title: "Alerte envoyée",
						message: "Email d’alerte stock envoyé.",
						color: "green",
					});
				} else {
					notifications.show({
						title: "Email non envoyé",
						message: "Aucun destinataire ou cooldown actif (1h).",
						color: "yellow",
					});
				}

				context.queryClient.setQueryData(["stock-alerts"], data);
			},
			onError: () => {
				notifications.show({
					title: "Erreur",
					message: "Impossible d’envoyer l’alerte email.",
					color: "red",
				});
			},
		},
		context.queryClient,
	);

	if (query.isLoading) {
		return (
			<Group justify="center" p="xl">
				<Loader />
			</Group>
		);
	}

	if (query.isError || !query.data) {
		return (
			<Alert color="red" title="Alertes stock">
				Impossible de charger les alertes de seuil.
			</Alert>
		);
	}

	const alerts = query.data.alerts;

	return (
		<Stack gap="md">
			<Group justify="space-between">
				<Title order={4}>Alertes stock</Title>
				<Group gap="sm">
					<Badge color={alerts.length > 0 ? "red" : "green"} size="lg">
						{alerts.length}
					</Badge>
					<Button
						size="xs"
						variant="light"
						loading={notifyMutation.isPending}
						onClick={() => notifyMutation.mutate()}
					>
						Envoyer email
					</Button>
				</Group>
			</Group>

			{alerts.length === 0 ? (
				<Alert color="green" title="Aucune alerte">
					Aucun objet n’est actuellement en seuil critique.
				</Alert>
			) : (
				<Alert color="orange" title="Attention seuil stock">
					<Text size="sm">
						{alerts.length} objet(s) en alerte (seuil bas/haut ou tension
						projetée {">"}90%).
					</Text>
				</Alert>
			)}

			{alerts.length > 0 && (
				<Table striped highlightOnHover>
					<Table.Thead>
						<Table.Tr>
							<Table.Th>Objet</Table.Th>
							{/* Deux grandeurs distinctes : « 10/5 » se lisait comme un
                  disponible supérieur au total, ce qui n'a pas de sens. */}
							<Table.Th>Stock physique</Table.Th>
							<Table.Th>Quantité louable</Table.Th>
							<Table.Th>Seuils</Table.Th>
							<Table.Th>Tension projetée</Table.Th>
							<Table.Th>Raisons</Table.Th>
						</Table.Tr>
					</Table.Thead>
					<Table.Tbody>
						{alerts.map((item) => (
							<Table.Tr key={item.part_id}>
								<Table.Td>{item.part_name}</Table.Td>
								<Table.Td>{item.stock_available}</Table.Td>
								<Table.Td>{item.stock_total}</Table.Td>
								<Table.Td>
									bas : {item.seuil_alerte_bas ?? "—"} · haut :{" "}
									{item.seuil_alerte_haut ?? "—"}
								</Table.Td>
								<Table.Td>
									{item.projected_occupation_rate.toFixed(1)} %{" "}
									<Text span size="xs" c="dimmed">
										({item.projected_reserved_quantity} réservé(s))
									</Text>
								</Table.Td>
								<Table.Td>
									{item.reasons.map((r) => r.message).join(" · ")}
								</Table.Td>
							</Table.Tr>
						))}
					</Table.Tbody>
				</Table>
			)}
		</Stack>
	);
}
