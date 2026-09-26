/** Logique de tournée livreur (LIV-04). */
import type { Ramassage } from '../ramassage/types';
import type { Delivery } from './types';

export type StopKind = 'livraison' | 'ramassage';

/** Un point de passage géolocalisé de la tournée. */
export interface TourneeStop {
  /** Identifiant stable dans l'URL : `l<id>` ou `r<id>`. */
  key: string;
  kind: StopKind;
  /** Id de la réservation (une même résa peut donner 2 arrêts : dépose + reprise). */
  id: number;
  numero: string;
  prestationNom: string;
  lieuNom: string;
  adresse: string;
  latitude: number;
  longitude: number;
  /** Heure prévue (ISO) : retrait pour une livraison, retour pour un ramassage. */
  heure: string | null;
  quantite: number;
}

/**
 * Facteur de sinuosité : un trajet routier est plus long que la ligne droite.
 * 1,3 est la valeur usuelle en zone périurbaine ; elle n'a pas vocation à être
 * exacte, seulement à ne pas annoncer une distance manifestement sous-estimée.
 */
const FACTEUR_ROUTE = 1.3;
/** Vitesse moyenne retenue pour l'estimation, en km/h (utilitaire chargé). */
const VITESSE_MOYENNE_KMH = 45;
/** Temps passé sur place à chaque arrêt (chargement / déchargement), en minutes. */
const MINUTES_PAR_ARRET = 15;
/** Rayon moyen de la Terre, en km. */
const RAYON_TERRE_KM = 6371;

/**
 * Nombre d'étapes intermédiaires acceptées par l'URL Google Maps Directions.
 */
export const MAX_WAYPOINTS_MAPS = 9;

function toNumber(value: string | null): number | null {
  if (value == null) {
    return null;
  }

  const parsed = Number.parseFloat(value);

  return Number.isFinite(parsed) ? parsed : null;
}

function parHeure(a: TourneeStop, b: TourneeStop): number {
  // Un arrêt sans heure prévue passe en fin de tournée plutôt que de
  // s'intercaler arbitrairement au début.
  if (!a.heure) {
    return b.heure ? 1 : 0;
  }

  if (!b.heure) {
    return -1;
  }

  return a.heure.localeCompare(b.heure);
}

/** Arrêts de livraison : dépose au lieu de la prestation. */
export function stopsDepuisLivraisons(deliveries: Delivery[]): TourneeStop[] {
  const stops: TourneeStop[] = [];

  for (const delivery of deliveries) {
    if (delivery.statut !== 'validee') {
      continue;
    }

    const lieu = delivery.lieu_detail;
    const latitude = toNumber(lieu?.latitude ?? null);
    const longitude = toNumber(lieu?.longitude ?? null);

    if (!lieu || latitude == null || longitude == null) {
      continue;
    }

    stops.push({
      key: `l${delivery.id}`,
      kind: 'livraison',
      id: delivery.id,
      numero: delivery.numero,
      prestationNom: delivery.prestation_nom,
      lieuNom: lieu.nom,
      adresse: lieu.adresse,
      latitude,
      longitude,
      heure: delivery.date_retrait_prevue,
      quantite: delivery.quantite_totale
    });
  }

  return stops;
}

/** Arrêts de ramassage : reprise après la prestation. */
export function stopsDepuisRamassages(ramassages: Ramassage[]): TourneeStop[] {
  const stops: TourneeStop[] = [];

  for (const ramassage of ramassages) {
    if (ramassage.statut !== 'livree') {
      continue;
    }

    const lieu = ramassage.lieu;
    const latitude = toNumber(lieu?.latitude ?? null);
    const longitude = toNumber(lieu?.longitude ?? null);

    if (!lieu || latitude == null || longitude == null) {
      continue;
    }

    stops.push({
      key: `r${ramassage.id}`,
      kind: 'ramassage',
      id: ramassage.id,
      numero: ramassage.numero,
      prestationNom: ramassage.prestation_nom,
      lieuNom: lieu.nom,
      adresse: lieu.adresse,
      latitude,
      longitude,
      heure: ramassage.date_retour_prevue,
      quantite: ramassage.quantite_totale
    });
  }

  return stops;
}

/** Nombre d'entrées écartées de la carte faute de coordonnées GPS. */
export function compterSansCoordonnees(
  deliveries: Delivery[],
  ramassages: Ramassage[]
): number {
  const retenus =
    stopsDepuisLivraisons(deliveries).length +
    stopsDepuisRamassages(ramassages).length;
  const candidats =
    deliveries.filter((delivery) => delivery.statut === 'validee').length +
    ramassages.filter((ramassage) => ramassage.statut === 'livree').length;

  return candidats - retenus;
}

/** Tous les arrêts de la période, dans l'ordre chronologique par défaut. */
export function construireStops(
  deliveries: Delivery[],
  ramassages: Ramassage[]
): TourneeStop[] {
  return [
    ...stopsDepuisLivraisons(deliveries),
    ...stopsDepuisRamassages(ramassages)
  ].sort(parHeure);
}

/** Distance orthodromique entre deux arrêts, en kilomètres. */
export function distanceKm(a: TourneeStop, b: TourneeStop): number {
  const rad = Math.PI / 180;
  const dLat = (b.latitude - a.latitude) * rad;
  const dLon = (b.longitude - a.longitude) * rad;
  const lat1 = a.latitude * rad;
  const lat2 = b.latitude * rad;

  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;

  return 2 * RAYON_TERRE_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Longueur totale du parcours dans l'ordre donné, en kilomètres (à vol d'oiseau). */
export function distanceTotaleKm(stops: TourneeStop[]): number {
  let total = 0;

  for (let index = 1; index < stops.length; index += 1) {
    total += distanceKm(stops[index - 1], stops[index]);
  }

  return total;
}

/** Distance routière estimée : vol d'oiseau corrigé du facteur de sinuosité. */
export function distanceRouteKm(stops: TourneeStop[]): number {
  return distanceTotaleKm(stops) * FACTEUR_ROUTE;
}

/** Durée estimée de la tournée en minutes : trajet + temps passé sur place. */
export function dureeEstimeeMin(stops: TourneeStop[]): number {
  if (stops.length === 0) {
    return 0;
  }

  const trajet = (distanceRouteKm(stops) / VITESSE_MOYENNE_KMH) * 60;

  return Math.round(trajet + stops.length * MINUTES_PAR_ARRET);
}

/**
 * Réordonne les arrêts au plus proche voisin depuis le premier arrêt donné.
 */
export function optimiserOrdre(stops: TourneeStop[]): TourneeStop[] {
  if (stops.length < 3) {
    return [...stops];
  }

  const restants = [...stops];
  const ordonnes: TourneeStop[] = [restants.shift() as TourneeStop];

  while (restants.length > 0) {
    const courant = ordonnes[ordonnes.length - 1];
    let meilleur = 0;
    let meilleureDistance = distanceKm(courant, restants[0]);

    for (let index = 1; index < restants.length; index += 1) {
      const candidate = distanceKm(courant, restants[index]);

      if (candidate < meilleureDistance) {
        meilleur = index;
        meilleureDistance = candidate;
      }
    }

    ordonnes.push(restants.splice(meilleur, 1)[0]);
  }

  return ordonnes;
}

/** Sérialise l'ordre courant pour l'URL : `l12,r7,l3`. */
export function serialiserOrdre(stops: TourneeStop[]): string {
  return stops.map((stop) => stop.key).join(',');
}

/** Applique un ordre mémorisé à des arrêts fraîchement chargés. */
export function appliquerOrdre(
  stops: TourneeStop[],
  ordre: string[]
): TourneeStop[] {
  if (ordre.length === 0) {
    return [...stops];
  }

  const restants = new Map(stops.map((stop) => [stop.key, stop]));
  const ordonnes: TourneeStop[] = [];

  for (const key of ordre) {
    const stop = restants.get(key);

    if (stop) {
      ordonnes.push(stop);
      restants.delete(key);
    }
  }

  return [...ordonnes, ...restants.values()];
}

/** Déplace un arrêt d'un cran (delta -1 : plus tôt, +1 : plus tard). */
export function deplacerStop(
  stops: TourneeStop[],
  index: number,
  delta: number
): TourneeStop[] {
  const cible = index + delta;

  if (
    index < 0 ||
    index >= stops.length ||
    cible < 0 ||
    cible >= stops.length
  ) {
    return stops;
  }

  const deplaces = [...stops];
  const [stop] = deplaces.splice(index, 1);
  deplaces.splice(cible, 0, stop);

  return deplaces;
}

function coordonnees(stop: TourneeStop): string {
  return `${stop.latitude},${stop.longitude}`;
}

/**
 * Lien Google Maps couvrant toute la tournée (origine → étapes → destination).
 */
export function construireItineraireUrl(stops: TourneeStop[]): string | null {
  if (stops.length === 0) {
    return null;
  }

  const params = new URLSearchParams({ api: '1', travelmode: 'driving' });

  if (stops.length === 1) {
    params.set('destination', coordonnees(stops[0]));
    return `https://www.google.com/maps/dir/?${params.toString()}`;
  }

  const retenus = stopsRetenusPourMaps(stops);
  const destination = retenus[retenus.length - 1];

  params.set('origin', coordonnees(retenus[0]));
  params.set('destination', coordonnees(destination));

  const etapes = retenus.slice(1, -1);

  if (etapes.length > 0) {
    params.set('waypoints', etapes.map(coordonnees).join('|'));
  }

  return `https://www.google.com/maps/dir/?${params.toString()}`;
}

/** Arrêts effectivement transmis à Google Maps (origine + étapes + destination). */
export function stopsRetenusPourMaps(stops: TourneeStop[]): TourneeStop[] {
  return stops.slice(0, MAX_WAYPOINTS_MAPS + 2);
}

/** Nombre d'arrêts que l'URL Google Maps ne peut pas embarquer. */
export function stopsHorsItineraire(stops: TourneeStop[]): number {
  return Math.max(0, stops.length - (MAX_WAYPOINTS_MAPS + 2));
}

/** Formate une durée en minutes façon « 1 h 25 » / « 40 min ». */
export function formaterDuree(minutes: number): string {
  if (minutes < 60) {
    return `${minutes} min`;
  }

  const heures = Math.floor(minutes / 60);
  const reste = minutes % 60;

  return reste === 0
    ? `${heures} h`
    : `${heures} h ${String(reste).padStart(2, '0')}`;
}
