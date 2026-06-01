import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import CompanyAvatar from "@/components/CompanyAvatar.vue";

describe("CompanyAvatar", () => {
  it("takes the first letter of each of the first two words", () => {
    const w = mount(CompanyAvatar, { props: { name: "Навоийский ГМК" } });
    expect(w.text()).toBe("НГ");
  });

  it("takes the first two chars of a single-word name", () => {
    const w = mount(CompanyAvatar, { props: { name: "Узбекнефтегаз" } });
    expect(w.text()).toBe("УЗ");
  });

  it("falls back to '?' for an empty name/code", () => {
    const w = mount(CompanyAvatar, { props: { name: "" } });
    expect(w.text()).toBe("?");
  });

  it("applies the sector color through the --co-c CSS variable", () => {
    const w = mount(CompanyAvatar, { props: { name: "A B", color: "#1D9E75" } });
    expect(w.attributes("style")).toContain("#1D9E75");
  });
});
