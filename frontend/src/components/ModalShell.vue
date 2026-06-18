<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch, nextTick } from "vue";

const props = defineProps<{
  open: boolean;
  title?: string;
  // Размер модалки
  size?: "sm" | "md" | "lg" | "xl" | "full";
  // Закрывать по клику на overlay (default true)
  closeOnOverlay?: boolean;
  // Скрыть кнопку закрытия в шапке
  hideClose?: boolean;
}>();

const emit = defineEmits<{
  (e: "close"): void;
}>();

function handleOverlayClick() {
  if (props.closeOnOverlay !== false) emit("close");
}

function handleEscape(e: KeyboardEvent) {
  if (e.key === "Escape" && props.open) {
    emit("close");
  }
}

const modalRef = ref<HTMLElement | null>(null);
let lastActive: HTMLElement | null = null;

function focusableEls(): HTMLElement[] {
  if (!modalRef.value) return [];
  return Array.from(
    modalRef.value.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
  ).filter((el) => el.offsetParent !== null || el === document.activeElement);
}

function handleTab(e: KeyboardEvent) {
  if (e.key !== "Tab" || !props.open || !modalRef.value) return;
  const els = focusableEls();
  if (els.length === 0) {
    e.preventDefault();
    modalRef.value.focus();
    return;
  }
  const first = els[0];
  const last = els[els.length - 1];
  const active = document.activeElement as HTMLElement | null;
  if (e.shiftKey) {
    if (active === first || !modalRef.value.contains(active)) {
      e.preventDefault();
      last.focus();
    }
  } else {
    if (active === last || !modalRef.value.contains(active)) {
      e.preventDefault();
      first.focus();
    }
  }
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      lastActive = document.activeElement as HTMLElement | null;
      nextTick(() => {
        if (!modalRef.value) return;
        const els = focusableEls();
        (els[0] || modalRef.value).focus();
      });
    } else if (lastActive) {
      lastActive.focus?.();
      lastActive = null;
    }
  }
);

onMounted(() => {
  window.addEventListener("keydown", handleEscape);
  window.addEventListener("keydown", handleTab, true);
  if (props.open) {
    lastActive = document.activeElement as HTMLElement | null;
    nextTick(() => {
      if (!modalRef.value) return;
      const els = focusableEls();
      (els[0] || modalRef.value).focus();
    });
  }
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleEscape);
  window.removeEventListener("keydown", handleTab, true);
});
</script>

<template>
  <Teleport to="body">
    <Transition name="uza-fade">
      <div v-if="open" class="uza-modal-ov" @click.self="handleOverlayClick">
        <div ref="modalRef" class="uza-modal" :class="`size-${size || 'md'}`"
             role="dialog" aria-modal="true" tabindex="-1"
             :aria-label="title || undefined">
          <header v-if="title || $slots.header || !hideClose" class="uza-modal-h">
            <div class="uza-modal-h-l">
              <slot name="header">
                <h2 v-if="title" class="uza-modal-title">{{ title }}</h2>
              </slot>
            </div>
            <button v-if="!hideClose" type="button" class="uza-modal-close"
                    @click="emit('close')" aria-label="Закрыть">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </header>

          <div class="uza-modal-b">
            <slot></slot>
          </div>

          <footer v-if="$slots.footer" class="uza-modal-f">
            <slot name="footer"></slot>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.uza-modal-ov {
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 40, 0.45);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9990;
  padding: 24px;
}

.uza-modal {
  background: var(--bg1, #fff);
  border-radius: 16px;
  width: min(960px, 96vw);
  max-height: 92vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.18),
              0 8px 24px rgba(15, 23, 60, 0.08);
}

.size-sm { width: min(420px, 96vw); }
.size-md { width: min(640px, 96vw); }
.size-lg { width: min(960px, 96vw); }
.size-xl { width: min(1280px, 96vw); }
.size-full { width: 96vw; height: 92vh; }

.uza-modal-h {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 22px;
  border-bottom: 1px solid var(--border1, #F1F5F9);
  flex-shrink: 0;
  gap: 16px;
}
.uza-modal-h-l {
  flex: 1;
  min-width: 0;
}
.uza-modal-title {
  margin: 0;
  font-size: 15px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--t1, #1E2A4A);
}
.uza-modal-close {
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 6px;
  border-radius: 6px;
  color: var(--t3, var(--t3));
  transition: background 0.12s, color 0.12s;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.uza-modal-close:hover {
  background: var(--bg3, #F1F5F9);
  color: var(--t1, #1E2A4A);
}

.uza-modal-b {
  padding: 22px;
  overflow-y: auto;
  flex: 1;
}

.uza-modal-f {
  padding: 14px 22px;
  border-top: 1px solid var(--border1, #F1F5F9);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  background: var(--bg2, #FAFBFC);
  flex-shrink: 0;
}

/* Animations — точно из легасиа (uzaModalIn .45s var(--ease-standard)) */
.modal-enter-active .uza-modal,
.modal-leave-active .uza-modal {
  transition: opacity 0.3s, transform 0.45s var(--ease-standard);
}
.modal-enter-from .uza-modal {
  opacity: 0;
  transform: scale(0.95) translateY(20px);
}
.modal-leave-to .uza-modal {
  opacity: 0;
  transform: scale(0.97) translateY(8px);
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.25s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
</style>
