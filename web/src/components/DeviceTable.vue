<template>
  <el-card class="card" shadow="never">
    <template #header>
      <div class="cardHeader">
        <div>
          <div class="title">设备列表</div>
          <div class="sub">点击行选择设备</div>
        </div>
        <div class="right">
          <el-tag :type="wsConnected ? 'success' : 'warning'" effect="light">
            WS {{ wsConnected ? 'Connected' : 'Disconnected' }}
          </el-tag>
        </div>
      </div>
    </template>

    <el-table
      :data="rows"
      size="small"
      stripe
      highlight-current-row
      :row-class-name="rowClass"
      @row-click="onRowClick"
    >
      <el-table-column prop="device_id" label="Device ID" min-width="180" />
      <el-table-column label="状态" width="110">
        <template #default="scope">
          <el-tag :type="scope.row.status === 'online' ? 'success' : 'info'" effect="light">
            {{ scope.row.status || 'offline' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最后上报" min-width="190">
        <template #default="scope">
          {{ formatTs(scope.row.lastSeen) }}
        </template>
      </el-table-column>
      <el-table-column label="温度" width="110">
        <template #default="scope">
          {{ valueOrDash(scope.row.temp) }}
        </template>
      </el-table-column>
      <el-table-column label="气压" width="120">
        <template #default="scope">
          {{ valueOrDash(scope.row.pressure) }}
        </template>
      </el-table-column>
      <el-table-column label="光照" width="110">
        <template #default="scope">
          {{ valueOrDash(scope.row.light) }}
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  devices: { type: Array, default: () => [] },
  latestById: { type: Object, default: () => ({}) },
  selectedDeviceId: { type: String, default: null },
  wsConnected: { type: Boolean, default: false },
  formatTs: { type: Function, required: true },
});

const emit = defineEmits(['select']);

function valueOrDash(v) {
  return v === null || v === undefined || v === '' ? '--' : v;
}

function pickEnv(latest) {
  const env = latest?.environment || {};
  const bmp = env.bmp280 || {};
  const light = env.light || {};
  return {
    temp: bmp.temp ?? null,
    pressure: bmp.pressure ?? null,
    light: light.percent ?? null,
    lastSeen: latest?.timestamp || null,
  };
}

const rows = computed(() => {
  return props.devices.map((d) => {
    const latest = props.latestById[d.device_id] || null;
    const env = pickEnv(latest);
    return {
      device_id: d.device_id,
      status: d.status || 'offline',
      lastSeen: env.lastSeen || d.last_seen || null,
      temp: env.temp,
      pressure: env.pressure,
      light: env.light,
    };
  });
});

function onRowClick(row) {
  emit('select', row.device_id);
}

function rowClass({ row }) {
  return row.device_id === props.selectedDeviceId ? 'is-selected-row' : '';
}
</script>

<style scoped>
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
</style>

<style>
.el-table .is-selected-row td {
  background: var(--el-fill-color-light) !important;
}
</style>
