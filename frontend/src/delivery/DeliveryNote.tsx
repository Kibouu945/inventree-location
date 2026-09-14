// Bon de livraison imprimable (US livreur) : détail d'une livraison + impression
// via CSS d'impression + window.print(). Pas de dépendance PDF pour l'instant —
// un futur modèle PDF pourra remplacer ce rendu sans toucher à l'assemblage des
// données (cf. DeliveriesList / types.ts). Les règles d'impression sont
// partagées avec le bon de ramassage (cf. print/printableModal.tsx).
import {
	Button,
	Divider,
	Group,
	Modal,
	Stack,
	Table,
	Text,
	Title,
} from "@mantine/core";

import {
	PRINT_AREA,
	PRINT_HIDE,
	PrintableModalStyles,
} from "../print/printableModal";
import { LieuMapLinks } from "../reservation/LieuMapLinks";
import type { Delivery } from "./types";

function formatDateTime(iso: string | null): string {
	return iso ? new Date(iso).toLocaleString() : "—";
}

export function DeliveryNote({
	delivery,
	onClose,
}: {
	delivery: Delivery | null;
	onClose: () => void;
}) {
	const lignes = delivery?.lignes ?? [];
	const materiel = lignes.filter((ligne) => !ligne.is_virtual);
	const services = lignes.filter((ligne) => ligne.is_virtual);

	return (
		<Modal
			opened={delivery != null}
			onClose={onClose}
			size="lg"
			title={delivery ? `Bon de livraison — ${delivery.numero}` : ""}
		>
			{delivery && (
				<Stack gap="md">
					<PrintableModalStyles />

					<div className={PRINT_AREA}>
						<Stack gap="xs">
							<Title order={4}>{delivery.prestation_nom}</Title>
							<Text size="sm">
								Horaire prévu : {formatDateTime(delivery.date_retrait_prevue)}
								{" — retour "}
								{formatDateTime(delivery.date_retour_prevue)}
							</Text>
						</Stack>

						<Divider my="sm" label="Lieu" labelPosition="left" />
						{delivery.lieu_detail ? (
							<LieuMapLinks lieu={delivery.lieu_detail} />
						) : (
							<Text size="sm" c="dimmed">
								Aucun lieu associé à cette prestation.
							</Text>
						)}

						<Divider my="sm" label="Contacts" labelPosition="left" />
						<Text size="sm">
							Organisateur : {delivery.organisateur_nom || "—"}
							{delivery.organisateur_telephone
								? ` (${delivery.organisateur_telephone})`
								: ""}
						</Text>
						<Text size="sm">
							Gérant interne : {delivery.demandeur_nom || "—"}
						</Text>

						{/* Les services sont listés à part : ils ne se chargent pas dans
                le camion et n'entrent donc pas dans le total. */}
						<Divider my="sm" label="Matériel" labelPosition="left" />
						<Table striped>
							<Table.Thead>
								<Table.Tr>
									<Table.Th>Article</Table.Th>
									<Table.Th>Quantité</Table.Th>
								</Table.Tr>
							</Table.Thead>
							<Table.Tbody>
								{materiel.map((ligne) => (
									<Table.Tr key={ligne.id}>
										<Table.Td>{ligne.part_name}</Table.Td>
										<Table.Td>{ligne.quantite_demandee}</Table.Td>
									</Table.Tr>
								))}
							</Table.Tbody>
						</Table>
						<Text size="sm" fw={500} ta="right">
							Total : {delivery.quantite_totale}
						</Text>

						{services.length > 0 && (
							<>
								<Divider my="sm" label="Prestations" labelPosition="left" />
								<Table striped>
									<Table.Thead>
										<Table.Tr>
											<Table.Th>Prestation</Table.Th>
											<Table.Th>Quantité</Table.Th>
										</Table.Tr>
									</Table.Thead>
									<Table.Tbody>
										{services.map((ligne) => (
											<Table.Tr key={ligne.id}>
												<Table.Td>{ligne.part_name}</Table.Td>
												<Table.Td>{ligne.quantite_demandee}</Table.Td>
											</Table.Tr>
										))}
									</Table.Tbody>
								</Table>
							</>
						)}

						{delivery.commentaire && (
							<>
								<Divider my="sm" label="Commentaire" labelPosition="left" />
								<Text size="sm">{delivery.commentaire}</Text>
							</>
						)}
					</div>

					<Group justify="flex-end" className={PRINT_HIDE}>
						<Button variant="default" onClick={onClose}>
							Fermer
						</Button>
						<Button onClick={() => window.print()}>Imprimer</Button>
					</Group>
				</Stack>
			)}
		</Modal>
	);
}
