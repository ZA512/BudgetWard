import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60000,
  workers: 1,
  fullyParallel: false,
  use: {
    baseURL: "http://127.0.0.1:8765",
    headless: true,
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "uv run python scripts/e2e_server.py",
      cwd: "..",
      url: "http://127.0.0.1:8765/health",
      reuseExistingServer: false,
    },
    {
      command: "uv run python scripts/e2e_server.py --real",
      cwd: "..",
      url: "http://127.0.0.1:8766/health",
      reuseExistingServer: false,
    },
    {
      command: "uv run python scripts/e2e_server.py --bank",
      cwd: "..",
      url: "http://127.0.0.1:8767/health",
      reuseExistingServer: false,
    },
  ],
});
