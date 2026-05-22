// frontend/src/composables/useAiPageContext.ts
//
// Pack 7.9e: per-page context registry for the floating AiBubble widget.
// Каждая страница (Dashboard/ExecDash/BP/Credit/Invest/etc) регистрирует
// свой PageContext при mount → AiBubble знает что показать в quick-actions
// и какой автопромпт собрать для «Сводка страницы».
//
// Usage в Vue view:
//   useAiPageContext({
//     key: "bp",
//     label: "Бизнес-план",
//     describeState: () => `Год ${year.value}, линза ${lens.value}`,
//     quickActions: [
//       { label: "Сводка по плану/факту", prompt: "Дай сводку..." },
//       { label: "Где провал?", prompt: "Найди ..." },
//     ],
//   });

import { ref, onMounted, onBeforeUnmount, computed } from "vue";

export interface PageQuickAction {
  label: string;
  prompt: string;        // Готовый промпт, который пойдёт в чат как user message
  icon?: string;         // Optional emoji/icon hint
}

export interface PageContext {
  key: string;
  label: string;
  describeState?: () => string;          // Один абзац о текущем состоянии страницы
  quickActions: PageQuickAction[];
}

const _activeStack = ref<PageContext[]>([]);

export function useAiPageContext(ctx: PageContext): void {
  onMounted(() => {
    _activeStack.value = [..._activeStack.value, ctx];
  });
  onBeforeUnmount(() => {
    _activeStack.value = _activeStack.value.filter((c) => c.key !== ctx.key);
  });
}

export function getCurrentPageContext() {
  // Top of stack = most recently mounted route
  return computed<PageContext | null>(() =>
    _activeStack.value.length > 0 ? _activeStack.value[_activeStack.value.length - 1] : null,
  );
}

/** Build the auto-prompt for the "Сводка страницы" button — combines page label
 *  with describeState() output, framed как explicit request to AI. */
export function buildSummaryPrompt(ctx: PageContext): string {
  const state = ctx.describeState ? ctx.describeState() : "";
  const stateLine = state ? `Текущее состояние: ${state}.` : "";
  return [
    `Я нахожусь на странице «${ctx.label}» платформы UzAssets.`,
    stateLine,
    "Дай сжатую аналитическую сводку: ключевые цифры, главные риски, " +
      "что требует внимания. Используй tools чтобы подтянуть актуальные данные. " +
      "Структурируй как: ▶ Что вижу / ▶ Что значит / ▶ Что делать.",
  ].filter(Boolean).join(" ");
}
