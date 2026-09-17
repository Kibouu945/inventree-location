// Cas alternatifs : ce que le système doit refuser, tolérer, ou masquer.
import { chromium } from 'playwright';

const BASE = 'http://localhost:8000';
const LENT = process.env.LENT === '1';
const T = (p, n) => p.waitForTimeout(n);
const bilan = [];

async function token() {
  const basic = 'Basic ' + Buffer.from('admin:admin123').toString('base64');
  const t = await (await fetch(`${BASE}/api/user/token/`, { headers: { Authorization: basic } })).json();
  return t.token;
}
async function api(chemin, opts = {}) {
  const r = await fetch(`${BASE}/plugin/inventree-location${chemin}`, {
    ...opts,
    headers: { Authorization: `Token ${await token()}`, 'Content-Type': 'application/json', ...(opts.headers ?? {}) }
  });
  return { status: r.status, body: await r.json().catch(() => null) };
}

async function connecte(user, pass) {
  const browser = await chromium.launch({ headless: !LENT, slowMo: LENT ? 250 : 0 });
  const ctx = await browser.newContext({ viewport: { width: 1700, height: 1300 }, timezoneId: 'Europe/Paris', locale: 'fr-FR' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(`PAGEERROR ${e.message}`));
  page.on('response', (r) => { if (r.status() >= 400 && !r.url().includes('/auth/session')) errors.push(`HTTP ${r.status()} ${r.url().replace(BASE, '')}`); });
  await page.goto(`${BASE}/web`, { waitUntil: 'domcontentloaded' });
  await T(page, 2500);
  await page.locator('input[data-path="username"], input[aria-label="login-username"]').first().fill(user);
  await page.locator('input[data-path="password"], input[aria-label="login-password"]').first().fill(pass);
  await page.getByRole('button', { name: /log ?in|se connecter/i }).click();
  await T(page, 5000);
  await page.goto(`${BASE}/web/home`, { waitUntil: 'domcontentloaded' });
  await T(page, 10000);
  return { browser, page, errors };
}

async function cibleRamassable() {
  const bons = await api('/reservations/');
  for (const b of (bons.body?.results ?? bons.body ?? [])) {
    if (!['livree', 'retournee'].includes(b.statut)) continue;
    const d = await api(`/reservations/${b.id}/`);
    const ligne = (d.body?.lignes ?? []).find((l) => !l.est_service && !l.virtuel) ?? (d.body?.lignes ?? [])[0];
    if (ligne) return { bon: b, ligne };
  }
  return null;
}

async function cas(titre, fn) {
  console.log(`\n▶ ${titre}`);
  try {
    const r = await fn();
    console.log(`   ${r.ok ? '✓' : '✗'} ${r.detail}`);
    bilan.push([r.ok ? '✓' : '✗', titre, r.detail]);
  } catch (e) {
    console.log('   ! ', String(e.stack).split('\n').slice(0, 2).join(' | ').slice(0, 220));
    bilan.push(['!', titre, String(e).split('\n')[0].slice(0, 120)]);
  }
}

// ── A. Le ramassage en surplus doit être accepté (R36 / L5b) ──────────────
await cas('A. Ramassage : récupérer PLUS que ce qui est sorti', async () => {
  const { browser, page } = await connecte('admin', 'admin123');
  try {
    await page.getByRole('tab', { name: 'Ramassages' }).first().click();
    await T(page, 4500);
    // L'écran s'ouvre sur l'arborescence (F7) ; le bouton « Voir » vit sur la
    // ligne plate de la vue « Liste ». `SegmentedControl` de Mantine rend un
    // `label`, pas un `button`.
    await page.locator('label').filter({ hasText: /^Liste$/ }).first().click();
    await T(page, 3000);
    // Toutes les lignes n'ont pas de bon de ramassage : un bon qui ne porte
    // qu'un service n'a rien à récupérer, donc pas de bouton.
    const ligne = page.locator('tr').filter({ has: page.getByRole('button', { name: /Voir/ }) }).first();
    await ligne.waitFor({ timeout: 15000 });
    const numero = (await ligne.innerText()).split('\t')[0];
    await ligne.getByRole('button', { name: /Voir/ }).click();
    await T(page, 3500);
    const nums = page.locator('input.mantine-NumberInput-input:visible');
    console.log('     compteurs à l\'écran :', await nums.count());
    await nums.nth(0).fill('99');                    // surplus franc
    await T(page, 1500);
    const bouton = page.getByRole('button', { name: 'Enregistrer le retour' }).first();
    const desactive = await bouton.isDisabled();
    // Le surplus doit se signaler sans bloquer (R36) : bandeau jaune, bouton
    // actif. Le bandeau rouge, lui, est réservé au manquant impossible.
    const signal = await page.getByText('Plus que ce qui est sorti').count();
    await page.screenshot({ path: `${process.env.SHOTS_DIR ?? '.'}/alt-a-surplus.png` });
    return {
      ok: !desactive,
      detail: `${numero} · bouton ${desactive ? 'DÉSACTIVÉ' : 'actif'} · signal « Plus que ce qui est sorti » ${signal ? 'affiché' : 'absent'}`
    };
  } finally { await browser.close(); }
});

// ── B. …mais le serveur, lui, l'accepte ───────────────────────────────────
await cas('B. Le serveur accepte-t-il ce même surplus ?', async () => {
  const cible = await cibleRamassable();
  if (!cible) return { ok: false, detail: 'aucun bon livré ou retourné à ramasser' };
  const { bon, ligne } = cible;
  const r = await api(`/ramassages/${bon.id}/retour/`, {
    method: 'PATCH',
    body: JSON.stringify({ lignes: [{ ligne: ligne.id, quantite_ramassee: 99, quantite_sav: 0, quantite_detruite: 0, quantite_manquante: 0 }], commentaire: 'test surplus' })
  });
  return { ok: r.status < 400, detail: `PATCH ramassage avec 99 récupérés → HTTP ${r.status} ${JSON.stringify(r.body).slice(0, 120)}` };
});

// ── C. Le manquant, lui, reste plafonné ───────────────────────────────────
await cas('C. Manquant supérieur à ce qui est sorti', async () => {
  const cible = await cibleRamassable();
  if (!cible) return { ok: false, detail: 'aucun bon livré ou retourné à ramasser' };
  const { bon, ligne } = cible;
  const r = await api(`/ramassages/${bon.id}/retour/`, {
    method: 'PATCH',
    body: JSON.stringify({ lignes: [{ ligne: ligne.id, quantite_ramassee: 0, quantite_sav: 0, quantite_detruite: 0, quantite_manquante: 999 }], commentaire: 'test manquant' })
  });
  return { ok: r.status === 400, detail: `HTTP ${r.status} — ${JSON.stringify(r.body?.detail ?? r.body).slice(0, 150)}` };
});

// ── D. Un rôle sans droit d'écriture ne voit pas les boutons ─────────────
await cas('D. Le lecteur ne peut rien créer', async () => {
  const { browser, page, errors } = await connecte('demo_lecteur', 'Demo!2026');
  try {
    const onglets = await page.getByRole('tab').allInnerTexts();
    const plus = await page.getByRole('button', { name: /^Ajouter une/ }).count();
    await page.screenshot({ path: `${process.env.SHOTS_DIR ?? '.'}/alt-d-lecteur.png` });
    return {
      ok: plus === 0 && !onglets.includes('Utilisateurs'),
      detail: `onglets : ${onglets.slice(6).join(', ')} · boutons d'ajout : ${plus} · erreurs : ${errors.length}`
    };
  } finally { await browser.close(); }
});

// ── E. L'écran Conflits montre le conflit semé ───────────────────────────
await cas('E. Conflits de stock', async () => {
  const { browser, page } = await connecte('admin', 'admin123');
  try {
    await page.getByRole('tab', { name: 'Conflits' }).first().click();
    await T(page, 4500);
    const lignes = await page.locator('table tbody tr').count();
    const txt = (await page.locator('body').innerText()).replace(/\n+/g, ' | ');
    await page.screenshot({ path: `${process.env.SHOTS_DIR ?? '.'}/alt-e-conflits.png` });
    return { ok: lignes > 0, detail: `${lignes} ligne(s) — ${txt.slice(txt.indexOf('Conflits'), txt.indexOf('Conflits') + 180)}` };
  } finally { await browser.close(); }
});

// ── F. Une date de fin avant la date de début ────────────────────────────
await cas('F. Manifestation dont la fin précède le début', async () => {
  const r = await api('/manifestations/', {
    method: 'POST',
    body: JSON.stringify({ nom: 'Cas limite — dates inversées', client: 1, date_debut: '2026-10-10T08:00:00Z', date_fin: '2026-10-05T08:00:00Z', statut: 'brouillon' })
  });
  return { ok: r.status === 400, detail: `HTTP ${r.status} — ${JSON.stringify(r.body).slice(0, 160)}` };
});

console.log('\n════ bilan des cas alternatifs ════');
for (const [s, t, d] of bilan) console.log(` ${s} ${t}\n     ${d}`);
