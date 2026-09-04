// Carte de la tournée (LIV-04) : un marqueur numéroté par arrêt dans l'ordre
// de passage, relié par le tracé du parcours. Tuiles OpenStreetMap, cohérent
// avec le géocodage Nominatim déjà utilisé côté backend.

import { Stack, Text } from '@mantine/core';
import L from 'leaflet';
// La feuille de style est injectée à la main (voir `useFeuilleLeaflet`) : le
// bundle du plugin est chargé en module par InvenTree, qui n'insère aucun
// `<link>` vers le CSS émis à côté. Importée normalement, elle n'arrivait
// jamais dans la page et la carte s'affichait en tuiles empilées.
import leafletCss from 'leaflet/dist/leaflet.css?inline';
import { useEffect, useMemo } from 'react';
import {
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  useMap
} from 'react-leaflet';

import type { StopKind, TourneeStop } from './tournee';

const STYLE_ID = 'inventree-location-leaflet-css';

/** Pose la feuille de style Leaflet dans la page, une seule fois. */
function useFeuilleLeaflet() {
  useEffect(() => {
    if (document.getElementById(STYLE_ID)) {
      return;
    }

    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = leafletCss;
    document.head.appendChild(style);
  }, []);
}

/** Centre de repli quand la tournée est vide : France métropolitaine. */
const CENTRE_DEFAUT: [number, number] = [46.6, 2.5];

const COULEURS: Record<StopKind, string> = {
  livraison: '#1c7ed6',
  ramassage: '#9c36b5'
};

/**
 * Marqueur portant son numéro d'ordre.
 *
 * Tous les marqueurs sont des `divIcon` : le correctif classique sur les
 * icônes PNG par défaut de Leaflet (URLs cassées une fois bundlées par Vite)
 * n'a donc plus lieu d'être ici — il redeviendrait nécessaire le jour où un
 * `Marker` sans `icon` serait ajouté.
 */
function iconeNumerotee(rang: number, kind: StopKind): L.DivIcon {
  return L.divIcon({
    className: '',
    html: `<div style="background:${COULEURS[kind]};color:#fff;width:26px;height:26px;border-radius:50%;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4);display:flex;align-items:center;justify-content:center;font:600 13px/1 sans-serif">${rang}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    popupAnchor: [0, -13]
  });
}

/** Recadre la carte sur l'ensemble des arrêts à chaque changement de tournée. */
function AjusterVue({ stops }: { stops: TourneeStop[] }) {
  const map = useMap();

  useEffect(() => {
    // Le widget dashboard fixe la largeur du conteneur *après* l'initialisation
    // de la carte : sans `invalidateSize`, Leaflet garde la taille du premier
    // rendu et pose les tuiles en décalé, sur une carte à moitié grise.
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(map.getContainer());

    return () => observer.disconnect();
  }, [map]);

  useEffect(() => {
    if (stops.length === 0) {
      return;
    }

    const bounds = L.latLngBounds(
      stops.map((stop) => [stop.latitude, stop.longitude] as [number, number])
    );

    map.invalidateSize();
    // `maxZoom` évite de coller au sol quand tous les arrêts sont au même lieu.
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
  }, [map, stops]);

  return null;
}

export function TourneeMap({ stops }: { stops: TourneeStop[] }) {
  useFeuilleLeaflet();

  const positions = useMemo(
    () =>
      stops.map((stop) => [stop.latitude, stop.longitude] as [number, number]),
    [stops]
  );

  return (
    <Stack gap={4}>
      <div style={{ height: 480, width: '100%' }}>
        <MapContainer
          center={positions[0] ?? CENTRE_DEFAUT}
          zoom={positions.length > 0 ? 10 : 5}
          style={{ height: '100%', width: '100%' }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
          />

          <AjusterVue stops={stops} />

          {positions.length > 1 && (
            <Polyline
              positions={positions}
              color='#495057'
              weight={3}
              opacity={0.7}
              dashArray='6 6'
            />
          )}

          {stops.map((stop, index) => (
            <Marker
              key={stop.key}
              position={[stop.latitude, stop.longitude]}
              icon={iconeNumerotee(index + 1, stop.kind)}
            >
              <Popup>
                <Stack gap={2}>
                  <Text fw={600} size='sm'>
                    {index + 1}. {stop.lieuNom}
                  </Text>
                  <Text size='xs' c='dimmed'>
                    {stop.adresse}
                  </Text>
                  <Text size='xs'>
                    {stop.kind === 'livraison' ? 'Livraison' : 'Ramassage'} —{' '}
                    {stop.numero}
                  </Text>
                  <Text size='xs' c='dimmed'>
                    {stop.prestationNom}
                  </Text>
                </Stack>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>

      <Text size='xs' c='dimmed'>
        Le tracé relie les arrêts à vol d'oiseau : il donne l'ordre de passage,
        pas l'itinéraire routier réel.
      </Text>
    </Stack>
  );
}
