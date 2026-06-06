import { chromium } from 'playwright';

const OUT = 'C:/Users/Artem Boiko/Desktop/CodeProjects/ERP_26030500/qa-sweep/screens/uniform2/cost-data-ai';
const BASE = 'http://localhost:5173';

const routes = [
  ['/costs', 'costs'],
  ['/costs/import', 'costs-import'],
  ['/catalog', 'catalog'],
  ['/5d', '5d'],
  ['/ai-estimate', 'ai-estimate'],
  ['/ai-estimator', 'ai-estimator'],
  ['/ai-agents', 'ai-agents'],
  ['/advisor', 'advisor'],
  ['/match-elements', 'match-elements'],
];

const suffix = process.argv[2] || '';

const consoleErrors = {};

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const cur = page.url();
      (consoleErrors[cur] ||= []).push(msg.text().slice(0, 300));
    }
  });
  page.on('pageerror', (err) => {
    const cur = page.url();
    (consoleErrors[cur] ||= []).push('PAGEERROR: ' + String(err).slice(0, 300));
  });

  // --- Login via real UI ---
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1800);
  // The demo accordion is open by default (demoOpen=true). Click the demo card
  // directly. If for some reason it is collapsed, open it first.
  let demoCard = page.locator('button', { hasText: 'demo@openconstructionerp.com' });
  if ((await demoCard.count()) === 0) {
    const tryDemo = page.getByRole('button', { name: /try demo/i });
    if (await tryDemo.count()) await tryDemo.first().click();
    await page.waitForTimeout(600);
    demoCard = page.locator('button', { hasText: 'demo@openconstructionerp.com' });
  }
  await demoCard.first().click();
  await page.waitForURL('**/dashboard', { timeout: 30000 });
  await page.waitForTimeout(1500);
  console.log('Logged in, at', page.url());

  for (const [route, slug] of routes) {
    try {
      await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(2500);
      const file = `${OUT}/${slug}${suffix}.png`;
      await page.screenshot({ path: file, fullPage: true });
      console.log('shot', route, '->', file);
    } catch (e) {
      console.log('FAIL', route, String(e).slice(0, 200));
    }
  }

  console.log('CONSOLE_ERRORS_JSON_START');
  console.log(JSON.stringify(consoleErrors, null, 2));
  console.log('CONSOLE_ERRORS_JSON_END');

  await browser.close();
})();
