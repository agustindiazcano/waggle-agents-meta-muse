import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

test("all distributed GLBs decode with their recorded animation clips", async ({ page }) => {
  const manifest = JSON.parse(readFileSync(new URL("../models.json", import.meta.url), "utf8"));
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/?gallery=1");
  for (const model of manifest.models) {
    await page.locator("#gallery-model").selectOption(model.id);
    await expect(page.locator("#gallery-status")).toHaveText(`${model.label}. Visual preview only.`);
    await expect(page.locator("#gallery-clip option")).toHaveCount(model.clips.length);
    for (const clip of model.clips) {
      await page.locator("#gallery-clip").selectOption(clip);
      await expect(page.locator("#gallery-clip")).toHaveValue(clip);
    }
  }
  expect(errors).toEqual([]);
});
