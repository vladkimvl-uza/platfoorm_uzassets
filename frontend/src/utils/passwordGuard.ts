/**
 * Глобальная защита от пробела в полях пароля: пароль не может содержать пробел.
 *
 * Один набор листенеров на document покрывает ВСЕ input[type=password]
 * (логин, смена пароля, сброс, инвайт, step-up, SMTP) — текущие и будущие,
 * без правки каждого поля. Защищает от случайного ввода и от вставки.
 */
function isPwdInput(el: EventTarget | null): el is HTMLInputElement {
  return (
    !!el &&
    (el as HTMLElement).tagName === "INPUT" &&
    (el as HTMLInputElement).type === "password"
  );
}

export function installNoSpacePasswordGuard(): void {
  if (typeof document === "undefined") return;

  // 1) Блокируем ввод пробела с клавиатуры — без мерцания значения.
  document.addEventListener(
    "keydown",
    (e) => {
      if ((e.key === " " || e.code === "Space") && isPwdInput(e.target)) {
        e.preventDefault();
      }
    },
    true,
  );

  // 2) Вырезаем пробелы из вставки/автозаполнения/IME. Правим el.value в
  //    capture-фазе — раньше, чем v-model читает event.target.value (bubble),
  //    поэтому модель сразу получает значение без пробелов (без ре-диспатча).
  document.addEventListener(
    "input",
    (e) => {
      const el = e.target;
      if (!isPwdInput(el)) return;
      if (!/\s/.test(el.value)) return;
      const pos = el.selectionStart ?? el.value.length;
      const before = el.value;
      el.value = before.replace(/\s+/g, "");
      const removedBefore = (before.slice(0, pos).match(/\s/g) || []).length;
      const newPos = Math.max(0, pos - removedBefore);
      try {
        el.setSelectionRange(newPos, newPos);
      } catch {
        /* noop */
      }
    },
    true,
  );
}
