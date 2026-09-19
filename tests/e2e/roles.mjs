  // Un poste par rôle : ce que chacun voit, ce qu'il peut écrire, ce qui casse.
import { chromium } from 'playwright';

const BASE = 'http://localhost:8000';
const LENT = process.env.LENT === '1';

// Attendu, lu dans `postes/definitions.tsx`. L'ordre compte : le premier
// onglet est l'écran sur lequel le poste s'ouvre.
const ATTENDU = {
  demo_gestionnaire: ['Manifestations', 'Clients', 'Planning', 'Fiches', 'Réservations', 'Catalogue', 'Conflits', 'Alertes stock'],
  demo_magasinier: ['Ramassages', 'Catalogue', 'Alertes stock', 'Réservations'],
  demo_livreur: ['Livraisons', 'Ramassages'],
  demo_acheteur: ['Alertes stock', 'Catalogue'],
  demo_lecteur: ['Planning', 'Réservations', 'Catalogue', 'Conflits'],
  demo_admin: ['Utilisateurs', 'Articles', 'Manifestations', 'Planning', 'Fiches', 'Réservations', 'Livraisons', 'Ramassages', 'Conflits', 'Alertes stock'],
  demo_sav: []      // aucun poste défini pour ce rôle : on regarde ce qui arrive
};

const ECRITURE = /^(Créer|Nouvelle|Nouveau|Ajouter|Valider|Refuser|Marquer|Déclarer|Enregistrer|Désactiver|Accepter)/;
const rapport = [];

for (const [compte, onglets] of Object.entries(ATTENDU)) {
  const browser = await chromium.launch({ headless: !LENT, slowMo: LENT ? 250 : 0, args: LENT ? ['--start-maximized'] : [] });
  const ctx = await browser.newContext({ viewport: LENT ? null : { width: 1700, height: 1300 }, timezoneId: 'Europe/Paris', locale: 'fr-FR' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(`JS ${e.message.slice(0, 90)}`));
  page.on('response', (r) => { if (r.status() >= 400 && !r.url().includes('/auth/session')) errors.push(`HTTP ${r.status()} ${r.url().replace(BASE, '').split('?')[0]}`); });

  const T = (n) => page.waitForTimeout(n);
  console.log(`\n══ ${compte} ══`);

  try {
    await page.goto(`${BASE}/web`, { waitUntil: 'domcontentloaded' });
    await T(2500);
    await page.locator('input[data-path="username"], input[aria-label="login-username"]').first().fill(compte);
    await page.locator('input[data-path="password"], input[aria-label="login-password"]').first().fill('Demo!2026');
    await page.getByRole('button', { name: /log ?in|se connecter/i }).click();
    await T(5000);
    await page.goto(`${BASE}/web/home`, { waitUntil: 'domcontentloaded' });
    await T(9000);

    const poste = page.locator('[role="tab"][data-placement="left"]');
    const vus = (await poste.allInnerTexts()).map((t) => t.trim()).filter(Boolean);
    const barre = (await page.locator('[role="tab"]:not([data-placement="left"])').allInnerTexts()).map((t) => t.trim()).filter(Boolean);
    const titre = await page.locator('h4, h3').first().innerText().catch(() => '—');
    console.log('  poste      :', titre.replace(/\n/g, ' '));
    console.log('  onglets    :', vus.join(' · ') || '(aucun)');
    console.log('  barre haute:', barre.join(' · ') || '(aucune)');

    const manquants = onglets.filter((o) => !vus.includes(o));
    const enTrop = vus.filter((o) => !onglets.includes(o));

    // Chaque onglet est ouvert : un écran qui répond 403 pour un rôle ne se
    // voit qu'en le montant.
    const parOnglet = [];
    for (const nom of vus) {
      const avant = errors.length;
      await poste.filter({ hasText: nom }).first().click();
      await T(3000);
      const ecriture = await page.getByRole('button', { name: ECRITURE }).count();
      parOnglet.push(`${nom}${errors.length > avant ? ' ⚠' : ''}${ecriture ? ` (${ecriture} action${ecriture > 1 ? 's' : ''})` : ''}`);
    }
    console.log('  écrans     :', parOnglet.join(' · ') || '(aucun)');
    if (manquants.length) console.log('  MANQUE     :', manquants.join(', '));
    if (enTrop.length) console.log('  EN TROP    :', enTrop.join(', '));
    console.log('  erreurs    :', errors.length ? errors.slice(0, 4).join(' | ') : 'aucune');

    await page.screenshot({ path: `${process.env.SHOTS_DIR ?? '.'}/role-${compte}.png` });
    rapport.push({ compte, vus, manquants, enTrop, erreurs: errors.length, premier: vus[0] ?? '—', ecrans: parOnglet });
  } catch (e) {
    console.log('  ! ', String(e).split('\n')[0].slice(0, 140));
    rapport.push({ compte, vus: [], manquants: onglets, enTrop: [], erreurs: errors.length, premier: 'échec', ecrans: [] });
  } finally {
    await browser.close();
  }
}

console.log('\n════ bilan par rôle ════');
for (const r of rapport) {
  const ok = r.manquants.length === 0 && r.enTrop.length === 0 && r.erreurs === 0;
  console.log(` ${ok ? '✓' : '✗'} ${r.compte.padEnd(18)} ouvre sur « ${r.premier} » · ${r.vus.length} écran(s) · ${r.erreurs} erreur(s)` +
    (r.manquants.length ? ` · manque ${r.manquants.join(',')}` : '') +
    (r.enTrop.length ? ` · en trop ${r.enTrop.join(',')}` : ''));
}
