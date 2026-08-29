<template>
  <CustomDialog
    :title="title"
    :visible.sync="visible"
    width="600px"
    class="param-dialog-wrapper"
    @confirm="submit"
    @close="cancel"
    :confirmLoading="saving"
  >
    <div class="dialog-container">
      <el-form :model="form" :rules="rules" ref="form" label-width="auto" label-position="left" class="param-form">
        <el-form-item :label="$t('paramDialog.paramCode')" prop="paramCode" class="form-item">
          <el-input v-model="form.paramCode" :placeholder="$t('paramDialog.paramCodePlaceholder')"
            class="custom-input"></el-input>
        </el-form-item>

        <el-form-item :label="$t('paramDialog.valueType')" prop="valueType" class="form-item">
          <el-select
            v-model="form.valueType"
            :placeholder="$t('paramDialog.valueTypePlaceholder')"
            class="custom-select"
          >
            <el-option
              v-for="item in valueTypeOptions"
              :key="item.value"
              :label="$t(`paramDialog.${item.value}Type`)"
              :value="item.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item :label="$t('paramDialog.paramValue')" prop="paramValue" class="form-item">
          <el-input
            v-if="form.valueType !== 'json' && form.valueType !== 'array'"
            v-model="form.paramValue"
            :placeholder="$t('paramDialog.paramValuePlaceholder')"
            class="custom-input"
          ></el-input>
          <el-input
            v-else
            type="textarea"
            v-model="form.paramValue"
            :placeholder="$t('paramDialog.paramValuePlaceholder')"
            :rows="6"
            class="custom-textarea"
          ></el-input>
        </el-form-item>

        <div v-if="isAdvertisedEndpoint" class="advertised-endpoint-card">
          <div class="advertised-endpoint-title">{{ $t('paramDialog.advertisedEndpointTitle') }}</div>
          <div class="advertised-endpoint-description">
            {{ $t('paramDialog.advertisedEndpointDescription') }}
          </div>
          <el-alert
            :title="endpointScopeMessage"
            :type="endpointScopeType"
            :closable="false"
            show-icon
            class="advertised-endpoint-alert"
          />
          <div class="advertised-endpoint-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :loading="endpointTesting"
              :disabled="!form.paramValue"
              @click="testCurrentEndpoint"
            >
              {{ $t('paramDialog.testFromBrowser') }}
            </el-button>
            <span>{{ $t('paramDialog.endpointTestAdvisory') }}</span>
          </div>
        </div>

        <el-form-item :label="$t('paramDialog.remark')" prop="remark" class="form-item remark-item">
          <el-input type="textarea" v-model="form.remark" :placeholder="$t('paramDialog.remarkPlaceholder')" :rows="3"
            class="custom-textarea"></el-input>
        </el-form-item>
      </el-form>
    </div>
  </CustomDialog>
</template>

<script>
import CustomDialog from './CustomDialog.vue';
import {
  endpointScope,
  isAdvertisedEndpointParam,
  testAdvertisedEndpoint
} from '@/utils/advertisedEndpoint.mjs';
export default {
  props: {
    title: {
      type: String,
      default: '新增参数'
    },
    visible: {
      type: Boolean,
      default: false
    },
    form: {
      type: Object,
      default: () => ({
        id: null,
        paramCode: '',
        paramValue: '',
        valueType: 'string',
        remark: ''
      })
    }
  },
  components: {
    CustomDialog
  },
  data() {
    return {
      dialogKey: Date.now(),
      saving: false,
      endpointTesting: false,
      valueTypeOptions: [
        { value: 'string' },
        { value: 'number' },
        { value: 'boolean' },
        { value: 'array' },
        { value: 'json' }
      ],
      rules: {
        paramCode: [
          { required: true, message: this.$t('paramDialog.requiredParamCode'), trigger: "blur" }
        ],
        paramValue: [
          { required: true, message: this.$t('paramDialog.requiredParamValue'), trigger: "blur" }
        ],
        valueType: [
          { required: true, message: this.$t('paramDialog.requiredValueType'), trigger: "change" }
        ]
      }
    };
  },
  computed: {
    isAdvertisedEndpoint() {
      return isAdvertisedEndpointParam(this.form.paramCode);
    },
    advertisedEndpointScope() {
      return endpointScope(this.form.paramCode, this.form.paramValue);
    },
    endpointScopeMessage() {
      return this.$t(`paramDialog.endpointScope.${this.advertisedEndpointScope}`);
    },
    endpointScopeType() {
      if (this.advertisedEndpointScope === 'invalid' || this.advertisedEndpointScope === 'unspecified') {
        return 'error';
      }
      if (this.advertisedEndpointScope === 'loopback') return 'warning';
      return 'info';
    }
  },
  methods: {
    submit() {
      this.$refs.form.validate((valid) => {
        if (valid) {
          const submitData = { ...this.form };

          // 如果是 array 类型，校验格式并转换
          if (submitData.valueType === 'array' && submitData.paramValue) {
            const lines = submitData.paramValue.split('\n').filter(line => line.trim());

            // 检查除最后一行外的每行是否以分号结尾
            for (let i = 0; i < lines.length - 1; i++) {
              if (!lines[i].trim().endsWith(';')) {
                this.$message.error('数组格式错误，需要使用英文分号结尾');
                return;
              }
            }

            const items = lines
              .map(item => item.trim().replace(/;$/, ''))
              .filter(item => item);
            submitData.paramValue = items.join(';');
          }
          // 如果是 json 类型，压缩 JSON 格式后再提交
          else if (submitData.valueType === 'json' && submitData.paramValue) {
            try {
              const parsed = JSON.parse(submitData.paramValue);
              submitData.paramValue = JSON.stringify(parsed);
            } catch (e) {
              // 如果解析失败，保持原值
            }
          }

          this.saving = true; // 开始加载
          this.$emit('submit', submitData);
        }
      });
    },
    cancel() {
      this.saving = false; // 取消时重置状态
      this.dialogKey = Date.now();
      this.$emit('cancel');
    },

    // 提供给父组件调用以重置saving状态
    resetSaving() {
      this.saving = false;
    },
    async testCurrentEndpoint() {
      this.endpointTesting = true;
      try {
        const count = await testAdvertisedEndpoint(this.form.paramCode, this.form.paramValue);
        this.$message.success(this.$t('paramDialog.endpointTestSuccess', { count }));
      } catch (error) {
        this.$message.error(this.$t('paramDialog.endpointTestFailed'));
      } finally {
        this.endpointTesting = false;
      }
    }
  },
  watch: {
    visible(newVal) {
      if (newVal) {
        if (this.form.paramValue) {
          // 如果是 json 类型，格式化显示
          if (this.form.valueType === 'json') {
            try {
              const parsed = JSON.parse(this.form.paramValue);
              this.form.paramValue = JSON.stringify(parsed, null, 2);
            } catch (e) {
              // 如果解析失败，保持原值
            }
          }
          // 如果是 array 类型，将分号分隔的字符串转换为每行一个项目
          else if (this.form.valueType === 'array') {
            const items = this.form.paramValue.split(';').filter(item => item.trim());
            this.form.paramValue = items.join(';\n');
          }
        }
      } else {
        // 当对话框关闭时，重置saving状态
        this.saving = false;
        this.endpointTesting = false;
      }
    }
  }
};
</script>

<style>
.custom-param-dialog {
  border-radius: 16px !important;
  overflow: hidden;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15) !important;
  border: none !important;

  .el-dialog__header {
    display: none;
  }

  .el-dialog__body {
    padding: 0 !important;
    border-radius: 16px;
  }
}
</style>

<style scoped lang="scss">
.param-dialog-wrapper {
  .param-form {
    .form-item {
      margin-bottom: 20px;
      :deep(.el-form-item__label) {
        color: #475569;
        font-weight: 500;
        padding-right: 12px;
        text-align: right;
        font-size: 14px;
        letter-spacing: 0.2px;
      }
    }

    .custom-input {
      :deep(.el-input__inner) {
        background-color: #ffffff;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
        height: 42px;
        padding: 0 14px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        font-size: 14px;
        color: #334155;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);

        &:focus {
          border-color: #3b82f6;
          box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
          background-color: #ffffff;
        }

        &::placeholder {
          color: #94a3b8;
          font-weight: 400;
        }
      }
    }

    .custom-select {
      width: 100%;

      :deep(.el-input__inner) {
        background-color: #ffffff;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
        height: 42px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        font-size: 14px;
        color: #334155;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);

        &:focus {
          border-color: #3b82f6;
          box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
          background-color: #ffffff;
        }

        &::placeholder {
          color: #94a3b8;
          font-weight: 400;
        }
      }
    }

    .custom-textarea {
      :deep(.el-textarea__inner) {
        background-color: #ffffff;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
        padding: 12px 14px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        font-size: 14px;
        color: #334155;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
        line-height: 1.5;

        &:focus {
          border-color: #3b82f6;
          box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
          background-color: #ffffff;
        }

        &::placeholder {
          color: #94a3b8;
          font-weight: 400;
        }
      }
    }

    .remark-item :deep(.el-form-item__label) {
      margin-top: -4px;
    }
  }

  .advertised-endpoint-card {
    margin: -4px 0 20px;
    padding: 14px;
    border: 1px solid #dbeafe;
    border-radius: 8px;
    background: #f8fbff;
  }

  .advertised-endpoint-title {
    color: #334155;
    font-size: 14px;
    font-weight: 600;
  }

  .advertised-endpoint-description {
    margin-top: 6px;
    color: #64748b;
    font-size: 13px;
    line-height: 1.6;
  }

  .advertised-endpoint-alert {
    margin-top: 10px;
  }

  .advertised-endpoint-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 10px;
    color: #94a3b8;
    font-size: 12px;
  }
}
</style>
