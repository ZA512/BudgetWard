import { test, expect, type Page } from "@playwright/test";

async function upload(page: Page, content: string, name = "releve.csv") {
  await page
    .getByRole("button", { name: "Importer un CSV", exact: true })
    .first()
    .click();
  await page.getByLabel("Fichier CSV", { exact: true }).setInputFiles({
    name,
    mimeType: "text/csv",
    buffer: Buffer.from(content, "utf-8"),
  });
  await page.getByLabel("Compte qui figure sur ce relevé").selectOption("1");
}

test("CSV, validation historique sélective et réimport sans doublon", async ({
  page,
  request,
}) => {
  const content =
    "Date;Libellé;Montant;Référence\n05/08/2026;ABONNEMENT E2E CSV;-35,00;e2e-csv-08\n05/09/2026;ABONNEMENT E2E CSV;-39,00;e2e-csv-09\n";
  await page.goto("/");
  await upload(page, content);
  await page
    .getByRole("button", { name: "Vérifier l’aperçu", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("2 à importer");
  await page.screenshot({
    path: "../artifacts/csv-preview.png",
    fullPage: false,
  });
  const before = await (await request.get("/api/export")).json();
  expect(
    before.transactions.filter(
      (t: { raw_label: string }) => t.raw_label === "ABONNEMENT E2E CSV",
    ),
  ).toHaveLength(0);
  await page
    .getByRole("button", { name: "Confirmer l’import", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Import terminé", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Analyser l’historique", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Analyse historique", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "ABONNEMENT E2E CSV", exact: true })
    .click();
  await page.screenshot({
    path: "../artifacts/history-proposal.png",
    fullPage: false,
  });
  await expect(page.getByRole("dialog")).toContainText("37,00");
  await page
    .getByLabel("Nom de la charge", { exact: true })
    .fill("Abonnement validé CSV");
  await page.getByRole("dialog").getByRole("checkbox").first().uncheck();
  await expect(page.getByRole("dialog")).toContainText("1 sélectionnée(s)");
  await page
    .getByRole("button", {
      name: "Valider la règle et la sélection",
      exact: true,
    })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const exported = await (await request.get("/api/export")).json();
  const charge = exported.charges.find(
    (c: { name: string }) => c.name === "Abonnement validé CSV",
  );
  expect(
    exported.classifications.filter(
      (c: { charge_id: number }) => c.charge_id === charge.id,
    ),
  ).toHaveLength(1);
  await page.getByRole("button", { name: "Charges", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Abonnement validé CSV", exact: true }),
  ).toBeVisible();
  await upload(page, content);
  await page
    .getByRole("button", { name: "Vérifier l’aperçu", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("2 déjà présent");
  await page
    .getByRole("button", { name: "Terminer sans doublon", exact: true })
    .click();
  await expect(
    page.getByRole("heading", {
      name: "Ce fichier a déjà été traité",
      exact: true,
    }),
  ).toBeVisible();
});

test("aucun import partiel et corrections conservées en revenant aux colonnes", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await upload(
    page,
    "Date;Libellé;Montant;Référence\n40/09/2026;INVALID E2E CSV;-10,00;e2e-invalid\n",
  );
  await page
    .getByRole("button", { name: "Vérifier l’aperçu", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("1 ligne invalide");
  await page
    .getByRole("button", { name: "Confirmer l’import", exact: true })
    .click();
  await expect(
    page.getByRole("dialog").getByRole("alert").last(),
  ).toContainText("Corrigez les lignes invalides");
  expect(
    (await (await request.get("/api/export")).json()).transactions.some(
      (t: { raw_label: string }) => t.raw_label === "INVALID E2E CSV",
    ),
  ).toBe(false);
  await page
    .getByRole("button", { name: "Revenir aux colonnes", exact: false })
    .click();
  await page.getByLabel("Fichier CSV", { exact: true }).setInputFiles({
    name: "iso.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Date;Libellé;Montant;Référence\n2026-09-05;VALID ISO E2E;-10,00;e2e-iso\n",
    ),
  });
  await page
    .getByLabel("Format des dates", { exact: true })
    .selectOption("%Y-%m-%d");
  await page
    .getByRole("button", { name: "Vérifier l’aperçu", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("1 à importer");
  await page
    .getByRole("button", { name: "Revenir aux colonnes", exact: false })
    .click();
  await expect(page.getByLabel("Compte qui figure sur ce relevé")).toHaveValue(
    "1",
  );
  await expect(
    page.getByLabel("Format des dates", { exact: true }),
  ).toHaveValue("%Y-%m-%d");
  for (const width of [320, 390, 768]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
});

test("doublon possible : la décision humaine conserve les vrais paiements identiques", async ({
  page,
  request,
}) => {
  const header = "Date;Libellé;Montant\n";
  const row = "05/09/2026;DEUX VRAIS PAIEMENTS E2E;-15,00\n";
  await page.goto("/");
  await upload(page, header + row + row);
  await page
    .getByRole("button", { name: "Vérifier l’aperçu", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("2 à importer");
  await page
    .getByRole("button", { name: "Confirmer l’import", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Voir les opérations", exact: true })
    .click();
  await upload(page, header + row);
  await page
    .getByRole("button", { name: "Vérifier l’aperçu", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("1 à décider");
  await page.getByLabel("Décision ligne 2").selectOption("SKIP");
  await page
    .getByRole("button", { name: "Confirmer l’import", exact: true })
    .click();
  const exported = await (await request.get("/api/export")).json();
  expect(
    exported.transactions.filter(
      (t: { raw_label: string }) => t.raw_label === "DEUX VRAIS PAIEMENTS E2E",
    ),
  ).toHaveLength(2);
});
