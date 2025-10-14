// eslint.config.js
import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";
import eslintConfigPrettier from "eslint-config-prettier";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import simpleImportSort from "eslint-plugin-simple-import-sort";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig([
  // Ignore build outputs
  globalIgnores(["dist"]),

  // Core JS + TypeScript (no type-checking for now for stability)
  js.configs.recommended,
  ...tseslint.configs.recommended,

  // React & Vite-specific enhancements
  reactHooks.configs["recommended-latest"],
  reactRefresh.configs.vite,

  // General project-wide rules
  {
    files: ["**/*.{ts,tsx,js,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: globals.browser,
    },
    plugins: {
      "simple-import-sort": simpleImportSort,
    },
    rules: {
      "no-unused-vars": "off",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^[A-Z_]" },
      ],
      // ✅ Auto-sort imports
      "simple-import-sort/imports": "warn",
      "simple-import-sort/exports": "warn",
    },
  },

  // JS-only override (prevents TS rules from crashing on config files)
  {
    files: ["**/*.js"],
    rules: {
      "@typescript-eslint/await-thenable": "off",
      "@typescript-eslint/no-floating-promises": "off",
    },
  },

  // Disable formatting conflicts with Prettier
  eslintConfigPrettier,
]);
