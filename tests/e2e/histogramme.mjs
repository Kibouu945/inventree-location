// L'histogramme de disponibilité (SCRUM-123). Étapes indépendantes, capture
// par étape.
import { chromium } from 'playwright';

const BASE = 'http://localhost:8000';
const LENT = process.env.LENT === '1';
const SHOTS = process.env.SHOTS_DIR ?? '.';

// Seul article que les données de démo saturent (15/15 le 20 septembre).
const ARTICLE = { id: '11', nom: 'Borne électrique 8 prises' };
const SERVICE = { id: '16', nom: 'Nettoyage du lieu' };
const MOIS = '2026-09-01';

const browser = await chromium.launch({
  headless: !LENT,
  slowMo: LENT ? 250 : 0
});
const ctx = await browser.newContext({
  viewport: { width: 1700, height: 1300 },
  timezoneId: 'Europe/Paris',
  locale: 'fr-FR'
});
const page = await ctx.newPage();

const errors = [];
page.on('pageerror', (e) => errors.push(`JS ${e.message.slice(0, 120)}`));
page.on('response', (r) => {
  if (r.status() >= 400 && !r.url().includes('/auth/session')) {
    errors.push(`HTTP ${r.status()} ${r.url().replace(BASE, '')}`);
  }
});

const T = (n) => page.waitForTimeout(n);
const bilan = [];

async function etape(nom, fn) {
  const avant = errors.length;
  try {
    const detail = await fn();
    const casse = errors.length > avant;
    bilan.push(`${casse ? '✗' : '✓'} ${nom}${detail ? ` — ${detail}` : ''}`);
    console.log(`${casse ? '✗' : '✓'} ${nom}${detail ? ` — ${detail}` : ''}`);
  } catch (e) {
    bilan.push(`✗ ${nom} — ${String(e).split('\n')[0].slice(0, 120)}`);
    console.log(`✗ ${nom} — ${String(e).split('\n')[0].slice(0, 120)}`);
    await page.screenshot({ path: `${SHOTS}/histo-echec-${nom}.png` });
  }
}

const query = () =>
  page.evaluate(() => decodeURIComponent(window.location.search));

// Mantine masque les `input` de SegmentedControl et Chip : on clique le
// `label`. « Article » est ambigu dans la page, d'où le placeholder.
const champArticle = () =>
  page.locator('input[placeholder="Rechercher un article…"]');
const segment = (nom) =>
  page.locator('label').filter({ hasText: new RegExp(`^${nom}$`) });

async function ouvrir(suffixe = '') {
  await page.goto(`${BASE}/web/home?gestionnaire_ecran=histogramme${suffixe}`, {
    waitUntil: 'domcontentloaded'
  });
  await T(9000);
}

await page.goto(`${BASE}/web`, { waitUntil: 'domcontentloaded' });
await T(2500);
await page
  .locator('input[data-path="username"], input[aria-label="login-username"]')
  .first()
  .fill('demo_gestionnaire');
await page
  .locator('input[data-path="password"], input[aria-label="login-password"]')
  .first()
  .fill('Demo!2026');
await page.getByRole('button', { name: /log ?in|se connecter/i }).click();
await T(5000);

await etape("l'onglet Histogramme monte l'écran", async () => {
  await ouvrir();
  const titre = await page
    .getByText('Histogramme de disponibilité')
    .first()
    .innerText();
  await page.screenshot({ path: `${SHOTS}/histo-1-vide.png` });
  return titre;
});

await etape('choisir un article dessine la période', async () => {
  await champArticle().click();
  await T(500);
  await champArticle().fill('Borne');
  await T(1800);
  await page.getByRole('option', { name: ARTICLE.nom }).first().click();
  await T(2500);
  await page.screenshot({ path: `${SHOTS}/histo-2-semaine.png` });
  return `URL : ${await query()}`;
});

await etape('le mois de septembre montre la saturation', async () => {
  // Bouton, pas champ. Le nom accessible d'une journée est sa date en toutes
  // lettres : viser « 1 » ne trouve rien.
  await page.getByText('26/09/2026').first().click();
  await T(1200);
  await page
    .getByRole('button', { name: '1 septembre 2026', exact: true })
    .first()
    .click();
  await T(1500);
  await page.keyboard.press('Escape');
  await T(800);
  await segment('Mois').click();
  await T(2500);
  await page.screenshot({ path: `${SHOTS}/histo-3-mois.png` });
  return `URL : ${await query()}`;
});

await etape('la vue Tableau chiffre les journées', async () => {
  await segment('Tableau').click();
  await T(2000);
  const lignes = await page.locator('table tbody tr').count();
  await page.screenshot({ path: `${SHOTS}/histo-4-tableau.png` });
  return `${lignes} journées`;
});

await etape("l'état d'URL rouvre le même écran", async () => {
  const avant = await query();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await T(9000);
  const lignes = await page.locator('table tbody tr').count();
  const nom = await champArticle().inputValue();
  await page.screenshot({ path: `${SHOTS}/histo-5-rechargement.png` });
  if (!lignes) throw new Error(`rien rouvert (URL avant : ${avant})`);
  return `${nom}, ${lignes} journées, URL conservée`;
});

await etape('le filtre de jours restreint la période', async () => {
  await segment('Sam').click();
  await segment('Dim').click();
  await T(1500);
  const lignes = await page.locator('table tbody tr').count();
  await page.screenshot({ path: `${SHOTS}/histo-6-week-end.png` });
  return `${lignes} journées · URL : ${await query()}`;
});

await etape("l'article immatériel est nommé, pas confondu", async () => {
  await ouvrir(`&hist_part=${SERVICE.id}&hist_from=${MOIS}&hist_periode=mois`);
  const alerte = await page
    .getByText(/immatériel|service/i)
    .first()
    .innerText();
  await page.screenshot({ path: `${SHOTS}/histo-7-immateriel.png` });
  return alerte.replace(/\n/g, ' ').slice(0, 90);
});

console.log('\n════ bilan ════');
for (const l of bilan) console.log(' ', l);
console.log('\n--- erreurs réseau / JS ---');
console.log(errors.length ? errors.slice(0, 15).join('\n') : '  aucune');

await browser.close();
