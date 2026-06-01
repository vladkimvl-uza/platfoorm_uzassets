import { describe, it, expect, beforeEach } from "vitest";
import {
  applyTheme,
  initTheme,
  toggleTheme,
  currentTheme,
} from "@/composables/useTheme";

describe("useTheme", () => {
  beforeEach(() => {
    localStorage.removeItem("uza-theme");
    document.documentElement.removeAttribute("data-theme");
    applyTheme("light");
    localStorage.removeItem("uza-theme");
  });

  it("applyTheme sets the data-theme attribute and persists to localStorage", () => {
    applyTheme("dark");
    expect(currentTheme.value).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("uza-theme")).toBe("dark");
  });

  it("toggleTheme flips between light and dark", () => {
    applyTheme("light");
    toggleTheme();
    expect(currentTheme.value).toBe("dark");
    toggleTheme();
    expect(currentTheme.value).toBe("light");
  });

  it("initTheme restores dark from localStorage", () => {
    localStorage.setItem("uza-theme", "dark");
    initTheme();
    expect(currentTheme.value).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("initTheme defaults to light when nothing is stored", () => {
    initTheme();
    expect(currentTheme.value).toBe("light");
  });
});
