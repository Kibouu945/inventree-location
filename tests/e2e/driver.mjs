// Driver Playwright pour la stack InvenTree + plugin Location.

import { chromium } from 'playwright';

export const BASE = 'http://localhost:8000';
const CREDS = { user: 'admin', pass: 'admin123' };

/** Token DRF, pour les vérifications API en parallèle du navigateur. */
export async function apiToken() {
  const res = await fetch(`${BASE}/api/user/token/`, {
    headers: {
      Authorization: `Basic ${Buffer.from(`${CREDS.user}:${CREDS.pass}`).toString('base64')}`
    }
  });
  return (await res.json()).token;
}

/** Ouvre un navigateur, se connecte et s'arrête sur le dashboard. */
export async function session({
  headless = true,
  width = 1700,
  height = 1300
} = {}) {
  const browser = await chromium.launch({ headless });
  const ctx = await browser.newContext({
    viewport: { width, height },
    timezoneId: 'Europe/Paris',
    locale: 'fr-FR'
  });
  const page = await ctx.newPage();

  const errors = [];
  page.on('pageerror', (e) => errors.push(`PAGEERROR ${e.message}`));
  page.on('response', (r) => {
    if (r.status() >= 400 && !r.url().includes('/auth/session')) {
      errors.push(`HTTP ${r.status()} ${r.url().replace(BASE, '')}`);
    }
  });

  await page.goto(`${BASE}/web`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  // Cibler les champs par `data-path` : depuis InvenTree 1.5, la page de login
  // ajoute un bouton « Toggle password visibility » que
  await page
    .locator('input[data-path="username"], input[aria-label="login-username"]')
    .first()
    .fill(CREDS.user);
  await page
    .locator('input[data-path="password"], input[aria-label="login-password"]')
    .first()
    .fill(CREDS.pass);
  await page.getByRole('button', { name: /log ?in|se connecter/i }).click();
  await page.waitForTimeout(5000);

  await page.goto(`${BASE}/web/home`, { waitUntil: 'domcontentloaded' });
  // Les widgets sont chargés en import dynamique : laisser le temps au bundle.
  await page.waitForTimeout(8000);

  return { browser, ctx, page, errors };
}

/** Le dashboard contient plusieurs tableaux : cibler par un en-tête unique. */
export function table(page, entete) {
  return page.locator('table').filter({ hasText: entete }).first();
}

export async function rows(page, entete) {
  return table(page, entete).locator('tbody tr').count();
}

/** Ajoute un widget à la disposition du dashboard. */
export async function addWidget(page, titre) {
  const heading = page.getByText('InvenTree - admin').first();
  const box = await heading.boundingBox();

  // Le ⋮ de la carte dashboard, pas celui du profil : même ligne que le titre,
  // côté droit.
  const buttons = page.locator('button');
  let target = null;
  for (let i = 0; i < (await buttons.count()); i++) {
    const b = await buttons
      .nth(i)
      .boundingBox()
      .catch(() => null);
    if (b && Math.abs(b.y - box.y) < 40 && b.x > box.x + 800)
      target = buttons.nth(i);
  }
  if (!target) throw new Error('menu ⋮ du dashboard introuvable');

  await target.click();
  await page.waitForTimeout(1500);
  await page
    .locator('[role="menuitem"]')
    .filter({ hasText: /add widget/i })
    .first()
    .click();
  await page.waitForTimeout(2500);

  await page.getByPlaceholder(/Filter dashboard widgets/i).fill(titre);
  await page.waitForTimeout(1500);

  const row = page.locator(`text=${titre}`).first();
  const rb = await row.boundingBox();
  await page.mouse.click(rb.x - 40, rb.y + rb.height / 2);
  await page.waitForTimeout(2500);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(4000);
}

export async function shot(page, nom, opts = {}) {
  const dir = process.env.SHOTS_DIR ?? './shots';
  await page.screenshot({ path: `${dir}/${nom}.png`, ...opts });
  console.log(`  [shot] ${nom}.png`);
}

export function dumpErrors(errors) {
  console.log('\n--- erreurs ---');
  console.log(errors.length ? errors.slice(0, 20).join('\n') : '  aucune');
}
