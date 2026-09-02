// Carte des livraisons (US livreur) : un marqueur par lieu, tuiles OpenStreetMap
// (cohérent avec le géocodage Nominatim déjà utilisé côté backend).
import { Stack, Text } from '@mantine/core';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import iconUrl from 'leaflet/dist/images/marker-icon.png';
// Correctif Vite/Leaflet : les icônes par défaut référencent des URLs qui ne
// se résolvent pas une fois bundlées, il faut les importer explicitement.
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png';
import shadowUrl from 'leaflet/dist/images/marker-shadow.png';
import { useMemo } from 'react';
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet';
import type { Delivery } from './types';

delete (L.Icon.Default.prototype as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl,
  iconUrl,
  shadowUrl
});

const DEFAULT_CENTER: [number, number] = [46.6, 2.5]; // France métropolitaine

interface LieuGroup {
  id: number;
  nom: string;
  adresse: string;
  latitude: number;
  longitude: number;
  deliveries: Delivery[];
}

function groupByLieu(deliveries: Delivery[]): LieuGroup[] {
  const groups = new Map<number, LieuGroup>();

  for (const delivery of deliveries) {
    const lieu = delivery.lieu_detail;

    if (!lieu || lieu.latitude == null || lieu.longitude == null) {
      continue;
    }

    const existing = groups.get(lieu.id);

    if (existing) {
      existing.deliveries.push(delivery);
      continue;
    }

    groups.set(lieu.id, {
      id: lieu.id,
      nom: lieu.nom,
      adresse: lieu.adresse,
      latitude: Number.parseFloat(lieu.latitude),
      longitude: Number.parseFloat(lieu.longitude),
      deliveries: [delivery]
    });
  }

  return Array.from(groups.values());
}

export function DeliveryMap({ deliveries }: { deliveries: Delivery[] }) {
  const groups = useMemo(() => groupByLieu(deliveries), [deliveries]);
  const withoutCoords =
    deliveries.length - groups.reduce((sum, g) => sum + g.deliveries.length, 0);

  const center: [number, number] =
    groups.length > 0
      ? [groups[0].latitude, groups[0].longitude]
      : DEFAULT_CENTER;

  return (
    <Stack gap='xs'>
      {withoutCoords > 0 && (
        <Text size='sm' c='dimmed'>
          {withoutCoords} livraison(s) sans coordonnées GPS non affichée(s) sur
          la carte.
        </Text>
      )}

      <div style={{ height: 480, width: '100%' }}>
        <MapContainer
          center={center}
          zoom={groups.length > 0 ? 10 : 5}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
          />
          {groups.map((group) => (
            <Marker key={group.id} position={[group.latitude, group.longitude]}>
              <Popup>
                <Stack gap={4}>
                  <Text fw={600} size='sm'>
                    {group.nom}
                  </Text>
                  <Text size='xs' c='dimmed'>
                    {group.adresse}
                  </Text>
                  {group.deliveries.map((delivery) => (
                    <Text key={delivery.id} size='xs'>
                      {delivery.numero} — {delivery.prestation_nom}
                    </Text>
                  ))}
                </Stack>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>
    </Stack>
  );
}
