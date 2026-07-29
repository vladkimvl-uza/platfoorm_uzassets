// useEntityEditor — глобальная модалка редактора задачи/проекта.
//
// Назначение: открывать задачу/проект ПОВЕРХ текущей страницы (из клика по
// уведомлению, drill-модалей и т.п.) — без навигации на список /tasks.
// Раньше уведомление вело на /tasks?open=<id>, что выкидывало пользователя
// на полный список задач. Теперь TaskProjectEditor (self-contained fixed
// overlay) монтируется глобально в AppShell и управляется этим синглтоном.
//
// Хост-компонент: components/GlobalEntityEditor.vue (рендерит редактор).
// Интерсепторы ссылок: NotificationBell.vue / NotificationToast.vue вызывают
// openFromLink(link) и, если ссылка ведёт на задачу/проект, открывают модалку
// вместо router.push.
import { reactive } from "vue";
import { api } from "@/api/client";
import { t } from "@/locale/i18n";


type Kind = "task" | "project";

interface EntityEditorState {
  open: boolean;
  kind: Kind;
  entity: any | null;
  loading: boolean;
  error: string;
  // create-режим (создание задачи/проекта с предзаполненными полями)
  mode: "view" | "create";
  createDue: string | null;       // YYYY-MM-DD — дедлайн при создании из календаря
  createCompanyId: string | null; // контекст компании при создании
}

const state = reactive<EntityEditorState>({
  open: false,
  kind: "task",
  entity: null,
  loading: false,
  error: "",
  mode: "view",
  createDue: null,
  createCompanyId: null,
});

// Создание новой задачи/проекта с предзаполненным дедлайном и компанией
// (из клика по дню в календаре). entity остаётся null → редактор в create-режиме.
function createEntity(kind: Kind, opts?: { due?: string | null; companyId?: string | null }): void {
  state.kind = kind;
  state.mode = "create";
  state.entity = null;
  state.loading = false;
  state.error = "";
  state.createDue = opts?.due || null;
  state.createCompanyId = opts?.companyId || null;
  state.open = true;
}

async function openEntity(kind: Kind, id: string): Promise<void> {
  state.kind = kind;
  state.mode = "view";
  state.createDue = null;
  state.createCompanyId = null;
  state.open = true;
  state.loading = true;
  state.error = "";
  state.entity = null;
  try {
    const url = kind === "project" ? `/projects/${id}` : `/tasks/${id}`;
    const { data } = await api.get(url);
    state.entity = data;
  } catch (e: any) {
    state.error =
      e?.response?.data?.detail || e?.message || t('Не удалось загрузить запись');
  } finally {
    state.loading = false;
  }
}

function close(): void {
  state.open = false;
  state.entity = null;
  state.error = "";
  state.mode = "view";
  state.createDue = null;
  state.createCompanyId = null;
}

/**
 * Распарсить ссылку уведомления и, если она ведёт на задачу/проект, открыть
 * глобальную модалку. Возвращает true, если ссылка обработана (навигация не
 * нужна). Понимает форматы:
 *   /tasks/<id>          /projects/<id>
 *   /tasks?open=<id>     /projects?open=<id>
 *   /tasks?task=<id>
 */
function openFromLink(link: string | null | undefined): boolean {
  if (!link) return false;
  const m = link.match(
    /^\/(tasks|projects)(?:\/([^/?#]+)|\/?\?(?:[^#]*&)?(?:open|task|project)=([^&#]+))/,
  );
  if (!m) return false;
  const id = decodeURIComponent(m[2] || m[3] || "");
  if (!id) return false;
  const kind: Kind = m[1] === "projects" ? "project" : "task";
  void openEntity(kind, id);
  return true;
}

export function useEntityEditor() {
  return {
    state,
    openTask: (id: string) => openEntity("task", id),
    openProject: (id: string) => openEntity("project", id),
    createTask: (opts?: { due?: string | null; companyId?: string | null }) => createEntity("task", opts),
    createProject: (opts?: { due?: string | null; companyId?: string | null }) => createEntity("project", opts),
    openFromLink,
    close,
  };
}
