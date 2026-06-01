// Глобальный setup для vitest. Некоторые версии jsdom поставляют localStorage
// без рабочих Storage-методов — ставим минимальный in-memory polyfill, чтобы
// тесты, проверяющие персист (useTheme и т.п.), работали детерминированно.

class MemStorage implements Storage {
  private m = new Map<string, string>();
  get length(): number {
    return this.m.size;
  }
  clear(): void {
    this.m.clear();
  }
  getItem(key: string): string | null {
    return this.m.has(key) ? (this.m.get(key) as string) : null;
  }
  key(index: number): string | null {
    return Array.from(this.m.keys())[index] ?? null;
  }
  removeItem(key: string): void {
    this.m.delete(key);
  }
  setItem(key: string, value: string): void {
    this.m.set(key, String(value));
  }
}

function ensureStorage(name: "localStorage" | "sessionStorage"): void {
  const g = globalThis as unknown as Record<string, unknown>;
  const cur = g[name] as Storage | undefined;
  if (!cur || typeof cur.setItem !== "function") {
    Object.defineProperty(globalThis, name, {
      value: new MemStorage(),
      writable: true,
      configurable: true,
    });
  }
}

ensureStorage("localStorage");
ensureStorage("sessionStorage");
