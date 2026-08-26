<template>
  <div class="index-tts-test">
    <div class="index-tts-test__actions">
      <el-button type="primary" plain size="small" :loading="testing" @click="runTest">
        {{ $t('modelConfigDialog.testConnection') }}
      </el-button>
      <span>{{ $t('modelConfigDialog.testConnectionHint') }}</span>
    </div>
    <div v-if="result" class="index-tts-test__results">
      <div v-for="item in resultItems" :key="item.key" class="index-tts-test__result">
        <span>{{ item.label }}</span>
        <el-tag :type="item.value && item.value.ok ? 'success' : 'danger'" size="mini">
          {{ item.value && item.value.ok ? $t('modelConfigDialog.available') : $t('modelConfigDialog.unavailable') }}
        </el-tag>
        <span class="index-tts-test__message">{{ item.value && item.value.message }}</span>
      </div>
    </div>
  </div>
</template>

<script>
import Api from '@/apis/api';

export default {
  name: 'IndexTtsConnectionTest',
  props: {
    configJson: {
      type: Object,
      required: true
    }
  },
  data() {
    return {
      testing: false,
      result: null
    };
  },
  computed: {
    resultItems() {
      if (!this.result) return [];
      return [
        { key: 'health', label: this.$t('modelConfigDialog.healthCheck'), value: this.result.health },
        { key: 'wav', label: this.$t('modelConfigDialog.normalWav'), value: this.result.wav },
        { key: 'stream', label: this.$t('modelConfigDialog.streamingApi'), value: this.result.stream }
      ];
    }
  },
  methods: {
    runTest() {
      this.testing = true;
      this.result = null;
      Api.model.testIndexTtsConnection(
        this.configJson,
        ({ data }) => {
          this.testing = false;
          if (data && data.code === 0) {
            this.result = data.data;
          } else {
            this.$message.error((data && data.msg) || this.$t('modelConfigDialog.testConnectionFailed'));
          }
        },
        (error) => {
          this.testing = false;
          this.$message.error((error && error.msg) || this.$t('modelConfigDialog.testConnectionFailed'));
        }
      );
    }
  }
};
</script>

<style lang="scss" scoped>
.index-tts-test {
  margin: 8px 0 4px;
  padding: 12px;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  background: #fafbff;
}

.index-tts-test__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #909399;
  font-size: 12px;
}

.index-tts-test__results {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.index-tts-test__result {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
  padding: 8px;
  background: #fff;
  border-radius: 4px;
}

.index-tts-test__message {
  flex-basis: 100%;
  color: #606266;
  font-size: 12px;
  overflow-wrap: anywhere;
}

@media (max-width: 900px) {
  .index-tts-test__results {
    grid-template-columns: 1fr;
  }
}
</style>
