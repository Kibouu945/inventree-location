// Calendrier mensuel des réservations (DIS-01) : vue d'ensemble pour le
// gestionnaire, chaque réservation placée entre sa date de retrait et de
// retour prévues, colorée par statut.

import type { EventInput } from '@fullcalendar/core';
import frLocale from '@fullcalendar/core/locales/fr';
import dayGridPlugin from '@fullcalendar/daygrid';
import FullCalendar from '@fullcalendar/react';
import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Group, Stack, Text, Title } from '@mantine/core';

const CALENDAR_URL = '/plugin/inventree-location/reservations/calendar/';

/** Miroir de `STATUT_COULEURS` (`inventree_location/calendrier.py`) : les
 * pastilles des évènements viennent de l'API, cette légende doit donc lui
 * répondre statut pour statut. */
const STATUT_LEGEND: Array<{ label: string; color: string }> = [
  { label: 'Brouillon', color: '#868e96' },
  { label: 'Soumise', color: '#228be6' },
  { label: 'Validée', color: '#40c057' },
  { label: 'Refusée', color: '#fa5252' },
  { label: 'Annulée', color: '#e8590c' },
  { label: 'Livrée', color: '#12b886' },
  { label: 'Retournée', color: '#be4bdb' },
  { label: 'Clôturée', color: '#343a40' }
];

export function ReservationCalendar({
  context
}: {
  context: InvenTreePluginContext;
}) {
  return (
    <Stack gap='md'>
      <Title order={4} c={context.theme.primaryColor}>
        Calendrier des réservations
      </Title>

      <Group gap='lg'>
        {STATUT_LEGEND.map((entry) => (
          <Group key={entry.label} gap={6}>
            <div
              style={{
                width: 10,
                height: 10,
                borderRadius: 2,
                backgroundColor: entry.color
              }}
            />
            <Text size='xs' c='dimmed'>
              {entry.label}
            </Text>
          </Group>
        ))}
      </Group>

      <FullCalendar
        plugins={[dayGridPlugin]}
        initialView='dayGridMonth'
        locale={frLocale}
        headerToolbar={{
          left: 'prev,next today',
          center: 'title',
          right: ''
        }}
        height='auto'
        events={(info, successCallback, failureCallback) => {
          context.api
            .get(CALENDAR_URL, {
              params: { from: info.startStr, to: info.endStr }
            })
            .then((response) => successCallback(response.data as EventInput[]))
            .catch((error) => failureCallback(error));
        }}
        eventDidMount={(info) => {
          const statut = info.event.extendedProps.statut as string | undefined;
          if (statut) {
            info.el.title = `${info.event.title} — ${statut}`;
          }
        }}
      />
    </Stack>
  );
}
