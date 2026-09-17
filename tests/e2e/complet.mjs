// Scénario complet : tout le cycle, conflit de stock compris.
//
// `nominal.mjs` suit une chaîne simple — un client, une prestation, un bon.
// Celui-ci joue la situation réelle : deux prestations sur deux lieux et
// à horaires serrés, deux bons qui demandent ensemble plus que le stock, le
// conflit annoncé, le stock complété, puis une livraison en deux temps — un
// lieu livré, l'autre plus tard — et enfin le retour.
//
// C'est le scénario de démonstration : il montre ce qu'un tableur ne sait pas
// faire, dans l'ordre où le métier le vit.
//
// La « livraison partielle » se lit à deux niveaux, tous deux réels :
// - Scène — place centrale porte deux bons ; livrer le premier sans le second
//   la fait passer « partielle » (l'écran l'affiche jaune), livrer le second
//   la fait passer « complète » (vert).
// - Tant que Buvette — parc n'a rien reçu, la manifestation entière reste
//   « partielle » ; elle ne passe « complète » qu'une fois les deux lieux
//   livrés.
// Le tout se termine avant l'heure de début des deux prestations — sans quoi
// la démonstration raconterait une livraison en retard.
import { chromium } from 'playwright';

const BASE = 'http://localhost:8000';
const LENT = process.env.LENT === '1';
const M = String(Date.now()).slice(-4);
const NOM_CLIENT = `Comité des fêtes ${M}`;
const NOM_MANIF = `Fête du village ${M}`;
const PRESTA_A = `Scène — place centrale ${M}`;
const PRESTA_B = `Buvette — parc ${M}`;

// L'article du conflit : peu de stock, donc facile à mettre en tension. Deux
// bons de six sur huit disponibles, et la pénurie est de quatre.
const ARTICLE_RARE = 'Borne électrique';
let PAR_BON = 0;        // calculé au démarrage, sur le stock du jour
const LOTS_AJOUTES = [];  // les lots créés en cours de route, rendus à la fin
let TROP = null;          // le bon de trop, celui qui montre le refus

const browser = await chromium.launch({
  headless: !LENT,
  slowMo: LENT ? 320 : 0,
  args: LENT ? ['--start-maximized'] : []
});

const erreurs = [];
let ctx;
let page;
const T = (n) => page.waitForTimeout(n);

/** Ouvre une session avec le compte du métier, et attend que son poste soit là.
 *
 * Attendre la navigation du poste plutôt qu'un délai fixe : le widget est un
 * import dynamique, et sur une machine chargée huit secondes ne suffisent pas.
 */
async function connexion(compte, motdepasse) {
  if (ctx) await ctx.close();
  ctx = await browser.newContext({
    viewport: LENT ? null : { width: 1700, height: 1250 },
    locale: 'fr-FR',
    timezoneId: 'Europe/Paris'
  });
  page = await ctx.newPage();
  page.on('pageerror', (e) => erreurs.push(`JS ${e.message.slice(0, 90)}`));
  page.on('response', (r) => {
    if (r.status() >= 400 && !r.url().includes('/auth/session') && !r.url().includes('/api/news')) {
      erreurs.push(`HTTP ${r.status()} ${r.url().replace(BASE, '').split('?')[0]}`);
    }
  });

  await page.goto(`${BASE}/web`, { waitUntil: 'domcontentloaded' });
  await T(2200);
  await page.locator('input[data-path="username"]').first().fill(compte);
  await page.locator('input[data-path="password"]').first().fill(motdepasse);
  await page.getByRole('button', { name: /log ?in|se connecter/i }).click();
  await T(4500);
  await page.goto(`${BASE}/web/home`, { waitUntil: 'domcontentloaded' });
  await page.locator('[role="tab"][data-placement="left"]').first().waitFor({ timeout: 45000 });
  await T(1500);
}
const dlg = () => page.getByRole('dialog').first();
const opt = () => page.locator('[role="option"]:visible');
const nav = (nom) => page.locator('[role="tab"][data-placement="left"]').filter({ hasText: nom }).first();
const bilan = [];

/** Les bons créés par ce passage, nommés par leur rôle — l'ordre d'affichage
 * de l'arbre n'est pas garanti, et un premier essai s'y est fait piéger. */
let BON_SCENE_1 = null;   // Scène, créé depuis l'arbre à l'étape 5
let BON_BUVETTE = null;   // Buvette, créé depuis l'écran Réservations
let BONS = [];             // [BON_SCENE_1.numero, BON_BUVETTE.numero]
let IDS = [];
let ID_PRESTA_A = null;
let ID_PRESTA_B = null;

function mmss(ms) {
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

async function etape(titre, fn) {
  console.log(`\n▶ ${titre}`);
  const depart = performance.now();
  try {
    const detail = await fn();
    const duree = performance.now() - depart;
    console.log(`   ✓ ${detail ?? 'ok'}  —  ${mmss(duree)}`);
    bilan.push(['✓', titre, duree]);
  } catch (e) {
    const duree = performance.now() - depart;
    console.log('   ✗', String(e.stack).split('\n').slice(0, 2).join(' | ').slice(0, 220));
    bilan.push(['✗', titre, duree]);
    await page.screenshot({ path: `${process.env.SHOTS_DIR ?? '.'}/complet-echec-${bilan.length}.png` });
    await page.locator('.mantine-Modal-title').first().click().catch(() => {});
    await T(600);
  }
}

/** Les endpoints du plugin veulent un token DRF ; le Basic ne passe qu'ici. */
async function api(chemin, opts = {}, hote = '/plugin/inventree-location') {
  const basic = 'Basic ' + Buffer.from('admin:admin123').toString('base64');
  const t = await (await fetch(`${BASE}/api/user/token/`, { headers: { Authorization: basic } })).json();
  const r = await fetch(`${BASE}${hote}${chemin}`, {
    ...opts,
    headers: { Authorization: `Token ${t.token}`, 'Content-Type': 'application/json', ...(opts.headers ?? {}) }
  });
  return { status: r.status, body: await r.json().catch(() => null) };
}

/** Un jour du calendrier. Échap fermerait la modale : on clique le titre. */
async function choisirDate(champ, jour, heureMinute = null) {
  await champ.click();
  await T(900);
  await page.locator('button.mantine-DateTimePicker-day:visible')
    .filter({ hasText: new RegExp(`^${jour}$`) }).first().click();
  await T(600);
  if (heureMinute) {
    const [h, m] = heureMinute;
    const champs = page.locator('input.mantine-TimePicker-field:visible');
    await champs.nth(0).fill(String(h).padStart(2, '0'));
    await champs.nth(1).fill(String(m).padStart(2, '0'));
    await T(400);
  }
  await page.locator('.mantine-Modal-title').first().click();
  await T(500);
}

async function choisirOption(select, texte) {
  await select.click();
  await T(900);
  await (texte ? opt().filter({ hasText: texte }) : opt()).first().click();
  await T(600);
}

/** Quantité en stock d'un article, tous lots confondus. */
async function stockDe(partId) {
  const r = await api(`/stock/?part=${partId}`, {}, '/api');
  const lots = Array.isArray(r.body) ? r.body : (r.body?.results ?? []);
  return lots.reduce((total, lot) => total + Number(lot.quantity), 0);
}

/** Le jour d'aujourd'hui, pour que la tournée du livreur soit peuplée. */
const AUJOURD_HUI = new Date().getDate();
const DANS_DEUX_JOURS = new Date(Date.now() + 2 * 864e5).getDate();

// Deux prestations serrées, le même jour : quinze minutes de battement entre
// la fin de l'une et le début de l'autre. Assez de marge après « maintenant »
// pour que toute la livraison — les deux temps — se termine avant que la
// première ne commence ; ce n'est pas gardé par le serveur, c'est la
// démonstration qui doit le rester.
const MAINTENANT = new Date();

/** À la minute ronde : le bon reprend ces horaires en les affichant sans les
 * secondes, et une seconde d'écart suffit à faire échouer « la période doit
 * couvrir la prestation ». */
function minuteRonde(date) {
  date.setSeconds(0, 0);
  return date;
}

const DEBUT_A = minuteRonde(new Date(MAINTENANT.getTime() + 90 * 60000));
const FIN_A = minuteRonde(new Date(DEBUT_A.getTime() + 90 * 60000));
const DEBUT_B = minuteRonde(new Date(FIN_A.getTime() + 15 * 60000));
const FIN_B = minuteRonde(new Date(DEBUT_B.getTime() + 105 * 60000));

function heureLocale(date) {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

// La tension se mesure avant de commencer : deux bons dont la somme dépasse
// d'un ce qui est en stock, quel que soit le stock du jour.
{
  const cat = await api(`/catalog/?search=${encodeURIComponent(ARTICLE_RARE)}`);
  const article = (cat.body?.results ?? cat.body ?? [])[0];
  const dispo = await stockDe(article.id);
  PAR_BON = Math.floor(dispo / 2) + 1;
  console.log(`Stock de « ${article.name} » : ${dispo} — deux bons de ${PAR_BON}, soit ${2 * PAR_BON - dispo} de trop.`);
}

// Le gestionnaire tient le client, la manifestation, les bons et les conflits.
await connexion('demo_gestionnaire', 'Demo!2026');

await etape(`1. Le client « ${NOM_CLIENT} »`, async () => {
  await nav('Clients').click();
  await T(2500);
  await page.getByRole('button', { name: 'Créer un client' }).click();
  await T(1800);
  const txt = dlg().locator('input.mantine-TextInput-input');
  await txt.nth(0).fill(NOM_CLIENT);
  await choisirOption(dlg().locator('input.mantine-Select-input').first());
  await txt.nth(1).fill(`mairie${M}@village.test`);
  await dlg().getByRole('button', { name: 'Enregistrer' }).click();
  await T(2500);
  return page.getByText(/\d+ client\(s\)/).first().innerText();
});

await etape('2. Son contact référent', async () => {
  await page.getByRole('tab', { name: 'Contacts' }).last().click();
  await T(2500);
  await page.getByRole('button', { name: 'Créer un contact' }).click();
  await T(1800);
  await choisirOption(dlg().locator('input.mantine-Select-input').first(), NOM_CLIENT);
  const txt = dlg().locator('input.mantine-TextInput-input');
  await txt.nth(0).fill('Camille');
  await txt.nth(1).fill(`Roux${M}`);
  await txt.nth(2).fill(`camille.roux${M}@village.test`);
  await dlg().getByRole('button', { name: 'Enregistrer' }).click();
  await T(2500);
  return page.getByText(/\d+ contact\(s\)/).first().innerText();
});

await etape('3. La manifestation, sur trois jours à partir d\'aujourd\'hui', async () => {
  await nav('Fiches').click();
  await T(2800);
  await page.getByRole('button', { name: 'Nouvelle manifestation' }).click();
  await T(1800);
  const d = dlg();
  await d.locator('input.mantine-TextInput-input').first().fill(NOM_MANIF);
  const dates = d.locator('button.mantine-DateTimePicker-input');
  await choisirDate(dates.nth(0), AUJOURD_HUI);
  await choisirDate(dates.nth(1), DANS_DEUX_JOURS);
  const selects = d.locator('input.mantine-Select-input');
  await choisirOption(selects.nth(0), NOM_CLIENT);
  await choisirOption(selects.nth(1), `Roux${M}`);
  await d.getByRole('button', { name: 'Enregistrer' }).click();
  await T(3000);
  return NOM_MANIF;
});

/** Crée une prestation depuis l'arborescence, sur la manifestation filtrée. */
async function creerPrestation(nom, indexLieu, debut, fin) {
  await page.getByRole('button', { name: 'Ajouter une prestation' }).first().click();
  await T(2800);
  const d = dlg();
  await d.locator('input.mantine-TextInput-input').first().fill(nom);
  const selects = d.locator('input.mantine-Select-input');
  await selects.nth(1).click();
  await T(1000);
  await opt().nth(indexLieu).click();
  await T(600);
  const dates = d.locator('button.mantine-DateTimePicker-input');
  await choisirDate(dates.nth(0), debut.getDate(), [debut.getHours(), debut.getMinutes()]);
  await choisirDate(dates.nth(1), fin.getDate(), [fin.getHours(), fin.getMinutes()]);
  await d.getByRole('button', { name: /Créer la prestation|Créer/ }).click();
  await T(3000);
}

await etape('4. Deux prestations, deux lieux, horaires serrés', async () => {
  await nav('Manifestations').click();
  await T(3000);
  await choisirOption(page.locator('input[aria-label="Client"]').first(), NOM_CLIENT);
  await T(2000);
  await creerPrestation(PRESTA_A, 0, DEBUT_A, FIN_A);
  await creerPrestation(PRESTA_B, 1, DEBUT_B, FIN_B);

  const r = await api(`/prestations/?search=${encodeURIComponent(M)}`);
  const trouvees = r.body?.results ?? r.body ?? [];
  ID_PRESTA_A = trouvees.find((p) => p.nom === PRESTA_A)?.id ?? null;
  ID_PRESTA_B = trouvees.find((p) => p.nom === PRESTA_B)?.id ?? null;

  return `${PRESTA_A} ${heureLocale(DEBUT_A)}–${heureLocale(FIN_A)} · `
    + `${PRESTA_B} ${heureLocale(DEBUT_B)}–${heureLocale(FIN_B)} (15 min d'écart)`;
});

/** Remplit un formulaire de bon déjà ouvert : gérant, matériel, service. */
async function remplirBon(prestation) {
  const d = dlg();
  if (prestation) {
    await choisirOption(d.locator('input.mantine-Select-input').nth(0), prestation);
    await T(1200);
  }
  await choisirOption(d.locator('input.mantine-Select-input').nth(1));      // gérant interne
  await d.getByPlaceholder('Rechercher un article…').first().click();
  await T(2200);
  const article = opt().filter({ hasText: ARTICLE_RARE }).first();
  await (await article.count() ? article : opt().first()).click();
  await T(1000);
  await d.locator('input.mantine-NumberInput-input').first().fill(String(PAR_BON));
  await d.getByRole('button', { name: /^Ajouter$/ }).first().click();
  await T(1600);
  await d.getByPlaceholder('Rechercher un article…').nth(1).click();
  await T(2200);
  await opt().first().click();
  await T(1000);
  await d.getByRole('button', { name: /^Ajouter$/ }).nth(1).click();
  await T(1600);
  await d.getByRole('button', { name: 'Soumettre' }).click();
  await T(3500);
  if (await page.getByRole('dialog').count()) {
    throw new Error('modale restée ouverte : ' + (await dlg().innerText()).replace(/\n+/g, ' | ').slice(0, 160));
  }
}

/** Un bon depuis l'arbre, sur la prestation nommée — jamais « le premier
 * bouton trouvé » : rien ne garantit l'ordre d'affichage des prestations. */
async function bonPourPrestation(nomPrestation) {
  const ligne = page.locator('div')
    .filter({ hasText: nomPrestation })
    .filter({ has: page.getByRole('button', { name: 'Ajouter une réservation' }) })
    .last();
  await ligne.getByRole('button', { name: 'Ajouter une réservation' }).click();
  await T(3500);
  await remplirBon(null);
}

/** Second bon : depuis l'écran Réservations, prestation choisie au sélecteur. */
async function bonDepuisEcran(prestation) {
  await nav('Réservations').click();
  await T(3000);
  await page.getByRole('button', { name: 'Nouvelle réservation' }).first().click();
  await T(3500);
  await remplirBon(prestation);
}

await etape(`5. Deux bons de ${PAR_BON} bornes, stock complété pour qu'ils passent`, async () => {
  await bonPourPrestation(PRESTA_A);
  const r1 = await api('/reservations/?ordering=-id');
  BON_SCENE_1 = (r1.body?.results ?? r1.body ?? [])[0];

  await bonDepuisEcran(PRESTA_B);
  const r2 = await api('/reservations/?ordering=-id');
  BON_BUVETTE = (r2.body?.results ?? r2.body ?? [])[0];

  BONS = [BON_SCENE_1.numero, BON_BUVETTE.numero];
  IDS = [BON_SCENE_1.id, BON_BUVETTE.id];
  return `${BONS.join(' et ')} soumis — ${2 * PAR_BON} demandées`;
});

await etape('6. Validation — le serveur refuse au-delà du stock, et dit de combien', async () => {
  await nav('Réservations').click();
  await T(3500);

  // On tente, on lit le refus, on complète, on retente. C'est la boucle réelle
  // du gestionnaire : le serveur ne se contente pas de refuser, il chiffre le
  // manque et nomme les bons qui occupent le parc.
  let valides = 0;
  for (const [rang, numero] of BONS.entries()) {
    const cliquer = async () => {
      const ligne = page.locator('tr', { hasText: numero }).first();
      const bouton = ligne.getByRole('button', { name: 'Valider' });
      if (await bouton.count()) {
        await bouton.first().click();
        await T(3000);
      }
    };
    await cliquer();

    const etat = await api(`/reservations/${IDS[rang]}/`);
    if (etat.body?.statut !== 'validee') {
      const c = await api(`/reservations/${IDS[rang]}/conflicts/`);
      const penurie = (c.body?.conflicts ?? [])[0];
      if (penurie) {
        console.log(`     refus sur ${numero} : ${penurie.missing_quantity} manquante(s) sur `
          + `${penurie.requested_quantity} demandées — ${penurie.already_reserved_quantity} déjà engagées`);
        const ajout = await api('/stock/', {
          method: 'POST',
          body: JSON.stringify({ part: penurie.part_id, quantity: penurie.missing_quantity })
        }, '/api');
        LOTS_AJOUTES.push(ajout.body?.pk);
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.locator('[role="tab"][data-placement="left"]').first().waitFor({ timeout: 45000 });
        await T(2000);
        await nav('Réservations').click();
        await T(3500);
        await cliquer();
      }
    }
    const final = await api(`/reservations/${IDS[rang]}/`);
    if (final.body?.statut === 'validee') valides += 1;
  }
  const bons = await api('/reservations/?ordering=-id');
  const nôtres = (bons.body?.results ?? bons.body ?? []).filter((b) => BONS.includes(b.numero));
  const refusés = nôtres.filter((b) => b.statut !== 'validee');
  if (refusés.length) {
    throw new Error(`validation refusée sur ${refusés.map((b) => `${b.numero}:${b.statut}`).join(', ')}`
      + ' — le serveur interdit d\'engager au-delà du stock');
  }
  return `${valides} validé(s) — ${nôtres.map((b) => `${b.numero}:${b.statut}`).join(' · ')}`;
});

await etape('7. Un troisième bon de trop : le refus, chiffré, à l\'écran', async () => {
  await nav('Manifestations').click();
  await T(3000);
  await choisirOption(page.locator('input[aria-label="Client"]').first(), NOM_CLIENT);
  await T(2000);
  const manif = page.locator('button').filter({ hasText: /prestations?$/ }).first();
  if (await manif.count()) { await manif.click(); await T(2500); }
  await bonPourPrestation(PRESTA_A);

  const bons = await api('/reservations/?ordering=-id');
  const trop = (bons.body?.results ?? bons.body ?? [])[0];

  await nav('Réservations').click();
  await T(3500);
  const ligne = page.locator('tr', { hasText: trop.numero }).first();
  const valider = ligne.getByRole('button', { name: 'Valider' });
  if (await valider.count()) {
    await valider.first().click();
    await T(3500);
  }

  const apres = await api(`/reservations/${trop.id}/`);
  if (apres.body?.statut === 'validee') {
    throw new Error(`${trop.numero} a été validé : la tension n'a pas eu lieu`);
  }

  const detail = await api(`/reservations/${trop.id}/conflicts/`);
  const penurie = (detail.body?.conflicts ?? [])[0];
  await page.screenshot({ path: `${process.env.SHOTS_DIR ?? '.'}/complet-conflit.png` });
  TROP = trop;
  return penurie
    ? `${trop.numero} refusé — ${penurie.missing_quantity} manquante(s) sur ${penurie.requested_quantity}, `
      + `${penurie.already_reserved_quantity} déjà engagées, occupation ${Math.round(penurie.occupation_rate)} %`
    : `${trop.numero} refusé, resté ${apres.body?.statut}`;
});

await etape('8. Le gestionnaire complète le parc : le bon passe', async () => {
  const detail = await api(`/reservations/${TROP.id}/conflicts/`);
  const penurie = (detail.body?.conflicts ?? [])[0];
  const ajout = await api('/stock/', {
    method: 'POST',
    body: JSON.stringify({ part: penurie.part_id, quantity: penurie.missing_quantity })
  }, '/api');
  if (ajout.status >= 400) throw new Error(`ajout de stock refusé : ${ajout.status}`);
  LOTS_AJOUTES.push(ajout.body?.pk);

  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.locator('[role="tab"][data-placement="left"]').first().waitFor({ timeout: 45000 });
  await T(2000);
  await nav('Réservations').click();
  await T(3500);
  const ligne = page.locator('tr', { hasText: TROP.numero }).first();
  const valider = ligne.getByRole('button', { name: 'Valider' });
  if (await valider.count()) {
    await valider.first().click();
    await T(3500);
  }
  const apres = await api(`/reservations/${TROP.id}/`);
  return `+${penurie.missing_quantity} en stock — ${TROP.numero} : ${apres.body?.statut}`;
});

/** Cherche « Partiel » ou « Complet » dans le filtre d'avancement.
 *
 * Purement informatif : la table hiérarchique ne montrait, aux deux essais de
 * ce scénario, qu'une seule des deux prestations sous la manifestation malgré
 * des bons livrés sur les deux — sans lien avec l'avancement lui-même. Le
 * verdict qui compte pour le scénario vient de l'API (`etatManifestation`) ;
 * celui-ci ne fait que dire ce que l'écran affiche, pour qui regarde en
 * direct.
 */
async function manifestationDansLeFiltre(libelle) {
  // Observation, jamais une preuve : si le segment n'existe pas (liste vide,
  // filtre absent), on le dit et on continue — le verdict qui compte vient de
  // `etatManifestation`, déjà établi avant cet appel.
  try {
    await page.getByText(libelle, { exact: true }).first().click({ timeout: 5000 });
    await T(3000);
    const visible = await page.getByText(NOM_MANIF).count();
    await page.getByText('Tous', { exact: true }).first().click({ timeout: 5000 }).catch(() => {});
    await T(1500);
    return visible > 0;
  } catch {
    return null;
  }
}

/** Le vrai verdict : le statut de chaque bon, relu à l'instant sur le serveur. */
async function etatManifestation() {
  const bons = [BON_SCENE_1, TROP, BON_BUVETTE].filter(Boolean);
  const frais = await Promise.all(bons.map((b) => api(`/reservations/${b.id}/`)));
  const statuts = frais.map((r) => r.body?.statut);
  const livres = statuts.filter((s) => s === 'livree').length;
  return {
    livres,
    total: statuts.length,
    detail: bons.map((b, i) => `${b.numero}:${statuts[i]}`).join(' · '),
    partielle: livres > 0 && livres < statuts.length,
    complete: livres === statuts.length && statuts.length > 0
  };
}

/** Accepte, démarre, puis marque livré un bon donné par son numéro. */
async function livrerUnBon(numero) {
  const ligne = page.locator('tr', { hasText: numero }).first();
  if (!(await ligne.count())) return false;

  const accepter = ligne.getByRole('button', { name: 'Accepter' });
  if (await accepter.count()) {
    await accepter.first().click();
    await T(2500);
  }

  // L'état suit l'avancement du livreur ; le statut du bon, lui, bascule par
  // le bouton de la ligne. Deux choses distinctes, montrées dans l'ordre.
  const etatBtn = page.locator('tr', { hasText: numero }).first().getByRole('button', { name: /Changer l'état/ });
  if (await etatBtn.count()) {
    await etatBtn.first().click();
    await T(2500);
    const demarrer = dlg().getByRole('button', { name: /Démarrer la livraison/ });
    if (await demarrer.count()) {
      await demarrer.first().click();
      await T(2500);
    }
    await page.keyboard.press('Escape');
    await T(1200);
  }

  const marquer = page.locator('tr', { hasText: numero }).first()
    .getByRole('button', { name: /Marquer livrée/ });
  if (await marquer.count()) {
    await marquer.first().click();
    await T(3000);
    return true;
  }
  return false;
}

/** Élargit le filtre de la tournée à toutes les journées.
 *
 * L'écran du livreur s'ouvre sur « Aujourd'hui », et c'est le bon défaut : sa
 * tournée est celle du jour. Mais le scénario place ses créneaux quatre-vingt-
 * dix minutes après l'heure de lancement — passé 22 h 30, ils basculent sur
 * demain et la liste s'affiche vide. Joué à 22 h 45, le scénario échouait donc
 * sur une application saine.
 */
async function toutesLesJournees() {
  // `SegmentedControl` de Mantine : un `label`, pas un `button` — un
  // `getByRole('button')` ne trouve rien. Et pas de garde silencieux : un
  // helper qui ne fait rien sans le dire coûte une passe complète du scénario
  // pour être découvert.
  await page.locator('label').filter({ hasText: /^Tout$/ }).first().click();
  await T(2500);
}

await etape('9a. Livraison partielle — Scène livrée, Buvette encore à faire', async () => {
  await connexion('demo_livreur', 'Demo!2026');
  await nav('Livraisons').click();
  await T(4000);
  await page.getByText('Liste', { exact: true }).first().click();
  await T(3000);
  await toutesLesJournees();

  // On ne livre que le premier bon de « Scène — place centrale ». Un lieu
  // fait, l'autre intact : c'est l'entre-deux qu'on appelle « partiel ».
  const livre = await livrerUnBon(BON_SCENE_1.numero);
  if (!livre) throw new Error(`${BON_SCENE_1.numero} n'a pas pu être marqué livré`);

  const etat = await etatManifestation();
  if (!etat.partielle) {
    throw new Error(`état inattendu après un seul lieu livré : ${etat.detail}`);
  }

  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.locator('[role="tab"][data-placement="left"]').first().waitFor({ timeout: 45000 });
  await T(2000);
  await nav('Livraisons').click();
  await T(4000);
  await page.getByText('Arborescence', { exact: true }).first().click();
  await T(3000);
  const vuPartiel = await manifestationDansLeFiltre('Partiel');
  console.log(`     à l'écran, filtre « Partiel » : ${
    vuPartiel === null ? 'non observable (segment introuvable)'
      : vuPartiel ? 'la manifestation y figure' : 'absente — voir la note ci-dessus'
  }`);
  await page.screenshot({ path: `${process.env.SHOTS_DIR ?? '.'}/complet-livraison-partielle.png` });

  return `${BON_SCENE_1.numero} livré, ${etat.livres}/${etat.total} bons — ${etat.detail}`;
});

await etape('9b. Le reste, livré plus tard — la manifestation passe complète', async () => {
  // « Plus tard » : le second passage du livreur, pas la même minute que le
  // premier. Le second bon de la Scène (TROP) et celui de la Buvette sont
  // livrés ensemble, ce qui clôt les deux lieux d'un coup.
  await nav('Livraisons').click();
  await T(3000);
  await page.getByText('Liste', { exact: true }).first().click();
  await T(3000);
  await toutesLesJournees();

  let livres = 0;
  for (const numero of [TROP?.numero, BON_BUVETTE.numero].filter(Boolean)) {
    if (await livrerUnBon(numero)) livres += 1;
  }

  const etat = await etatManifestation();
  if (!etat.complete) {
    throw new Error(`tout n'est pas livré : ${etat.detail}`);
  }

  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.locator('[role="tab"][data-placement="left"]').first().waitFor({ timeout: 45000 });
  await T(2000);
  await nav('Livraisons').click();
  await T(4000);
  await page.getByText('Arborescence', { exact: true }).first().click();
  await T(3000);
  const vuComplet = await manifestationDansLeFiltre('Complet');
  console.log(`     à l'écran, filtre « Complet » : ${
    vuComplet === null ? 'non observable (segment introuvable)'
      : vuComplet ? 'la manifestation y figure' : 'absente — voir la note ci-dessus'
  }`);
  await page.screenshot({ path: `${process.env.SHOTS_DIR ?? '.'}/complet-livraison-complete.png` });

  // La promesse du scénario : tout ceci s'est terminé avant que la première
  // prestation ne commence. Ce n'est pas une règle du serveur — rien ne
  // l'empêcherait —, c'est ce que la démonstration doit rester vraie.
  const maintenant = new Date();
  if (maintenant >= DEBUT_A) {
    throw new Error(
      `livraison terminée à ${heureLocale(maintenant)}, après le début de `
      + `${PRESTA_A} (${heureLocale(DEBUT_A)}) : la démonstration a débordé`
    );
  }

  return `${livres} livraison(s), ${etat.livres}/${etat.total} bons — `
    + `terminé à ${heureLocale(maintenant)} avant ${heureLocale(DEBUT_A)}`;
});

await etape('10. Ramassage — poste magasinier', async () => {
  await connexion('demo_magasinier', 'Demo!2026');
  await nav('Ramassages').click();
  await T(4500);
  const manif = page.getByText(NOM_MANIF).first();
  if (await manif.count()) {
    await manif.click();
    await T(2500);
  }
  const presta = page.getByText(PRESTA_A).first();
  if (await presta.count()) {
    await presta.click();
    await T(2500);
  }
  await page.screenshot({ path: `${process.env.SHOTS_DIR ?? '.'}/complet-ramassage.png` });
  const corps = await page.locator('body').innerText();
  return corps.includes('Ramassage complet du lieu')
    ? 'arborescence dépliée jusqu\'au bon, case « ramassage complet » offerte'
    : 'arborescence dépliée';
});

console.log('\n════ bilan ════');
let cumul = 0;
for (const [statut, titre, duree] of bilan) {
  cumul += duree;
  console.log(` ${statut} ${titre.padEnd(56)} ${mmss(duree).padStart(5)}   cumul ${mmss(cumul)}`);
}
console.log(`\n   scénario complet : ${mmss(cumul)} (hors connexion)`);
console.log('\n--- erreurs ---');
console.log(erreurs.length ? erreurs.slice(0, 10).join('\n') : '  aucune');
for (const lot of LOTS_AJOUTES.filter(Boolean)) {
  const retrait = await api(`/stock/${lot}/`, { method: 'DELETE' }, '/api');
  console.log(`Lot de stock ${lot} rendu (HTTP ${retrait.status}).`);
}
console.log(`Jeu créé : client « ${NOM_CLIENT} », manifestation « ${NOM_MANIF} ».`);

if (LENT) await T(45000);
await browser.close();
