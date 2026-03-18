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
              <div class="title">TF/SD 卡管理</div>
              <div class="sub">sd_info / sd_list / sd_read_text / sd_delete / sd_clear_queue</div>
            </div>
          </div>
        </template>

        <el-empty v-if="!device" description="请选择有效设备" />

        <div v-else>
          <el-form label-width="90px">
            <el-form-item label="路径">
              <el-input v-model="sdPath" placeholder="/sd" />
            </el-form-item>

            <el-form-item>
              <el-button :loading="sdBusy" :disabled="!canSend" @click="sdInfoCmd">查询容量</el-button>
              <el-button :loading="sdBusy" :disabled="!canSend" type="primary" @click="sdListCmd">列出目录</el-button>
              <el-button :loading="sdBusy" :disabled="!canSend" plain @click="sdListQueueCmd">列出队列目录</el-button>
              <el-button :loading="sdBusy" :disabled="!canSend" type="danger" plain @click="sdClearQueueCmd">清空队列</el-button>
            </el-form-item>
          </el-form>

          <div v-if="sdInfo" class="sdInfo">
            <div><b>挂载点：</b>{{ sdInfo.mount_point || '--' }}</div>
            <div><b>剩余：</b>{{ formatBytes(sdInfo.free_bytes) }} / <b>总计：</b>{{ formatBytes(sdInfo.total_bytes) }}</div>
          </div>

          <el-alert v-if="sdError" :title="sdError" type="error" show-icon :closable="false" style="margin: 8px 0;" />

          <el-table v-if="sdItems.length" :data="sdItems" size="small" style="width: 100%; margin-top: 8px;">
            <el-table-column prop="name" label="名称" min-width="160" />
            <el-table-column label="类型" width="80">
              <template #default="scope">
                <el-tag size="small" effect="light" :type="scope.row.is_dir ? 'info' : 'success'">
                  {{ scope.row.is_dir ? 'DIR' : 'FILE' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="大小" width="110">
              <template #default="scope">
                <span>{{ scope.row.is_dir ? '--' : formatBytes(scope.row.size) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="160">
              <template #default="scope">
                <el-button
                  size="small"
                  :disabled="sdBusy || !canSend || scope.row.is_dir"
                  @click="sdReadCmd(scope.row)"
                >
                  读取
                </el-button>
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :disabled="sdBusy || !canSend || scope.row.is_dir"
                  @click="sdDeleteCmd(scope.row)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <div v-if="sdText" style="margin-top: 10px;">
            <div class="sectionTitle" style="margin-bottom: 6px;">文件内容（前 {{ sdMaxBytes }} 字节）</div>
            <el-input v-model="sdText" type="textarea" :rows="8" readonly />
          </div>
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

// --- TF/SD 管理（复用命令通道） ---
const sdPath = ref('/sd');
const sdListedPath = ref('/sd');
const sdItems = ref([]);
const sdInfo = ref(null);
const sdText = ref('');
const sdMaxBytes = 4096;
const sdBusy = ref(false);
const sdPendingCmdId = ref(null);
const sdError = ref('');

function formatBytes(n) {
  const v = Number(n);
  if (!Number.isFinite(v) || v < 0) return '--';
  if (v < 1024) return `${v} B`;
  if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
  if (v < 1024 * 1024 * 1024) return `${(v / (1024 * 1024)).toFixed(1)} MB`;
  return `${(v / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

async function runSdCommand(command) {
  if (!canSend.value) return;
  sdBusy.value = true;
  sdError.value = '';
  try {
    const r = await sendCommand({ deviceId: props.id, command });
    sdPendingCmdId.value = r.cmd_id;
    ElMessage.success(`命令已下发：${r.cmd_id}`);
  } catch (e) {
    sdError.value = String(e);
    ElMessage.error(String(e));
    sdBusy.value = false;
    sdPendingCmdId.value = null;
  }
}

function sdInfoCmd() {
  runSdCommand({ type: 'sd_info' });
}

function sdListCmd() {
  sdText.value = '';
  runSdCommand({ type: 'sd_list', path: sdPath.value || '/sd' });
}

function sdListQueueCmd() {
  sdText.value = '';
  sdPath.value = '/sd/sls_queue';
  runSdCommand({ type: 'sd_list', path: sdPath.value });
}

function sdClearQueueCmd() {
  runSdCommand({ type: 'sd_clear_queue' });
}

function joinPath(dir, name) {
  const d = String(dir || '/sd').replace(/\/+$/, '');
  const n = String(name || '').replace(/^\/+/, '');
  return `${d}/${n}`;
}

function sdReadCmd(row) {
  const path = joinPath(sdListedPath.value, row?.name);
  runSdCommand({ type: 'sd_read_text', path, max_bytes: sdMaxBytes });
}

function sdDeleteCmd(row) {
  const path = joinPath(sdListedPath.value, row?.name);
  runSdCommand({ type: 'sd_delete', path });
}

watch(
  () => lastAck.value,
  (ack) => {
    if (!ack) return;
    if (!sdPendingCmdId.value) return;
    if (ack.cmd_id !== sdPendingCmdId.value) return;

    sdBusy.value = false;
    sdPendingCmdId.value = null;

    if (!ack.ok) {
      sdError.value = String(ack.error || 'error');
      return;
    }

    const t = ack.command?.type;
    if (t === 'sd_info') {
      sdInfo.value = ack.result || null;
      return;
    }
    if (t === 'sd_list') {
      sdListedPath.value = ack.result?.path || sdPath.value || '/sd';
      sdItems.value = Array.isArray(ack.result?.items) ? ack.result.items : [];
      return;
    }
    if (t === 'sd_read_text') {
      sdText.value = String(ack.result?.text || '');
      return;
    }
    if (t === 'sd_delete') {
      // 简单处理：删除后刷新列表（如果之前列过目录）
      if (sdListedPath.value) {
        runSdCommand({ type: 'sd_list', path: sdListedPath.value });
      }
      return;
    }
    if (t === 'sd_clear_queue') {
      // 清空后刷新队列目录
      sdPath.value = '/sd/sls_queue';
      runSdCommand({ type: 'sd_list', path: sdPath.value });
    }
  },
);

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
