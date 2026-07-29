import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";

import {
  describeNotification,
  translateActivityDetail,
} from "@/composables/useNotificationMeta";
import { useLocaleStore } from "@/stores/locale";

describe("localized system activity", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    useLocaleStore().set("en", { sync: false });
  });

  it("translates known activity templates and status values", () => {
    expect(translateActivityDetail("Статус: Новая → Завершено"))
      .toBe("Status: New → Completed");
    expect(translateActivityDetail("Обновлено 12 показателей за 2026"))
      .toBe("Updated 12 indicators for 2026");
  });

  it("preserves unknown persisted text byte-for-byte", () => {
    expect(translateActivityDetail("План")).toBe("План");
    expect(translateActivityDetail("Комментарий директора")).toBe("Комментарий директора");
  });

  it("translates system labels but keeps entity and company names", () => {
    const result = describeNotification({
      type: "owner.activity",
      title: "Финансы: изменение",
      payload: {
        verb: "изменение",
        label: "Финансы",
        entity_title: "План",
        company: "Финансы",
        fields: ["выручка"],
      },
    });

    expect(result.verb).toBe("Modified");
    expect(result.entity).toBe("План · Finance · Финансы");
    expect(result.detail).toEqual({ kind: "text", text: "Changed: revenue" });
  });
});
