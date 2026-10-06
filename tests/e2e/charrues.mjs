// Démo live « Vieilles Charrues » : six temps, à commenter pendant qu'ils
// déroulent. Sur une instance semée par `make demo-seed`, jamais sur la prod.
//
//   CHARRUES_MOT_DE_PASSE=… node charrues.mjs        environ 5 minutes
//   DEMO_URL=https://… TEMPO=0.8 VIDEO=1 node charrues.mjs
import { chromium } from 'playwright';

const BASE = process.env.DEMO_URL ?? 'http://localhost:8001';
const MOT_DE_PASSE = process.env.CHARRUES_MOT_DE_PASSE;
// TEMPO règle les arrêts sur image (0.8 = plus court) ; RALENTI, chaque geste.
const TEMPO = Number(process.env.TEMPO ?? 1);
const PAUSE = Number(process.env.PAUSE ?? 1500);
const RALENTI = Number(process.env.RALENTI ?? 220);
const VIDEO = process.env.VIDEO === '1';

const MANIFESTATION = 'Les Vieilles Charrues';
const GRALL_SOIR = 'Podium Grall — concert du soir';

if (!MOT_DE_PASSE) {
  console.error('CHARRUES_MOT_DE_PASSE manquant (voir .demo/mot-de-passe).');
  process.exit(1);
}

let ctx;
let page;
const T = (n) => page.waitForTimeout(n);
// Un arrêt sur un écran à commenter, en secondes.
const regarder = (secondes) => T(secondes * 1000 * TEMPO);
const dlg = () => page.getByRole('dialog').first();
const opt = () => page.locator('[role="option"]:visible');
const nav = (nom) =>
  page.locator('[role="tab"][data-placement="left"]').filter({ hasText: nom }).first();
const segment = (nom) => page.locator('label').filter({ hasText: new RegExp(`^${nom}$`) }).first();
const bilan = [];

/** Bandeau en bas de l'écran : il survit aux navigations via sessionStorage. */
function bandeau() {
  const poser = () => {
    const texte = sessionStorage.getItem('legende-demo');
    if (!texte || !document.body) return;
    let el = document.getElementById('legende-demo');
    if (!el) {
      el = document.createElement('div');
      el.id = 'legende-demo';
      el.style.cssText =
        'position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:2147483647;'
        + 'background:#12161f;color:#fff;font:600 20px system-ui;padding:12px 22px;'
        + 'border-radius:6px;box-shadow:0 6px 24px rgba(0,0,0,.25);pointer-events:none';
      document.body.appendChild(el);
    }
    el.textContent = texte;
  };
  document.addEventListener('DOMContentLoaded', poser);
  setInterval(poser, 500);
}

async function legende(texte) {
  await page.evaluate((t) => sessionStorage.setItem('legende-demo', t), texte);
}

/** Se connecte et attend le poste. Juste après un redémarrage, le premier envoi
 * du formulaire se perd : on attend que la session existe, et on réessaie. */
async function seConnecter(p, compte) {
  for (let essai = 1; essai <= 3; essai++) {
    // Un Wi-Fi qui bascule (ERR_NETWORK_CHANGED) ne doit pas tuer la démo.
    const ouverte = await p
      .goto(`${BASE}/web/login`, { waitUntil: 'domcontentloaded' })
      .then(() => true, () => false);
    if (!ouverte) {
      if (essai === 3) throw new Error(`${BASE} injoignable`);
      await p.waitForTimeout(3000);
      continue;
    }
    await p.locator('input[data-path="username"]').first().waitFor({ timeout: 60000 });
    await p.waitForTimeout(1500);
    await p.locator('input[data-path="username"]').first().fill(compte);
    await p.locator('input[data-path="password"]').first().fill(MOT_DE_PASSE);
    await p.getByRole('button', { name: /log ?in|se connecter/i }).click();

    const connecte = await p
      .waitForURL((url) => !url.pathname.includes('/login'), { timeout: 30000 })
      .then(() => true, () => false);

    if (connecte) break;
    if (essai === 3) throw new Error(`connexion de ${compte} impossible`);
  }

  await p.goto(`${BASE}/web/home`, { waitUntil: 'domcontentloaded' });
  await p.locator('[role="tab"][data-placement="left"]').first().waitFor({ timeout: 90000 });
}

/** Une connexion par compte, sans fenêtre, pour que la démo parte à chaud. */
async function prechauffer() {
  const invisible = await chromium.launch();
  for (const compte of ['demo_gestionnaire', 'demo_livreur', 'demo_magasinier']) {
    const c = await invisible.newContext({ locale: 'fr-FR' });
    await seConnecter(await c.newPage(), compte);
    await c.close();
  }
  await invisible.close();
}

async function connexion(compte) {
  if (ctx) await ctx.close();
  ctx = await browser.newContext({
    viewport: null,
    locale: 'fr-FR',
    timezoneId: 'Europe/Paris',
    ...(VIDEO ? { recordVideo: { dir: 'videos-charrues' } } : {})
  });
  await ctx.addInitScript(bandeau);
  page = await ctx.newPage();
  await seConnecter(page, compte);
  await T(1200);
}

/** Les endpoints du plugin, pour retrouver un numéro de bon sans le lire à l'écran. */
async function api(chemin, compte = 'demo_gestionnaire') {
  const basic = 'Basic ' + Buffer.from(`${compte}:${MOT_DE_PASSE}`).toString('base64');
  const jeton = await (await fetch(`${BASE}/api/user/token/`, { headers: { Authorization: basic } })).json();
  const r = await fetch(`${BASE}/plugin/inventree-location${chemin}`, {
    headers: { Authorization: `Token ${jeton.token}` }
  });
  return r.json();
}

function mmss(ms) {
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

/** Un temps de la démo. Une étape qui casse n'arrête pas les suivantes. */
async function temps(numero, titre, fn) {
  console.log(`\n▶ ${numero}. ${titre}`);
  const depart = performance.now();
  try {
    await legende(`${numero} · ${titre}`);
    const detail = await fn();
    await T(PAUSE);
    bilan.push(['✓', `${numero}. ${titre}`, performance.now() - depart]);
    console.log(`   ✓ ${detail ?? ''}`);
  } catch (e) {
    bilan.push(['✗', `${numero}. ${titre}`, performance.now() - depart]);
    console.log('   ✗', String(e.message).split('\n')[0].slice(0, 200));
    await page.screenshot({ path: `charrues-echec-${numero}.png` }).catch(() => {});
    await page.keyboard.press('Escape').catch(() => {});
  }
}

async function choisirOption(select, texte) {
  await select.click();
  await T(700);
  await (texte ? opt().filter({ hasText: texte }) : opt()).first().click();
  await T(400);
}

async function ouvrirLeFestival() {
  await nav('Manifestations').click();
  await T(2500);
  await page.getByPlaceholder(/Rechercher une manifestation/i).fill('Vieilles');
  await T(2500);
  await page.getByText(MANIFESTATION).first().waitFor({ timeout: 15000 });
}

console.log('Préchauffage des trois comptes, sans fenêtre…');
await prechauffer();

const browser = await chromium.launch({
  headless: false,
  slowMo: RALENTI,
  args: ['--start-maximized']
});

// ── Le gestionnaire ─────────────────────────────────────────────────────────
await connexion('demo_gestionnaire');

await temps(1, 'Le client et ses interlocuteurs', async () => {
  await nav('Clients').click();
  await T(2000);
  await page.getByRole('tab', { name: 'Contacts' }).last().click();
  await T(2000);

  await page.getByRole('button', { name: 'Créer un contact' }).click();
  await T(1200);
  await choisirOption(dlg().locator('input.mantine-Select-input').first(), 'Les Charrues');
  const champs = dlg().locator('input.mantine-TextInput-input');
  await champs.nth(0).fill('Erwan');
  await champs.nth(1).fill('Le Bihan');
  await champs.nth(2).fill('erwan.lebihan@charrues.demo.test');
  await dlg().getByRole('button', { name: 'Enregistrer' }).click();
  await T(2000);
  await regarder(11);

  // L'ancienne régisseuse quitte les listes de choix, pas l'historique.
  const marion = page.locator('tr', { hasText: 'Kervella' }).first();
  await marion.getByRole('button', { name: 'Désactiver' }).click();
  await T(1500);
  await regarder(10);
  return 'Erwan Le Bihan créé, Marion Kervella désactivée';
});

await temps(2, 'L\'arborescence du festival', async () => {
  await ouvrirLeFestival();
  await page.getByText(MANIFESTATION).first().click();
  await T(1500);
  const glenmor = page.getByText('Podium Glenmor — concert du soir').first();
  if (await glenmor.count()) {
    await glenmor.click();
    await T(1800);
  }
  await regarder(24);
  return 'client → manifestation → prestations → bons';
});

await temps(3, 'Le planning, puis les pics des projecteurs lyre', async () => {
  await nav('Planning').click();
  await T(4000);
  await regarder(13);
  await nav('Histogramme').click();
  await T(2500);
  const article = page.locator('input[placeholder="Rechercher un article…"]');
  await article.click();
  await article.fill('lyre');
  await T(1500);
  await page.getByRole('option', { name: 'Projecteur lyre' }).first().click();
  await T(3000);
  await regarder(18);
  return 'lyres : 10 sur 12 engagées le jour des concerts';
});

let bonGrall = null;

await temps(4, 'Un bon de trop : le conflit avant la validation', async () => {
  await ouvrirLeFestival();
  await page.getByText(MANIFESTATION).first().click();
  await T(1500);

  const ligne = page.locator('div')
    .filter({ hasText: GRALL_SOIR })
    .filter({ has: page.getByRole('button', { name: 'Ajouter une réservation' }) })
    .last();
  await ligne.getByRole('button', { name: 'Ajouter une réservation' }).click();
  await T(2500);

  const d = dlg();
  await choisirOption(d.locator('input.mantine-Select-input').nth(1));  // gérant interne
  await d.getByPlaceholder('Rechercher un article…').first().click();
  await d.getByPlaceholder('Rechercher un article…').first().fill('lyre');
  await T(1500);
  await opt().filter({ hasText: 'Projecteur lyre' }).first().click();
  await d.locator('input.mantine-NumberInput-input').first().fill('4');
  await d.getByRole('button', { name: /^Ajouter$/ }).first().click();
  await T(1000);
  await d.getByPlaceholder('Rechercher un article…').nth(1).click();
  await T(1500);
  await opt().first().click();
  await d.getByRole('button', { name: /^Ajouter$/ }).nth(1).click();
  await T(1000);
  await d.getByRole('button', { name: 'Soumettre' }).click();
  await T(2500);
  await regarder(8);

  const bons = await api('/reservations/?ordering=-id');
  bonGrall = (bons.results ?? bons)[0];

  await nav('Réservations').click();
  await T(2500);
  const bon = page.locator('tr', { hasText: bonGrall.numero }).first();
  await bon.getByRole('button', { name: 'Valider' }).click();
  await T(3500);
  await regarder(17);

  const apres = await api(`/reservations/${bonGrall.id}/`);
  if (apres.statut === 'validee') throw new Error(`${bonGrall.numero} validé : pas de conflit`);
  return `${bonGrall.numero} refusé : 4 lyres demandées, 2 libres`;
});

// ── Le livreur ──────────────────────────────────────────────────────────────
await connexion('demo_livreur');

await temps(5, 'La tournée du livreur, par lieu', async () => {
  await nav('Livraisons').click();
  await T(3500);
  await segment('Tournée').click();
  await T(4500);
  await regarder(24);
  return 'les livraisons du jour sur les podiums';
});

// ── Le magasinier ───────────────────────────────────────────────────────────
await connexion('demo_magasinier');

await temps(6, 'Le retour des balances : casse, SAV, manquants', async () => {
  const balances = (await api('/reservations/?search=balances', 'demo_magasinier'));
  const numero = (balances.results ?? balances)[0].numero;

  await nav('Ramassages').click();
  await T(3000);
  await segment('Liste').click();
  await T(2500);
  await page.locator('tr', { hasText: numero }).first()
    .getByRole('button', { name: /Voir/ }).click();
  await T(2500);

  // Revenue OK, SAV, détruite, manquante — dans l'ordre des colonnes.
  const saisir = async (article, valeurs) => {
    const champs = dlg().locator('tr', { hasText: article }).locator('input.mantine-NumberInput-input');
    for (const [i, v] of valeurs.entries()) {
      await champs.nth(i).fill(String(v));
    }
    await T(500);
  };
  await saisir('Micro HF main', [10, 0, 2, 0]);
  await saisir('Multiprise 6 prises', [15, 5, 0, 0]);
  await saisir('Câble électrique 20 m', [30, 0, 0, 10]);
  await regarder(13);
  await dlg().getByRole('button', { name: 'Enregistrer le retour' }).click();
  await T(3000);
  await regarder(10);
  return `${numero} : 2 micros détruits, 5 multiprises en SAV, 10 câbles manquants`;
});

await legende('Fin de la démonstration');

console.log('\n════ bilan ════');
let cumul = 0;
for (const [statut, titre, duree] of bilan) {
  cumul += duree;
  console.log(` ${statut} ${titre.padEnd(52)} ${mmss(duree).padStart(5)}   cumul ${mmss(cumul)}`);
}

await T(PAUSE);
if (ctx) await ctx.close();
await browser.close();
