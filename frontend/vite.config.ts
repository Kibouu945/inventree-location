import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteExternalsPlugin } from "vite-plugin-externals";

/**
 * The following libraries are externalized to avoid bundling them with the plugin.
 * These libraries are expected to be provided by the InvenTree core application.
 */
export const externalLibs: Record<string, string> = {
  react: "React",
  "react-dom": "ReactDOM",
  ReactDom: "ReactDOM",
  "@lingui/core": "LinguiCore",
  "@lingui/react": "LinguiReact",
  "@mantine/core": "MantineCore",
  "@mantine/notifications": "MantineNotifications",
};

// Just the keys of the externalLibs object
const externalKeys = Object.keys(externalLibs);

/**
 * Vite config to build the frontend plugin as an exported module.
 * This will be distributed in the 'static' directory of the plugin.
 */
export default defineConfig({
  plugins: [
    react({
      jsxRuntime: "classic",
    }),
    viteExternalsPlugin(externalLibs),
  ],
  esbuild: {
    jsx: "preserve",
  },
  build: {
    target: "esnext",
    cssCodeSplit: false,
    manifest: true,
    sourcemap: true,
    rollupOptions: {
      preserveEntrySignatures: "exports-only",
      input: [
        "./src/Panel.tsx",
        "./src/Dashboard.tsx",
        "./src/Settings.tsx",
        "./src/Catalog.tsx",
        "./src/Reservations.tsx",
        "./src/Ramassages.tsx",
        "./src/BackOfficeUsers.tsx",
        "./src/BackOfficeParts.tsx",
        "./src/Conflicts.tsx",
        "./src/PartDetail.tsx",
      ],
      output: [
        {
          dir: "../inventree_location/static",
          entryFileNames: "[name].js",
          assetFileNames: "assets/[name].[ext]",
          globals: externalLibs,
        },
        {
          dir: "../inventree_location/static",
          entryFileNames: "[name]-[hash].js",
          assetFileNames: "assets/[name].[ext]",
          globals: externalLibs,
        },
      ],
      external: externalKeys,
    },
  },
  optimizeDeps: {
    exclude: externalKeys,
  },
});