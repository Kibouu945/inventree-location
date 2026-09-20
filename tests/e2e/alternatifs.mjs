// Cas alternatifs : ce que le système doit refuser, tolérer, ou masquer.
//
// Le scénario **fabrique son propre bon** — manifestation, prestation, bon,
// conduit jusqu'à « livrée » — et ne travaille que sur celui-là.
//
// Il attrapait autrefois le premier bon `livree` ou `retournee` que rendait
// `/reservations/`, trié `-date_demande` : donc le plus récent, c'est-à-dire
// celui que `nominal.mjs` venait de créer, ou n'importe lequel de la base de
// démonstration. Il lui écrivait 99 récupérés dessus, et la base mentait
// jusqu'à ce qu'on pense à la remettre en état à la main.
//
// Ce qu'il laisse : le bon fabriqué, **clôturé** en fin de course. On ne peut
// pas le supprimer — le serveur ne supprime qu'un brouillon, et refuse d'y
// revenir une fois le bon livré. Clôturé, il sort des écrans Livraisons et
// Ramassages (leur requête exclut `cloturee`) : il ne gêne plus personne et
// reste lisible comme une pièce ordinaire. Sa manifestation porte l'horodatage
// de la campagne, pour qu'on sache d'où il sort.
import { chromium } from 'playwright';

const BASE = 'http://localhost:8000';
const LENT = process.env.LENT === '1';
const T = (p, n) => p.waitForTimeout(n);
const bilan = [];
const M = String(Date.now()).slice(-4);
const NOM_MANIF = `Cas alternatifs ${M}`;

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

const iso = (d) => d.toISOString().replace(/\.\d{3}Z$/, 'Z');

/** Fabrique le bon du scénario et le conduit jusqu'à « livrée ».
 *
 * Quelques contraintes du serveur, payées une fois chacune :
 *  - la manifestation se crée **sans statut** : posée « planifiée » alors
 *    qu'elle commence maintenant, son statut effectif passe « en cours » et
 *    elle n'accepte plus de prestation ;
 *  - un bon veut son `demandeur` (le gérant interne) et des lignes en
 *    `quantite_demandee` ;
 *  - `date_retour_prevue` est obligatoire pour que le bon entre dans l'écran
 *    Ramassages, dont la requête écarte les bons qui n'en ont pas ;
 *  - un bon livré n'est plus modifiable : les dates se posent à la création.
 */
async function fabriquerLeBon() {
  const clients = await api('/clients/?page_size=1');
  const client = (clients.body?.results ?? [])[0];
  if (!client) throw new Error('aucun client en base — jouer seed_demo');

  const lieux = await api('/lieux/?page_size=1');
  const lieu = (lieux.body?.results ?? [])[0];
  if (!lieu) throw new Error('aucun lieu en base — jouer seed_demo');

  const catalogue = await api('/catalog/?page_size=100');
  const articles = catalogue.body?.results ?? [];
  const materiel = articles.find((a) => a.rentable && !a.is_virtual);
  const virtuel = articles.find((a) => a.is_virtual);
  if (!materiel) throw new Error('aucun article louable au catalogue');

  const debut = new Date();
  const fin = new Date(debut.getTime() + 2 * 24 * 3600 * 1000);

  const manif = await api('/manifestations/', {
    method: 'POST',
    body: JSON.stringify({ nom: NOM_MANIF, client: client.id, date_debut: iso(debut), date_fin: iso(fin) })
  });
  if (manif.status >= 400) throw new Error(`manifestation refusée : ${JSON.stringify(manif.body)}`);

  const presta = await api('/prestations/', {
    method: 'POST',
    body: JSON.stringify({ manifestation: manif.body.id, nom: `Zone de test ${M}`, lieu: lieu.id, date_debut: iso(debut), date_fin: iso(fin) })
  });
  if (presta.status >= 400) throw new Error(`prestation refusée : ${JSON.stringify(presta.body)}`);

  // Le gérant interne est obligatoire à la soumission : on prend le compte qui
  // pilote le scénario, il existe forcément.
  const moi = await api('/backoffice/users/?search=admin');
  const demandeur = (moi.body?.results ?? moi.body ?? []).find((u) => u.username === 'admin');

  const lignes = [{ part: materiel.id, quantite_demandee: 4 }];
  if (virtuel) lignes.push({ part: virtuel.id, quantite_demandee: 1 });

  const bon = await api('/reservations/', {
    method: 'POST',
    body: JSON.stringify({
      prestation: presta.body.id,
      demandeur: demandeur?.id ?? demandeur?.pk,
      date_retrait_prevue: iso(debut),
      date_retour_prevue: iso(fin),
      lignes
    })
  });
  if (bon.status >= 400) throw new Error(`bon refusé : ${JSON.stringify(bon.body)}`);

  for (const statut of ['validee', 'livree']) {
    const r = await api(`/reservations/${bon.body.id}/transition/`, {
      method: 'PATCH',
      body: JSON.stringify({ statut })
    });
    if (r.status >= 400) throw new Error(`transition ${statut} refusée : ${JSON.stringify(r.body)}`);
  }

  const detail = await api(`/reservations/${bon.body.id}/`);
  const ligne = (detail.body?.lignes ?? []).find((l) => l.part === materiel.id);

  return { bon: bon.body, ligne, manifestation: manif.body, prestation: presta.body };
}

/** Clôture le bon fabriqué : il sort des écrans sans disparaître des pièces. */
async function ranger(cible) {
  if (!cible) return '—';
  const etat = (await api(`/reservations/${cible.bon.id}/`)).body?.statut;
  const chemin = etat === 'livree' ? ['retournee', 'cloturee'] : etat === 'retournee' ? ['cloturee'] : [];
  for (const statut of chemin) {
    await api(`/reservations/${cible.bon.id}/transition/`, { method: 'PATCH', body: JSON.stringify({ statut }) });
  }
  return (await api(`/reservations/${cible.bon.id}/`)).body?.statut;
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

let cible = null;
try {
  cible = await fabriquerLeBon();
  console.log(`\n▶ Préparation`);
  console.log(`   ✓ bon ${cible.bon.numero} fabriqué et livré — manifestation « ${NOM_MANIF} »`);
} catch (e) {
  console.log(`\n▶ Préparation`);
  console.log(`   ! ${e.message}`);
  bilan.push(['!', 'Préparation du bon de test', e.message.slice(0, 160)]);
}

// ── A. Le ramassage en surplus doit être accepté (R36 / L5b) ──────────────
await cas('A. Ramassage : récupérer PLUS que ce qui est sorti', async () => {
  if (!cible) return { ok: false, detail: 'préparation échouée — cas non joué' };
  const { browser, page } = await connecte('admin', 'admin123');
  try {
    await page.getByRole('tab', { name: 'Ramassages' }).first().click();
    await T(page, 4500);
    // L'écran s'ouvre sur l'arborescence (F7) ; le bouton « Voir » vit sur la
    // ligne plate de la vue « Liste ». `SegmentedControl` de Mantine rend un
    // `label`, pas un `button`.
    await page.locator('label').filter({ hasText: /^Liste$/ }).first().click();
    await T(page, 3000);
    // Sa ligne à lui, repérée par son numéro : prendre la première venue
    // faisait écrire 99 récupérés sur un bon de la démonstration.
    const numero = cible.bon.numero;
    const ligne = page.locator('tr', { hasText: numero }).first();
    await ligne.waitFor({ timeout: 15000 });
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
  if (!cible) return { ok: false, detail: 'préparation échouée — cas non joué' };
  const { bon, ligne } = cible;
  const r = await api(`/ramassages/${bon.id}/retour/`, {
    method: 'PATCH',
    body: JSON.stringify({ lignes: [{ ligne: ligne.id, quantite_ramassee: 99, quantite_sav: 0, quantite_detruite: 0, quantite_manquante: 0 }], commentaire: 'test surplus' })
  });
  return { ok: r.status < 400, detail: `PATCH ramassage avec 99 récupérés → HTTP ${r.status} ${JSON.stringify(r.body).slice(0, 120)}` };
});

// ── C. Le manquant, lui, reste plafonné ───────────────────────────────────
await cas('C. Manquant supérieur à ce qui est sorti', async () => {
  if (!cible) return { ok: false, detail: 'préparation échouée — cas non joué' };
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
  // Le client se lit, il ne se devine pas : « 1 » en dur n'existe plus dès
  // qu'une base repart de zéro, et le refus serait alors celui du client
  // introuvable, pas celui des dates.
  const client = ((await api('/clients/?page_size=1')).body?.results ?? [])[0];
  const r = await api('/manifestations/', {
    method: 'POST',
    body: JSON.stringify({ nom: 'Cas limite — dates inversées', client: client?.id, date_debut: '2026-10-10T08:00:00Z', date_fin: '2026-10-05T08:00:00Z', statut: 'brouillon' })
  });
  return { ok: r.status === 400, detail: `HTTP ${r.status} — ${JSON.stringify(r.body).slice(0, 160)}` };
});

const statutFinal = await ranger(cible);

console.log('\n════ bilan des cas alternatifs ════');
for (const [s, t, d] of bilan) console.log(` ${s} ${t}\n     ${d}`);

if (cible) {
  console.log(`\n   bon de test ${cible.bon.numero} → ${statutFinal}`);
  console.log(`   « ${NOM_MANIF} » reste en base : un bon livré ne se supprime plus.`);
  console.log(`   Clôturé, il sort des écrans Livraisons et Ramassages.`);
}
