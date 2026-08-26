<template>
  <div class="character-style-panel">
    <div class="style-toolbar">
      <el-select
        v-model="selectedId"
        clearable
        filterable
        :placeholder="$t('characterStyle.unbound')"
        :loading="loading"
        @change="handleSelectionChange"
      >
        <el-option
          v-for="style in styles"
          :key="style.id"
          :label="style.name"
          :value="style.id"
        />
      </el-select>
      <el-button
        v-if="selectedId && selectedId !== localBoundId"
        size="small"
        type="primary"
        :loading="binding"
        @click="bindSelected"
      >{{ $t('characterStyle.bind') }}</el-button>
      <el-button
        v-if="localBoundId"
        size="small"
        :loading="binding"
        @click="unbind"
      >{{ $t('characterStyle.unbind') }}</el-button>
      <el-button size="small" @click="openManager">
        {{ $t('characterStyle.manage') }}
      </el-button>
    </div>
    <div v-if="localBoundId" class="binding-notice">
      {{ $t('characterStyle.boundNotice') }}
    </div>
    <div v-else class="style-help">{{ $t('characterStyle.optionalHelp') }}</div>

    <el-dialog
      :title="$t('characterStyle.libraryTitle')"
      :visible.sync="dialogVisible"
      width="920px"
      top="5vh"
      append-to-body
      @closed="stopAudio"
    >
      <el-tabs v-model="activeTab">
        <el-tab-pane :label="$t('characterStyle.library')" name="library">
          <div class="library-layout" v-loading="loading">
            <div class="style-list">
              <div
                v-for="style in styles"
                :key="style.id"
                class="style-row"
                :class="{ active: detail && detail.id === style.id }"
                @click="loadDetail(style.id)"
              >
                <div>
                  <div class="style-name">
                    {{ style.name }}
                    <el-tag v-if="style.id === localBoundId" size="mini">
                      {{ $t('characterStyle.bound') }}
                    </el-tag>
                  </div>
                  <div class="style-meta">{{ style.sourceType }} · {{ shortHash(style.sourceHash) }}</div>
                </div>
                <el-button
                  type="text"
                  class="danger-link"
                  @click.stop="removeStyle(style)"
                >{{ $t('characterStyle.delete') }}</el-button>
              </div>
              <el-empty v-if="!styles.length" :description="$t('characterStyle.empty')" />
            </div>

            <div class="style-detail">
              <template v-if="detail">
                <div class="detail-heading">
                  <div>
                    <h3>{{ detail.name }}</h3>
                    <div class="style-meta">
                      {{ detail.sourceUrl || $t('characterStyle.zipSource') }}
                    </div>
                  </div>
                  <el-button
                    v-if="detail.id !== localBoundId"
                    size="small"
                    type="primary"
                    @click="bindStyle(detail.id)"
                  >{{ $t('characterStyle.bind') }}</el-button>
                </div>
                <el-descriptions :column="2" size="small" border>
                  <el-descriptions-item :label="$t('characterStyle.sourceHash')">
                    {{ detail.sourceHash }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="$t('characterStyle.sourceRef')">
                    {{ detail.sourceRef || '-' }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="$t('characterStyle.includedFiles')">
                    {{ diagnostics.includedFiles && diagnostics.includedFiles.length
                      ? diagnostics.includedFiles.join(', ') : '-' }}
                  </el-descriptions-item>
                  <el-descriptions-item :label="$t('characterStyle.characterCount')">
                    {{ diagnostics.rawCharacterCount || 0 }} / {{ diagnostics.resolvedCharacterCount || 0 }}
                  </el-descriptions-item>
                </el-descriptions>
                <el-tabs class="diagnostic-tabs">
                  <el-tab-pane :label="$t('characterStyle.rawSkill')">
                    <el-input type="textarea" :rows="12" readonly :value="detail.rawSkillText" />
                  </el-tab-pane>
                  <el-tab-pane :label="$t('characterStyle.finalPrompt')">
                    <el-input type="textarea" :rows="12" readonly :value="detail.resolvedPrompt" />
                  </el-tab-pane>
                  <el-tab-pane :label="$t('characterStyle.diagnostics')">
                    <pre class="diagnostics">{{ formattedDiagnostics }}</pre>
                  </el-tab-pane>
                </el-tabs>
              </template>
              <el-empty v-else :description="$t('characterStyle.selectToView')" />
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="$t('characterStyle.importUpdate')" name="import">
          <div class="import-mode-header">
            <div>
              <div class="import-mode-title">{{ $t('characterStyle.mode') }}</div>
              <div class="style-help">
                {{ importMode === 'create'
                  ? $t('characterStyle.importModeHelp')
                  : $t('characterStyle.updateModeHelp') }}
              </div>
            </div>
            <el-radio-group v-model="importMode" size="small" @change="handleImportModeChange">
              <el-radio-button label="create">{{ $t('characterStyle.modeImport') }}</el-radio-button>
              <el-radio-button label="update">{{ $t('characterStyle.modeUpdate') }}</el-radio-button>
            </el-radio-group>
          </div>
          <el-alert
            :title="importMode === 'create'
              ? $t('characterStyle.importModeHelp')
              : $t('characterStyle.updateModeHelp')"
            :type="importMode === 'create' ? 'info' : 'warning'"
            :closable="false"
            show-icon
            class="import-mode-alert"
          />
          <el-form label-width="160px" class="import-form">
            <el-form-item v-if="importMode === 'update'" :label="$t('characterStyle.updateTarget')" required>
              <el-select
                v-model="importForm.styleId"
                :placeholder="$t('characterStyle.selectUpdateTarget')"
                @change="handleUpdateTargetChange"
              >
                <el-option v-for="style in styles" :key="style.id" :label="style.name" :value="style.id" />
              </el-select>
            </el-form-item>
            <el-form-item :label="$t('characterStyle.name')">
              <el-input v-model.trim="importForm.name" maxlength="100" />
            </el-form-item>
            <el-form-item :label="$t('characterStyle.importType')">
              <el-radio-group v-model="importForm.type">
                <el-radio-button label="github">GitHub</el-radio-button>
                <el-radio-button label="zip">ZIP</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <template v-if="importForm.type === 'github'">
              <el-form-item label="GitHub URL">
                <el-input v-model.trim="importForm.sourceUrl" placeholder="https://github.com/owner/repository" />
              </el-form-item>
              <el-form-item :label="$t('characterStyle.sourceRef')">
                <el-input v-model.trim="importForm.sourceRef" placeholder="HEAD / branch / tag / commit" />
                <div class="style-help">{{ $t('characterStyle.sourceRefHelp') }}</div>
              </el-form-item>
            </template>
            <el-form-item v-else :label="$t('characterStyle.zipFile')">
              <input type="file" accept=".zip,application/zip" @change="handleZipChange" />
              <div class="style-help">{{ importForm.zipFile ? importForm.zipFile.name : $t('characterStyle.zipLimit') }}</div>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="importing" @click="submitImport">
                {{ importMode === 'update'
                  ? $t('characterStyle.atomicUpdate')
                  : $t('characterStyle.modeImport') }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <el-tab-pane :label="$t('characterStyle.signatures')" name="signatures">
          <div v-if="styles.length" class="signature-owner">
            <span>{{ $t('characterStyle.signatureOwner') }}</span>
            <el-select v-model="selectedId" size="small" @change="handleSignatureOwnerChange">
              <el-option v-for="style in styles" :key="style.id" :label="style.name" :value="style.id" />
            </el-select>
            <span class="style-help">{{ $t('characterStyle.signatureOwnerHelp') }}</span>
          </div>
          <template v-if="detail">
            <div class="signature-flow">
              <div class="signature-flow-step">
                <span>1</span>
                <div><strong>{{ $t('characterStyle.flowSkill') }}</strong><small>{{ $t('characterStyle.flowSkillHelp') }}</small></div>
              </div>
              <i class="el-icon-right"></i>
              <div class="signature-flow-step">
                <span>2</span>
                <div><strong>{{ $t('characterStyle.flowLlm') }}</strong><small>{{ $t('characterStyle.flowLlmHelp') }}</small></div>
              </div>
              <i class="el-icon-right"></i>
              <div class="signature-flow-step">
                <span>3</span>
                <div><strong>{{ $t('characterStyle.flowAudio') }}</strong><small>{{ $t('characterStyle.flowAudioHelp') }}</small></div>
              </div>
            </div>
            <el-alert
              :title="$t('characterStyle.notUserTriggerHelp')"
              type="info"
              :closable="false"
              show-icon
              class="signature-context-alert"
            />
            <div class="signature-header">
              <div>
                <el-switch
                  v-model="signatureConfig.enabled"
                  :active-text="$t('characterStyle.signatureEnabled')"
                />
                <div class="style-help">{{ $t('characterStyle.signatureOptionalHelp') }}</div>
              </div>
              <div class="signature-header-actions">
                <el-button size="small" icon="el-icon-magic-stick" @click="generateSignatureSuggestions">
                  {{ $t('characterStyle.suggestFromSkill') }}
                </el-button>
                <el-button size="small" @click="addSignature">{{ $t('characterStyle.addSignature') }}</el-button>
              </div>
            </div>
            <div v-if="signatureSuggestions.length" class="signature-suggestions">
              <div class="signature-suggestions-title">{{ $t('characterStyle.suggestionTitle') }}</div>
              <div v-for="suggestion in signatureSuggestions" :key="suggestion.id" class="signature-suggestion">
                <div>
                  <div class="signature-suggestion-text">{{ suggestion.displayText }}</div>
                  <div class="style-help">{{ $t('characterStyle.suggestionEvidence') }}：{{ suggestion.sourceExcerpt }}</div>
                </div>
                <el-button size="mini" type="primary" plain @click="adoptSignatureSuggestion(suggestion)">
                  {{ $t('characterStyle.adoptSuggestion') }}
                </el-button>
              </div>
            </div>
            <div v-for="(item, index) in signatureConfig.items" :key="item.id" class="signature-row">
              <div class="signature-item-heading">
                <el-switch v-model="item.enabled" :active-text="$t('characterStyle.itemEnabled')" />
                <span class="style-meta">{{ item.id }}</span>
              </div>
              <div class="signature-fields">
                <div class="signature-field signature-field-main">
                  <label>{{ $t('characterStyle.displayText') }}</label>
                  <el-input v-model="item.display_text" maxlength="300" />
                  <div class="style-help">{{ $t('characterStyle.displayTextHelp') }}</div>
                </div>
                <div class="signature-field">
                  <label>{{ $t('characterStyle.aliases') }}</label>
                  <el-input v-model="item.aliasesText" maxlength="1000" />
                  <div class="style-help">{{ $t('characterStyle.aliasesHelp') }}</div>
                </div>
              </div>
              <div class="signature-actions">
                <el-tag :type="!item.audio_path ? 'info' : (item.enabled ? 'success' : 'warning')" size="small">
                  {{ !item.audio_path
                    ? $t('characterStyle.useCurrentTts')
                    : (item.enabled
                      ? $t('characterStyle.recordingReady')
                      : $t('characterStyle.recordingUploadedDisabled')) }}
                </el-tag>
                <el-upload
                  action="#"
                  accept=".wav,audio/wav"
                  :show-file-list="false"
                  :http-request="request => uploadAudio(item, request.file)"
                >
                  <el-button type="text">{{ item.audio_path ? $t('characterStyle.replaceAudio') : $t('characterStyle.uploadAudio') }}</el-button>
                </el-upload>
                <el-button v-if="item.audio_path" type="text" @click="playAudio(item)">
                  {{ $t('characterStyle.preview') }}
                </el-button>
                <el-button v-if="item.audio_path" type="text" @click="deleteAudio(item)">
                  {{ $t('characterStyle.deleteAudio') }}
                </el-button>
                <el-button type="text" class="danger-link" @click="removeSignature(index)">
                  {{ $t('characterStyle.removeExpression') }}
                </el-button>
              </div>
            </div>
            <el-empty v-if="!signatureConfig.items.length" :description="$t('characterStyle.zeroSignatures')" />
            <div class="signature-save">
              <el-button type="primary" :loading="savingSignatures" @click="saveSignatures">
                {{ $t('characterStyle.saveSignatures') }}
              </el-button>
            </div>
            <div class="signature-trial">
              <div class="signature-trial-title">{{ $t('characterStyle.contextTrial') }}</div>
              <div class="style-help">{{ $t('characterStyle.contextTrialHelp') }}</div>
              <el-input
                v-model.trim="signatureTrialText"
                type="textarea"
                :rows="2"
                maxlength="1000"
                show-word-limit
                :placeholder="$t('characterStyle.contextTrialPlaceholder')"
              />
              <el-button type="primary" plain size="small" :loading="signatureTrialLoading" @click="runSignatureTrial">
                {{ $t('characterStyle.runContextTrial') }}
              </el-button>
              <div v-if="signatureTrialResult" class="signature-trial-result">
                <div class="signature-result-label">{{ $t('characterStyle.modelActualOutput') }}</div>
                <pre>{{ signatureTrialResult.modelOutput }}</pre>
                <div class="signature-result-label">{{ $t('characterStyle.routeResult') }}</div>
                <div v-if="signatureTrialResult.matches && signatureTrialResult.matches.length">
                  <el-tag
                    v-for="match in signatureTrialResult.matches"
                    :key="match.itemId"
                    :type="match.fixedAudio ? 'success' : 'info'"
                    size="small"
                  >
                    {{ match.matchedText }} · {{ match.fixedAudio
                      ? $t('characterStyle.fixedRecordingPlayback')
                      : $t('characterStyle.currentTtsPlayback') }}
                  </el-tag>
                </div>
                <div v-else class="style-help">{{ $t('characterStyle.noSignatureMatched') }}</div>
              </div>
            </div>
          </template>
          <el-empty v-else :description="$t('characterStyle.selectToView')" />
        </el-tab-pane>
      </el-tabs>
    </el-dialog>
  </div>
</template>

<script>
import Api from '@/apis/api';
import { suggestSignaturesFromSkill } from './characterStyleSignatureSuggestions.mjs';

export default {
  name: 'CharacterStylePanel',
  props: {
    agentId: { type: String, required: true },
    boundStyleId: { type: String, default: '' }
  },
  data() {
    return {
      styles: [],
      selectedId: '',
      localBoundId: '',
      detail: null,
      diagnostics: {},
      signatureConfig: { enabled: false, items: [] },
      loading: false,
      binding: false,
      importing: false,
      savingSignatures: false,
      signatureSuggestions: [],
      signatureTrialText: '',
      signatureTrialLoading: false,
      signatureTrialResult: null,
      dialogVisible: false,
      activeTab: 'library',
      importMode: 'create',
      importForm: {
        type: 'github',
        styleId: '',
        name: '',
        sourceUrl: '',
        sourceRef: '',
        zipFile: null
      },
      currentAudio: null,
      currentAudioUrl: ''
    };
  },
  computed: {
    formattedDiagnostics() {
      return JSON.stringify(this.diagnostics, null, 2);
    }
  },
  watch: {
    boundStyleId: {
      immediate: true,
      handler(value) {
        this.localBoundId = value || '';
        if (value) this.selectedId = value;
      }
    }
  },
  mounted() {
    this.loadStyles();
  },
  beforeDestroy() {
    this.stopAudio();
  },
  methods: {
    callApi(invoke) {
      return new Promise((resolve, reject) => {
        invoke(
          ({ data }) => data && data.code === 0 ? resolve(data.data) : reject(data),
          reject
        );
      });
    },
    errorMessage(error) {
      return error?.data?.msg || error?.msg || this.$t('characterStyle.operationFailed');
    },
    async loadStyles() {
      this.loading = true;
      try {
        this.styles = await this.callApi((success, fail) => Api.characterStyle.list(success, fail)) || [];
        const preferred = this.localBoundId || this.selectedId;
        if (preferred && this.styles.some(style => style.id === preferred)) {
          this.selectedId = preferred;
        }
      } catch (error) {
        this.$message.error(this.errorMessage(error));
      } finally {
        this.loading = false;
      }
    },
    async openManager() {
      this.dialogVisible = true;
      await this.loadStyles();
      const target = this.localBoundId || this.selectedId || this.styles[0]?.id;
      if (target) await this.loadDetail(target);
    },
    async handleSelectionChange(styleId) {
      if (this.dialogVisible && styleId) await this.loadDetail(styleId);
    },
    async handleSignatureOwnerChange(styleId) {
      const previousId = this.detail?.id || null;
      await this.loadDetail(styleId);
      if (this.detail?.id !== styleId) this.selectedId = previousId;
    },
    async loadDetail(styleId) {
      if (!styleId) return;
      this.loading = true;
      try {
        const value = await this.callApi((success, fail) => Api.characterStyle.get(styleId, success, fail));
        this.applyDetail(value);
        this.selectedId = styleId;
      } catch (error) {
        this.$message.error(this.errorMessage(error));
      } finally {
        this.loading = false;
      }
    },
    applyDetail(value) {
      this.detail = value;
      this.diagnostics = this.parseJson(value?.diagnostics, {});
      const parsed = this.parseJson(value?.signatureConfig, { enabled: false, items: [] });
      this.signatureConfig = {
        enabled: parsed.enabled === true,
        items: Array.isArray(parsed.items) ? parsed.items.map(item => ({
          id: item.id,
          display_text: item.display_text || '',
          aliasesText: Array.isArray(item.aliases) ? item.aliases.join(', ') : '',
          audio_path: item.audio_path || null,
          enabled: item.enabled === true
        })) : []
      };
      this.signatureSuggestions = [];
      this.signatureTrialResult = null;
    },
    parseJson(value, fallback) {
      if (!value) return fallback;
      if (typeof value === 'object') return value;
      try { return JSON.parse(value); } catch (error) { return fallback; }
    },
    async bindSelected() {
      if (this.selectedId) await this.bindStyle(this.selectedId);
    },
    async bindStyle(styleId) {
      this.binding = true;
      try {
        await this.callApi((success, fail) => Api.characterStyle.bind(styleId, this.agentId, success, fail));
        this.localBoundId = styleId;
        this.selectedId = styleId;
        this.$emit('binding-changed', styleId);
        this.$message.success(this.$t('characterStyle.bindSuccess'));
      } catch (error) {
        this.$message.error(this.errorMessage(error));
      } finally {
        this.binding = false;
      }
    },
    async unbind() {
      this.binding = true;
      try {
        await this.callApi((success, fail) => Api.characterStyle.unbind(this.agentId, success, fail));
        this.localBoundId = '';
        this.$emit('binding-changed', null);
        this.$message.success(this.$t('characterStyle.unbindSuccess'));
      } catch (error) {
        this.$message.error(this.errorMessage(error));
      } finally {
        this.binding = false;
      }
    },
    async removeStyle(style) {
      try {
        await this.$confirm(
          this.$t('characterStyle.deleteConfirm', { name: style.name }),
          this.$t('message.info'),
          { type: 'warning' }
        );
        await this.callApi((success, fail) => Api.characterStyle.remove(style.id, success, fail));
        if (this.detail?.id === style.id) this.detail = null;
        await this.loadStyles();
      } catch (error) {
        if (error !== 'cancel' && error !== 'close') this.$message.error(this.errorMessage(error));
      }
    },
    handleZipChange(event) {
      this.importForm.zipFile = event.target.files && event.target.files[0] || null;
    },
    handleImportModeChange(mode) {
      this.resetImportForm();
      this.importMode = mode;
    },
    async handleUpdateTargetChange(styleId) {
      if (!styleId) return;
      try {
        const value = await this.callApi((success, fail) => Api.characterStyle.get(styleId, success, fail));
        this.importForm.name = value.name || '';
        this.importForm.sourceUrl = value.sourceUrl || '';
        this.importForm.sourceRef = value.sourceRef || '';
        if (value.sourceType === 'github' || value.sourceUrl) this.importForm.type = 'github';
      } catch (error) {
        this.$message.error(this.errorMessage(error));
      }
    },
    resetImportForm() {
      this.importForm = {
        type: 'github',
        styleId: '',
        name: '',
        sourceUrl: '',
        sourceRef: '',
        zipFile: null
      };
    },
    async submitImport() {
      if (this.importMode === 'update' && !this.importForm.styleId) {
        this.$message.warning(this.$t('characterStyle.updateTargetRequired'));
        return;
      }
      if (!this.importForm.name) {
        this.$message.warning(this.$t('characterStyle.nameRequired'));
        return;
      }
      if (this.importForm.type === 'github' && !this.importForm.sourceUrl) {
        this.$message.warning(this.$t('characterStyle.githubRequired'));
        return;
      }
      if (this.importForm.type === 'zip' && !this.importForm.zipFile) {
        this.$message.warning(this.$t('characterStyle.zipRequired'));
        return;
      }
      this.importing = true;
      try {
        if (this.importMode === 'update') {
          await this.$confirm(
            this.$t('characterStyle.atomicUpdateConfirm', { name: this.importForm.name }),
            this.$t('message.info'),
            { type: 'warning' }
          );
        }
        const styleId = this.importMode === 'update' ? this.importForm.styleId : null;
        const value = this.importForm.type === 'github'
          ? await this.callApi((success, fail) => Api.characterStyle.importGithub({
              styleId,
              name: this.importForm.name,
              sourceUrl: this.importForm.sourceUrl,
              sourceRef: this.importForm.sourceRef || null
            }, success, fail))
          : await this.callApi((success, fail) => Api.characterStyle.importZip({
              name: this.importForm.name,
              styleId,
              file: this.importForm.zipFile
            }, success, fail));
        await this.loadStyles();
        this.applyDetail(value);
        this.selectedId = value.id;
        const completedMode = this.importMode;
        this.importMode = 'create';
        this.resetImportForm();
        this.activeTab = 'library';
        this.$message.success(this.$t(
          completedMode === 'update' ? 'characterStyle.updateSuccess' : 'characterStyle.importSuccess'
        ));
      } catch (error) {
        if (error !== 'cancel' && error !== 'close') this.$message.error(this.errorMessage(error));
      } finally {
        this.importing = false;
      }
    },
    addSignature() {
      this.signatureConfig.items.push({
        id: `signature_${Date.now().toString(36)}`,
        display_text: '',
        aliasesText: '',
        audio_path: null,
        enabled: true
      });
    },
    generateSignatureSuggestions() {
      const existing = new Set(this.signatureConfig.items.map(item => item.display_text.trim().toLocaleLowerCase()));
      this.signatureSuggestions = suggestSignaturesFromSkill(this.detail?.rawSkillText)
        .filter(item => !existing.has(item.displayText.toLocaleLowerCase()));
      if (!this.signatureSuggestions.length) {
        this.$message.info(this.$t('characterStyle.noSuggestions'));
      }
    },
    uniqueSignatureId(baseId) {
      const used = new Set(this.signatureConfig.items.map(item => item.id));
      if (!used.has(baseId)) return baseId;
      let suffix = 2;
      while (used.has(`${baseId}_${suffix}`)) suffix += 1;
      return `${baseId}_${suffix}`;
    },
    adoptSignatureSuggestion(suggestion) {
      this.signatureConfig.items.push({
        id: this.uniqueSignatureId(suggestion.id),
        display_text: suggestion.displayText,
        aliasesText: '',
        audio_path: null,
        enabled: false
      });
      this.signatureSuggestions = this.signatureSuggestions.filter(item => item !== suggestion);
      this.$message.success(this.$t('characterStyle.suggestionAdopted'));
    },
    removeSignature(index) {
      this.signatureConfig.items.splice(index, 1);
    },
    signaturePayload() {
      return {
        enabled: this.signatureConfig.enabled,
        items: this.signatureConfig.items.map(item => ({
          id: item.id,
          display_text: item.display_text.trim(),
          aliases: item.aliasesText.split(/[\n,，;；]/).map(value => value.trim()).filter(Boolean),
          enabled: item.enabled
        }))
      };
    },
    signatureTrialPayload() {
      return {
        enabled: this.signatureConfig.enabled,
        items: this.signatureConfig.items
          .filter(item => item.display_text.trim())
          .map(item => ({
            id: item.id,
            display_text: item.display_text.trim(),
            aliases: item.aliasesText.split(/[\n,，;；]/).map(value => value.trim()).filter(Boolean),
            enabled: item.enabled
          }))
      };
    },
    async runSignatureTrial() {
      if (!this.signatureTrialText) {
        this.$message.warning(this.$t('characterStyle.contextTrialRequired'));
        return;
      }
      this.signatureTrialLoading = true;
      this.signatureTrialResult = null;
      try {
        this.signatureTrialResult = await this.callApi((success, fail) => Api.characterStyle.trialSignatureContext(
          this.detail.id,
          {
            agentId: this.agentId,
            userText: this.signatureTrialText,
            signatureConfig: this.signatureTrialPayload()
          },
          success,
          fail
        ));
      } catch (error) {
        this.$message.error(this.errorMessage(error));
      } finally {
        this.signatureTrialLoading = false;
      }
    },
    async saveSignatures(showSuccess = true) {
      if (!this.detail) return null;
      this.savingSignatures = true;
      try {
        const value = await this.callApi((success, fail) => Api.characterStyle.updateSignatures(
          this.detail.id,
          this.signaturePayload(),
          success,
          fail
        ));
        this.applyDetail(value);
        if (showSuccess) {
          const hasUploadedButDisabled = this.signatureConfig.enabled
            && this.signatureConfig.items.some(item => item.audio_path && !item.enabled);
          if (hasUploadedButDisabled) {
            this.$message.warning(this.$t('characterStyle.recordingDisabledWarning'));
          } else {
            this.$message.success(this.$t('characterStyle.signatureSaveSuccess'));
          }
        }
        return value;
      } catch (error) {
        this.$message.error(this.errorMessage(error));
        return null;
      } finally {
        this.savingSignatures = false;
      }
    },
    async uploadAudio(item, file) {
      if (!file || !file.name.toLowerCase().endsWith('.wav')) {
        this.$message.warning(this.$t('characterStyle.wavRequired'));
        return;
      }
      const saved = await this.saveSignatures(false);
      if (!saved) {
        return;
      }
      try {
        const value = await this.callApi((success, fail) => Api.characterStyle.uploadSignatureAudio(
          this.detail.id, item.id, file, success, fail
        ));
        this.applyDetail(value);
        const uploaded = this.signatureConfig.items.find(value => value.id === item.id);
        this.$message[uploaded?.enabled ? 'success' : 'warning'](
          this.$t(uploaded?.enabled
            ? 'characterStyle.audioUploadSuccess'
            : 'characterStyle.audioUploadDisabled')
        );
      } catch (error) {
        this.$message.error(this.errorMessage(error));
      }
    },
    async deleteAudio(item) {
      try {
        const value = await this.callApi((success, fail) => Api.characterStyle.deleteSignatureAudio(
          this.detail.id, item.id, success, fail
        ));
        this.stopAudio();
        this.applyDetail(value);
      } catch (error) {
        this.$message.error(this.errorMessage(error));
      }
    },
    async playAudio(item) {
      this.stopAudio();
      try {
        const data = await new Promise((resolve, reject) => {
          Api.characterStyle.getSignatureAudio(
            this.detail.id,
            item.id,
            response => resolve(response.data),
            reject
          );
        });
        this.currentAudioUrl = URL.createObjectURL(new Blob([data], { type: 'audio/wav' }));
        this.currentAudio = new Audio(this.currentAudioUrl);
        this.currentAudio.addEventListener('ended', this.stopAudio, { once: true });
        await this.currentAudio.play();
      } catch (error) {
        this.stopAudio();
        this.$message.error(this.errorMessage(error));
      }
    },
    stopAudio() {
      if (this.currentAudio) {
        this.currentAudio.pause();
        this.currentAudio = null;
      }
      if (this.currentAudioUrl) {
        URL.revokeObjectURL(this.currentAudioUrl);
        this.currentAudioUrl = '';
      }
    },
    shortHash(value) {
      return value ? value.slice(0, 12) : '-';
    }
  }
};
</script>

<style lang="scss" scoped>
.character-style-panel { width: 100%; }
.style-toolbar { display: flex; align-items: center; gap: 8px; }
.style-toolbar .el-select { flex: 1; }
.binding-notice { margin-top: 7px; padding: 8px 10px; color: #8a5a00; background: #fff8e8; border-radius: 6px; font-size: 12px; }
.style-help, .style-meta { margin-top: 5px; color: #909399; font-size: 12px; line-height: 1.5; }
.library-layout { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 18px; min-height: 470px; }
.style-list { border-right: 1px solid #ebeef5; padding-right: 14px; max-height: 60vh; overflow: auto; }
.style-row { display: flex; justify-content: space-between; gap: 8px; padding: 12px; margin-bottom: 8px; border: 1px solid #ebeef5; border-radius: 8px; cursor: pointer; }
.style-row.active { border-color: #5778ff; background: #f4f7ff; }
.style-name { color: #303133; font-weight: 600; }
.detail-heading, .signature-header, .signature-fields, .signature-actions { display: flex; align-items: center; gap: 10px; }
.detail-heading { justify-content: space-between; margin-bottom: 12px; }
.detail-heading h3 { margin: 0; }
.diagnostic-tabs { margin-top: 12px; }
.diagnostics { max-height: 300px; overflow: auto; padding: 12px; background: #f6f8fc; white-space: pre-wrap; word-break: break-word; }
.import-mode-header { display: flex; align-items: center; justify-content: space-between; gap: 24px; max-width: 800px; padding-top: 12px; }
.import-mode-title { color: #303133; font-weight: 600; }
.import-mode-alert { max-width: 800px; margin-top: 12px; }
.import-form { max-width: 800px; padding-top: 18px; }
.import-form ::v-deep .el-form-item__label { white-space: nowrap; }
.import-form .el-select { width: 100%; }
.signature-header { justify-content: space-between; margin-bottom: 14px; }
.signature-owner { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; padding: 10px 12px; border: 1px solid #dce8ff; border-radius: 6px; background: #f7faff; }
.signature-owner .el-select { width: 220px; }
.signature-owner .style-help { margin: 0; }
.signature-flow { display: flex; align-items: stretch; justify-content: center; gap: 12px; margin-bottom: 12px; }
.signature-flow > i { align-self: center; color: #a6b1c8; }
.signature-flow-step { display: flex; align-items: center; gap: 9px; flex: 1; min-width: 0; padding: 10px 12px; border: 1px solid #e4eaf5; border-radius: 7px; background: #fafbff; }
.signature-flow-step > span { display: inline-flex; align-items: center; justify-content: center; flex: 0 0 24px; height: 24px; color: #fff; background: #5f7cff; border-radius: 50%; font-size: 12px; font-weight: 600; }
.signature-flow-step strong, .signature-flow-step small { display: block; }
.signature-flow-step strong { color: #3d4566; font-size: 13px; }
.signature-flow-step small { margin-top: 3px; color: #8b95aa; font-size: 11px; line-height: 16px; }
.signature-context-alert { margin-bottom: 14px; }
.signature-header-actions { display: flex; gap: 8px; }
.signature-suggestions { margin-bottom: 14px; padding: 12px; border: 1px dashed #8eabff; border-radius: 7px; background: #f8faff; }
.signature-suggestions-title { margin-bottom: 8px; color: #3d4566; font-weight: 600; }
.signature-suggestion { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 8px 0; border-top: 1px solid #edf1f8; }
.signature-suggestion:first-of-type { border-top: none; }
.signature-suggestion-text { color: #303133; font-family: monospace; }
.signature-row { padding: 14px; margin-bottom: 10px; border: 1px solid #e5eaf3; border-radius: 8px; }
.signature-item-heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.signature-fields { align-items: flex-start; }
.signature-field { flex: 1; min-width: 0; }
.signature-field-main { flex: 1.2; }
.signature-field label { display: block; margin-bottom: 6px; color: #606266; font-size: 13px; }
.signature-actions { justify-content: flex-end; margin-top: 10px; flex-wrap: wrap; }
.signature-save { text-align: right; margin-top: 14px; }
.signature-trial { margin-top: 18px; padding: 14px; border: 1px solid #dfe6f4; border-radius: 8px; background: #fafbff; }
.signature-trial-title { color: #3d4566; font-weight: 600; }
.signature-trial .el-textarea { margin: 10px 0; }
.signature-trial-result { margin-top: 12px; padding-top: 12px; border-top: 1px solid #e5eaf3; }
.signature-result-label { margin: 8px 0 6px; color: #606266; font-size: 12px; font-weight: 600; }
.signature-trial-result pre { margin: 0; padding: 10px; color: #303133; background: #fff; border-radius: 5px; white-space: pre-wrap; word-break: break-word; }
.signature-trial-result .el-tag { margin: 0 8px 6px 0; }
.danger-link { color: #f56c6c; }
@media (max-width: 980px) {
  .library-layout { grid-template-columns: 1fr; }
  .style-list { border-right: none; border-bottom: 1px solid #ebeef5; padding-right: 0; max-height: 220px; }
  .signature-flow { flex-direction: column; }
  .signature-flow > i { transform: rotate(90deg); }
  .signature-fields { flex-direction: column; align-items: stretch; }
}
</style>
