// Vue calendrier des livraisons (US livreur) : un badge par jour indique le
// nombre de livraisons dont le retrait est prévu ce jour-là ; un clic filtre
// la liste sur cette journée.
import { Group, Indicator, Stack, Text } from "@mantine/core";
import { Calendar } from "@mantine/dates";
import { useMemo } from "react";

import type { Delivery } from "./types";

function dayKey(iso: string): string {
	return iso.slice(0, 10);
}

export function DeliveryCalendar({
	deliveries,
	onSelectDay,
}: {
	deliveries: Delivery[];
	onSelectDay: (day: string) => void;
}) {
	const countsByDay = useMemo(() => {
		const counts = new Map<string, number>();

		for (const delivery of deliveries) {
			if (!delivery.date_retrait_prevue) {
				continue;
			}

			const key = dayKey(delivery.date_retrait_prevue);
			counts.set(key, (counts.get(key) ?? 0) + 1);
		}

		return counts;
	}, [deliveries]);

	return (
		<Stack gap="xs">
			<Group justify="center">
				<Calendar
					renderDay={(date) => {
						const key = typeof date === "string" ? date.slice(0, 10) : "";
						const count = countsByDay.get(key) ?? 0;
						const day = new Date(`${key}T00:00:00`).getDate();

						return (
							<Indicator
								size={6}
								offset={-2}
								disabled={count === 0}
								label={count > 1 ? count : undefined}
							>
								<div>{day}</div>
							</Indicator>
						);
					}}
					getDayProps={(date) => {
						const key = typeof date === "string" ? date.slice(0, 10) : "";

						return {
							onClick: () => onSelectDay(key),
						};
					}}
				/>
			</Group>
			<Text size="xs" c="dimmed" ta="center">
				Cliquez sur un jour pour filtrer la liste sur cette date.
			</Text>
		</Stack>
	);
}
