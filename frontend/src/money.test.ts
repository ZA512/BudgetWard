import { describe, expect, it } from "vitest";
import { cents } from "./money";

describe("montants monétaires exacts", () => {
  it("gère les virgules, espaces français et débits sans erreur de float", () => {
    expect(cents("1 350,27")).toBe(135027);
    expect(cents("-161,50")).toBe(-16150);
    expect(cents("0.29")).toBe(29);
  });
  it.each(["", "1,001", "1e3", "NaN", "1.234,56", "10000001"])(
    "refuse %s",
    (value) => {
      expect(() => cents(value)).toThrow();
    },
  );
});
