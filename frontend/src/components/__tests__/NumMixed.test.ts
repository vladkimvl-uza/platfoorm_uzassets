import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import NumMixed from "@/components/NumMixed.vue";

describe("NumMixed", () => {
  it("splits a decimal percent into int / dec / unit parts", () => {
    const w = mount(NumMixed, { props: { value: "87.4%" } });
    expect(w.find(".uza-num-i").text()).toBe("87");
    expect(w.find(".uza-num-d").text()).toBe(".4");
    expect(w.find(".uza-num-u").text()).toBe("%");
  });

  it("renders a plain integer as the bold int part with no dec/unit", () => {
    const w = mount(NumMixed, { props: { value: 1234 } });
    expect(w.find(".uza-num-i").text()).toBe("1234");
    expect(w.find(".uza-num-d").exists()).toBe(false);
    expect(w.find(".uza-num-u").exists()).toBe(false);
  });

  it("renders a non-numeric value verbatim (no parsing)", () => {
    const w = mount(NumMixed, { props: { value: "н/д" } });
    expect(w.text()).toContain("н/д");
    expect(w.find(".uza-num-i").exists()).toBe(false);
  });
});
