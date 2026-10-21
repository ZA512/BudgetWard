export function cents(value: FormDataEntryValue | null): number {
  const text = String(value ?? "")
    .trim()
    .replace(/[\s\u00a0\u202f]/g, "");
  if (!/^-?\d+(?:[.,]\d{1,2})?$/.test(text))
    throw new Error("Saisissez un montant avec deux décimales maximum.");
  const negative = text.startsWith("-");
  const [whole, fraction = ""] = text
    .replace("-", "")
    .replace(",", ".")
    .split(".");
  const result = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  if (result > 1_000_000_000n)
    throw new Error("Ce montant dépasse la limite autorisée.");
  return Number(result) * (negative ? -1 : 1);
}
export const money = (value: number) =>
  new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: 2,
  }).format(value / 100);
export const decimal = (value: number) =>
  (value / 100).toFixed(2).replace(".", ",");
export const shortDate = (value: string) =>
  new Intl.DateTimeFormat("fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(value + "T12:00:00"));
export const monthLabel = (value: string) =>
  new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric" }).format(
    new Date(value + "-01T12:00:00"),
  );
export const frequencyLabel: Record<string, string> = {
  MONTHLY: "Chaque mois",
  WEEKLY: "Chaque semaine",
  EVERY_2_WEEKS: "Toutes les 2 semaines",
  QUARTERLY: "Chaque trimestre",
  YEARLY: "Chaque année",
  MANUAL: "Nombre défini par mois",
};
