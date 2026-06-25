/**
 * useFocusTrap — модальная фокус-механика для диалогов (a11y).
 *
 * При маунте:
 *   • запоминает элемент, у которого был фокус (чтобы вернуть его при закрытии);
 *   • переводит фокус внутрь диалога (первый интерактивный элемент, иначе сам контейнер).
 * Пока диалог открыт:
 *   • Tab/Shift+Tab не выпускают фокус за пределы контейнера (циклический трап).
 * При анмаунте:
 *   • возвращает фокус туда, где он был до открытия.
 *
 * Escape/скролл-лок остаются на стороне модалки/шелла — здесь только фокус.
 * Контейнер желательно сделать программно-фокусируемым (`tabindex="-1"`),
 * чтобы фокус было куда поставить, если внутри ещё нет интерактивных элементов
 * (например, во время загрузки).
 *
 * Использование (модалка-компонент, монтируется при открытии):
 *   const dialogEl = ref<HTMLElement | null>(null);
 *   useFocusTrap(dialogEl);
 *   // <div ref="dialogEl" tabindex="-1" role="dialog"> … </div>
 *
 * Использование (панель через v-if внутри всегда-смонтированного компонента):
 *   const panelEl = ref<HTMLElement | null>(null);
 *   const open = ref(false);
 *   useFocusTrap(panelEl, open);   // трап активен, пока open === true
 */
import { onBeforeUnmount, onMounted, nextTick, watch, type Ref } from "vue";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type=hidden])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

export function useFocusTrap(
  container: Ref<HTMLElement | null>,
  active?: Ref<boolean>,
): void {
  let prevActive: HTMLElement | null = null;
  let listening = false;

  function focusables(): HTMLElement[] {
    const el = container.value;
    if (!el) return [];
    return Array.from(el.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
      (e) => e.offsetWidth > 0 || e.offsetHeight > 0 || e === document.activeElement,
    );
  }

  function onKeydown(e: KeyboardEvent): void {
    if (e.key !== "Tab") return;
    const el = container.value;
    if (!el) return;
    const items = focusables();
    const active = document.activeElement as HTMLElement | null;
    // Фокус ушёл за пределы (или некуда) — вернуть внутрь.
    if (!items.length) {
      e.preventDefault();
      el.focus();
      return;
    }
    const first = items[0];
    const last = items[items.length - 1];
    const outside = !active || !el.contains(active);
    if (e.shiftKey) {
      if (outside || active === first) {
        e.preventDefault();
        last.focus();
      }
    } else if (outside || active === last) {
      e.preventDefault();
      first.focus();
    }
  }

  async function activate(): Promise<void> {
    if (listening) return;
    prevActive = (document.activeElement as HTMLElement | null) ?? null;
    await nextTick();
    const items = focusables();
    (items[0] ?? container.value)?.focus?.();
    // capture-фаза: перехватываем Tab раньше, чем он сдвинет фокус.
    document.addEventListener("keydown", onKeydown, true);
    listening = true;
  }

  function deactivate(): void {
    if (!listening) return;
    document.removeEventListener("keydown", onKeydown, true);
    listening = false;
    // Возврат фокуса инициатору открытия (если он ещё в DOM).
    if (prevActive && document.contains(prevActive)) prevActive.focus?.();
  }

  if (active) {
    // Панель через v-if: активируем трап по флагу, а не по маунту компонента.
    watch(active, (v) => { if (v) void activate(); else deactivate(); }, { immediate: true });
  } else {
    // Модалка-компонент: монтируется и размонтируется при открытии/закрытии.
    onMounted(() => { void activate(); });
  }

  onBeforeUnmount(deactivate);
}
