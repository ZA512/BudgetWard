import { test, expect } from "@playwright/test";

const token = "e2e-fake-token-more-than-24-characters";

test("banque fictive : aperçu sans écriture, reprise et réimport", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Banque", exact: true }).click();
  await expect(
    page.getByText("Banque de démonstration", { exact: true }),
  ).toBeVisible();
  const before = await (await page.request.get("/api/export")).json();
  await page.getByRole("button", { name: "Découvrir les comptes" }).click();
  await expect(page.getByLabel("Compte bancaire pour CHARGES")).toHaveValue("");
  await page
    .getByLabel("Compte bancaire pour CHARGES")
    .selectOption({ index: 1 });
  await page
    .getByLabel("Compte bancaire pour DÉPENSES")
    .selectOption({ index: 1 });
  await page
    .getByRole("checkbox", { name: "Je confirme que ces comptes" })
    .check();
  await page
    .getByRole("button", { name: "Associer les comptes choisis" })
    .click();
  await page.getByRole("button", { name: "Préparer l’aperçu fictif" }).click();
  await expect(
    page.getByRole("heading", { name: "Vérifier avant de mettre à jour" }),
  ).toBeVisible();
  const pending = await (await page.request.get("/api/export")).json();
  expect(pending.transactions).toEqual(before.transactions);
  expect(pending.accounts).toEqual(before.accounts);
  await page.reload();
  await expect(
    page.getByText("Une lecture bancaire attend votre confirmation", {
      exact: false,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Banque", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Vérifier avant de mettre à jour" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({
    path: "../artifacts/bank-desktop.png",
    fullPage: true,
  });
  for (const width of [320, 390, 768]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  }
  await page
    .getByRole("checkbox", { name: "Je confirme l’import de cette sélection" })
    .check();
  await page
    .getByRole("button", { name: "Confirmer l’import et les soldes" })
    .click();
  await expect(
    page.getByText("4 opération(s) ajoutée(s).", { exact: false }),
  ).toBeVisible();
  const after = await (await page.request.get("/api/export")).json();
  expect(after.transactions.length).toBe(before.transactions.length + 4);
  await page.getByRole("button", { name: "Préparer l’aperçu fictif" }).click();
  await page
    .getByRole("checkbox", { name: "Je confirme l’import de cette sélection" })
    .check();
  await page
    .getByRole("button", { name: "Confirmer l’import et les soldes" })
    .click();
  await expect(
    page.getByText("0 opération(s) ajoutée(s).", { exact: false }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("sans configuration bancaire, la saisie et le CSV restent accessibles", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:8766/");
  await page.getByLabel("Clé d’accès").fill(token);
  await page.getByRole("button", { name: "Se connecter", exact: true }).click();
  await page.getByRole("button", { name: "Banque", exact: true }).click();
  await expect(
    page.getByText("Connexion bancaire à configurer sur le serveur", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Découvrir les comptes" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Opérations", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Importer un CSV", exact: true }),
  ).toBeVisible();
});

test("premier démarrage : compte en attente signalé et autres comptes sélectionnables", async ({
  page,
}) => {
  await page.route("**/api/bank/discover", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({
      response,
      json: {
        ...data,
        accounts: data.accounts.slice(0, 1),
        unavailable_accounts_count: 1,
      },
    });
  });
  await page.goto("http://127.0.0.1:8767/");
  await page.getByLabel("Clé d’accès").fill(token);
  await page.getByRole("button", { name: "Se connecter", exact: true }).click();
  await page
    .getByRole("button", { name: "Choisir mes comptes dans la banque" })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Un compte courant n’a pas encore de solde disponible",
  );
  await expect(
    page.getByLabel("Compte bancaire pour CHARGES").locator("option"),
  ).toHaveCount(2);
  await page
    .getByLabel("Compte bancaire pour CHARGES")
    .selectOption({ index: 1 });
  await expect(
    page.getByLabel("Compte bancaire pour DÉPENSES").locator("option"),
  ).toHaveCount(1);
  await page
    .getByRole("checkbox", { name: "Je confirme que ces comptes" })
    .check();
  await page
    .getByRole("button", { name: "Utiliser ces comptes", exact: true })
    .click();
  await expect(page.getByLabel("Solde constaté")).toHaveValue("4970,00");
});

test("premier démarrage : choix bancaire explicite et confirmation des soldes", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:8767/");
  await page.getByLabel("Clé d’accès").fill(token);
  await page.getByRole("button", { name: "Se connecter", exact: true }).click();
  await page
    .getByRole("button", { name: "Choisir mes comptes dans la banque" })
    .click();
  await expect(page.getByLabel("Compte bancaire pour CHARGES")).toHaveValue("");
  await page
    .getByLabel("Compte bancaire pour CHARGES")
    .selectOption({ index: 1 });
  await page
    .getByLabel("Compte bancaire pour DÉPENSES")
    .selectOption({ index: 1 });
  await page
    .getByRole("checkbox", { name: "Je confirme que ces comptes" })
    .check();
  await page
    .getByRole("button", { name: "Utiliser ces comptes", exact: true })
    .click();
  await expect(page.getByLabel("Solde constaté")).toHaveValue("4970,00");
  await expect(page.getByLabel("Solde DÉPENSES")).toHaveValue("535,00");
  await page
    .getByRole("checkbox", { name: "Je confirme les comptes choisis" })
    .check();
  await page.getByRole("button", { name: "Créer le suivi" }).click();
  await expect(
    page.getByRole("heading", { name: "Prévision du mois" }),
  ).toBeVisible();
  const bank = await (
    await page.request.get("http://127.0.0.1:8767/api/bank/status")
  ).json();
  expect(bank.bindings).toHaveLength(2);
  const data = await (
    await page.request.get("http://127.0.0.1:8767/api/export")
  ).json();
  expect(data.transactions).toHaveLength(0);
});
