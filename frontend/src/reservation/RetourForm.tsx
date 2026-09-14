// Déclaration du retour d'une prestation (SCRUM-95) : qty rendue par ligne.
//
// Adaptation d'architecture : le plugin ne dispose pas de routeur client
// (pages rendues par InvenTree via des dashboard items), la vue ligne par
// ligne du bon de réservation est donc portée par une modale ouverte depuis
// la liste des réservations plutôt qu'une route dédiée.
import type { InvenTreePluginContext } from "@inventreedb/ui";
import {
	Alert,
	Badge,
	Button,
	Group,
	Loader,
	NumberInput,
	Stack,
	Table,
	Text,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import {
	computeStatutRetour,
	normalizeRetourErrors,
	type RetourErrors,
	type RetourLigneValues,
	type StatutRetour,
	validateRetourLignes,
} from "./retourLogic";

const RESERVATIONS_URL = "/plugin/inventree-location/reservations/";

const STATUT_RETOUR_LABELS: Record<StatutRetour, string> = {
	aucun: "Aucun retour déclaré",
	partiel: "Retour partiel",
	complet: "Retour complet",
};

const STATUT_RETOUR_COLORS: Record<StatutRetour, string> = {
	aucun: "gray",
	partiel: "orange",
	complet: "green",
};

interface RetourLigneApi {
	id: number;
	part: number;
	part_name: string;
	quantite_demandee: number;
	quantite_retournee: number;
}

interface RetourResponse {
	reservation: number;
	numero: string;
	statut: string;
	statut_retour: StatutRetour;
	quantite_demandee_totale: number;
	quantite_rendue_totale: number;
	lignes: RetourLigneApi[];
}

function toFormLignes(lignes: RetourLigneApi[]): RetourLigneValues[] {
	return lignes.map((ligne) => ({
		id: ligne.id,
		quantite_demandee: ligne.quantite_demandee,
		quantite_rendue: ligne.quantite_retournee || 0,
	}));
}

/**
 * Formulaire de déclaration du retour d'une prestation, ligne par ligne.
 */
export function RetourForm({
	context,
	reservationId,
	onSaved,
}: {
	context: InvenTreePluginContext;
	reservationId: number;
	onSaved: () => void;
}) {
	const [lignes, setLignes] = useState<RetourLigneValues[]>([]);
	const [errors, setErrors] = useState<RetourErrors>({});
	const [partNames, setPartNames] = useState<Record<number, string>>({});
	// Le formulaire n'est initialisé qu'une fois par réservation : un refetch
	// (retour de focus sur l'onglet, invalidation) ne doit pas écraser la
	// saisie en cours du magasinier.
	const seededFor = useRef<number | null>(null);

	const query = useQuery<RetourResponse>(
		{
			queryKey: ["reservation-retour", reservationId],
			queryFn: async () => {
				const response = await context.api.get(
					`${RESERVATIONS_URL}${reservationId}/retour/`,
				);
				return response.data;
			},
		},
		context.queryClient,
	);

	useEffect(() => {
		if (!query.data || seededFor.current === reservationId) {
			return;
		}

		seededFor.current = reservationId;
		setLignes(toFormLignes(query.data.lignes));
		setPartNames(
			Object.fromEntries(
				query.data.lignes.map((ligne) => [ligne.id, ligne.part_name]),
			),
		);
	}, [query.data, reservationId]);

	const saveMutation = useMutation(
		{
			mutationFn: async (payload: RetourLigneValues[]) => {
				const response = await context.api.post(
					`${RESERVATIONS_URL}${reservationId}/retour/`,
					{
						lignes: payload.map((ligne) => ({
							id: ligne.id,
							quantite_rendue: ligne.quantite_rendue,
						})),
					},
				);
				return response.data as RetourResponse;
			},
			onSuccess: (data) => {
				context.queryClient.invalidateQueries({ queryKey: ["reservations"] });
				context.queryClient.invalidateQueries({
					queryKey: ["reservation-retour", reservationId],
				});
				notifications.show({
					title: "Retour enregistré",
					message:
						data.statut_retour === "complet"
							? "Retour complet : la réservation est marquée retournée."
							: "Retour partiel enregistré.",
					color: data.statut_retour === "complet" ? "green" : "orange",
				});

				if (data.statut_retour === "complet") {
					onSaved();
				}
			},
			onError: (error: unknown, envoyees) => {
				const data = (error as { response?: { data?: { detail?: string } } })
					?.response?.data;

				setErrors(normalizeRetourErrors(data, envoyees));

				notifications.show({
					title: "Retour impossible",
					message: data?.detail || "Vérifiez les quantités saisies.",
					color: "red",
				});
			},
		},
		context.queryClient,
	);

	function updateLigne(id: number, quantite_rendue: number) {
		setLignes((current) =>
			current.map((ligne) =>
				ligne.id === id ? { ...ligne, quantite_rendue } : ligne,
			),
		);
	}

	function handleSubmit() {
		const validationErrors = validateRetourLignes(lignes);
		setErrors(validationErrors);

		if (Object.keys(validationErrors).length > 0) {
			return;
		}

		saveMutation.mutate(lignes);
	}

	const statutSaisi = computeStatutRetour(lignes);

	if (query.isLoading) {
		return (
			<Group justify="center" p="xl">
				<Loader />
			</Group>
		);
	}

	if (query.isError) {
		const detail = (
			query.error as { response?: { data?: { detail?: string } } }
		)?.response?.data?.detail;

		return (
			<Alert color="red" title="Retour indisponible">
				{detail || "Impossible de charger le retour de cette réservation."}
			</Alert>
		);
	}

	return (
		<Stack gap="md">
			<Group justify="space-between">
				<Text size="sm" c="dimmed">
					Bon {query.data?.numero} — saisissez la quantité rendue pour chaque
					ligne.
				</Text>
				{/* Calculé sur la saisie en cours, pas sur la réponse serveur : le
            magasinier voit tout de suite où en est le bon qu'il pointe. */}
				<Badge color={STATUT_RETOUR_COLORS[statutSaisi]}>
					{STATUT_RETOUR_LABELS[statutSaisi]}
				</Badge>
			</Group>

			<Table striped>
				<Table.Thead>
					<Table.Tr>
						<Table.Th>Article</Table.Th>
						<Table.Th>Qté demandée</Table.Th>
						<Table.Th>Qté rendue</Table.Th>
					</Table.Tr>
				</Table.Thead>
				<Table.Tbody>
					{lignes.map((ligne) => (
						<Table.Tr key={ligne.id}>
							<Table.Td>{partNames[ligne.id] || "—"}</Table.Td>
							<Table.Td>{ligne.quantite_demandee}</Table.Td>
							<Table.Td>
								<NumberInput
									value={ligne.quantite_rendue}
									min={0}
									max={ligne.quantite_demandee}
									// Le serveur attend un entier : sans ça, une saisie « 2,5 »
									// partait au POST et revenait en erreur de champ DRF.
									allowDecimal={false}
									w={110}
									onChange={(value) =>
										updateLigne(ligne.id, Math.trunc(Number(value)) || 0)
									}
								/>
							</Table.Td>
						</Table.Tr>
					))}
				</Table.Tbody>
			</Table>

			{Object.entries(errors).map(([id, message]) =>
				message ? (
					<Alert
						key={id}
						color="red"
						title={`Ligne ${partNames[Number(id)] || id}`}
					>
						{message}
					</Alert>
				) : null,
			)}

			<Group justify="flex-end">
				<Button
					onClick={handleSubmit}
					loading={saveMutation.isPending}
					disabled={lignes.length === 0}
				>
					Enregistrer le retour
				</Button>
			</Group>
		</Stack>
	);
}
