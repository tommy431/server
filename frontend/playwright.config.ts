import { defineConfig, devices } from "@playwright/test";

// Browsertests tegen een eigen testomgeving: een aparte SQLite-database met gegenereerde koersen,
// die bij elke start opnieuw wordt gevuld. Er is geen internet of PostgreSQL nodig.
const API_POORT = 8010;
const WEB_POORT = 5174;
const omgeving = {
  DATABASE_URL: "sqlite:///./e2e-test.db",
  JWT_GEHEIM: "e2e-geheim-alleen-voor-de-browsertests-0123456789",
  VERSLEUTELSLEUTEL: "ZTJlLXNsZXV0ZWwtZTJlLXNsZXV0ZWwtZTJlLXNsZXU=",
  VIER_OGEN: "true",
  // Tweestapsverificatie voor beheerders staat uit, zodat de beheertests zonder codes kunnen.
  // De tweestapsflow zelf wordt getest in accounts.spec.ts.
  TWEESTAPS_VERPLICHT_BEHEERDER: "false",
  // Alle tests komen van hetzelfde adres; de limiet zelf wordt in de backendtests getest.
  LIMIET_VERZOEKEN_PER_MINUUT: "0",
  MARKTKOERSEN_OPHALEN: "false",
};

export default defineConfig({
  testDir: "./e2e",
  // Eén database voor alle tests: na elkaar uitvoeren.
  workers: 1,
  fullyParallel: false,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${WEB_POORT}`,
    trace: "off",
    // Elders geïnstalleerde Chromium gebruiken als die is opgegeven.
    launchOptions: process.env.CHROMIUM_PAD ? { executablePath: process.env.CHROMIUM_PAD } : {},
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1100, height: 900 } } }],
  webServer: [
    {
      command: `uv run python -m app.cli testomgeving && uv run uvicorn app.main:app --port ${API_POORT}`,
      cwd: "../backend",
      env: omgeving,
      url: `http://localhost:${API_POORT}/gezondheid`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npx vite --port ${WEB_POORT} --strictPort`,
      env: { API_URL: `http://localhost:${API_POORT}` },
      url: `http://localhost:${WEB_POORT}`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
