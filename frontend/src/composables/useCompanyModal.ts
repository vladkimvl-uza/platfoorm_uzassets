import { reactive } from "vue";
import { companiesApi, type CompanyCard, type CompanyEmployee } from "@/api/companies";

/**
 * useCompanyModal — контроллер премиум-модалки профиля компании.
 *
 * Наведение на тикер показывает быструю карточку (useCompanyCard), КЛИК —
 * полноценную модалку: идентичность, сайт, ключевые цифры, сотрудники, переходы.
 * Один глобальный CompanyViewModal в AppShell.
 */
interface ModalState {
  open: boolean;
  loading: boolean;
  code: string | null;
  data: CompanyCard | null;
  preview: Partial<CompanyCard> | null;
  employees: CompanyEmployee[];
}

const state = reactive<ModalState>({
  open: false, loading: false, code: null, data: null, preview: null, employees: [],
});

const cardCache = new Map<string, CompanyCard>();
const empCache = new Map<string, CompanyEmployee[]>();

async function load(code: string) {
  // Карточка
  if (cardCache.has(code)) {
    if (state.code === code) state.data = cardCache.get(code)!;
  } else {
    state.loading = true;
    try {
      const d = await companiesApi.getCard(code);
      cardCache.set(code, d);
      if (state.code === code) state.data = d;
    } catch { /* превью */ }
    finally { if (state.code === code) state.loading = false; }
  }
  // Сотрудники (для аватаров)
  if (empCache.has(code)) {
    if (state.code === code) state.employees = empCache.get(code)!;
  } else {
    try {
      const r = await companiesApi.getEmployees(code);
      empCache.set(code, r.employees);
      if (state.code === code) state.employees = r.employees;
    } catch { /* нет сотрудников */ }
  }
}

function open(code: string, preview?: Partial<CompanyCard> | null) {
  state.code = code;
  state.preview = preview || null;
  state.data = cardCache.get(code) || null;
  state.employees = empCache.get(code) || [];
  state.open = true;
  void load(code);
}

function close() {
  state.open = false;
}

export function useCompanyModal() {
  return { state, open, close };
}
