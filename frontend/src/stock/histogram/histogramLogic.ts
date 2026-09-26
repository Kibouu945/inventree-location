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

// Trois classes pour les cinq niveaux du serveur : à cinq teintes, l'échelle
// est illisible en deutéranopie (ΔE 3,6, plancher 6). Le taux exact reste
// écrit dans l'infobulle et le tableau. `piste` = fond de jauge.
export type ClasseTension = 'disponible' | 'tendu' | 'complet';

export interface DefinitionClasse {
  libelle: string;
  seuil: string;
  accordFeminin: { singulier: string; pluriel: string };
  couleur: string;
  piste: string;
}

export const CLASSES_TENSION: Record<ClasseTension, DefinitionClasse> = {
  disponible: {
    libelle: 'Disponible',
    seuil: 'moins de 75 %',
    accordFeminin: { singulier: 'disponible', pluriel: 'disponibles' },
    couleur: 'light-dark(#087f5b, #12b886)',
    piste: 'light-dark(#c3fae8, #17423a)'
  },
  tendu: {
    libelle: 'Tendu',
    seuil: 'de 75 à 98 %',
    accordFeminin: { singulier: 'tendue', pluriel: 'tendues' },
    couleur: 'light-dark(#e67700, #fd7e14)',
    piste: 'light-dark(#ffe8cc, #4a3414)'
  },
  complet: {
    libelle: 'Complet',
    seuil: 'au-delà de 98 %',
    accordFeminin: { singulier: 'complète', pluriel: 'complètes' },
    couleur: 'light-dark(#c92a2a, #e03131)',
    piste: 'light-dark(#ffe3e3, #4a2020)'
  }
};

export function libelleJournees(classe: ClasseTension, nombre: number): string {
  const accord = CLASSES_TENSION[classe].accordFeminin;

  return nombre > 1
    ? `journées ${accord.pluriel}`
    : `journée ${accord.singulier}`;
}

export const ORDRE_CLASSES: ClasseTension[] = [
  'disponible',
  'tendu',
  'complet'
];

export function classeDeTension(niveau: TensionLevel): ClasseTension {
  if (niveau === 'red') {
    return 'complet';
  }

  return niveau === 'orange' || niveau === 'yellow' ? 'tendu' : 'disponible';
}

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

// Ce qui est engagé, pas ce qui reste : dessiner le disponible réduisait la
// journée saturée — la seule qu'on cherche — à deux pixels.
export function hauteurRemplissagePourcent(jour: HistogramDay): number {
  if (jour.total_stock <= 0) {
    return jour.reserved > 0 ? 100 : 0;
  }

  const ratio = (jour.reserved / jour.total_stock) * 100;

  return Math.max(0, Math.min(100, ratio));
}

export function tauxOccupationArrondi(jour: HistogramDay): number {
  return Math.round(jour.occupation_rate);
}

export function estWeekEnd(jour: string): boolean {
  return jourIso(jour) >= 6;
}

export function etiquetteColonne(jour: string): {
  numero: string;
  semaine: string;
} {
  const date = enDate(jour);

  return {
    numero: String(date.getUTCDate()),
    semaine: date.toLocaleDateString('fr-FR', {
      weekday: 'short',
      timeZone: 'UTC'
    })
  };
}

// `text-transform: capitalize` relèverait aussi le mois.
export function capitaliser(texte: string): string {
  return texte.charAt(0).toUpperCase() + texte.slice(1);
}

export function libelleJourLong(jour: string): string {
  return enDate(jour).toLocaleDateString('fr-FR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC'
  });
}

// La moitié n'apparaît que si elle tombe juste : un « 7,5 » n'apprend rien.
export function graduations(totalStock: number): number[] {
  if (totalStock <= 0) {
    return [0];
  }

  const moitie = totalStock / 2;

  return Number.isInteger(moitie) && moitie > 0
    ? [0, moitie, totalStock]
    : [0, totalStock];
}

export function resumeTension(
  jours: HistogramDay[]
): Record<ClasseTension, number> {
  const resume: Record<ClasseTension, number> = {
    disponible: 0,
    tendu: 0,
    complet: 0
  };

  for (const jour of jours) {
    resume[classeDeTension(jour.tension_level)] += 1;
  }

  return resume;
}

// Une seule journée étiquetée : une valeur sur chaque colonne ne se lit plus.
export function jourLePlusTendu(jours: HistogramDay[]): HistogramDay | null {
  let pic: HistogramDay | null = null;

  for (const jour of jours) {
    if (
      jour.reserved > 0 &&
      (!pic || jour.occupation_rate > pic.occupation_rate)
    ) {
      pic = jour;
    }
  }

  return pic;
}
