import { defineConfig } from "@playwright/test";
import base from "./playwright.config.mjs";

export default defineConfig({ ...base, testMatch: "models.spec.mjs", timeout: 60_000 });
