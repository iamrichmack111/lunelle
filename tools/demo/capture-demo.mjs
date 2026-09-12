import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE = process.env.BASE_URL || "http://127.0.0.1:5055";
const root = path.resolve(process.cwd(), "../..");
const screenshots = path.join(root, "docs", "screenshots");
const demoDir = path.join(root, "docs", "demo");

fs.mkdirSync(screenshots, { recursive: true });
fs.mkdirSync(demoDir, { recursive: true });

const browser = await chromium.launch({ headless: true });

async function settle(page, ms = 900) {
  await page.waitForLoadState("domcontentloaded").catch(() => {});
  await page.waitForTimeout(ms);
}

async function screenshot(page, name, url) {
  const response = await page.goto(`${BASE}${url}`, { waitUntil: "domcontentloaded" }).catch(() => null);
  await settle(page);

  if (!response || response.status() >= 400) {
    console.log(`SKIP ${name}: ${url}`);
    return false;
  }

  if (url !== "/login" && page.url().includes("/login")) {
    console.log(`SKIP ${name}: redirected to login`);
    return false;
  }

  await page.screenshot({
    path: path.join(screenshots, `${name}.png`),
    fullPage: true
  });
  console.log(`SHOT ${name}`);
  return true;
}

async function addSceneCard(page, eyebrow, title, subtitle) {
  await page.evaluate(({ eyebrow, title, subtitle }) => {
    document.getElementById("__lunelle_demo_card")?.remove();

    const card = document.createElement("div");
    card.id = "__lunelle_demo_card";
    card.innerHTML = `
      <div style="
        font: 700 12px/1.2 system-ui,sans-serif;
        letter-spacing:.18em;
        text-transform:uppercase;
        color:#f0a7c7;
        margin-bottom:10px">${eyebrow}</div>
      <div style="
        font: 700 34px/1.05 Georgia,serif;
        color:#fff;
        letter-spacing:-.02em;
        margin-bottom:8px">${title}</div>
      <div style="
        max-width:540px;
        font: 500 16px/1.45 system-ui,sans-serif;
        color:rgba(255,255,255,.74)">${subtitle}</div>
    `;

    Object.assign(card.style, {
      position: "fixed",
      zIndex: "2147483647",
      left: "42px",
      bottom: "38px",
      width: "min(610px, calc(100vw - 84px))",
      padding: "24px 28px",
      borderRadius: "24px",
      background: "linear-gradient(135deg, rgba(24,14,28,.92), rgba(55,25,48,.82))",
      border: "1px solid rgba(255,155,203,.28)",
      boxShadow: "0 28px 90px rgba(0,0,0,.48), inset 0 1px 0 rgba(255,255,255,.08)",
      backdropFilter: "blur(22px)",
      WebkitBackdropFilter: "blur(22px)",
      transform: "translateY(18px)",
      opacity: "0",
      transition: "transform .55s cubic-bezier(.2,.8,.2,1), opacity .45s ease"
    });

    document.body.appendChild(card);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      card.style.transform = "translateY(0)";
      card.style.opacity = "1";
    }));
  }, { eyebrow, title, subtitle });
}

async function removeSceneCard(page) {
  await page.evaluate(() => {
    const card = document.getElementById("__lunelle_demo_card");
    if (!card) return;
    card.style.opacity = "0";
    card.style.transform = "translateY(12px)";
    setTimeout(() => card.remove(), 400);
  }).catch(() => {});
}

async function animatePage(page) {
  await page.mouse.move(1520, 260);
  await page.waitForTimeout(250);
  await page.mouse.move(980, 520, { steps: 16 });
  await page.waitForTimeout(350);

  const interactive = page.locator(
    "button:visible, a:visible, .card:visible, .panel:visible, [data-magnetic]:visible"
  );
  const count = Math.min(await interactive.count(), 4);
  for (let i = 0; i < count; i++) {
    const el = interactive.nth(i);
    await el.hover().catch(() => {});
    await page.waitForTimeout(220);
  }

  await page.mouse.wheel(0, 380).catch(() => {});
  await page.waitForTimeout(400);
  await page.mouse.wheel(0, -380).catch(() => {});
}

async function scene(page, name, route, eyebrow, title, subtitle, hold = 3200) {
  const response = await page.goto(`${BASE}${route}`, { waitUntil: "domcontentloaded" }).catch(() => null);
  await settle(page, 1100);

  if (!response || response.status() >= 400 || (route !== "/login" && page.url().includes("/login"))) {
    console.log(`SKIP ${name}: ${route}`);
    return false;
  }

  await page.screenshot({
    path: path.join(screenshots, `${name}.png`),
    fullPage: true
  });

  await addSceneCard(page, eyebrow, title, subtitle);
  await animatePage(page);
  await page.waitForTimeout(hold);
  await removeSceneCard(page);
  await page.waitForTimeout(450);
  console.log(`SCENE ${name}`);
  return true;
}

// First context: create a disposable account without putting signup mechanics in the product video.
const authContext = await browser.newContext({
  viewport: { width: 1600, height: 1000 },
  colorScheme: "dark"
});
const authPage = await authContext.newPage();
authPage.setDefaultTimeout(8000);

await screenshot(authPage, "01-login", "/login");

const username = `lunelle_demo_${Date.now()}`;
const password = "VelvetMotion!2026";

await authPage.goto(`${BASE}/signup`, { waitUntil: "domcontentloaded" });
await settle(authPage);

const usernameInput = authPage.locator('input[name="username"]');
const passwordInput = authPage.locator('input[name="password"]');
if (await usernameInput.count()) await usernameInput.fill(username);
if (await passwordInput.count()) await passwordInput.fill(password);

const confirm = authPage.locator(
  'input[name="confirm_password"], input[name="password_confirm"], input[name="confirm"]'
);
if (await confirm.count()) await confirm.first().fill(password);

const signupSubmit = authPage.locator('button[type="submit"], input[type="submit"]').first();
if (await signupSubmit.count()) {
  await signupSubmit.click();
  await settle(authPage);
}

if (authPage.url().includes("/login")) {
  const loginUser = authPage.locator('input[name="username"]');
  const loginPass = authPage.locator('input[name="password"]');
  if (await loginUser.count()) await loginUser.fill(username);
  if (await loginPass.count()) await loginPass.fill(password);
  await authPage.locator('button[type="submit"], input[type="submit"]').first().click();
  await settle(authPage);
}

const state = await authContext.storageState();
await authContext.close();

// Second context: clean 1080p product video.
const context = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  colorScheme: "dark",
  storageState: state,
  recordVideo: {
    dir: demoDir,
    size: { width: 1920, height: 1080 }
  }
});

const page = await context.newPage();
page.setDefaultTimeout(8000);

// A deliberate product-story sequence.
await scene(
  page, "02-home", "/dashboard",
  "LUNELLE", "Your rhythm, at a glance.",
  "A private cycle and wellness home designed around clarity, motion, and your personal patterns.",
  3600
);

await scene(
  page, "03-calendar", "/calendar",
  "CYCLE CALENDAR", "See the month in context.",
  "Tracked periods, estimates, cycle phases, check-ins, and lunar context live in one view.",
  3300
);

await scene(
  page, "04-checkin", "/log",
  "DAILY CHECK-IN", "Capture how today actually feels.",
  "Log mood, pain, energy, sleep, stress, flow, symptoms, and personal notes.",
  3300
);

await scene(
  page, "05-journal", "/journal",
  "PRIVATE JOURNAL", "Keep the story behind the numbers.",
  "Reflections stay connected to your cycle without turning the experience into a spreadsheet.",
  3200
);

await scene(
  page, "06-sky", "/sky",
  "SKY SYNC", "Connect your rhythm to the real sky.",
  "Explore sunrise, sunset, moon phases, local darkness, stars, and bright planets.",
  3900
);

await scene(
  page, "07-insights", "/insights",
  "PERSONAL INSIGHTS", "Notice patterns over time.",
  "Compare cycles and surface descriptive trends without pretending to diagnose.",
  3500
);

await scene(
  page, "09-history", "/history",
  "PRIVATE HISTORY", "Your data stays yours.",
  "Review past cycles and check-ins, export your information, and keep control of your history.",
  3300
);

const video = page.video();
await context.close();
await browser.close();

if (video) {
  const oldPath = await video.path();
  const finalPath = path.join(demoDir, "lunelle-demo.webm");
  fs.copyFileSync(oldPath, finalPath);
  if (oldPath !== finalPath) fs.rmSync(oldPath, { force: true });
  console.log(`VIDEO ${finalPath}`);
}
