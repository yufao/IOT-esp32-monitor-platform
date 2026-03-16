<template>
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
              <div class="title">历史回放</div>
              <div class="sub">从 SQLite 拉取历史并填充曲线</div>
            </div>
          </div>
        </template>

        <div class="historyRow">
          <el-date-picker
            v-model="historyRange"
            type="datetimerange"
            range-separator="→"
            start-placeholder="开始"
            end-placeholder="结束"
            format="YYYY-MM-DD HH:mm"
            style="width: 100%"
          />
          <el-button type="primary" :loading="historyLoading" @click="loadHistory">加载历史</el-button>
        </div>
      </el-card>

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

      <el-card class="card" shadow="never" style="margin-top: 12px;">
        <template #header>
          <div class="cardHeader">
            <div>
              <div class="title">配置参数</div>
              <div class="sub">展示并下发阈值 / 采样周期</div>
            </div>
            <el-button
              type="primary"
              plain
              :disabled="!selectedDeviceId"
              @click="goDevice"
            >
              进入设备页
            </el-button>
          </div>
        </template>

        <el-empty v-if="!selectedDevice" description="请先在左侧选择设备" />

        <div v-else>
          <div class="kvGrid">
            <div class="kv">
              <div class="k">设备</div>
              <div class="v">{{ selectedDevice.device_id }}</div>
            </div>
            <div class="kv">
              <div class="k">状态</div>
              <div class="v">
                <el-tag size="small" effect="light" :type="selectedDevice.status === 'online' ? 'success' : 'info'">
                  {{ selectedDevice.status || 'offline' }}
                </el-tag>
              </div>
            </div>
          </div>

          <el-divider style="margin: 12px 0;" />

          <el-form :model="draft" label-width="110px" size="default">
            <el-form-item label="温度上限">
              <el-input-number v-model="draft.temp_high" :step="0.5" :precision="1" style="width: 100%" />
            </el-form-item>
            <el-form-item label="温度下限">
              <el-input-number v-model="draft.temp_low" :step="0.5" :precision="1" style="width: 100%" />
            </el-form-item>
            <el-form-item label="采样周期(s)">
              <el-input-number v-model="draft.sample_interval_sec" :min="1" :max="3600" style="width: 100%" />
            </el-form-item>

            <el-form-item label="最后回执">
              <div class="ackRow">
                <el-tag v-if="lastAck" size="small" effect="light" :type="lastAck.ok ? 'success' : 'danger'">
                  {{ lastAck.ok ? 'OK' : 'FAIL' }}
                </el-tag>
                <span class="ackText">{{ lastAckText }}</span>
              </div>
            </el-form-item>

            <el-form-item>
              <el-button
                type="primary"
                :loading="sendingThreshold"
                :disabled="!canSend"
                @click="sendThreshold"
              >
                下发阈值
              </el-button>
              <el-button
                type="primary"
                plain
                :loading="sendingInterval"
                :disabled="!canSend"
                @click="sendInterval"
              >
                下发采样周期
              </el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { useRouter } from 'vue-router';

import DeviceTable from '../components/DeviceTable.vue';
import TelemetryChart from '../components/TelemetryChart.vue';

import { useMonitorStore } from '../stores/monitor';
import { sendCommand } from '../api/rest';

const router = useRouter();
const store = useMonitorStore();

const historyLoading = ref(false);
const historyRange = ref(null);

const devices = computed(() => store.devicesList);
const latestById = computed(() => store.latestById);
const selectedDeviceId = computed(() => store.selectedDeviceId);
const selectedSeries = computed(() => store.selectedSeries);
const wsConnected = computed(() => store.wsConnected);
const lastMsgText = computed(() => store.lastMsgText);
const formatTs = store.formatTs;

const selectedDevice = computed(() => store.selectedDevice);

const sendingThreshold = ref(false);
const sendingInterval = ref(false);

const draft = ref({
  temp_high: null,
  temp_low: null,
  sample_interval_sec: null,
});

function readCfgFromSelected() {
  const cfg = selectedDevice.value?.capabilities?.config || {};
  draft.value = {
    temp_high: cfg.temp_high ?? null,
    temp_low: cfg.temp_low ?? null,
    sample_interval_sec: cfg.sample_interval_sec ?? null,
  };
}

watch(
  () => selectedDeviceId.value,
  () => {
    readCfgFromSelected();
  },
  { immediate: true },
);

watch(
  () => selectedDevice.value?.capabilities?.config,
  () => {
    readCfgFromSelected();
  },
  { deep: true },
);

const lastAck = computed(() => {
  const id = selectedDeviceId.value;
  if (!id) return null;
  return store.lastCommandByDeviceId[id]?.ack || null;
});

const lastAckText = computed(() => {
  if (!lastAck.value) return '—';
  if (!lastAck.value.ok) return String(lastAck.value.error || 'error');
  const cmd = lastAck.value.command || {};
  const t = cmd.type;
  if (t === 'set_threshold') return `阈值已应用 (high=${cmd.temp_high}, low=${cmd.temp_low})`;
  if (t === 'set_sample_interval') return `采样周期已应用 (${cmd.sample_interval_sec}s)`;
  return '已应用';
});

const canSend = computed(() => selectedDeviceId.value && selectedDevice.value?.status === 'online');

function onSelect(deviceId) {
  store.setSelected(deviceId);
}

async function loadHistory() {
  if (!store.selectedDeviceId) {
    ElMessage.warning('请先选择设备');
    return;
  }

  let sinceTs;
  let untilTs;
  if (Array.isArray(historyRange.value) && historyRange.value.length === 2) {
    const [s, e] = historyRange.value;
    if (s instanceof Date && !Number.isNaN(s.getTime())) sinceTs = Math.floor(s.getTime() / 1000);
    if (e instanceof Date && !Number.isNaN(e.getTime())) untilTs = Math.floor(e.getTime() / 1000);
  }

  historyLoading.value = true;
  try {
    const count = await store.loadHistory({
      deviceId: store.selectedDeviceId,
      sinceTs: sinceTs || null,
      untilTs: untilTs || null,
      limit: 800,
    });
    ElMessage.success(`已加载历史点数：${count}`);
  } catch (e) {
    ElMessage.error(String(e));
  } finally {
    historyLoading.value = false;
  }
}

function goDevice() {
  const id = selectedDeviceId.value;
  if (!id) return;
  router.push({ name: 'device', params: { id } });
}

async function sendThreshold() {
  if (!canSend.value) return;
  if (draft.value.temp_high === null || draft.value.temp_low === null) {
    ElMessage.warning('请先填写温度上限/下限');
    return;
  }
  sendingThreshold.value = true;
  try {
    const r = await sendCommand({
      deviceId: selectedDeviceId.value,
      command: {
        type: 'set_threshold',
        temp_high: draft.value.temp_high,
        temp_low: draft.value.temp_low,
      },
    });
    ElMessage.success(`命令已下发：${r.cmd_id}`);
  } catch (e) {
    ElMessage.error(String(e));
  } finally {
    sendingThreshold.value = false;
  }
}

async function sendInterval() {
  if (!canSend.value) return;
  if (draft.value.sample_interval_sec === null) {
    ElMessage.warning('请先填写采样周期');
    return;
  }
  sendingInterval.value = true;
  try {
    const r = await sendCommand({
      deviceId: selectedDeviceId.value,
      command: {
        type: 'set_sample_interval',
        sample_interval_sec: draft.value.sample_interval_sec,
      },
    });
    ElMessage.success(`命令已下发：${r.cmd_id}`);
  } catch (e) {
    ElMessage.error(String(e));
  } finally {
    sendingInterval.value = false;
  }
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
.historyRow {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  align-items: center;
}
.pre {
  margin: 0;
  padding: 10px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.35;
  max-height: 240px;
  overflow: auto;
}
.kvGrid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.kv {
  padding: 10px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
}
.k {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.v {
  margin-top: 4px;
  font-weight: 600;
}
.ackRow {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ackText {
  font-size: 12px;
  color: var(--el-text-color-regular);
}
</style>
