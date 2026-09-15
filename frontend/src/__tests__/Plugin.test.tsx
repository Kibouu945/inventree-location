import { describe, expect, it } from 'vitest';

describe('Settings module', () => {
  // Le graphe de dépendances transformé par Vitest a grossi (leaflet /
  // react-leaflet pour la carte livreur) : le délai par défaut de 5 s devient
  // trop juste pour cet import dynamique.
  it('exports renderPluginSettings', async () => {
    const mod = await import('../Settings');
    expect(mod.renderPluginSettings).toBeDefined();
    expect(typeof mod.renderPluginSettings).toBe('function');
  }, 15000);
});

describe('Plugin structure', () => {
  it('has required entry points', async () => {
    const fs = await import('node:fs');
    const path = await import('node:path');
    const srcDir = path.resolve(__dirname, '..');

    expect(fs.existsSync(path.join(srcDir, 'Panel.tsx'))).toBe(true);
    expect(fs.existsSync(path.join(srcDir, 'Dashboard.tsx'))).toBe(true);
    expect(fs.existsSync(path.join(srcDir, 'Settings.tsx'))).toBe(true);
  });
});
