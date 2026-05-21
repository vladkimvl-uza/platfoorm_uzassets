<template>
  <nav class="fm-tabbar">
    <button :class="tabClass('balance')" @click="emit('change', 'balance')">Баланс · НСБУ</button>
    <button :class="tabClass('pl')" @click="emit('change', 'pl')">P&amp;L · НСБУ</button>
    <span class="fm-tab-sep"></span>
    <button :class="tabClass('dash_pl')" @click="emit('change', 'dash_pl')">Dashboard · P&amp;L</button>
    <button :class="tabClass('dash_bs')" @click="emit('change', 'dash_bs')">Dashboard · BS</button>
    <button :class="tabClass('dash_cf')" @click="emit('change', 'dash_cf')">Dashboard · CF</button>
    <span class="fm-tab-sep"></span>
    <button :class="tabClass('macro')" @click="emit('change', 'macro')">Макро</button>
    <button :class="tabClass('checks')" @click="emit('change', 'checks')">Проверки</button>

    <div class="fm-tabbar-right">
      <div class="fm-units">
        <span class="fm-muted">Единицы:</span>
        <select
          class="fm-select"
          :value="unit"
          @change="emit('update:unit', ($event.target as HTMLSelectElement).value as 'thousand' | 'million' | 'billion')"
        >
          <option value="thousand">тыс. сум</option>
          <option value="million">млн</option>
          <option value="billion">млрд</option>
        </select>
      </div>
      <div class="fm-legend">
        <span class="fm-legend-item">
          <span class="fm-swatch fm-swatch-input"></span>
          ввод
        </span>
        <span class="fm-legend-item">
          <span class="fm-swatch fm-swatch-calc"></span>
          расчёт
        </span>
      </div>
    </div>
  </nav>
</template>

<script setup lang="ts">
const props = defineProps<{ active: string; unit: "thousand" | "million" | "billion" }>();
const emit = defineEmits<{
  change: [tab: string];
  "update:unit": [u: "thousand" | "million" | "billion"];
}>();
const tabClass = (id: string) => props.active === id ? "fm-tab fm-tab-on" : "fm-tab fm-tab-off";
</script>

<style scoped>
.fm-tabbar {
  background: #FAFAFC;
  padding: 6px 14px;
  border-bottom: 0.5px solid #F1EFE8;
  display: flex;
  gap: 2px;
  align-items: center;
}
.fm-tab {
  padding: 7px 13px;
  font-size: 11.5px;
  font-family: inherit;
  cursor: pointer;
  border-radius: 8px;
}
.fm-tab-on {
  background: #fff;
  border: 0.5px solid #E5E7EB;
  color: #1E2A4A;
  font-weight: 500;
  box-shadow: 0 1px 2px rgba(0, 0, 0, .04);
}
.fm-tab-off {
  background: transparent;
  border: none;
  color: #888780;
}
.fm-tab-sep {
  width: 1px;
  height: 18px;
  background: #E5E7EB;
  margin: 0 5px;
}
.fm-tabbar-right {
  margin-left: auto;
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 10.5px;
}
.fm-units {
  display: flex;
  gap: 4px;
  align-items: center;
}
.fm-muted { color: #888780; }
.fm-select {
  height: 22px;
  border: 0.5px solid #E5E7EB;
  border-radius: 5px;
  font-size: 10.5px;
  padding: 0 5px;
  outline: none;
  font-family: inherit;
  background: #fff;
}
.fm-legend {
  display: flex;
  gap: 8px;
  align-items: center;
}
.fm-legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #888780;
}
.fm-swatch {
  width: 9px;
  height: 9px;
  border-radius: 2px;
}
.fm-swatch-input {
  background: rgba(55, 138, 221, .15);
  border: 0.5px solid rgba(55, 138, 221, .3);
}
.fm-swatch-calc {
  background: rgba(127, 119, 221, .15);
  border: 0.5px solid rgba(127, 119, 221, .3);
}
</style>
