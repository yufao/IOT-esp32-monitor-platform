<template>
  <el-row :gutter="12">
    <el-col :xs="24" :lg="14">
      <el-card class="card" shadow="never">
        <template #header>
          <div class="cardHeader">
            <div>
              <div class="title">设备详情</div>
              <div class="sub">信息 / 参数 / 配置</div>
            </div>
            <div class="right">
              <el-button @click="goHome">返回首页</el-button>
            </div>
          </div>
        </template>

        <el-empty v-if="!device" description="设备不存在或尚未上报" />

        <div v-else>
          <div class="kvGrid">
            <div class="kv">
              <div class="k">Device ID</div>
              <div class="v">{{ device.device_id }}</div>
            </div>
            <div class="kv">
              <div class="k">状态</div>
              <div class="v">
                <el-tag size="small" effect="light" :type="device.status === 'online' ? 'success' : 'info'">
                  {{ device.status || 'offline' }}
                </el-tag>
              </div>
            </div>
            <div class="kv">
              <div class="k">最后上报</div>
              <div class="v">{{ formatTs(device.last_seen) }}</div>
            </div>
            <div class="kv">
              <div class="k">固件</div>
              <div class="v">{{ device.firmware_version || '--' }}</div>
            </div>
          </div>

          <el-divider style="margin: 12px 0;" />

          <div class="sectionTitle">最新采集</div>
          <div class="kvGrid">
            <div class="kv">
              <div class="k">温度</div>
              <div class="v">{{ valueOrDash(latestTemp) }}</div>
            </div>
            <div class="kv">
              <div class="k">气压</div>
              <div class="v">{{ valueOrDash(latestPressure) }}</div>
            </div>
            <div class="kv">
              <div class="k">光照</div>
              <div class="v">{{ valueOrDash(latestLight) }}</div>
            </div>
            <div class="kv">
              <div class="k">时间戳</div>
              <div class="v">{{ formatTs(latest?.timestamp) }}</div>
            </div>
          </div>
        </div>
      </el-card>
    </el-col>

    <el-col :xs="24" :lg="10">
      <el-card class="card" shadow="never">
        <template #header>
          <div class="cardHeader">
            <div>
              <div class="title">配置下发</div>
              <div class="sub">set_threshold / set_sample_interval</div>
            </div>
          </div>
        </template>

        <el-empty v-if="!device" description="请选择有效设备" />

        <div v-else>
          <el-form :model="draft" label-width="110px">
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

      <el-card class="card" shadow="never" style="margin-top: 12px;">
        <template #header>
          <div class="cardHeader">
            <div>
              <div class="title">最近消息</div>
              <div class="sub">沿用 dashboard WS</div>
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
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';

import { useMonitorStore } from '../stores/monitor';
import { sendCommand } from '../api/rest';

const props = defineProps({
  id: { type: String, required: true },
});

const router = useRouter();
const store = useMonitorStore();

const wsConnected = computed(() => store.wsConnected);
const lastMsgText = computed(() => store.lastMsgText);
const formatTs = store.formatTs;

const device = computed(() => store.devicesById[props.id] || null);
const latest = computed(() => store.latestById[props.id] || null);

function valueOrDash(v) {
  return v === null || v === undefined || v === '' ? '--' : v;
}

const latestTemp = computed(() => latest.value?.environment?.bmp280?.temp ?? null);
const latestPressure = computed(() => latest.value?.environment?.bmp280?.pressure ?? null);
const latestLight = computed(() => latest.value?.environment?.light?.percent ?? null);

const sendingThreshold = ref(false);
const sendingInterval = ref(false);

const draft = ref({
  temp_high: null,
  temp_low: null,
  sample_interval_sec: null,
});

function readCfg() {
  const cfg = device.value?.capabilities?.config || {};
  draft.value = {
    temp_high: cfg.temp_high ?? null,
    temp_low: cfg.temp_low ?? null,
    sample_interval_sec: cfg.sample_interval_sec ?? null,
  };
}

watch(
  () => props.id,
  () => {
    store.setSelected(props.id);
    readCfg();
  },
  { immediate: true },
);

watch(
  () => device.value?.capabilities?.config,
  () => {
    readCfg();
  },
  { deep: true },
);

const lastAck = computed(() => store.lastCommandByDeviceId[props.id]?.ack || null);

const lastAckText = computed(() => {
  if (!lastAck.value) return '—';
  if (!lastAck.value.ok) return String(lastAck.value.error || 'error');
  const cmd = lastAck.value.command || {};
  const t = cmd.type;
  if (t === 'set_threshold') return `阈值已应用 (high=${cmd.temp_high}, low=${cmd.temp_low})`;
  if (t === 'set_sample_interval') return `采样周期已应用 (${cmd.sample_interval_sec}s)`;
  return '已应用';
});

const canSend = computed(() => props.id && device.value?.status === 'online');

function goHome() {
  router.push({ name: 'home' });
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
      deviceId: props.id,
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
      deviceId: props.id,
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
.sectionTitle {
  font-weight: 600;
  margin-bottom: 10px;
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
