<template>
  <header class="company-header">
    <div class="ch-left">
      <div
        class="ch-sector-badge"
        :style="{ background: sectorBg, color: sectorText }"
      >
        {{ sectorAbbr }}
      </div>
      <div class="ch-title-block">
        <a class="ch-eyebrow" @click="$emit('back-to-portfolio')">← Портфель</a>
        <div class="ch-title" :title="company.name">{{ company.name }}</div>
      </div>
    </div>

    <div class="ch-right">
      <span class="ch-pill ch-pill-online">
        <span class="ch-dot ch-dot-green"></span>
        online
      </span>
      <span class="ch-pill ch-pill-year" @click="$emit('year-click')">
        Год: {{ year }}
      </span>
      <button class="ch-btn-ghost" @click="$emit('export-click')">⌃ Экспорт</button>
      <button class="ch-btn-icon" @click="$emit('more-click')" aria-label="Ещё">⋯</button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { SECTOR_META, type SectorId } from './companyNavConfig';

const props = defineProps<{
  company: { name: string; abbr: string; sector: SectorId };
  year: number;
}>();

defineEmits<{
  'back-to-portfolio': [];
  'year-click': [];
  'export-click': [];
  'more-click': [];
}>();

const sectorMeta = computed(() => SECTOR_META[props.company.sector] || SECTOR_META.other);
const sectorBg = computed(() => sectorMeta.value.bg);
const sectorText = computed(() => sectorMeta.value.text);
const sectorAbbr = computed(() => props.company.abbr);
</script>

<style scoped>
.company-header {
  padding: 11px 18px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-bottom: 0.5px solid #F1EFE8;
  background: #fff;
}
.ch-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.ch-sector-badge {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  font-weight: 500;
  flex-shrink: 0;
}
.ch-title-block {
  min-width: 0;
}
.ch-eyebrow {
  font-size: 10px;
  color: #888780;
  letter-spacing: .08em;
  text-transform: uppercase;
  cursor: pointer;
  text-decoration: none;
  display: inline-block;
}
.ch-eyebrow:hover { color: #534AB7; }
.ch-title {
  font-size: 13px;
  font-weight: 500;
  color: #1E2A4A;
  letter-spacing: -.01em;
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 360px;
}
.ch-right {
  margin-left: auto;
  display: flex;
  gap: 6px;
  align-items: center;
  flex-shrink: 0;
}
.ch-pill {
  padding: 4px 9px;
  border-radius: 6px;
  font-size: 10.5px;
  display: flex;
  align-items: center;
  gap: 5px;
  font-weight: 500;
}
.ch-pill-online {
  background: rgba(29, 158, 117, .10);
  color: #0F6E56;
}
.ch-pill-year {
  background: rgba(127, 119, 221, .06);
  color: #534AB7;
  cursor: pointer;
}
.ch-pill-year:hover {
  background: rgba(127, 119, 221, .12);
}
.ch-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.ch-dot-green {
  background: #1D9E75;
  animation: pulseDot 2s infinite;
}
.ch-btn-ghost {
  height: 26px;
  padding: 0 10px;
  background: transparent;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  color: #1E2A4A;
  font-size: 10.5px;
  font-family: inherit;
  cursor: pointer;
  font-weight: 500;
}
.ch-btn-ghost:hover { background: #FAFAFC; }
.ch-btn-icon {
  height: 26px;
  width: 26px;
  background: transparent;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  color: #888780;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
}
.ch-btn-icon:hover { background: #FAFAFC; color: #1E2A4A; }

@keyframes pulseDot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: .5; transform: scale(1.3); }
}
@media (prefers-reduced-motion: reduce) {
  .ch-dot-green { animation: none; }
}
</style>
