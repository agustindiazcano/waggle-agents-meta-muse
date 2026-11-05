import { test, expect } from "@playwright/test";

test("replay plays, seeks, focuses and pans without changing recorded state", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  // Exercise the renderer's primitive fallback independently of generated binary files.
  await page.route("**/models/*.glb", (route) => route.fulfill({ status: 404, body: "missing" }));
  await page.goto("/?demo=1");
  const slider = page.getByRole("slider", { name: "Frame", exact: true });
  await expect(slider).toHaveAttribute("max", "29");
  await expect(page.locator("#hash")).toHaveText(/^[a-f0-9]{64}$/);
  const initialHash = await page.locator("#hash").textContent();
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect.poll(() => slider.inputValue()).not.toBe("0");
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await slider.fill("0"); await slider.dispatchEvent("input");
  await expect(page.locator("#hash")).toHaveText(initialHash);
  const canvas = page.locator("#canvas canvas");
  const before = (await canvas.screenshot()).toString("base64");
  const bounds = await canvas.boundingBox();
  expect(bounds).not.toBeNull();
  const x = bounds.x + bounds.width / 2, y = bounds.y + bounds.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down({ button: "right" });
  await page.mouse.move(x + 100, y + 60, { steps: 8 });
  await page.mouse.up({ button: "right" });
  await expect.poll(async () => (await canvas.screenshot()).toString("base64")).not.toBe(before);
  await expect(page.locator("#hash")).toHaveText(initialHash);
  await page.getByRole("button", { name: "Focus", exact: true }).click();
  await page.getByRole("button", { name: "Fit all", exact: true }).click();
  expect(errors).toEqual([]);
});

test("gallery lists all models, builds modular equipment and reports a missing asset", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/models/*.glb", (route) => route.fulfill({ status: 404, body: "missing" }));
  await page.goto("/?gallery=1");
  const model = page.locator("#gallery-model");
  await expect(model.locator("option")).toHaveCount(25);
  for (const id of ["modular-rack", "dock", "conveyor"]) {
    await model.selectOption(id);
    await expect(page.locator("#gallery-status")).toContainText(/preview/i);
  }
  await model.selectOption("modular-rack");
  await page.locator("#rack-bays").fill("5");
  await page.locator("#rack-levels").fill("4");
  await expect(page.locator("#gallery-status")).toContainText("Modular rack");
  await page.locator("#rack-bays").fill("0");
  await expect(page.locator("#gallery-status")).toContainText("Choose 1 to 10");
  await model.selectOption("worker-black");
  await expect(page.locator("#gallery-status")).toContainText("Model unavailable: worker_black.glb");
  await expect(page.locator("#gallery-clip")).toBeDisabled();
  expect(errors).toEqual([]);
});

test("unknown replay fields produce a visible error", async ({ page }) => {
  const response = await page.request.get("/demo.jsonl");
  const lines = (await response.text()).trim().split("\n");
  const frame = JSON.parse(lines[1]); frame.unknown = true;
  lines[1] = JSON.stringify(frame);
  await page.route("**/demo.jsonl", (route) => route.fulfill({ status: 200, contentType: "text/plain", body: lines.join("\n") + "\n" }));
  await page.goto("/?demo=1");
  await expect(page.locator("#error")).toBeVisible();
  await expect(page.locator("#viewer")).toBeHidden();
});
