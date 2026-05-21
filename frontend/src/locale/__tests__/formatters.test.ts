/**
 * Locale formatter tests. Run with:
 *   cd frontend && npx vitest run src/locale/__tests__/
 *
 * If vitest is not installed yet:
 *   npm i -D vitest @vitest/ui
 */
import { describe, it, expect } from "vitest";
import {
  fmtNumber, fmtNumberCompact, fmtPercent,
  fmtMoney, fmtMoneyCompact,
  fmtDate, fmtDateNumeric, fmtTime, fmtDateTime, fmtRelativeTime,
} from "../index";

// thin no-break space used as thousand separator in ru/uz Intl output
const TS = " ";

describe("fmtNumber", () => {
  it("formats with thin-space in ru", () => {
    expect(fmtNumber(62480000, "ru")).toBe(`62${TS}480${TS}000`);
  });
  it("formats with comma in en", () => {
    expect(fmtNumber(62480000, "en")).toBe("62,480,000");
  });
  it("respects decimals", () => {
    expect(fmtNumber(1234.5, "ru", { decimals: 2 })).toBe(`1${TS}234,50`);
    expect(fmtNumber(1234.5, "en", { decimals: 2 })).toBe("1,234.50");
  });
  it("returns dash for null/NaN", () => {
    expect(fmtNumber(null, "ru")).toBe("—");
    expect(fmtNumber(NaN, "ru")).toBe("—");
    expect(fmtNumber(undefined, "ru")).toBe("—");
  });
});

describe("fmtMoney", () => {
  it("formats UZS in ru", () => {
    expect(fmtMoney(62480000, "ru", "UZS")).toBe(`62${TS}480${TS}000 сум`);
  });
  it("formats UZS in uz-latn", () => {
    expect(fmtMoney(62480000, "uz-latn", "UZS")).toBe(`62${TS}480${TS}000 soʻm`);
  });
  it("formats UZS in uz-cyr", () => {
    expect(fmtMoney(62480000, "uz-cyr", "UZS")).toBe(`62${TS}480${TS}000 сўм`);
  });
  it("formats UZS in en", () => {
    expect(fmtMoney(62480000, "en", "UZS")).toBe("62,480,000 UZS");
  });
  it("uses USD symbol when useSymbol=true and en", () => {
    expect(fmtMoney(1200, "en", "USD", { useSymbol: true })).toBe("$1,200.00");
  });
  it("uses USD symbol postfixed for ru", () => {
    expect(fmtMoney(1200, "ru", "USD", { useSymbol: true })).toBe(`1${TS}200,00 $`);
  });
  it("returns dash for null", () => {
    expect(fmtMoney(null, "ru", "UZS")).toBe("—");
  });
});

describe("fmtMoneyCompact", () => {
  it("billions UZS in ru", () => {
    expect(fmtMoneyCompact(62480000000, "ru", "UZS")).toBe("62,48 млрд сум");
  });
  it("billions UZS in uz-latn", () => {
    expect(fmtMoneyCompact(62480000000, "uz-latn", "UZS")).toBe("62,48 mlrd soʻm");
  });
  it("billions UZS in en", () => {
    expect(fmtMoneyCompact(62480000000, "en", "UZS")).toBe("62.48 B UZS");
  });
  it("USD billions in en uses prefix symbol", () => {
    expect(fmtMoneyCompact(1_200_000_000, "en", "USD")).toBe("$1.20B");
  });
  it("trillions UZS in ru", () => {
    expect(fmtMoneyCompact(93_500_000_000_000, "ru", "UZS")).toBe("93,50 трлн сум");
  });
  it("negative number keeps sign", () => {
    expect(fmtMoneyCompact(-1_500_000_000, "ru", "UZS")).toBe("-1,50 млрд сум");
  });
});

describe("fmtNumberCompact", () => {
  it("billions in ru", () => {
    expect(fmtNumberCompact(2_300_000_000, "ru")).toBe("2,30 млрд");
  });
  it("millions in en", () => {
    expect(fmtNumberCompact(5_400_000, "en")).toBe("5.40 M");
  });
});

describe("fmtPercent", () => {
  it("space before % in ru/uz", () => {
    expect(fmtPercent(94.3, "ru")).toBe("94,3 %");
    expect(fmtPercent(94.3, "uz-latn")).toBe("94,3 %");
    expect(fmtPercent(94.3, "uz-cyr")).toBe("94,3 %");
  });
  it("no space in en", () => {
    expect(fmtPercent(94.3, "en")).toBe("94.3%");
  });
  it("signed=true shows plus sign for positive", () => {
    expect(fmtPercent(5.2, "ru", { signed: true })).toBe("+5,2 %");
  });
});

describe("fmtDate", () => {
  const d = new Date("2026-03-14T14:32:00+05:00");
  it("ru short", () => {
    expect(fmtDate(d, "ru")).toMatch(/14[ ]?мар[\w. ]*2026/);
  });
  it("en short", () => {
    expect(fmtDate(d, "en")).toMatch(/Mar.+14.+2026/);
  });
  it("includes year by default", () => {
    expect(fmtDate(d, "ru")).toMatch(/2026/);
  });
  it("can skip year", () => {
    expect(fmtDate(d, "ru", { includeYear: false })).not.toMatch(/2026/);
  });
  it("returns dash on null", () => {
    expect(fmtDate(null, "ru")).toBe("—");
  });
});

describe("fmtDateNumeric", () => {
  const d = new Date("2026-03-14T14:32:00+05:00");
  it("ru format", () => {
    expect(fmtDateNumeric(d, "ru")).toMatch(/14\.03\.2026/);
  });
  it("en format", () => {
    expect(fmtDateNumeric(d, "en")).toMatch(/03\/14\/2026/);
  });
});

describe("fmtTime", () => {
  const d = new Date("2026-03-14T09:32:00Z");  // 14:32 in Tashkent (UTC+5)
  it("24h in ru", () => {
    expect(fmtTime(d, "ru")).toBe("14:32");
  });
  it("12h in en", () => {
    expect(fmtTime(d, "en")).toMatch(/2:32/);
  });
});

describe("fmtRelativeTime", () => {
  it("uz-latn past hour", () => {
    const d = new Date(Date.now() - 2 * 3600_000);
    expect(fmtRelativeTime(d, "uz-latn")).toMatch(/2 soat oldin/);
  });
  it("uz-cyr future day", () => {
    const d = new Date(Date.now() + 3 * 86_400_000);
    expect(fmtRelativeTime(d, "uz-cyr")).toMatch(/3 кун кейин/);
  });
  it("en past minute", () => {
    const d = new Date(Date.now() - 5 * 60_000);
    expect(fmtRelativeTime(d, "en")).toMatch(/5/);  // exact format depends on Intl backend
  });
});
