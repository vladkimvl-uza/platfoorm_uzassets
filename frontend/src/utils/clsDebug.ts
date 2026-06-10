/**
 * clsDebug — временный диагностический наблюдатель Layout Instability (CLS).
 *
 * Ловит «подёргивания» интерфейса: при каждом сдвиге без участия пользователя
 * (hadRecentInput=false) пишет в консоль ТОЧНЫЙ элемент, который сдвинулся,
 * его CSS-путь и величину сдвига. Молчит, пока сдвигов нет.
 *
 * Включён по умолчанию (внутренняя платформа). Чтобы отключить:
 *   localStorage.setItem('uza_cls_off', '1')  — и перезагрузить.
 *
 * Удалить после локализации причины джанка.
 */

function cssPath(el: Element | null): string {
  if (!el || !(el instanceof Element)) return "(не-элемент)";
  const parts: string[] = [];
  let node: Element | null = el;
  let depth = 0;
  while (node && node.nodeType === 1 && depth < 5) {
    let sel = node.tagName.toLowerCase();
    if (node.id) { sel += `#${node.id}`; parts.unshift(sel); break; }
    const cls = (node.getAttribute("class") || "")
      .split(/\s+/)
      .filter((c) => c && !c.startsWith("router-link") && !/^v-/.test(c))
      .slice(0, 2)
      .join(".");
    if (cls) sel += `.${cls}`;
    parts.unshift(sel);
    node = node.parentElement;
    depth++;
  }
  return parts.join(" > ");
}

export function initClsDebug(): void {
  try {
    if (localStorage.getItem("uza_cls_off") === "1") return;
  } catch { /* storage off — продолжаем */ }
  if (typeof PerformanceObserver === "undefined") return;
  if (!PerformanceObserver.supportedEntryTypes?.includes("layout-shift")) return;

  let lastLog = 0;
  const obs = new PerformanceObserver((list) => {
    for (const entry of list.getEntries() as any[]) {
      if (entry.hadRecentInput) continue;        // сдвиг по вине пользователя — игнор
      if (entry.value < 0.0008) continue;         // микросдвиги-шум отбрасываем
      const now = performance.now();
      if (now - lastLog < 250) continue;          // троттлинг консоли
      lastLog = now;
      const sources = (entry.sources || [])
        .map((s: any) => cssPath(s.node))
        .filter(Boolean);
      // eslint-disable-next-line no-console
      console.warn(
        `%c[CLS] сдвиг ${entry.value.toFixed(4)}`,
        "color:#E24B4A;font-weight:600",
        "\n  элементы:", sources.length ? sources : "(нет node — обычно текст/псевдоэлемент)",
        "\n  путь:", location.pathname + location.hash,
      );
    }
  });
  try {
    obs.observe({ type: "layout-shift", buffered: true });
    // eslint-disable-next-line no-console
    console.info("%c[CLS] диагностика активна — подёргивания будут логироваться. Отключить: localStorage.uza_cls_off='1'", "color:#7C6FF7");
  } catch { /* type не поддержан */ }
}
