// Scénario nominal complet : client → contact → manifestation → prestation →
// bon → validation → livraison → ramassage → retour.
import { chromium } from 'playwright';

const BASE = 'http://localhost:8000';
const LENT = process.env.LENT === '1';
const M = String(Date.now()).slice(-4);
const NOM_CLIENT = `Festival du Lac ${M}`;
const NOM_MANIF = `Festival du Lac — édition ${M}`;
const NOM_PRESTA = `Scène principale ${M}`;

// Les dates se calculent, elles ne se figent pas. Datées en dur au 13 → 15, la
// manifestation du scénario est tombée dans le passé le 16 : l'arborescence
// s'ouvre sur « Futur », l'écran affiche « Aucune manifestation sur cette
// période », et les six étapes suivantes échouaient sur une application saine.
const AUJOURD_HUI = new Date().getDate();
// Borné au mois courant : le sélecteur de jour n'ouvre pas la page suivante
// tout seul, un 31 + 2 ne serait donc pas cliquable.
const DERNIER_JOUR = new Date(
  new Date().getFullYear(),
  new Date().getMonth() + 1,
  0
).getDate();
const DANS_DEUX_JOURS = Math.min(AUJOURD_HUI + 2, DERNIER_JOUR);

const browser = await chromium.launch({ headless: !LENT, slowMo: LENT ? 300 : 0, args: ['--start-maximized'] });
const ctx = await browser.newContext({ viewport: LENT ? null : { width: 1700, height: 1300 }, timezoneId: 'Europe/Paris', locale: 'fr-FR' });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(`PAGEERROR ${e.message}`));
page.on('response', (r) => { if (r.status() >= 400 && !r.url().includes('/auth/session')) errors.push(`HTTP ${r.status()} ${r.url().replace(BASE, '')}`); });

const dlg = () => page.getByRole('dialog').first();
const opt = () => page.locator('[role="option"]:visible');
const T = (n) => page.waitForTimeout(n);
const bilan = [];
let NUMERO = '';

/** Le statut du bon de la répétition, lu par l'API. */
async function statutBon() {
  const basic = 'Basic ' + Buffer.from('admin:admin123').toString('base64');
  const t = await (await fetch(`${BASE}/api/user/token/`, { headers: { Authorization: basic } })).json();
  const r = await fetch(`${BASE}/plugin/inventree-location/reservations/?ordering=-id`, { headers: { Authorization: `Token ${t.token}` } });
  const d = await r.json();
  const bon = (d.results ?? d).find((b) => b.numero === NUMERO);
  return bon ? `${bon.numero} → ${bon.statut}` : 'bon introuvable';
}

/** Le dernier bon créé, lu par l'API : la liste n'affiche pas la prestation. */
async function dernierBon() {
  // Les endpoints du plugin veulent un token DRF : le Basic ne passe que sur
  // /api/user/token/, qui le délivre.
  const basic = 'Basic ' + Buffer.from('admin:admin123').toString('base64');
  const t = await (await fetch(`${BASE}/api/user/token/`, { headers: { Authorization: basic } })).json();
  const r = await fetch(`${BASE}/plugin/inventree-location/reservations/?ordering=-id`, { headers: { Authorization: `Token ${t.token}` } });
  const d = await r.json();
  return (d.results ?? d)[0]?.numero ?? '';
}

/** mm:ss — le format dans lequel on raisonne quand on minute une soutenance. */
function mmss(ms) {
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

async function etape(titre, fn) {
  console.log(`\n▶ ${titre}`);
  const depart = performance.now();
  try {
    const r = await fn();
    const duree = performance.now() - depart;
    console.log(`   ✓ ${r ?? 'ok'}  —  ${mmss(duree)}`);
    bilan.push(['✓', titre, r ?? '', duree]);
  } catch (e) {
    const duree = performance.now() - depart;
    console.log('   ✗', String(e.stack).split('\n').slice(0, 2).join(' | ').slice(0, 260));
    bilan.push(['✗', titre, String(e).split('\n')[0].slice(0, 120), duree]);
    await page.screenshot({ path: `${process.env.SHOTS_DIR ?? '.'}/echec-${bilan.length}.png` });
    await page.keyboard.press('Escape').catch(() => {});
    await T(800);
  }
}

/** Un jour du calendrier ; Échap fermerait la modale, on clique le titre. */
async function choisirDate(champ, jour) {
  await champ.click();
  await T(1000);
  await page.locator('button.mantine-DateTimePicker-day:visible').filter({ hasText: new RegExp(`^${jour}$`) }).first().click();
  await T(700);
  await page.locator('.mantine-Modal-title').first().click();
  await T(500);
}

async function choisirOption(select, texte) {
  await select.click();
  await T(1000);
  const cible = texte ? opt().filter({ hasText: texte }) : opt();
  await cible.first().click();
  await T(600);
}

await page.goto(`${BASE}/web`, { waitUntil: 'domcontentloaded' });
await T(2500);
await page.locator('input[data-path="username"], input[aria-label="login-username"]').first().fill('admin');
await page.locator('input[data-path="password"], input[aria-label="login-password"]').first().fill('admin123');
await page.getByRole('button', { name: /log ?in|se connecter/i }).click();
await T(5000);
await page.goto(`${BASE}/web/home`, { waitUntil: 'domcontentloaded' });
await T(10000);

await etape(`1. Le client « ${NOM_CLIENT} »`, async () => {
  await page.getByRole('tab', { name: 'Clients' }).first().click();
  await T(2500);
  await page.getByRole('button', { name: 'Créer un client' }).click();
  await T(2000);
  const txt = dlg().locator('input.mantine-TextInput-input');
  await txt.nth(0).fill(NOM_CLIENT);
  await choisirOption(dlg().locator('input.mantine-Select-input').first());
  await txt.nth(1).fill(`contact@festival${M}.test`);
  await txt.nth(2).fill('0299000000');
  await dlg().getByRole('button', { name: 'Enregistrer' }).click();
  await T(3000);
  return page.getByText(/\d+ client\(s\)/).first().innerText();
});

await etape('2. Son contact référent', async () => {
  await page.getByRole('tab', { name: 'Contacts' }).first().click();
  await T(2500);
  await page.getByRole('button', { name: 'Créer un contact' }).click();
  await T(2000);
  await choisirOption(dlg().locator('input.mantine-Select-input').first(), NOM_CLIENT);
  const txt = dlg().locator('input.mantine-TextInput-input');
  await txt.nth(0).fill('Hélène');
  await txt.nth(1).fill(`Vasseur${M}`);
  await txt.nth(2).fill(`helene.vasseur${M}@festival.test`);
  await txt.nth(3).fill('0600000042');
  await dlg().getByRole('button', { name: 'Enregistrer' }).click();
  await T(3000);
  return page.getByText(/\d+ contact\(s\)/).first().innerText();
});

await etape(`3. La manifestation, ${AUJOURD_HUI} → ${DANS_DEUX_JOURS}`, async () => {
  await page.getByRole('tab', { name: 'Fiches' }).first().click();
  await T(3000);
  await page.getByRole('button', { name: 'Nouvelle manifestation' }).click();
  await T(2000);
  const d = dlg();
  await d.locator('input.mantine-TextInput-input').first().fill(NOM_MANIF);
  const dates = d.locator('button.mantine-DateTimePicker-input');
  await choisirDate(dates.nth(0), AUJOURD_HUI);
  await choisirDate(dates.nth(1), DANS_DEUX_JOURS);
  const selects = d.locator('input.mantine-Select-input');
  await choisirOption(selects.nth(0), NOM_CLIENT);
  await choisirOption(selects.nth(1), `Vasseur${M}`);
  await d.getByRole('button', { name: 'Enregistrer' }).click();
  await T(3500);
  return NOM_MANIF;
});

await etape('4. Une prestation, depuis l\'arborescence', async () => {
  await page.getByRole('tab', { name: 'Manifestations' }).first().click();
  await T(3000);
  // L'arbre part du client (F3) : le filtre client a disparu — il faisait
  // doublon avec le niveau — et les clients s'ouvrent repliés. La recherche
  // fait le chemin : elle ne garde que les clients portant une manifestation
  // qui corresponde, et les déplie. Le délai couvre les 300 ms de saisie
  // différée, puis l'appel de repérage.
  await page
    .getByPlaceholder(/Rechercher une manifestation/i)
    .fill(NOM_MANIF);
  await T(3500);
  await page.getByRole('button', { name: 'Ajouter une prestation' }).first().click();
  await T(3000);
  const d = dlg();
  const txt = d.locator('input.mantine-TextInput-input');
  await txt.first().fill(NOM_PRESTA);
  const selects = d.locator('input.mantine-Select-input');
  console.log('     selects de la modale prestation :', await selects.count());
  await choisirOption(selects.nth(1));            // Lieu (0 = manifestation, pré-remplie)
  const dates = d.locator('button.mantine-DateTimePicker-input');
  await choisirDate(dates.nth(0), AUJOURD_HUI);
  await choisirDate(dates.nth(1), DANS_DEUX_JOURS);
  await d.getByRole('button', { name: /Créer la prestation|Créer/ }).click();
  await T(3500);
  return NOM_PRESTA;
});

await etape('5. Un bon de réservation avec du matériel', async () => {
  await page.getByRole('button', { name: 'Ajouter une réservation' }).first().click();
  await T(4000);
  const d = dlg();
  const selects = d.locator('input.mantine-Select-input');
  // 0 = prestation (pré-remplie), 1 = gérant interne, 2 et 3 = les deux
  // sélecteurs d'article. Le demandeur est obligatoire à la soumission.
  await choisirOption(selects.nth(1));
  // PartPicker « Ajouter un article » : chercher, choisir, quantité, ajouter
  const recherche = d.getByPlaceholder('Rechercher un article…').first();
  await recherche.click();
  await T(2500);
  console.log('     articles proposés :', (await opt().allInnerTexts()).slice(0, 3).join(' · '));
  await opt().first().click();
  await T(1200);
  const qte = d.locator('input.mantine-NumberInput-input').first();
  await qte.fill('4');
  await d.getByRole('button', { name: /^Ajouter$/ }).first().click();
  await T(2000);
  // Article virtuel, obligatoire à la soumission
  const recherche2 = d.getByPlaceholder('Rechercher un article…').nth(1);
  await recherche2.click();
  await T(2500);
  console.log('     articles virtuels :', (await opt().allInnerTexts()).slice(0, 3).join(' · '));
  await opt().first().click();
  await T(1200);
  await d.getByRole('button', { name: /^Ajouter$/ }).nth(1).click();
  await T(2000);
  await d.getByRole('button', { name: 'Soumettre' }).click();
  await T(4000);
  if (await page.getByRole('dialog').count()) {
    const reste = await dlg().innerText();
    throw new Error('modale encore ouverte : ' + reste.replace(/\n+/g, ' | ').slice(0, 200));
  }
  NUMERO = await dernierBon();
  return `bon ${NUMERO} soumis`;
});

await etape('6. Validation du bon', async () => {
  await page.getByRole('tab', { name: 'Réservations' }).first().click();
  await T(4000);
  const ligne = page.locator('tr', { hasText: NUMERO }).first();
  console.log('     ligne trouvée :', (await ligne.innerText().catch(() => '—')).replace(/\n/g, ' · ').slice(0, 160));
  await ligne.getByRole('button', { name: 'Valider' }).click();
  await T(3500);
  return (await page.locator('tr', { hasText: NUMERO }).first().innerText()).replace(/\n/g, ' · ').slice(0, 120);
});

await etape('7. Livraison : marquer livrée', async () => {
  await page.getByRole('tab', { name: 'Livraisons' }).first().click();
  await T(4000);
  // L'écran s'ouvre sur la table hiérarchique (F6), où le numéro du bon
  // n'apparaît qu'une fois l'arbre déplié. La vue « Liste » garde la ligne
  // plate et son bouton : c'est elle que ce scénario pilote.
  await page.getByText('Liste', { exact: true }).first().click();
  await T(3000);
  // Et le filtre de journée s'élargit : un créneau qui déborde sur demain
  // sortirait de « Aujourd'hui », et la liste s'afficherait vide.
  await page.locator('label').filter({ hasText: /^Tout$/ }).first().click();
  await T(2500);
  const ligne = page.locator('tr', { hasText: NUMERO }).first();
  console.log('     ligne :', (await ligne.innerText().catch(() => '—')).replace(/\n/g, ' · ').slice(0, 160));
  await ligne.getByRole('button', { name: /Marquer livrée/ }).click();
  await T(3500);
  return 'livrée';
});

await etape('8. Ramassage : les quatre compteurs', async () => {
  await page.getByRole('tab', { name: 'Ramassages' }).first().click();
  await T(4000);
  // L'écran s'ouvre sur l'arborescence (F7), où le numéro du bon ne paraît
  // qu'une fois l'arbre déplié : la vue « Liste » garde la ligne plate et ses
  // boutons. Sans cette bascule, l'étape cherchait une ligne absente, épuisait
  // trente secondes d'attente, et se déclarait bonne — elle ne vérifiait rien.
  await page.locator('label').filter({ hasText: /^Liste$/ }).first().click();
  await T(3000);

  const ligne = page.locator('tr', { hasText: NUMERO }).first();
  // `waitFor` plutôt qu'un `catch` : une ligne absente doit faire échouer
  // l'étape, pas la rendre muette.
  await ligne.waitFor({ timeout: 15000 });
  console.log('     bon à ramasser :', (await ligne.innerText()).replace(/\n/g, ' · ').slice(0, 160));

  const boutons = await ligne.getByRole('button').allInnerTexts();

  // Et le titre de l'étape se vérifie : on ouvre le bon et on compte ses
  // compteurs — récupéré, SAV, détruit, manquant.
  await ligne.getByRole('button', { name: /Voir/ }).click();
  await T(3500);
  const compteurs = await page.locator('input.mantine-NumberInput-input:visible').count();
  await page.keyboard.press('Escape');
  await T(1200);

  if (compteurs !== 4) {
    throw new Error(`${compteurs} compteur(s) sur la ligne, quatre attendus`);
  }

  return `actions : ${boutons.join(', ')} · ${compteurs} compteurs`;
});

await etape('9. Retour complet : les 4 bancs rendus', async () => {
  await page.getByRole('tab', { name: 'Réservations' }).first().click();
  await T(4000);
  const ligne = page.locator('tr', { hasText: NUMERO }).first();
  console.log('     actions :', (await ligne.getByRole('button').allInnerTexts()).join(', '));
  await ligne.getByRole('button', { name: 'Déclarer le retour' }).click();
  await T(3500);
  const d = dlg();
  const nums = d.locator('input.mantine-NumberInput-input');
  console.log('     lignes à rendre :', await nums.count());
  // Retour complet : seul un retour complet fait passer le bon en « retournée ».
  // À 3 sur 4, le serveur le laisse « livrée » et annonce « partiel » — c'est
  // la règle, pas un bug : le manquant se traite au check-in.
  await nums.nth(0).fill('4');
  await T(600);
  await d.getByRole('button', { name: 'Enregistrer le retour' }).click();
  await T(4000);
  await page.screenshot({ path: `${process.env.SHOTS_DIR ?? '.'}/retour.png` });
  return `statut du bon : ${await statutBon()}`;
});

console.log('\n════ bilan ════');
let cumul = 0;
for (const [statut, titre, detail, duree] of bilan) {
  cumul += duree;
  console.log(` ${statut} ${String(titre).padEnd(46)} ${mmss(duree).padStart(5)}   cumul ${mmss(cumul)}`);
  if (detail) console.log(`     ${detail}`);
}
console.log(`\n   parcours complet : ${mmss(cumul)} (hors connexion)`);
console.log('\n--- erreurs ---');
console.log(errors.length ? errors.slice(0, 12).join('\n') : '  aucune');
if (LENT) await T(30000);
await browser.close();
