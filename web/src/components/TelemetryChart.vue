<template>
  <el-card class="card" shadow="never">
    <template #header>
      <div class="cardHeader">
        <div>
          <div class="title">实时曲线</div>
          <div class="sub">{{ deviceId ? `设备：${deviceId}` : '未选择设备' }}</div>
        </div>
        <div class="hint">自动保留最近 ~240 点</div>
      </div>
    </template>

    <div v-if="!deviceId" class="empty">请选择一个设备</div>
    <div v-else ref="el" class="chart"></div>
  </el-card>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import * as echarts from 'echarts';

const props = defineProps({
  deviceId: { type: String, default: null },
  series: { type: Object, default: null },
});

const el = ref(null);
let chart = null;

const safeSeries = computed(() => {
  return props.series || { temp: [], pressure: [], light: [] };
});

function buildOption() {
  const s = safeSeries.value;
  return {
    animation: false,
    tooltip: { trigger: 'axis' },
    legend: { data: ['温度(°C)', '气压(hPa)', '光照(%)'] },
    grid: { left: 48, right: 20, top: 28, bottom: 36 },
    xAxis: {
      type: 'time',
      axisLabel: { hideOverlap: true },
    },
    yAxis: [
      { type: 'value', name: '温度/光照', scale: true },
      { type: 'value', name: '气压', scale: true },
    ],
    series: [
      {
        name: '温度(°C)',
        type: 'line',
        showSymbol: false,
        data: s.temp,
        yAxisIndex: 0,
      },
      {
        name: '光照(%)',
        type: 'line',
        showSymbol: false,
        data: s.light,
        yAxisIndex: 0,
      },
      {
        name: '气压(hPa)',
        type: 'line',
        showSymbol: false,
        data: s.pressure,
        yAxisIndex: 1,
      },
    ],
  };
}

function ensureChart() {
  if (!el.value) return;
  if (!chart) chart = echarts.init(el.value);
}

function render() {
  if (!props.deviceId) return;
  ensureChart();
  if (!chart) return;
  chart.setOption(buildOption(), { notMerge: true, lazyUpdate: true });
}

onMounted(() => {
  ensureChart();
  render();
  window.addEventListener('resize', onResize);
});

function onResize() {
  if (chart) chart.resize();
}

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize);
  if (chart) {
    chart.dispose();
    chart = null;
  }
});

watch(
  () => [props.deviceId, safeSeries.value.temp.length, safeSeries.value.pressure.length, safeSeries.value.light.length],
  () => render(),
);
</script>

<style scoped>
.chart {
  height: 320px;
}
.cardHeader {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.title {
  font-weight: 600;
}
.sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.empty {
  padding: 24px;
  color: var(--el-text-color-secondary);
}
</style>
