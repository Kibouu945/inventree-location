import { describe, expect, it } from 'vitest';

describe('Settings module', () => {
  it('exports renderPluginSettings', async () => {
    const mod = await import('../Settings');
    expect(mod.renderPluginSettings).toBeDefined();
    expect(typeof mod.renderPluginSettings).toBe('function');
  });
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
