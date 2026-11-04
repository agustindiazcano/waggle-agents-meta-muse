import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./browser",
  testMatch: "viewer.spec.mjs",
  workers: 1,
  retries: 0,
  timeout: 30_000,
  use: {
    baseURL: "http://127.0.0.1:5186",
    viewport: { width: 1280, height: 900 },
    launchOptions: {
      executablePath: process.env.WAGGLE_BROWSER_EXECUTABLE,
      args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl"],
    },
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 5186 --strictPort",
    url: "http://127.0.0.1:5186",
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
