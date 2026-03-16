<template>
  <el-container class="root">
    <el-header class="header">
      <div class="brand">
        <div class="name">Smart Lab Sentinel</div>
        <div class="meta">
          <span class="kv"><span class="k">API</span><span class="v">{{ apiBase }}</span></span>
          <span class="kv"><span class="k">WS</span><span class="v">{{ wsUrl }}</span></span>
        </div>
      </div>

      <div class="actions">
        <el-statistic title="设备" :value="totalCount" />
        <el-statistic title="在线" :value="onlineCount" />
        <el-button type="primary" @click="refresh" :loading="refreshing">刷新快照</el-button>
      </div>
    </el-header>

    <el-main class="main">
      <el-row :gutter="12">
        <el-col :xs="24" :lg="14">
          <DeviceTable
            :devices="devices"
            :latestById="latestById"
            :selectedDeviceId="selectedDeviceId"
            :wsConnected="wsConnected"
            :formatTs="formatTs"
            @select="onSelect"
          />
        </el-col>
        <el-col :xs="24" :lg="10">
          <TelemetryChart :deviceId="selectedDeviceId" :series="selectedSeries" />

          <el-card class="card" shadow="never" style="margin-top: 12px;">
            <template #header>
              <div class="cardHeader">
                <div>
                  <div class="title">最近消息</div>
                  <div class="sub">用于联调与协议演进</div>
                </div>
                <el-tag effect="light" :type="wsConnected ? 'success' : 'warning'">
                  {{ wsConnected ? '实时推送中' : '等待连接' }}
                </el-tag>
              </div>
            </template>
            <pre class="pre">{{ lastMsgText }}</pre>
          </el-card>
        </el-col>
      </el-row>
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { ElMessage } from 'element-plus';

import { getApiBase, getWsDashboardUrl } from './env';
import { fetchSnapshot } from './api/rest';
import { connectDashboardWs } from './ws/dashboard';
import { useMonitorStore } from './stores/monitor';

import DeviceTable from './components/DeviceTable.vue';
import TelemetryChart from './components/TelemetryChart.vue';

const store = useMonitorStore();

const apiBase = getApiBase();
const wsUrl = getWsDashboardUrl();

const refreshing = ref(false);
let wsConn = null;

const devices = computed(() => store.devicesList);
const latestById = computed(() => store.latestById);
const selectedDeviceId = computed(() => store.selectedDeviceId);
const selectedSeries = computed(() => store.selectedSeries);
const wsConnected = computed(() => store.wsConnected);
const lastMsgText = computed(() => store.lastMsgText);

const totalCount = computed(() => store.totalCount);
const onlineCount = computed(() => store.onlineCount);
const formatTs = store.formatTs;

function onSelect(deviceId) {
  store.setSelected(deviceId);
}

async function refresh() {
  refreshing.value = true;
  try {
    const snap = await fetchSnapshot();
    store.applySnapshot(snap);
  } catch (e) {
    ElMessage.error(String(e));
  } finally {
    refreshing.value = false;
  }
}

function handleWsMessage(text) {
  store.setLastMsg(text);
  let msg;
  try {
    msg = JSON.parse(text);
  } catch {
    return;
  }

  if (msg.type === 'snapshot') {
    store.applySnapshot({ devices: msg.devices || [], latest: msg.latest || [] });
    return;
  }

  if (msg.type === 'telemetry') {
    // server 直接广播 record（含 type=telemetry + device_id + environment...）
    store.applyTelemetry(msg);
    return;
  }

  if (msg.type === 'device_status') {
    // server 当前实现是平铺字段（type/device_id/status/last_seen）
    store.applyDeviceStatus({
      device_id: msg.device_id || msg.data?.device_id,
      status: msg.status || msg.data?.status,
      last_seen: msg.last_seen || msg.data?.last_seen,
    });
  }
}

onMounted(async () => {
  await refresh();

  wsConn = connectDashboardWs({
    onOpen({ url }) {
      store.setWsStatus(true, url);
    },
    onClose() {
      store.setWsStatus(false);
    },
    onError() {
      store.setWsStatus(false);
    },
    onMessage(text) {
      handleWsMessage(text);
    },
  });
});

onBeforeUnmount(() => {
  if (wsConn) wsConn.close();
  wsConn = null;
});
</script>

<style scoped>
.root {
  min-height: 100vh;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.brand {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.name {
  font-weight: 700;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.kv {
  display: inline-flex;
  gap: 6px;
}
.k {
  color: var(--el-text-color-secondary);
}
.v {
  color: var(--el-text-color-regular);
}
.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.main {
  padding-top: 12px;
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
.pre {
  margin: 0;
  font-size: 12px;
  line-height: 1.4;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  max-height: 220px;
  overflow: auto;
}
</style>
