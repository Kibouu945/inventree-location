export type TensionLevel = 'red' | 'orange' | 'yellow' | 'blue' | 'green';

export interface HistogramDay {
  date: string;
  total_stock: number;
  reserved: number;
  available: number;
  occupation_rate: number;
  tension_level: TensionLevel;
}

export type PeriodePreset = 'semaine' | 'mois';

const MS_PAR_JOUR = 24 * 60 * 60 * 1000;

export const TENSION_COLORS: Record<TensionLevel, string> = {
  red: 'red',
  orange: 'orange',
  yellow: 'yellow',
  blue: 'cyan',
  green: 'green'
};

function enDate(jour: string): Date {
  return new Date(`${jour}T00:00:00Z`);
}

function enJour(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function aujourdhui(maintenant: Date = new Date()): string {
  const mois = String(maintenant.getMonth() + 1).padStart(2, '0');
  const jour = String(maintenant.getDate()).padStart(2, '0');
  return `${maintenant.getFullYear()}-${mois}-${jour}`;
}

export function ajouterJours(jour: string, nombre: number): string {
  return enJour(new Date(enDate(jour).getTime() + nombre * MS_PAR_JOUR));
}

export function borneDePeriode(
  dateDebut: string,
  preset: PeriodePreset
): string {
  if (preset === 'semaine') {
    return ajouterJours(dateDebut, 6);
  }

  const debut = enDate(dateDebut);
  const dernierJourDuMois = new Date(
    Date.UTC(debut.getUTCFullYear(), debut.getUTCMonth() + 1, 0)
  );

  return enJour(dernierJourDuMois);
}

export function jourIso(jour: string): number {
  const rang = enDate(jour).getUTCDay();
  return rang === 0 ? 7 : rang;
}

export function filtrerJoursVisibles(
  jours: HistogramDay[],
  joursVisibles: number[] | null | undefined
): HistogramDay[] {
  if (!joursVisibles || joursVisibles.length === 0) {
    return jours;
  }

  const autorises = new Set(joursVisibles);

  return jours.filter((jour) => autorises.has(jourIso(jour.date)));
}

export function hauteurBarrePourcent(jour: HistogramDay): number {
  if (jour.total_stock <= 0) {
    return 0;
  }

  const ratio = (jour.available / jour.total_stock) * 100;

  return Math.max(0, Math.min(100, ratio));
}
