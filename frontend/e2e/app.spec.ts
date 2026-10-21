import { test, expect } from "@playwright/test";

test("prévision, détail, ajustement mensuel, paiement et affectation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByTestId("transferable")).toHaveText("535,00 €");
  await page
    .getByRole("button", {
      name: "Comprendre Courses alimentaires",
      exact: true,
    })
    .click();
  await expect(page.getByRole("dialog")).toContainText("5 × 270,00");
  await page.getByLabel("Nombre d’occurrences").fill("4");
  await page.getByRole("button", { name: "Ajuster pour ce mois" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByTestId("transferable")).toHaveText("805,00 €");
  await page.getByRole("button", { name: "Mois suivant" }).click();
  await expect(page.getByText("Simulation : ce mois utilise")).toBeVisible();
  await page.getByRole("button", { name: "Mois précédent" }).click();
  await expect(page.getByTestId("transferable")).toHaveText("805,00 €");
  await page.getByRole("button", { name: "Opérations", exact: true }).click();
  await page
    .getByRole("button", { name: "Renseigner une opération", exact: true })
    .click();
  await page.getByLabel("Libellé bancaire").fill("EDF test navigateur");
  await page.getByLabel("Montant signé").fill("-172,00");
  await page.getByLabel("Date comptable").fill("2026-10-05");
  await page.getByRole("button", { name: "Enregistrer l’opération" }).click();
  await page.getByRole("button", { name: "Affecter", exact: true }).click();
  await page
    .getByLabel("Charge concernée")
    .selectOption({ label: "Électricité · EDF" });
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await page
    .getByRole("button", { name: "À vérifier", exact: false })
    .first()
    .click();
  await expect(
    page.getByText("Montant payé différent de la règle.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Ce mois-ci", exact: true }).click();
  await expect(page.getByTestId("transferable")).toHaveText("966,50 €");
  await page.reload();
  await expect(page.getByTestId("transferable")).toHaveText("966,50 €");
  expect(errors).toEqual([]);
});

test("clavier, petits écrans et captures de la vue de travail", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Prévision du mois" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Ajouter une charge", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.setViewportSize({ width: 1440, height: 1120 });
  await page.screenshot({ path: "../artifacts/desktop.png", fullPage: true });
  for (const width of [320, 390, 768, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "../artifacts/mobile.png", fullPage: true });
});

test("vrai premier démarrage sans données fictives et reconnexion", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:8766/");
  await expect(
    page.getByRole("heading", { name: "Ouvrir votre budget" }),
  ).toBeVisible();
  await page
    .getByLabel("Clé d’accès")
    .fill("e2e-fake-token-more-than-24-characters");
  await page.getByRole("button", { name: "Se connecter", exact: true }).click();
  await page.getByLabel("Solde constaté").fill("2500");
  await page.getByLabel("Solde DÉPENSES").fill("150");
  await page.getByRole("button", { name: "Créer le suivi" }).click();
  await expect(
    page.getByText("Prévision à compléter", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Prêts du foyer" }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Ajouter une charge", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Nom", { exact: true })
    .fill("Internet");
  await page.getByLabel("Montant par échéance").fill("29,99");
  await page
    .getByRole("button", { name: "Créer la charge", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Internet", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Se déconnecter", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Ouvrir votre budget" }),
  ).toBeVisible();
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
});
