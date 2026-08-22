<template>
  <CustomDialog :visible.sync="localVisible" :title="$t('modelConfig.voiceManagement')" width="90%"
    :close-on-click-modal="true" :destroy-on-close="false" :footer="false" :append-to-body="true"
    @close="handleClose">
    <div v-if="isIndexTts" class="index-voice-toolbar">
      <div>
        <div class="index-voice-title">IndexTTS2.5 远端音色库</div>
        <div class="index-voice-description">
          远端是音色真源。当前远端 {{ indexRemoteVoices.length }} 个，本地目录 {{ ttsModels.length }} 个。
          <span v-if="indexUnsyncedCount > 0" class="index-warning">{{ indexUnsyncedCount }} 个尚未同步</span>
        </div>
      </div>
      <div class="index-voice-toolbar-actions">
        <el-button size="small" icon="el-icon-refresh" :loading="indexRemoteLoading" @click="loadIndexRemoteVoices">
          刷新状态
        </el-button>
        <el-button size="small" type="primary" icon="el-icon-refresh-right" :loading="indexSyncing" @click="syncIndexRemoteVoices">
          同步远端音色
        </el-button>
      </div>
    </div>
    <div class="scroll-wrapper">
      <div class="table-container" ref="tableContainer" @scroll="handleScroll">
        <el-table v-loading="loading" :data="filteredTtsModels" style="width: 100%;" class="data-table"
          header-row-class-name="table-header" :fit="true" :element-loading-text="$t('voicePrint.loading')"
          element-loading-spinner="el-icon-loading" element-loading-background="rgba(0, 0, 0, 0.8)">
          <el-table-column :label="$t('ttsModel.select')" width="50" align="center">
            <template slot-scope="scope">
              <el-checkbox v-model="scope.row.selected"></el-checkbox>
            </template>
          </el-table-column>
          <el-table-column :label="$t('ttsModel.voiceCode')" align="center">
            <template slot-scope="scope">
              <el-input v-if="scope.row.editing" v-model="scope.row.voiceCode"></el-input>
              <span v-else>{{ scope.row.voiceCode }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('ttsModel.voiceName')" align="center">
            <template slot-scope="scope">
              <el-input v-if="scope.row.editing" v-model="scope.row.voiceName"></el-input>
              <span v-else>{{ scope.row.voiceName }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('ttsModel.languageType')" align="center">
            <template slot-scope="scope">
              <el-input v-if="scope.row.editing" v-model="scope.row.languageType"></el-input>
              <span v-else>{{ scope.row.languageType }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="isIndexTts" label="远端状态" align="center" width="130">
            <template slot-scope="scope">
              <el-tag v-if="indexRemoteVoiceMap[scope.row.voiceCode]" size="mini"
                :type="indexRemoteVoiceMap[scope.row.voiceCode].defaultVoice ? 'success' : ''">
                {{ indexRemoteVoiceMap[scope.row.voiceCode].defaultVoice ? '默认音色' : '已注册' }}
              </el-tag>
              <el-tag v-else size="mini" type="danger">远端缺失</el-tag>
            </template>
          </el-table-column>
          <el-table-column v-if="!showReferenceColumns" :label="$t('ttsModel.preview')" align="center" class-name="audio-column">
            <template slot-scope="scope">
              <div class="custom-audio-container">
                <el-input v-if="scope.row.editing" v-model="scope.row.voiceDemo" :placeholder="$t('ttsModel.enterMp3Url')"
                  class="audio-input">
                </el-input>
                <AudioPlayer v-else-if="isValidAudioUrl(scope.row.voiceDemo)" :audioUrl="scope.row.voiceDemo" />
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="!showReferenceColumns" :label="$t('ttsModel.remark')" align="center">
            <template slot-scope="scope">
              <el-input v-if="scope.row.editing" type="textarea" :rows="1" autosize v-model="scope.row.remark"
                  :placeholder="$t('ttsModel.enterRemark')" class="remark-input"></el-input>
              <span v-else>{{ scope.row.remark }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="showReferenceColumns" :label="$t('ttsModel.referenceAudioPath')" align="center">
            <template slot-scope="scope">
              <el-input v-if="scope.row.editing" v-model="scope.row.referenceAudio" :placeholder="$t('ttsModel.enterReferenceAudio')"></el-input>
              <span v-else>{{ scope.row.referenceAudio }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="showReferenceColumns" :label="$t('ttsModel.referenceText')" align="center">
            <template slot-scope="scope">
              <el-input v-if="scope.row.editing" v-model="scope.row.referenceText" :placeholder="$t('ttsModel.enterReferenceText')"></el-input>
              <span v-else>{{ scope.row.referenceText }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('ttsModel.operation')" align="center" :width="isIndexTts ? 190 : 150">
            <template slot-scope="scope">
              <template v-if="isIndexTts">
                <el-button type="text" size="mini" :loading="previewingVoiceId === scope.row.voiceCode"
                  :disabled="!indexRemoteVoiceMap[scope.row.voiceCode]" @click="previewIndexVoice(scope.row)">
                  {{ previewingVoiceId === scope.row.voiceCode ? '播放中' : '试听' }}
                </el-button>
                <el-button type="text" size="mini" @click="openIndexVoiceDialog(scope.row)">
                  重新上传
                </el-button>
                <el-button type="text" size="mini" class="delete-btn"
                  :disabled="Boolean(indexRemoteVoiceMap[scope.row.voiceCode] && indexRemoteVoiceMap[scope.row.voiceCode].defaultVoice)"
                  @click="deleteIndexVoice(scope.row)">
                  {{ $t('ttsModel.delete') }}
                </el-button>
              </template>
              <template v-else-if="!scope.row.editing">
                <el-button type="text" size="mini" @click="startEdit(scope.row)" class="edit-btn">
                    {{ $t('ttsModel.edit') }}
                  </el-button>
                  <el-button type="text" size="mini" @click="deleteRow(scope.row)" class="delete-btn">
                    {{ $t('ttsModel.delete') }}
                  </el-button>
              </template>
              <template v-else>
                <el-button type="success" size="mini" @click="cancelEdit(scope.row)" class="save-Tts">
                  {{ $t('button.cancel') }}
                </el-button>
                <el-button type="success" size="mini" @click="saveEdit(scope.row)" class="save-Tts">
                  {{ $t('ttsModel.save') }}
                </el-button>
              </template>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 自定义滚动条 -->
      <div class="custom-scrollbar" ref="scrollbar">
        <div class="custom-scrollbar-track" ref="scrollbarTrack" @click="handleTrackClick">
          <div class="custom-scrollbar-thumb" ref="scrollbarThumb" @mousedown="startDrag"></div>
        </div>
      </div>
    </div>
    <div v-if="isIndexTts" class="action-buttons">
      <CustomButton icon="el-icon-upload2" size="small" type="add" @click="openIndexVoiceDialog()">
        上传并注册音色
      </CustomButton>
    </div>
    <div v-else class="action-buttons">
      <CustomButton :icon="selectAll ? 'el-icon-circle-close' : 'el-icon-circle-check'" size="small" type="default" @click="toggleSelectAll">
        {{ selectAll ? $t('ttsModel.deselectAll') : $t('ttsModel.selectAll') }}
      </CustomButton>
      <CustomButton icon="el-icon-plus" size="small" type="add" @click="addNew">
        {{ $t('ttsModel.add') }}
      </CustomButton>
      <CustomButton icon="el-icon-delete" size="small" type="delete" @click="deleteRow(filteredTtsModels.filter(row => row.selected))">
        {{ $t('ttsModel.delete') }}
      </CustomButton>
    </div>

    <el-dialog title="注册 IndexTTS2.5 音色" :visible.sync="indexVoiceDialogVisible" width="520px"
      append-to-body :close-on-click-modal="false" @closed="resetIndexVoiceForm">
      <el-form label-width="105px">
        <el-form-item label="Voice ID" required>
          <el-input v-model.trim="indexVoiceForm.voiceId" maxlength="80"
            :disabled="Boolean(indexVoiceForm.originalVoiceId)" placeholder="例如：tuniang-soft" />
          <div class="index-form-tip">只能使用字母、数字、点、下划线和连字符。</div>
        </el-form-item>
        <el-form-item label="音色名称" required>
          <el-input v-model.trim="indexVoiceForm.name" maxlength="100" placeholder="例如：兔娘温柔音" />
        </el-form-item>
        <el-form-item label="语言" required>
          <el-input v-model.trim="indexVoiceForm.languages" maxlength="100" placeholder="普通话" />
        </el-form-item>
        <el-form-item label="参考音频文本">
          <el-input v-model.trim="indexVoiceForm.promptText" type="textarea" :rows="2" maxlength="500"
            show-word-limit placeholder="可选，用于记录参考音频内容" />
        </el-form-item>
        <el-form-item label="参考音频" required>
          <el-upload drag action="#" accept=".wav,audio/wav" :auto-upload="false" :limit="1"
            :file-list="indexVoiceFileList" :on-change="handleIndexVoiceFileChange"
            :on-remove="handleIndexVoiceFileRemove" :on-exceed="handleIndexVoiceFileExceed">
            <i class="el-icon-upload"></i>
            <div class="el-upload__text">拖入 WAV 文件，或<em>点击选择</em></div>
            <div class="el-upload__tip" slot="tip">仅支持 WAV，最大 20MB。重新上传会更新同一 Voice ID。</div>
          </el-upload>
        </el-form-item>
      </el-form>
      <span slot="footer" class="dialog-footer">
        <el-button @click="indexVoiceDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="indexRegistering" @click="registerIndexVoice">上传并注册</el-button>
      </span>
    </el-dialog>
  </CustomDialog>
</template>

<script>
import Api from "@/apis/api";
import AudioPlayer from './AudioPlayer.vue';
import CustomDialog from './CustomDialog.vue';
import CustomButton from './CustomButton.vue';

export default {
  components: { AudioPlayer, CustomDialog, CustomButton },
  props: {
    visible: {
      type: Boolean,
      default: false
    },
    ttsModelId: {
      type: String,
      required: true
    },
    modelConfig: {
      type: Object,
      default: null
    }
  },
  data() {
    return {
      localVisible: this.visible,
      searchQuery: '',
      editDialogVisible: false,
      editVoiceData: {},
      ttsModels: [],
      currentPage: 1,
      pageSize: 10000,
      total: 0,
      isDragging: false,
      startY: 0,
      scrollTop: 0,
      selectAll: false,
      selectedRows: [],
      loading: false,
      showReferenceColumns: false, // 控制是否显示参考列
      indexRemoteVoices: [],
      indexRemoteLoading: false,
      indexSyncing: false,
      indexVoiceDialogVisible: false,
      indexRegistering: false,
      indexVoiceFile: null,
      indexVoiceFileList: [],
      indexVoiceForm: {
        originalVoiceId: '',
        voiceId: '',
        name: '',
        languages: '普通话',
        promptText: ''
      },
      previewingVoiceId: '',
      previewAudioContext: null,
      previewAudioSource: null,
      previewRequestId: 0
    };
  },
  watch: {
    visible(newVal) {
      this.localVisible = newVal;
      if (newVal) {
        this.currentPage = 1;
        this.updateShowReferenceColumns(); // 更新显示状态
        this.loadData(); // 对话框显示时加载数据
        if (this.isIndexTts) {
          this.loadIndexRemoteVoices();
        }
        this.$nextTick(() => {
          this.updateScrollbar();
        });
      }
    },
    modelConfig: {
      handler(newVal) {
        this.updateShowReferenceColumns();
      },
      immediate: true
    },
    filteredTtsModels() {
      this.$nextTick(() => {
        this.updateScrollbar();
      });
    }
  },
  computed: {
    isIndexTts() {
      return Boolean(this.modelConfig && this.modelConfig.configJson
        && this.modelConfig.configJson.type === 'index_tts_v2_5');
    },
    indexRemoteVoiceMap() {
      return this.indexRemoteVoices.reduce((result, voice) => {
        result[voice.voiceId] = voice;
        return result;
      }, {});
    },
    indexUnsyncedCount() {
      return this.indexRemoteVoices.filter(voice => !voice.synced).length;
    },
    filteredTtsModels() {
      return this.ttsModels.filter(model =>
        model.voiceName.toLowerCase().includes(this.searchQuery.toLowerCase())
      );
    }
  },
  mounted() {
    this.updateScrollbar();
    window.addEventListener('resize', this.updateScrollbar);
    window.addEventListener('mouseup', this.stopDrag);
    window.addEventListener('mousemove', this.handleDrag);
  },
  beforeDestroy() {
    this.stopIndexPreview();
    if (this.previewAudioContext) {
      this.previewAudioContext.close().catch(() => {});
      this.previewAudioContext = null;
    }
    window.removeEventListener('resize', this.updateScrollbar);
    window.removeEventListener('mouseup', this.stopDrag);
    window.removeEventListener('mousemove', this.handleDrag);
  },
  methods: {
    // 更新是否显示参考列
    updateShowReferenceColumns() {
      if (this.modelConfig && this.modelConfig.configJson) {
        const providerType = this.modelConfig.configJson.type;
        this.showReferenceColumns = ['fishspeech', 'gpt_sovits_v2', 'gpt_sovits_v3'].includes(providerType);
      } else {
        this.showReferenceColumns = false;
      }
    },

    indexErrorMessage(error, fallback) {
      return error?.data?.msg || error?.response?.data?.msg || fallback;
    },

    loadIndexRemoteVoices() {
      if (!this.isIndexTts || this.indexRemoteLoading) return;
      this.indexRemoteLoading = true;
      Api.timbre.getIndexRemoteVoices(this.ttsModelId, (result) => {
        this.indexRemoteLoading = false;
        if (result && result.code === 0) {
          this.indexRemoteVoices = Array.isArray(result.data) ? result.data : [];
        } else {
          this.$message.error(result?.msg || '读取远端音色失败');
        }
      }, (error) => {
        this.indexRemoteLoading = false;
        this.$message.error(this.indexErrorMessage(error, '无法连接 IndexTTS2.5 音色服务'));
      });
    },

    syncIndexRemoteVoices() {
      if (this.indexSyncing) return;
      this.indexSyncing = true;
      Api.timbre.syncIndexRemoteVoices(this.ttsModelId, (result) => {
        this.indexSyncing = false;
        if (result && result.code === 0) {
          this.indexRemoteVoices = Array.isArray(result.data) ? result.data : [];
          this.$message.success(`已同步 ${this.indexRemoteVoices.length} 个远端音色`);
          this.loadData();
        } else {
          this.$message.error(result?.msg || '同步远端音色失败');
        }
      }, (error) => {
        this.indexSyncing = false;
        this.$message.error(this.indexErrorMessage(error, '同步远端音色失败'));
      });
    },

    openIndexVoiceDialog(row = null) {
      this.resetIndexVoiceForm();
      if (row) {
        const remote = this.indexRemoteVoiceMap[row.voiceCode] || {};
        this.indexVoiceForm = {
          originalVoiceId: row.voiceCode,
          voiceId: row.voiceCode,
          name: row.voiceName,
          languages: row.languageType || '普通话',
          promptText: remote.promptText || ''
        };
      }
      this.indexVoiceDialogVisible = true;
    },

    resetIndexVoiceForm() {
      this.indexVoiceForm = {
        originalVoiceId: '',
        voiceId: '',
        name: '',
        languages: '普通话',
        promptText: ''
      };
      this.indexVoiceFile = null;
      this.indexVoiceFileList = [];
      this.indexRegistering = false;
    },

    handleIndexVoiceFileChange(file) {
      const raw = file && file.raw;
      const isWav = raw && (raw.type === 'audio/wav' || /\.wav$/i.test(raw.name || ''));
      if (!isWav) {
        this.$message.error('只能上传 WAV 参考音频');
        this.indexVoiceFile = null;
        this.indexVoiceFileList = [];
        return;
      }
      if (raw.size > 20 * 1024 * 1024) {
        this.$message.error('参考音频不能超过 20MB');
        this.indexVoiceFile = null;
        this.indexVoiceFileList = [];
        return;
      }
      this.indexVoiceFile = raw;
      this.indexVoiceFileList = [file];
    },

    handleIndexVoiceFileRemove() {
      this.indexVoiceFile = null;
      this.indexVoiceFileList = [];
    },

    handleIndexVoiceFileExceed() {
      this.$message.warning('请先移除当前文件，再选择新的 WAV 音频');
    },

    registerIndexVoice() {
      const { voiceId, name, languages, promptText } = this.indexVoiceForm;
      if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/.test(voiceId)) {
        this.$message.error('Voice ID 格式不正确');
        return;
      }
      if (!name || !languages) {
        this.$message.error('请填写音色名称和语言');
        return;
      }
      if (!this.indexVoiceFile) {
        this.$message.error('请选择 WAV 参考音频');
        return;
      }
      const formData = new FormData();
      formData.append('voiceId', voiceId);
      formData.append('name', name);
      formData.append('languages', languages);
      formData.append('promptText', promptText || '');
      formData.append('audio', this.indexVoiceFile, this.indexVoiceFile.name);
      this.indexRegistering = true;
      Api.timbre.registerIndexVoice(this.ttsModelId, formData, (result) => {
        this.indexRegistering = false;
        if (result && result.code === 0) {
          this.$message.success('音色已上传、注册并同步');
          this.indexVoiceDialogVisible = false;
          this.loadData();
          this.loadIndexRemoteVoices();
        } else {
          this.$message.error(result?.msg || '音色注册失败');
        }
      }, (error) => {
        this.indexRegistering = false;
        this.$message.error(this.indexErrorMessage(error, '音色注册失败'));
      });
    },

    deleteIndexVoice(row) {
      const remote = this.indexRemoteVoiceMap[row.voiceCode];
      if (remote && remote.defaultVoice) {
        this.$message.warning('默认音色不能删除');
        return;
      }
      this.$confirm(`确认同时删除远端音色“${row.voiceName}”和本地目录记录吗？`, '删除音色', {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }).then(() => {
        Api.timbre.deleteIndexVoice(this.ttsModelId, row.voiceCode, (result) => {
          if (result && result.code === 0) {
            this.$message.success('音色已删除');
            this.loadData();
            this.loadIndexRemoteVoices();
          } else {
            this.$message.error(result?.msg || '音色删除失败');
          }
        }, (error) => {
          this.$message.error(this.indexErrorMessage(error, '音色删除失败'));
        });
      }).catch(() => {});
    },

    previewIndexVoice(row) {
      if (this.previewingVoiceId === row.voiceCode) {
        this.stopIndexPreview();
        return;
      }
      this.stopIndexPreview();
      this.previewingVoiceId = row.voiceCode;
      const requestId = this.previewRequestId;

      // 必须在点击手势仍有效时解锁 AudioContext。等待远端推理完成后再调用
      // HTMLAudioElement.play() 会被部分浏览器的自动播放策略拦截。
      this.ensureIndexPreviewAudioContext().then(() => {
        if (requestId !== this.previewRequestId) return;
        Api.timbre.previewIndexVoice(this.ttsModelId, {
          voiceId: row.voiceCode,
          text: `你好，我是${row.voiceName}，这是一段音色试听。`
        }, (response) => {
          this.playIndexPreviewResponse(response, requestId);
        }, (error) => {
          if (requestId !== this.previewRequestId) return;
          this.stopIndexPreview();
          this.$message.error(this.indexErrorMessage(error, '音色试听失败'));
        });
      }).catch((error) => {
        if (requestId !== this.previewRequestId) return;
        this.stopIndexPreview();
        this.$message.error(`浏览器音频设备初始化失败：${error?.message || '未知错误'}`);
      });
    },

    ensureIndexPreviewAudioContext() {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) {
        return Promise.reject(new Error('当前浏览器不支持 Web Audio'));
      }
      if (!this.previewAudioContext || this.previewAudioContext.state === 'closed') {
        this.previewAudioContext = new AudioContextClass();
      }
      if (this.previewAudioContext.state === 'suspended') {
        return this.previewAudioContext.resume();
      }
      return Promise.resolve();
    },

    async playIndexPreviewResponse(response, requestId) {
      if (requestId !== this.previewRequestId) return;
      try {
        const payload = response && response.data;
        let audioData;
        if (payload instanceof ArrayBuffer) {
          audioData = payload;
        } else if (ArrayBuffer.isView(payload)) {
          audioData = payload.buffer.slice(payload.byteOffset, payload.byteOffset + payload.byteLength);
        } else if (typeof Blob !== 'undefined' && payload instanceof Blob) {
          audioData = await payload.arrayBuffer();
        } else {
          throw new Error('接口未返回二进制音频');
        }
        if (requestId !== this.previewRequestId) return;
        const header = new Uint8Array(audioData, 0, Math.min(audioData.byteLength, 12));
        const isWav = header.length >= 12
          && String.fromCharCode(...header.slice(0, 4)) === 'RIFF'
          && String.fromCharCode(...header.slice(8, 12)) === 'WAVE';
        if (!isWav) {
          throw new Error('接口返回内容不是有效的 WAV 音频');
        }

        const decoded = await this.previewAudioContext.decodeAudioData(audioData.slice(0));
        if (requestId !== this.previewRequestId) return;
        const source = this.previewAudioContext.createBufferSource();
        source.buffer = decoded;
        source.connect(this.previewAudioContext.destination);
        source.onended = () => {
          if (this.previewAudioSource === source) {
            source.disconnect();
            this.previewAudioSource = null;
            this.previewingVoiceId = '';
          }
        };
        this.previewAudioSource = source;
        source.start(0);
      } catch (error) {
        if (requestId !== this.previewRequestId) return;
        this.stopIndexPreview();
        this.$message.error(`试听音频解码失败：${error?.message || '未知错误'}`);
      }
    },

    stopIndexPreview() {
      this.previewRequestId += 1;
      if (this.previewAudioSource) {
        this.previewAudioSource.onended = null;
        try {
          this.previewAudioSource.stop(0);
        } catch (error) {
          // 已自然结束的 AudioBufferSourceNode 再次 stop 会抛错，可安全忽略。
        }
        this.previewAudioSource.disconnect();
        this.previewAudioSource = null;
      }
      this.previewingVoiceId = '';
    },

    loadData() {
      this.loading = true;
      const params = {
        ttsModelId: this.ttsModelId,
        page: this.currentPage,
        limit: this.pageSize,
        name: this.searchQuery
      };
      Api.timbre.getVoiceList(params, (data) => {
        if (data.code === 0) {
          this.ttsModels = data.data.list
            .map(item => ({
              id: item.id || '',
              voiceCode: item.ttsVoice || '',
              voiceName: item.name || this.$t('ttsModel.unnamedVoice'),
              languageType: item.languages || '',
              remark: item.remark || '',
              referenceAudio: item.referenceAudio || '',
              referenceText: item.referenceText || '',
              voiceDemo: item.voiceDemo || '',
              selected: false,
              editing: false,
              sort: Number(item.sort)
            }))
            .sort((a, b) => a.sort - b.sort);
          this.total = data.total;
        } else {
          this.$message.error({
            message: data.msg || this.$t('ttsModel.getVoiceListFailed'),
            showClose: true
          });
        }
        this.loading = false;
      }, (err) => {
        console.error('加载失败:', err);
        this.$message.error({
          message: this.$t('ttsModel.loadVoiceDataFailed'),
          showClose: true
        });
        this.loading = false;
      });
    },

    handleClose() {
      // 重置状态
      this.ttsModels = [];
      this.currentPage = 1;
      this.total = 0;
      this.selectAll = false;
      this.searchQuery = '';
      this.showReferenceColumns = false;
      this.indexRemoteVoices = [];
      this.stopIndexPreview();

      this.localVisible = false;
      this.$emit('update:visible', false);
    },

    updateScrollbar() {
      const container = this.$refs.tableContainer;
      const scrollbarThumb = this.$refs.scrollbarThumb;
      const scrollbarTrack = this.$refs.scrollbarTrack;

      if (!container || !scrollbarThumb || !scrollbarTrack) return;

      const { scrollHeight, clientHeight } = container;
      const trackHeight = scrollbarTrack.clientHeight;
      const thumbHeight = Math.max((clientHeight / scrollHeight) * trackHeight, 20);

      scrollbarThumb.style.height = `${thumbHeight}px`;
      this.updateThumbPosition();
    },

    updateThumbPosition() {
      const container = this.$refs.tableContainer;
      const scrollbarThumb = this.$refs.scrollbarThumb;
      const scrollbarTrack = this.$refs.scrollbarTrack;

      if (!container || !scrollbarThumb || !scrollbarTrack) return;

      const { scrollHeight, clientHeight, scrollTop } = container;
      const trackHeight = scrollbarTrack.clientHeight;
      const thumbHeight = scrollbarThumb.clientHeight;
      const maxTop = trackHeight - thumbHeight;
      const thumbTop = (scrollTop / (scrollHeight - clientHeight)) * (trackHeight - thumbHeight);

      scrollbarThumb.style.top = `${Math.min(thumbTop, maxTop)}px`;
    },

    handleScroll() {
      const container = this.$refs.tableContainer;
      if (container.scrollTop + container.clientHeight >= container.scrollHeight - 50) {
        if (this.currentPage * this.pageSize < this.total) {
          this.currentPage++;
          this.loadData();
        }
      }
      this.updateThumbPosition();
    },

    startDrag(e) {
      this.isDragging = true;
      this.startY = e.clientY;
      this.scrollTop = this.$refs.tableContainer.scrollTop;
      e.preventDefault();
    },

    stopDrag() {
      this.isDragging = false;
    },

    handleDrag(e) {
      if (!this.isDragging) return;

      const container = this.$refs.tableContainer;
      const scrollbarTrack = this.$refs.scrollbarTrack;
      const scrollbarThumb = this.$refs.scrollbarThumb;
      const deltaY = e.clientY - this.startY;
      const trackHeight = scrollbarTrack.clientHeight;
      const thumbHeight = scrollbarThumb.clientHeight;
      const maxScrollTop = container.scrollHeight - container.clientHeight;

      const scrollRatio = (trackHeight - thumbHeight) / maxScrollTop;
      container.scrollTop = this.scrollTop + deltaY / scrollRatio;
    },

    handleTrackClick(e) {
      const container = this.$refs.tableContainer;
      const scrollbarTrack = this.$refs.scrollbarTrack;
      const scrollbarThumb = this.$refs.scrollbarThumb;

      if (!container || !scrollbarTrack || !scrollbarThumb) return;

      const trackRect = scrollbarTrack.getBoundingClientRect();
      const thumbHeight = scrollbarThumb.clientHeight;
      const clickPosition = e.clientY - trackRect.top;
      const thumbCenter = clickPosition - thumbHeight / 2;

      const trackHeight = scrollbarTrack.clientHeight;
      const maxTop = trackHeight - thumbHeight;
      const newTop = Math.max(0, Math.min(thumbCenter, maxTop));

      scrollbarThumb.style.top = `${newTop}px`;
      container.scrollTop = (newTop / (trackHeight - thumbHeight)) * (container.scrollHeight - container.clientHeight);
    },

    startEdit(row) {
      row.editing = true;
      this.$set(row, 'originalData', { ...row });
    },

    cancelEdit(row) {
      // 通过新增创建的数据，取消编辑时，需要从数组中移除
      if (!row.id) {
        this.ttsModels.shift(row);
      } else {
        Object.assign(row, row.originalData);
        delete row.originalData;
      }
      row.editing = false;
    },

    saveEdit(row) {
      if (!row.voiceCode || !row.voiceName || !row.languageType) {
        this.$message.error({
          message: this.$t('ttsModel.voiceCodeNameLanguageRequired'),
          showClose: true
        });
        return;
      }

      try {
        const params = {
          id: row.id,
          voiceCode: row.voiceCode,
          voiceName: row.voiceName,
          languageType: row.languageType,
          remark: row.remark,
          ttsModelId: this.ttsModelId,
          voiceDemo: row.voiceDemo || '',
          sort: row.sort
        };

        // 只有在显示参考列的情况下才添加参考字段
        if (this.showReferenceColumns) {
          params.referenceAudio = row.referenceAudio;
          params.referenceText = row.referenceText;
        }

        let res;
        if (row.id) {
          // 已有ID，执行更新操作
          Api.timbre.updateVoice(params, (response) => {
            res = response;
            this.handleResponse(res, row);
          });
        } else {
          // 没有ID，执行新增操作
          Api.timbre.saveVoice(params, (response) => {
            res = response;
            this.handleResponse(res, row);
          });
        }
      } catch (error) {
        console.error('操作失败:', error);
        // 异常情况下也恢复原始数据
        if (row.originalData) {
          Object.assign(row, row.originalData);
          row.editing = false;
          delete row.originalData;
        }
        this.$message.error({
          message: this.$t('ttsModel.operationFailed'),
          showClose: true
        });
      }
    },

    handleResponse(res, row) {
      if (res.code === 0) {
        this.$message.success({
          message: row.id ? this.$t('ttsModel.updateSuccess') : this.$t('ttsModel.saveSuccess'),
          showClose: true
        });
        row.editing = false;
        delete row.originalData;
        this.loadData(); // 刷新数据
      } else {
        // 保存失败时恢复原始数据
        if (row.originalData) {
          Object.assign(row, row.originalData);
          row.editing = false;
          delete row.originalData;
        }
        this.$message.error({
            message: res.msg || (row.id ? this.$t('ttsModel.updateFailed') : this.$t('ttsModel.saveFailed')),
            showClose: true
          });
      }
    },

    toggleSelectAll() {
      this.selectAll = !this.selectAll;
      this.filteredTtsModels.forEach(row => {
        row.selected = this.selectAll;
      });
    },

    addNew() {
      const hasEditing = this.ttsModels.some(row => row.editing);
      if (hasEditing) {
        this.$message.warning(this.$t('ttsModel.finishEditingFirst'));
        return;
      }

      const maxSort = this.ttsModels.length > 0
        ? Math.max(...this.ttsModels.map(item => Number(item.sort) || 0))
        : 0;

      const newRow = {
        voiceCode: '',
        voiceName: '',
        languageType: this.$t('editVoiceDialog.defaultLanguageType'),
        voiceDemo: '',
        remark: '',
        referenceAudio: '',
        referenceText: '',
        selected: false,
        editing: true,
        sort: 0 // 新增数据默认排序在顶部
      };

      this.ttsModels.unshift(newRow);
    },

    deleteRow(row) {
      // 处理单个音色或音色数组
      const voices = Array.isArray(row) ? row : [row];

      if (Array.isArray(row) && row.length === 0) {
        this.$message.warning(this.$t('ttsModel.selectVoiceToDelete'));
        return;
      }


      const voiceCount = voices.length;
      this.$confirm(this.$t('ttsModel.confirmDeleteVoice', {count: voiceCount}), this.$t('ttsModel.warning'), {
        confirmButtonText: this.$t('common.confirm'),
        cancelButtonText: this.$t('common.cancel'),
        type: "warning",
        distinguishCancelAndClose: true
      }).then(() => {
        const ids = voices.map(voice => voice.id);
        if (ids.some(id => !id)) {
          this.$message.error(this.$t('ttsModel.invalidVoiceId'));
          return;
        }

        Api.timbre.deleteVoice(ids, ({ data }) => {
          if (data.code === 0) {
            this.$message.success({
              message: this.$t('ttsModel.deleteVoiceSuccess', {count: voiceCount}),
              showClose: true
            });
            this.loadData(); // 刷新参数列表
          } else {
            this.$message.error({
              message: data.msg || this.$t('ttsModel.deleteFailed'),
              showClose: true
            });
          }
        });
      }).catch(action => {
        if (action === 'cancel') {
          this.$message({
            type: 'info',
            message: this.$t('ttsModel.deleteCancelled'),
            duration: 1000
          });
        } else {
          this.$message({
            type: 'info',
            message: this.$t('ttsModel.operationClosed'),
            duration: 1000
          });
        }
      });
    },

    isValidAudioUrl(url) {
      return url && (url.endsWith('.mp3') || url.endsWith('.ogg') || url.endsWith('.wav'));
    }
  }
};
</script>

<style lang="scss" scoped>
.index-voice-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid #dce8ff;
  border-radius: 8px;
  background: #f7faff;
}

.index-voice-title {
  margin-bottom: 4px;
  color: #263b66;
  font-weight: 600;
}

.index-voice-description,
.index-form-tip {
  color: #8791a8;
  font-size: 12px;
  line-height: 20px;
}

.index-warning {
  margin-left: 8px;
  color: #e6a23c;
}

.index-voice-toolbar-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
}

/* 表格样式 */
::v-deep .data-table .el-table__header th {
  color: black;
  padding: 6px 0 !important;
}

::v-deep .data-table .el-table__row td {
  padding: 8px 0 12px !important;
}

::v-deep .data-table {
  border: none !important;
}

::v-deep .data-table.el-table::before {
  display: none !important;
}

::v-deep .data-table .el-table__header-wrapper {
  border-bottom: 2px solid #f1f2fb !important;
}

::v-deep .data-table .el-table__body-wrapper .el-table__body td {
  border: none !important;
}

/* 备注文本 */
::v-deep .remark-input .el-textarea__inner {
  border-radius: 4px;
  border: 1px solid #e6e6e6;
  padding: 8px 12px;
  resize: none;
  max-height: 40px !important;
  line-height: 1.5;
  background-color: transparent !important;
}

::v-deep .remark-input .el-textarea__inner:focus {
  border-color: #409EFF !important;
  outline: none;
}

::v-deep .remark-input .el-textarea__inner::placeholder {
  color: #c0c4cc !important;
  opacity: 1;
}


/* 滚动容器 */
.scroll-wrapper {
  display: flex;
  max-height: 55vh;
  position: relative;
}

.table-container {
  flex: 1;
  overflow: auto;
  scrollbar-width: none;
  padding-right: 15px;
  width: calc(100% - 16px);
}

.table-container::-webkit-scrollbar {
  display: none;
}

/* 自定义滚动条 */
.custom-scrollbar {
  width: 8px;
  background: #f1f1f1;
  border-radius: 4px;
  position: relative;
  margin-left: 8px;
  height: 100%;
  top: 55px;
}

.custom-scrollbar-track {
  position: relative;
  height: 380px;
  cursor: pointer;
}

.custom-scrollbar-thumb {
  position: absolute;
  width: 100%;
  background: #9dade7;
  border-radius: 4px;
  cursor: grab;
  transition: background 0.2s;
}

.custom-scrollbar-thumb:hover {
  background: #6b84d9;
}

.custom-scrollbar-thumb:active {
  cursor: grabbing;
}

.save-Tts {
  background: #796dea;
  border: None;
}

.save-Tts:hover {
  background: #8b80f0;
}

.custom-audio-container audio {
  display: none;
}

/* 音频播放器容器样式 */
.custom-audio-container {
  width: 90%;
  margin: 0 auto;
}

.edit-btn,
.delete-btn,
.save-btn {
  margin: 0 8px;
  color: #7079aa !important;
  transition: all 0.3s;
}

.edit-btn:hover,
.delete-btn:hover,
.save-btn:hover {
  color: #5f70f3 !important;
  transform: scale(1.05);
}

.save-btn {
  color: #5cca8e !important;
}

/* 表格单元格自适应 */
::v-deep .el-table__body-wrapper {
  overflow-x: hidden !important;
}

::v-deep .el-table td {
  white-space: pre-wrap !important;
  word-break: break-all !important;
}

/* 按钮组定位调整 */
.action-buttons {
  padding-top: 10px;
  text-align: left;
}

/* 输入框自适应 */
::v-deep .el-input__inner,
::v-deep .el-textarea__inner {
  width: 100% !important;
  min-width: 120px;
}

/* 音频输入框特殊处理 */
.audio-input ::v-deep .el-input__inner {
  min-width: 200px;
}

/* 操作按钮弹性布局 */
::v-deep .el-table__row .el-button {
  flex-shrink: 0;
  margin: 2px !important;
}
</style>
