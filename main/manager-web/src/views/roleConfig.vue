<template>
  <div class="welcome">
    <HeaderBar />

    <div class="operation-bar">
      <h2 class="page-title">{{ $t("roleConfig.title") }}</h2>
    </div>

    <div class="main-wrapper" v-loading="agentReloading">
      <div class="content-panel">
        <div class="content-area">
          <el-card class="config-card" shadow="never">
            <div class="config-header">
              <div class="header-left">
                <div class="header-icon">
                  <img loading="lazy" src="@/assets/home/setting-user.png" alt="" />
                </div>
                <span class="header-title">{{ form.agentName }}</span>
                <span v-if="currentVersionNo" class="current-version-tag">
                  {{ $t("roleConfig.currentVersion", { version: currentVersionNo }) }}
                </span>
                <span class="save-state-tag" :class="{ dirty: hasUnsavedChanges }">
                  {{ hasUnsavedChanges ? '有未保存修改' : '已保存，等待设备重启生效' }}
                </span>
              </div>
              <div class="header-tags">
                <el-tag
                  v-for="tag in dynamicTags"
                  :key="tag.id"
                  class="custom-tag"
                  closable
                  :disable-transitions="false"
                  @close="handleClose(tag.id)">
                  {{tag.tagName}}
                </el-tag>
                <el-input
                  class="input-new-tag"
                  v-if="inputVisible"
                  v-model="inputValue"
                  ref="saveTagInput"
                  size="small"
                  maxLength="20"
                  @keyup.enter.native="handleInputConfirm"
                  @blur="handleInputConfirm"
                >
                </el-input>
                <el-button class="custom-tag-btn" v-else size="small" @click="showInput">+ {{ $t("roleConfig.addTag") }}</el-button>
              </div>
              <div class="header-actions">
                <div class="hint-text">
                  <img loading="lazy" src="@/assets/home/info.png" alt="" />
                  <span>{{ $t("roleConfig.restartNotice") }}</span>
                </div>
                <el-button class="history-btn" @click="showSnapshotDialog = true">
                  {{ $t("roleConfig.snapshotHistory") }}
                </el-button>
                <el-button
                  type="primary"
                  class="save-btn"
                  :disabled="configInteractionBlocked"
                  @click="saveConfig"
                >
                  {{ $t("roleConfig.saveConfig") }}
                </el-button>
                <el-button class="reset-btn" @click="resetConfig">{{
                  $t("roleConfig.reset")
                }}</el-button>
                <button class="custom-close-btn" @click="goToHome">×</button>
              </div>
            </div>
            <div class="divider"></div>

            <el-form ref="form" :model="form" label-width="72px">
              <div class="form-content">
                <div class="effective-config">
                  <div class="effective-config__title">当前配置预览</div>
                  <div class="effective-config__items">
                    <span><b>人物</b>{{ effectivePersonaLabel }}</span>
                    <span><b>关系记忆</b>{{ form.companionEnabled ? '独立启用' : '未启用' }}</span>
                    <span><b>旧版记忆</b>{{ selectedModelLabel('Memory', form.model.memModelId) || '未配置' }}</span>
                    <span><b>意图链</b>{{ selectedModelLabel('Intent', form.model.intentModelId) || '未配置' }}</span>
                    <span><b>声音</b>{{ selectedVoiceLabel || '未配置' }}</span>
                    <span><b>动态情绪</b>{{ dynamicEmotionStatus }}</span>
                  </div>
                  <div class="effective-config__hint">这是已加载的草稿配置；保存后重启设备才会成为运行时配置。</div>
                </div>
                <div class="form-grid">
                  <div class="form-column">
                    <div class="config-section-title"><span>1</span>人物身份</div>
                    <el-form-item>
                      <template #label>
                        <el-tooltip :content="$t('roleConfig.tooltip.agentName')" placement="top" effect="light" popper-class="custom-tooltip">
                          <span>{{ $t('roleConfig.agentName') }}：</span>
                        </el-tooltip>
                      </template>
                      <el-input
                        v-model="form.agentName"
                        class="form-input"
                        maxlength="64"
                      />
                    </el-form-item>
                    <div class="config-section-title"><span>2</span>人物关系与记忆</div>
                    <el-form-item>
                      <template #label>
                        <el-tooltip :content="$t('roleConfig.tooltip.companion')" placement="top" effect="light" popper-class="custom-tooltip">
                          <span>{{ $t('roleConfig.companion') }}：</span>
                        </el-tooltip>
                      </template>
                      <div class="companion-config">
                        <div class="companion-heading">
                          <el-switch
                            v-model="form.companionEnabled"
                            :active-text="$t('roleConfig.companionEnabled')"
                            @change="handleCompanionToggle"
                          />
                          <el-button type="text" icon="el-icon-user-solid" @click="$router.push('/persona-library')">
                            {{ $t('roleConfig.openPersonaLibrary') }}
                          </el-button>
                        </div>
                        <el-select
                          v-model="form.personaId"
                          :disabled="!form.companionEnabled"
                          :placeholder="$t('roleConfig.personaIdPlaceholder')"
                          filterable
                          clearable
                          class="form-input"
                          @change="handlePersonaChange"
                        >
                          <el-option v-for="item in personaOptions" :key="item.personaId"
                            :value="item.personaId" :label="`${item.displayName} · ${item.personaId}`">
                            <span>{{ item.displayName }}</span>
                            <span class="persona-option-meta">{{ item.relationshipCeiling }} · {{ item.publishedVersion }}</span>
                          </el-option>
                        </el-select>
                        <el-select
                          v-model="form.personaVersion"
                          :disabled="!form.companionEnabled"
                          :placeholder="$t('roleConfig.personaVersionPlaceholder')"
                          clearable
                          class="form-input"
                        >
                          <el-option value="" :label="$t('roleConfig.personaLatestVersion')" />
                          <el-option v-for="item in personaVersions" :key="item.version"
                            :value="item.version" :label="`${item.version} (${item.status})`" />
                        </el-select>
                        <div class="overlay-editor" :class="{ disabled: !form.companionEnabled }">
                          <div class="overlay-row">
                            <el-input v-model.trim="companionOverlayForm.user_address" :disabled="!form.companionEnabled"
                              :placeholder="$t('roleConfig.userAddressPlaceholder')" maxlength="40" />
                            <el-select v-model="companionOverlayForm.initial_stage" :disabled="!form.companionEnabled"
                              :placeholder="$t('roleConfig.initialStage')" clearable>
                              <el-option v-for="stage in companionStages" :key="stage" :value="stage" :label="$t(`roleConfig.stage_${stage}`)" />
                            </el-select>
                          </div>
                          <el-select v-model="companionOverlayForm.allowed_stages" :disabled="!form.companionEnabled"
                            multiple :placeholder="$t('roleConfig.allowedStages')" class="form-input">
                            <el-option v-for="stage in companionStages" :key="stage" :value="stage" :label="$t(`roleConfig.stage_${stage}`)" />
                          </el-select>
                          <el-input v-model.trim="companionOverlayForm.voice_reply_style" :disabled="!form.companionEnabled"
                            :placeholder="$t('roleConfig.voiceReplyStyle')" maxlength="200" />
                          <el-input v-model.trim="companionOverlayForm.tool_ack_prefix" :disabled="!form.companionEnabled"
                            :placeholder="$t('roleConfig.toolAckPrefix')" maxlength="100" />
                          <div class="proactive-settings">
                            <el-switch v-model="companionOverlayForm.proactive_enabled" :disabled="!form.companionEnabled"
                              active-text="启用主动关心" />
                            <span>最短间隔（分钟）</span>
                            <el-input-number v-model="companionOverlayForm.proactive_interval_minutes"
                              :disabled="!form.companionEnabled || !companionOverlayForm.proactive_enabled"
                              :min="5" :max="10080" :step="30" size="small" />
                          </div>
                          <div class="advanced-toggle">
                            <el-switch v-model="companionAdvanced" :active-text="$t('roleConfig.advancedOverlay')" />
                          </div>
                          <el-input v-if="companionAdvanced" v-model="form.companionOverlay"
                            :disabled="!form.companionEnabled" type="textarea" :rows="4" resize="none"
                            :placeholder="$t('roleConfig.companionOverlayPlaceholder')" @blur="syncOverlayFormFromJson" />
                        </div>
                        <div v-if="companionSummary" class="companion-summary">
                          {{ $t('roleConfig.companionSummary', {
                            stage: companionSummary.stage,
                            turns: companionSummary.meaningfulTurns,
                            memories: companionSummary.memoryCount
                          }) }}
                          <el-button type="text" class="companion-reset" @click="resetCompanionState">
                            {{ $t('roleConfig.resetCompanionState') }}
                          </el-button>
                          <el-button type="text" @click="openCompanionMemories">管理人物记忆</el-button>
                          <div class="persona-state-hint">每个人物拥有独立的关系和记忆；切换回来会恢复该人物原来的状态。</div>
                        </div>
                      </div>
                    </el-form-item>
                    <div class="config-subsection-title">对话快捷配置</div>
                    <el-form-item>
                      <template #label>
                        <el-tooltip :content="$t('roleConfig.tooltip.roleTemplate')" placement="top" effect="light" popper-class="custom-tooltip">
                          <span>{{ $t('roleConfig.roleTemplate') }}：</span>
                        </el-tooltip>
                      </template>
                      <div class="template-container">
                        <div
                          v-for="(template, index) in templates"
                          :key="`template-${index}`"
                          class="template-item"
                          :class="{ 'template-loading': loadingTemplate }"
                          @click="selectTemplate(template)"
                        >
                          {{ template.agentName }}
                        </div>
                      </div>
                    </el-form-item>
                    <el-form-item class="context-provider-item">
                      <template #label>
                        <el-tooltip :content="$t('roleConfig.tooltip.contextProvider')" placement="top" effect="light" popper-class="custom-tooltip">
                          <span>{{ $t('roleConfig.contextProvider') }}：</span>
                        </el-tooltip>
                      </template>
                      <div style="display: flex; align-items: center; justify-content: space-between;">
                        <span style="color: #606266; font-size: 13px;">
                          {{ $t('roleConfig.contextProviderSuccess', { count: currentContextProviders.length }) }}<a href="https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/main/docs/context-provider-integration.md" target="_blank" class="doc-link">{{ $t('roleConfig.contextProviderDocLink') }}</a>
                        </span>
                        <el-button
                          class="edit-function-btn"
                          size="small"
                          @click="openContextProviderDialog"
                        >
                          {{ $t('roleConfig.editContextProvider') }}
                        </el-button>
                      </div>
                    </el-form-item>
                    <el-form-item
                      style="display: none"
                    >
                      <template #label>
                        <el-tooltip :content="$t('roleConfig.tooltip.languageCode')" placement="top" effect="light" popper-class="custom-tooltip">
                          <span>{{ $t('roleConfig.languageCode') }}：</span>
                        </el-tooltip>
                      </template>
                      <el-input
                        v-model="form.langCode"
                        :placeholder="$t('roleConfig.pleaseEnterLangCode')"
                        maxlength="10"
                        show-word-limit
                        class="form-input"
                      />
                    </el-form-item>
                    <el-form-item
                      style="display: none"
                    >
                      <template #label>
                        <el-tooltip :content="$t('roleConfig.tooltip.interactionLanguage')" placement="top" effect="light" popper-class="custom-tooltip">
                          <span>{{ $t('roleConfig.interactionLanguage') }}：</span>
                        </el-tooltip>
                      </template>
                      <el-input
                        v-model="form.language"
                        :placeholder="$t('roleConfig.pleaseEnterLangName')"
                        maxlength="10"
                        show-word-limit
                        class="form-input"
                      />
                    </el-form-item>
                  </div>
                  <div class="form-column">
                    <div class="config-section-title"><span>3</span>对话与能力</div>
                    <div class="model-row">
                      <el-form-item 
                        v-if="featureStatus.vad" 
                        class="model-item"
                      >
                        <template #label>
                          <el-tooltip :content="$t('roleConfig.tooltip.vad')" placement="top" effect="light" popper-class="custom-tooltip">
                            <span>{{ $t('roleConfig.vad') }}</span>
                          </el-tooltip>
                        </template>
                        <div class="model-select-wrapper">
                          <el-select
                            v-model="form.model.vadModelId"
                            filterable
                            :placeholder="$t('roleConfig.pleaseSelect')"
                            class="form-select"
                            @change="handleModelChange('VAD', $event)"
                          >
                            <el-option
                              v-for="(item, optionIndex) in modelOptions['VAD']"
                              :key="`option-vad-${optionIndex}`"
                              :label="item.label"
                              :value="item.value"
                            />
                          </el-select>
                        </div>
                      </el-form-item>
                      <el-form-item 
                        v-if="featureStatus.asr" 
                        class="model-item"
                      >
                        <template #label>
                          <el-tooltip :content="$t('roleConfig.tooltip.asr')" placement="top" effect="light" popper-class="custom-tooltip">
                            <span>{{ $t('roleConfig.asr') }}</span>
                          </el-tooltip>
                        </template>
                        <div class="model-select-wrapper">
                          <el-select
                            v-model="form.model.asrModelId"
                            filterable
                            :placeholder="$t('roleConfig.pleaseSelect')"
                            class="form-select"
                            @change="handleModelChange('ASR', $event)"
                          >
                            <el-option
                              v-for="(item, optionIndex) in modelOptions['ASR']"
                              :key="`option-asr-${optionIndex}`"
                              :label="item.label"
                              :value="item.value"
                            />
                          </el-select>
                        </div>
                      </el-form-item>
                    </div>
                    <div class="model-row">
                      <el-form-item class="model-item">
                        <template #label>
                          <el-tooltip :content="$t('roleConfig.tooltip.llm')" placement="top" effect="light" popper-class="custom-tooltip">
                            <span>{{ $t('roleConfig.llm') }}</span>
                          </el-tooltip>
                        </template>
                        <div class="model-select-wrapper">
                          <el-select
                            v-model="form.model.llmModelId"
                            filterable
                            :placeholder="$t('roleConfig.pleaseSelect')"
                            class="form-select"
                            @change="handleModelChange('LLM', $event)"
                          >
                            <el-option
                              v-for="(item, optionIndex) in modelOptions['LLM']"
                              :key="`option-asr-${optionIndex}`"
                              :label="item.label"
                              :value="item.value"
                            />
                          </el-select>
                        </div>
                      </el-form-item>
                      <el-form-item class="model-item">
                        <template #label>
                          <el-tooltip :content="$t('roleConfig.tooltip.slm')" placement="top" effect="light" popper-class="custom-tooltip">
                            <span>{{ $t('roleConfig.slm') }}</span>
                          </el-tooltip>
                        </template>
                        <div class="model-select-wrapper">
                          <el-select
                            v-model="form.model.slmModelId"
                            filterable
                            :placeholder="$t('roleConfig.pleaseSelect')"
                            class="form-select"
                          >
                            <el-option
                              v-for="(item, optionIndex) in modelOptions['LLM']"
                              :key="`option-asr-${optionIndex}`"
                              :label="item.label"
                              :value="item.value"
                            />
                          </el-select>
                        </div>
                      </el-form-item>
                    </div>
                    <el-form-item
                      v-for="(model, index) in models.slice(4)"
                      :key="`model-${index}`"
                      class="model-item"
                      :class="{ 'legacy-memory-item': model.type === 'Memory' }"
                    >
                      <template #label>
                        <el-tooltip :content="$t('roleConfig.tooltip.' + model.type.toLowerCase())" placement="top" effect="light" popper-class="custom-tooltip">
                          <span>{{ $t('roleConfig.' + model.type.toLowerCase()) }}</span>
                        </el-tooltip>
                      </template>
                      <div
                        class="model-select-wrapper"
                        :class="{ 'legacy-memory-wrapper': model.type === 'Memory' }"
                      >
                        <el-select
                          v-model="form.model[model.key]"
                          filterable
                          :disabled="model.type === 'TTS' && voiceOptionsLoading"
                          :placeholder="$t('roleConfig.pleaseSelect')"
                          class="form-select"
                          @change="handleModelChange(model.type, $event)"
                        >
                          <el-option
                            v-for="(item, optionIndex) in visibleModelOptions(model.type)"
                            v-if="!item.isHidden"
                            :key="`option-${index}-${optionIndex}`"
                            :label="item.label"
                            :value="item.value"
                            :disabled="model.type === 'Intent' && form.companionEnabled && !isCompanionIntentCompatible(item.value)"
                          />
                        </el-select>
                        <div v-if="showFunctionIcons(model.type)" class="function-icons">
                          <el-tooltip
                            v-for="func in currentFunctions"
                            :key="func.name"
                            effect="light"
                            placement="top"
                          >
                            <div slot="content">
                              <div><strong>{{ $t("roleConfig.functionName") }}:</strong> {{ func.name }}</div>
                            </div>
                            <div class="icon-dot">
                              {{ getFunctionDisplayChar(func.name) }}
                            </div>
                          </el-tooltip>
                          <el-button
                            class="edit-function-btn"
                            @click="openFunctionDialog"
                            :class="{ 'active-btn': showFunctionDialog }"
                          >
                            {{ $t("roleConfig.editFunctions") }}
                          </el-button>
                        </div>
                        <div
                          v-if="
                            model.type === 'Memory' &&
                            form.model.memModelId !== 'Memory_nomem'
                          "
                          class="chat-history-options"
                        >
                          <el-radio-group
                            v-model="form.chatHistoryConf"
                            @change="updateChatHistoryConf"
                          >
                            <el-radio-button :label="1">{{
                              $t("roleConfig.reportText")
                            }}</el-radio-button>
                            <el-radio-button :label="2">{{
                              $t("roleConfig.reportTextVoice")
                            }}</el-radio-button>
                          </el-radio-group>
                        </div>
                        <div v-if="model.type === 'Memory'" class="legacy-memory-controls">
                          <el-alert
                            v-if="form.companionEnabled"
                            class="legacy-memory-hint"
                            type="warning"
                            :closable="false"
                            show-icon
                            title="兼容模式：Companion 已负责人物关系与长期记忆，建议选择“无记忆”或“仅上报”。"
                          />
                          <div class="legacy-memory-actions">
                            <el-switch
                              v-if="form.companionEnabled"
                              v-model="legacyMemoryAdvanced"
                              active-text="显示旧版高级提供器"
                            />
                            <el-button type="text" class="danger-text-button" @click="clearLegacyMemory">
                              清除旧版记录与摘要
                            </el-button>
                          </div>
                        </div>
                        <el-alert v-if="model.type === 'Intent' && form.companionEnabled && !isCompanionIntentCompatible(form.model.intentModelId)"
                          class="intent-compatibility-alert" type="error" :closable="false" show-icon
                          title="该旧版意图链会绕过人物上下文与轮次结算。请改用“大模型自主函数调用”或“无意图识别”。" />
                      </div>
                    </el-form-item>
                    <div class="config-section-title"><span>4</span>声音与表达</div>
                    <div class="model-row">
                      <!-- 语言筛选器 -->
                      <el-form-item class="model-item language-select-item">
                        <template #label>
                          <el-tooltip :content="$t('roleConfig.tooltip.language')" placement="top" effect="light" popper-class="custom-tooltip">
                            <span>{{ $t('roleConfig.language') }}</span>
                          </el-tooltip>
                        </template>
                        <div class="model-select-wrapper">
                          <el-select
                            v-model="selectedLanguage"
                            :disabled="voiceOptionsLoading"
                            :placeholder="$t('roleConfig.selectLanguage')"
                            class="form-select language-select"
                            @change="handleLanguageChange"
                          >
                            <el-option
                              v-for="(lang, index) in languageOptions"
                              :key="`lang-${index}`"
                              :label="lang.label"
                              :value="lang.value"
                            />
                          </el-select>
                        </div>
                      </el-form-item>

                      <!-- 音色选择器 -->
                      <el-form-item class="model-item">
                        <template #label>
                          <el-tooltip :content="$t('roleConfig.tooltip.voiceType')" placement="top" effect="light" popper-class="custom-tooltip">
                            <span>{{ $t('roleConfig.voiceType') }}</span>
                          </el-tooltip>
                        </template>
                        <div class="model-select-wrapper">
                          <el-select
                            v-model="form.ttsVoiceId"
                            filterable
                            :disabled="voiceOptionsLoading"
                            :placeholder="$t('roleConfig.pleaseSelect')"
                            class="form-select"
                            @change="handleVoiceChange"
                          >
                            <el-option
                              v-for="(item, index) in availableVoiceOptions"
                              :key="`voice-${index}`"
                              :label="item.label"
                              :value="item.value"
                            >
                              <div
                                style="
                                  display: flex;
                                  justify-content: space-between;
                                  align-items: center;
                                "
                              >
                                <span>{{ item.label }}</span>
                                <template v-if="hasAudioPreview(item)">
                                  <el-button
                                    type="text"
                                    :icon="
                                      playingVoice &&
                                      currentPlayingVoiceId === item.value &&
                                      !isPaused
                                        ? 'el-icon-video-pause'
                                        : 'el-icon-video-play'
                                    "
                                    size="small"
                                    @click.stop="toggleAudioPlayback(item.value)"
                                    :loading="false"
                                    class="play-button"
                                  />
                                </template>
                              </div>
                            </el-option>
                          </el-select>
                          <el-button
                            class="edit-function-btn"
                            style="margin-left: 10px;"
                            @click="openTtsAdvancedSettings"
                          >
                            {{ $t('roleConfig.advancedSettings') }}
                          </el-button>
                        </div>
                      </el-form-item>
                    </div>
                  </div>
                </div>
                <div class="advanced-section">
                  <div class="config-section-title"><span>5</span>高级与兼容</div>
                  <div class="advanced-config-toggle">
                    <el-switch v-model="advancedConfig" active-text="显示基础系统规则与兼容字段" />
                    <span v-if="form.companionEnabled">启用 Companion 后，人物特性由 Persona 决定；这里只保留中性的系统规则。</span>
                  </div>
                  <el-form-item v-if="advancedConfig || !form.companionEnabled">
                    <template #label>
                      <el-tooltip :content="$t('roleConfig.tooltip.roleIntroduction')" placement="top" effect="light" popper-class="custom-tooltip">
                        <span>{{ $t('roleConfig.roleIntroduction') }}：</span>
                      </el-tooltip>
                    </template>
                    <el-input
                      type="textarea"
                      rows="6"
                      resize="none"
                      :placeholder="$t('roleConfig.pleaseEnterContent')"
                      v-model="form.systemPrompt"
                      maxlength="2000"
                      show-word-limit
                      class="form-textarea"
                    />
                  </el-form-item>
                  <el-form-item v-if="form.model.memModelId === 'Memory_mem_local_short'">
                    <template #label>
                      <el-tooltip :content="$t('roleConfig.tooltip.memoryHis')" placement="top" effect="light" popper-class="custom-tooltip">
                        <span>{{ $t('roleConfig.memoryHis') }}：</span>
                      </el-tooltip>
                    </template>
                    <el-input
                      type="textarea"
                      rows="4"
                      resize="none"
                      v-model="form.summaryMemory"
                      maxlength="2000"
                      show-word-limit
                      class="form-textarea"
                      :disabled="form.model.memModelId !== 'Memory_mem_local_short'"
                    />
                  </el-form-item>
                </div>
              </div>
            </el-form>
          </el-card>
        </div>
      </div>
    </div>
    <function-dialog
      v-model="showFunctionDialog"
      :functions="currentFunctions"
      :all-functions="allFunctions"
      :agent-id="$route.query.agentId"
      @update-functions="handleUpdateFunctions"
      @dialog-closed="handleDialogClosed"
    />
    <context-provider-dialog
      :visible.sync="showContextProviderDialog"
      :providers="currentContextProviders"
      @confirm="handleUpdateContext"
    />
    <tts-advanced-settings
      :visible.sync="showTtsAdvancedDialog"
      :settings="ttsSettings"
      :checked-replacement-word-ids="checkedReplacementWordIds"
      @save="handleTtsSettingsSave"
    />
      <agent-snapshot-dialog
        v-if="$route.query.agentId"
        :visible.sync="showSnapshotDialog"
        :agent-id="$route.query.agentId"
        :current-version-no="currentVersionNo"
        @restored="handleSnapshotRestored"
      />
    <el-dialog title="预览并应用角色模板" :visible.sync="showTemplatePreview" width="560px">
      <el-alert type="info" :closable="false" show-icon
        title="默认只更新基础系统规则；Companion 人物、关系状态、人物记忆和声音不会被覆盖。" />
      <el-checkbox-group v-model="templateScopes" class="template-scope-options">
        <el-checkbox label="base">名称与基础系统规则</el-checkbox>
        <el-checkbox label="capabilities">对话模型与能力</el-checkbox>
        <el-checkbox label="legacyMemory">旧版记忆配置</el-checkbox>
        <el-checkbox label="voice">声音配置</el-checkbox>
      </el-checkbox-group>
      <div class="template-preview-list" v-if="pendingTemplate">
        <div><b>模板</b><span>{{ pendingTemplate.agentName }}</span></div>
        <div><b>保留</b><span>Persona、版本、Overlay、关系状态与人物记忆</span></div>
        <div><b>声音</b><span>{{ templateScopes.includes('voice') ? '将更新' : '保持当前配置' }}</span></div>
        <div><b>旧版记忆</b><span>{{ templateScopes.includes('legacyMemory') ? '将更新配置，不删除现有数据' : '保持当前配置' }}</span></div>
      </div>
      <span slot="footer">
        <el-button @click="showTemplatePreview = false">取消</el-button>
        <el-button type="primary" :disabled="templateScopes.length === 0" @click="confirmTemplateApply">应用所选范围</el-button>
      </span>
    </el-dialog>
    <el-dialog title="人物记忆管理" :visible.sync="showCompanionMemories" width="780px">
      <el-alert type="info" :closable="false" show-icon
        :title="`这里只管理当前人物 ${form.personaId || ''} 的记忆；切换人物后会看到另一套独立记忆。`" />
      <div v-if="editingMemory" class="memory-edit-panel">
        <el-input v-model.trim="memoryEditForm.content" type="textarea" :rows="3" maxlength="1000" show-word-limit />
        <div class="memory-edit-row">
          <span>重要度</span>
          <el-slider v-model="memoryEditForm.importance" :min="0" :max="1" :step="0.05" show-input />
          <span>过期时间</span>
          <el-date-picker v-model="memoryEditForm.expiresAt" type="datetime" value-format="yyyy-MM-dd'T'HH:mm:ss"
            placeholder="永久保留" clearable />
        </div>
        <div class="memory-edit-actions">
          <el-button size="small" @click="editingMemory = null">取消编辑</el-button>
          <el-button size="small" type="primary" @click="saveCompanionMemory">保存记忆</el-button>
        </div>
      </div>
      <el-table :data="companionMemories" v-loading="companionMemoriesLoading" max-height="430">
        <el-table-column prop="memoryType" label="类型" width="90" />
        <el-table-column prop="content" label="内容" min-width="300" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="95">
          <template slot-scope="scope">
            <el-tag size="mini" :type="scope.row.status === 'active' ? 'success' : 'info'">
              {{ scope.row.status === 'active' ? '有效' : '已被更新' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="importance" label="重要度" width="80" />
        <el-table-column label="操作" width="125" align="right">
          <template slot-scope="scope">
            <el-button type="text" :disabled="scope.row.status !== 'active'" @click="editCompanionMemory(scope.row)">编辑</el-button>
            <el-button type="text" class="companion-reset" @click="deleteCompanionMemory(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!companionMemoriesLoading && companionMemories.length === 0" class="memory-empty">当前人物还没有形成长期记忆。</div>
    </el-dialog>
    <el-footer>
      <version-footer />
    </el-footer>
  </div>
</template>

<script>
import Api from "@/apis/api";
import { getServiceUrl } from "@/apis/api";
import RequestService from "@/apis/httpRequest";
import FunctionDialog from "@/components/FunctionDialog.vue";
import ContextProviderDialog from "@/components/ContextProviderDialog.vue";
import TtsAdvancedSettings from "@/components/TtsAdvancedSettings.vue";
import AgentSnapshotDialog from "@/components/AgentSnapshotDialog.vue";
import HeaderBar from "@/components/HeaderBar.vue";
import i18n from "@/i18n";
import featureManager from "@/utils/featureManager"; 
import VersionFooter from "@/components/VersionFooter.vue";

export default {
  name: "RoleConfigPage",
  components: { HeaderBar, FunctionDialog, ContextProviderDialog, TtsAdvancedSettings, AgentSnapshotDialog, VersionFooter },
  data() {
    return {
      showContextProviderDialog: false,
      showTtsAdvancedDialog: false,
      showSnapshotDialog: false,
      ttsSettings: {
        volume: 0,
        speed: 0,
        pitch: 0
      },
      tempSummaryMemory: "",
      form: {
        agentCode: "",
        agentName: "",
        ttsVoiceId: "",
        ttsVolume: null,
        ttsRate: null,
        ttsPitch: null,
        chatHistoryConf: 0,
        systemPrompt: "",
        summaryMemory: "",
        companionEnabled: false,
        personaId: "",
        personaVersion: "",
        companionOverlay: "{}",
        langCode: "",
        language: "",
        sort: "",
        model: {
          ttsModelId: "",
          vadModelId: "",
          asrModelId: "",
          llmModelId: "",
          slmModelId: "",
          vllmModelId: "",
          memModelId: "",
          intentModelId: "",
        },
      },
      models: [
        { label: this.$t("roleConfig.vad"), key: "vadModelId", type: "VAD" },
        { label: this.$t("roleConfig.asr"), key: "asrModelId", type: "ASR" },
        { label: this.$t("roleConfig.llm"), key: "llmModelId", type: "LLM" },
        { label: this.$t("roleConfig.slm"), key: "slmModelId", type: "SLM" },
        { label: this.$t("roleConfig.vllm"), key: "vllmModelId", type: "VLLM" },
        { label: this.$t("roleConfig.intent"), key: "intentModelId", type: "Intent" },
        { label: this.$t("roleConfig.memory"), key: "memModelId", type: "Memory" },
        { label: this.$t("roleConfig.tts"), key: "ttsModelId", type: "TTS" },
      ],
      llmModeTypeMap: new Map(),
      modelOptions: {},
      templates: [],
      loadingTemplate: false,
      voiceOptions: [],
      voiceDetails: {}, // 保存完整的音色信息
      showFunctionDialog: false,
      currentVersionNo: null,
      currentFunctions: [],
      currentContextProviders: [],
      allFunctions: [],
      originalFunctions: [],
      playingVoice: false,
      isPaused: false,
      currentAudio: null,
      currentPlayingVoiceId: null,
      // 语言筛选相关状态
      languageOptions: [], // 语言选项列表
      selectedLanguage: '', // 当前选中的语言
      ttsLanguageTouched: false,
      ttsVoiceTouched: false,
      voiceFetchSeq: 0,
      voiceOptionsLoading: false,
      lastValidTtsDraft: null,
      agentReloading: false,
      agentReloadSeq: 0,
      agentConfigFetchSeq: 0,
      agentTagsFetchSeq: 0,
      currentVersionFetchSeq: 0,
      agentConfigLoaded: false,
      agentFunctionsLoaded: false,
      agentTagsLoaded: false,
      currentVersionLoaded: false,
      pluginMetadataReady: false,
      pluginMetadataLoading: null,
      // 功能状态
      featureStatus: {
        vad: false, // 语言检测活动功能状态
        asr: false, // 语音识别功能状态
      },
      dynamicTags: [],
      originalTagNames: [],
      inputVisible: false,
      inputValue: '',
      checkedReplacementWordIds: [],
      companionSummary: null,
      personaOptions: [],
      personaVersions: [],
      companionStages: ["stranger", "familiar", "friend", "ambiguous", "lover", "intimate"],
      companionAdvanced: false,
      advancedConfig: false,
      legacyMemoryAdvanced: false,
      showTemplatePreview: false,
      pendingTemplate: null,
      templateScopes: ["base"],
      savedFormFingerprint: "",
      showCompanionMemories: false,
      companionMemoriesLoading: false,
      companionMemories: [],
      editingMemory: null,
      memoryEditForm: { content: "", importance: 0.5, expiresAt: null },
      companionOverlayForm: {
        user_address: "",
        initial_stage: "",
        allowed_stages: [],
        voice_reply_style: "",
        tool_ack_prefix: "",
        proactive_enabled: false,
        proactive_interval_minutes: 180
      }
    };
  },
  computed: {
    availableVoiceOptions() {
      return this.voiceOptions;
    },
    configInteractionBlocked() {
      return this.agentReloading
        || this.voiceOptionsLoading
        || !this.agentConfigLoaded
        || !this.agentFunctionsLoaded
        || !this.agentTagsLoaded;
    },
    effectivePersonaLabel() {
      if (!this.form.companionEnabled) return "基础角色";
      const persona = this.personaOptions.find(item => item.personaId === this.form.personaId);
      const version = this.form.personaVersion || persona?.publishedVersion || "当前发布版";
      return persona ? `${persona.displayName} · ${version}` : (this.form.personaId || "未选择");
    },
    selectedVoiceLabel() {
      return this.voiceOptions.find(item => item.value === this.form.ttsVoiceId)?.label
        || this.voiceDetails?.[this.form.ttsVoiceId]?.name
        || "";
    },
    dynamicEmotionStatus() {
      const id = String(this.form.model.ttsModelId || "").toLowerCase();
      return id.includes("minimax") ? "提供器支持" : "仅基础语音（提供器未声明支持）";
    },
    hasUnsavedChanges() {
      return Boolean(this.savedFormFingerprint) && this.formFingerprint() !== this.savedFormFingerprint;
    }
  },
  methods: {
    goToHome() {
      this.$router.push("/home");
    },
    selectedModelLabel(type, value) {
      return (this.modelOptions[type] || []).find(item => item.value === value)?.label || value || "";
    },
    formFingerprint() {
      return JSON.stringify({
        ...this.form,
        companionOverlay: this.form.companionOverlay || "{}",
        companionOverlayDraft: this.companionOverlayForm,
        selectedLanguage: this.selectedLanguage || "",
        tagNames: this.dynamicTags.map(item => item.tagName),
        functions: this.currentFunctions.map(item => ({
          id: item.id,
          params: this.normalizeFunctionParams(item.params),
        })),
        contextProviders: this.currentContextProviders,
        replacementWordIds: this.checkedReplacementWordIds,
      });
    },
    visibleModelOptions(type) {
      const options = this.modelOptions[type] || [];
      if (type !== "Memory" || !this.form.companionEnabled || this.legacyMemoryAdvanced) {
        return options;
      }
      const recommended = new Set(["Memory_nomem", "Memory_mem_report_only", this.form.model.memModelId]);
      return options.filter(item => recommended.has(item.value));
    },
    handleCompanionToggle(enabled) {
      const recommendedMemory = new Set(["Memory_nomem", "Memory_mem_report_only"]);
      if (enabled && !recommendedMemory.has(this.form.model.memModelId)) {
        this.form.model.memModelId = "Memory_nomem";
        this.form.chatHistoryConf = 0;
        this.$message.info("已将旧版对话记忆切换为“无记忆”，避免与人物记忆重复注入；原有数据没有删除。");
      }
      if (!enabled) {
        this.legacyMemoryAdvanced = false;
      } else if (!this.isCompanionIntentCompatible(this.form.model.intentModelId)) {
        const functionCall = (this.modelOptions.Intent || []).find(item => item.value === "Intent_function_call");
        if (functionCall) this.form.model.intentModelId = functionCall.value;
      }
    },
    isCompanionIntentCompatible(value) {
      return !value || value === "Intent_nointent" || value === "Intent_function_call";
    },
    normalizeFunctionParams(params, fallback = {}) {
      if (params === null || params === undefined || params === '') {
        return { ...fallback };
      }
      if (typeof params === 'string') {
        try {
          const parsed = JSON.parse(params);
          return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
            ? parsed
            : { ...fallback };
        } catch (error) {
          return { ...fallback };
        }
      }
      if (typeof params === 'object' && !Array.isArray(params)) {
        return { ...params };
      }
      return { ...fallback };
    },
    loadPersonaOptions() {
      return new Promise((resolve) => {
        Api.persona.options(({ data }) => {
          this.personaOptions = data?.code === 0 && Array.isArray(data.data) ? data.data : [];
          const requestedPersonaId = this.$route.query.personaId;
          if (requestedPersonaId && this.personaOptions.some(item => item.personaId === requestedPersonaId)) {
            this.form.companionEnabled = true;
            this.form.personaId = requestedPersonaId;
            this.handlePersonaChange(requestedPersonaId);
          } else if (this.form.personaId) {
            this.handlePersonaChange(this.form.personaId);
          }
          resolve(true);
        }, () => resolve(false));
      });
    },
    handlePersonaChange(personaId) {
      this.personaVersions = [];
      if (!personaId) {
        this.form.personaVersion = "";
        return;
      }
      Api.persona.versions(personaId, ({ data }) => {
        if (data?.code !== 0) return;
        this.personaVersions = (data.data || []).filter(item => item.status === "published");
        if (this.form.personaVersion && !this.personaVersions.some(item => item.version === this.form.personaVersion)) {
          this.form.personaVersion = "";
        }
      });
    },
    syncOverlayFormFromJson() {
      try {
        const value = JSON.parse(this.form.companionOverlay || "{}");
        this.validateCompanionOverlay(value);
        this.companionOverlayForm = {
          user_address: value.user_address || "",
          initial_stage: value.initial_stage || "",
          allowed_stages: Array.isArray(value.allowed_stages) ? value.allowed_stages : [],
          voice_reply_style: value.voice_reply_style || "",
          tool_ack_prefix: value.tool_ack_prefix || "",
          proactive_enabled: Boolean(value.proactive_enabled),
          proactive_interval_minutes: Number(value.proactive_interval_minutes || 180)
        };
      } catch (error) {
        this.$message.error(this.$t("roleConfig.companionOverlayInvalid"));
      }
    },
    buildCompanionOverlay() {
      let base = JSON.parse(this.form.companionOverlay || "{}");
      this.validateCompanionOverlay(base);
      Object.entries(this.companionOverlayForm).forEach(([key, value]) => {
        const populated = key === "proactive_enabled"
          ? value === true
          : Array.isArray(value) ? value.length > 0 : Boolean(value && String(value).trim());
        if (populated) base[key] = value;
        else delete base[key];
      });
      this.form.companionOverlay = JSON.stringify(base);
      return this.form.companionOverlay;
    },
    validateCompanionOverlay(value) {
      if (!value || Array.isArray(value) || typeof value !== "object") {
        throw new TypeError("overlay must be an object");
      }
      const textFields = new Set(["ai_identity_notice", "user_address", "voice_reply_style", "tool_rephrase_style", "tool_ack_prefix"]);
      const listFields = new Set(["allowed_stages", "intimacy_boundaries", "memory_rules", "proactive_behavior_rules", "additional_rules"]);
      const scalarFields = new Set(["initial_stage", "proactive_enabled", "proactive_interval_minutes"]);
      Object.entries(value).forEach(([key, item]) => {
        if (!textFields.has(key) && !listFields.has(key) && !scalarFields.has(key)) {
          throw new TypeError(`unsupported overlay field: ${key}`);
        }
        if (textFields.has(key) && typeof item !== "string") throw new TypeError(`${key} must be text`);
        if (listFields.has(key) && (!Array.isArray(item) || item.some(entry => typeof entry !== "string"))) {
          throw new TypeError(`${key} must be a text array`);
        }
        if (key === "proactive_enabled" && typeof item !== "boolean") throw new TypeError(`${key} must be boolean`);
        if (key === "proactive_interval_minutes" && (typeof item !== "number" || item < 5 || item > 10080)) {
          throw new TypeError(`${key} must be between 5 and 10080`);
        }
      });
      return true;
    },
    async saveConfig() {
      if (this.configInteractionBlocked) {
        return;
      }
      if (this.form.companionEnabled && !this.form.personaId) {
        this.$message.error(this.$t("roleConfig.personaIdRequired"));
        return;
      }
      if (this.form.companionEnabled && !this.isCompanionIntentCompatible(this.form.model.intentModelId)) {
        this.$message.error("当前意图识别会绕过 Companion 人物链，请改用大模型自主函数调用或无意图识别");
        return;
      }
      try {
        this.buildCompanionOverlay();
      } catch (error) {
        this.$message.error(this.$t("roleConfig.companionOverlayInvalid"));
        return;
      }
      const configData = {
        agentCode: this.form.agentCode,
        agentName: this.form.agentName,
        asrModelId: this.form.model.asrModelId,
        vadModelId: this.form.model.vadModelId,
        llmModelId: this.form.model.llmModelId,
        slmModelId: this.form.model.slmModelId,
        vllmModelId: this.form.model.vllmModelId,
        ttsModelId: this.form.model.ttsModelId,
        chatHistoryConf: this.form.chatHistoryConf,
        memModelId: this.form.model.memModelId,
        intentModelId: this.form.model.intentModelId,
        systemPrompt: this.form.systemPrompt,
        summaryMemory: this.form.summaryMemory,
        companionEnabled: this.form.companionEnabled,
        personaId: this.form.personaId,
        personaVersion: this.form.personaVersion,
        companionOverlay: this.form.companionOverlay || "{}",
        langCode: this.form.langCode,
        language: this.form.language,
        sort: this.form.sort,
        functions: this.currentFunctions.map((item) => {
          return {
            pluginId: item.id,
            paramInfo: this.normalizeFunctionParams(item.params),
          };
        }),
        contextProviders: this.currentContextProviders,
        correctWordFileIds: this.checkedReplacementWordIds,
      };
      const tagNames = this.dynamicTags.map(tag => tag.tagName);
      const tagsChanged = !this.isSameStringList(tagNames, this.originalTagNames);
      if (tagsChanged) {
        configData.tagNames = tagNames;
      }
      if (this.shouldSubmitTtsLanguage()) {
        configData.ttsLanguage = this.selectedLanguage;
      }
      if (this.ttsVoiceTouched && this.form.ttsVoiceId !== null && this.form.ttsVoiceId !== undefined) {
        configData.ttsVoiceId = this.form.ttsVoiceId;
      }
      const submittedTtsLanguageTouched = this.ttsLanguageTouched;
      const submittedTtsVoiceTouched = this.ttsVoiceTouched;
      const submittedTtsLanguage = configData.ttsLanguage;
      const submittedTtsVoiceId = configData.ttsVoiceId;
      const submittedVoiceFetchSeq = this.voiceFetchSeq;

      // 只在用户设置了TTS参数时才传递（不为null/undefined）
      if (this.form.ttsVolume !== null && this.form.ttsVolume !== undefined) {
        configData.ttsVolume = this.form.ttsVolume;
      }
      if (this.form.ttsRate !== null && this.form.ttsRate !== undefined) {
        configData.ttsRate = this.form.ttsRate;
      }
      if (this.form.ttsPitch !== null && this.form.ttsPitch !== undefined) {
        configData.ttsPitch = this.form.ttsPitch;
      }
      const agentId = this.$route.query.agentId;
      Api.agent.updateAgentConfig(agentId, configData, ({ data }) => {
        if (data.code === 0) {
          const afterSave = () => {
            if (tagsChanged) {
              this.originalTagNames = [...tagNames];
            }
            this.originalFunctions = JSON.parse(JSON.stringify(this.currentFunctions));
            if (submittedVoiceFetchSeq === this.voiceFetchSeq
              && submittedTtsLanguageTouched
              && this.selectedLanguage === submittedTtsLanguage) {
              this.form.ttsLanguage = submittedTtsLanguage;
              this.ttsLanguageTouched = false;
            }
            if (submittedVoiceFetchSeq === this.voiceFetchSeq
              && submittedTtsVoiceTouched
              && this.form.ttsVoiceId === submittedTtsVoiceId) {
              this.ttsVoiceTouched = false;
            }
            if (submittedVoiceFetchSeq === this.voiceFetchSeq) {
              this.lastValidTtsDraft = this.captureTtsDraft();
            }
            this.savedFormFingerprint = this.formFingerprint();
            this.$message.success({
              message: i18n.t("roleConfig.saveSuccess"),
              showClose: true,
            });
            this.fetchCurrentVersion(agentId);
          };
          afterSave();
        } else {
          this.$message.error({
            message: data.msg || i18n.t("roleConfig.saveFailed"),
            showClose: true,
          });
        }
      });
      
    },
    async reloadAgentPage(agentId, options = {}) {
      if (!agentId) {
        return false;
      }
      const requestSeq = ++this.agentReloadSeq;
      this.agentReloading = true;
      if (options.closeEditors) {
        this.showSnapshotDialog = false;
        this.showFunctionDialog = false;
        this.showContextProviderDialog = false;
        this.showTtsAdvancedDialog = false;
        this.inputVisible = false;
      }

      const results = await Promise.all([
        this.fetchAgentConfig(agentId, { showError: false }),
        this.getAgentTags(agentId, { showError: false }),
        this.fetchCurrentVersion(agentId, { showError: false })
      ]);
      this.fetchCompanionSummary(agentId);
      if (requestSeq !== this.agentReloadSeq) {
        return false;
      }

      this.agentReloading = false;
      if (results.every(Boolean)) {
        this.$nextTick(() => {
          this.savedFormFingerprint = this.formFingerprint();
        });
      }
      if (!this.pluginMetadataReady && this.agentConfigLoaded) {
        this.$message.error(i18n.t("roleConfig.fetchPluginsFailed"));
      } else if (!results.every(Boolean)) {
        this.$message.error(i18n.t("roleConfig.fetchConfigFailed"));
      }
      return results.every(Boolean);
    },
    fetchCompanionSummary(agentId) {
      return new Promise((resolve) => {
        Api.agent.getCompanionSummary(agentId, ({ data }) => {
          if (data?.code === 0) {
            this.companionSummary = data.data;
            resolve(true);
          } else {
            this.companionSummary = null;
            resolve(false);
          }
        }, () => {
          this.companionSummary = null;
          resolve(false);
        });
      });
    },
    resetCompanionState() {
      const agentId = this.$route.query.agentId;
      this.$confirm(
        this.$t("roleConfig.resetCompanionConfirm"),
        this.$t("message.info"),
        {
          confirmButtonText: this.$t("button.ok"),
          cancelButtonText: this.$t("button.cancel"),
          type: "warning",
        }
      ).then(() => {
        Api.agent.resetCompanionState(agentId, ({ data }) => {
          if (data?.code === 0) {
            this.$message.success(this.$t("roleConfig.resetCompanionSuccess"));
            this.fetchCompanionSummary(agentId);
          } else {
            this.$message.error(data?.msg || this.$t("roleConfig.resetCompanionFailed"));
          }
        });
      }).catch(() => {});
    },
    clearLegacyMemory() {
      const agentId = this.$route.query.agentId;
      this.$confirm(
        "这会永久删除旧版聊天记录和本地短记忆摘要，但不会删除 Companion 的人物关系与记忆。确定继续吗？",
        "清除旧版记忆",
        {
          confirmButtonText: this.$t("button.ok"),
          cancelButtonText: this.$t("button.cancel"),
          type: "warning",
        }
      ).then(() => {
        Api.agent.clearLegacyMemory(agentId, ({ data }) => {
          if (data?.code === 0) {
            this.form.summaryMemory = "";
            this.$message.success("旧版聊天记录与摘要已清除");
          } else {
            this.$message.error(data?.msg || "清除旧版记忆失败");
          }
        });
      }).catch(() => {});
    },
    openCompanionMemories() {
      this.showCompanionMemories = true;
      this.editingMemory = null;
      this.loadCompanionMemories();
    },
    loadCompanionMemories() {
      const agentId = this.$route.query.agentId;
      this.companionMemoriesLoading = true;
      Api.agent.getCompanionMemories(agentId, ({ data }) => {
        this.companionMemoriesLoading = false;
        if (data?.code === 0) {
          this.companionMemories = data.data || [];
        } else {
          this.companionMemories = [];
          this.$message.error(data?.msg || "加载人物记忆失败");
        }
      }, () => {
        this.companionMemoriesLoading = false;
        this.companionMemories = [];
        this.$message.error("加载人物记忆失败，请检查服务连接");
      });
    },
    editCompanionMemory(memory) {
      this.editingMemory = memory;
      this.memoryEditForm = {
        content: memory.content || "",
        importance: Number(memory.importance ?? 0.5),
        expiresAt: memory.expiresAt || null,
      };
    },
    saveCompanionMemory() {
      if (!this.editingMemory || !this.memoryEditForm.content) return;
      Api.agent.updateCompanionMemory(
        this.$route.query.agentId,
        this.editingMemory.id,
        this.memoryEditForm,
        ({ data }) => {
          if (data?.code === 0) {
            this.$message.success("人物记忆已更新");
            this.editingMemory = null;
            this.loadCompanionMemories();
            this.fetchCompanionSummary(this.$route.query.agentId);
          } else {
            this.$message.error(data?.msg || "更新人物记忆失败");
          }
        }
      );
    },
    deleteCompanionMemory(memory) {
      this.$confirm(`永久删除这条人物记忆：“${String(memory.content || '').slice(0, 40)}”？`, "删除人物记忆", {
        confirmButtonText: this.$t("button.ok"),
        cancelButtonText: this.$t("button.cancel"),
        type: "warning",
      }).then(() => {
        Api.agent.deleteCompanionMemory(this.$route.query.agentId, memory.id, ({ data }) => {
          if (data?.code === 0) {
            this.$message.success("人物记忆已删除");
            this.loadCompanionMemories();
            this.fetchCompanionSummary(this.$route.query.agentId);
          } else {
            this.$message.error(data?.msg || "删除人物记忆失败");
          }
        });
      }).catch(() => {});
    },
    handleSnapshotRestored() {
      const agentId = this.$route.query.agentId;
      if (agentId) {
        this.reloadAgentPage(agentId, { closeEditors: true });
      }
    },
    fetchCurrentVersion(agentId, options = {}) {
      const requestSeq = ++this.currentVersionFetchSeq;
      this.currentVersionLoaded = false;
      if (!agentId) {
        this.currentVersionNo = null;
        this.currentVersionLoaded = true;
        return Promise.resolve(true);
      }

      return new Promise((resolve) => {
        const handleFailure = (error) => {
          if (requestSeq !== this.currentVersionFetchSeq) {
            resolve(false);
            return;
          }
          this.currentVersionLoaded = false;
          if (options.showError !== false) {
            this.$message.error(error?.data?.msg || i18n.t("roleConfig.fetchConfigFailed"));
          }
          resolve(false);
        };
        Api.agent.getDeviceConfig(agentId, ({ data }) => {
          if (requestSeq !== this.currentVersionFetchSeq) {
            resolve(false);
            return;
          }
          if (data?.code === 0) {
            this.currentVersionNo = data.data?.currentVersionNo || null;
            this.currentVersionLoaded = true;
            resolve(true);
          } else {
            handleFailure(data);
          }
        }, handleFailure);
      });
    },
    resetConfig() {
      this.$confirm("放弃当前页面尚未保存的修改，并重新加载最后一次保存的配置？", i18n.t("message.info"), {
        confirmButtonText: i18n.t("button.ok"),
        cancelButtonText: i18n.t("button.cancel"),
        type: "warning",
      })
        .then(async () => {
          await this.reloadAgentPage(this.$route.query.agentId, { closeEditors: true });
          this.$message.success({ message: "已恢复最后一次保存的配置", showClose: true });
        })
        .catch(() => {});
    },
    fetchTemplates() {
      Api.agent.getAgentTemplate(({ data }) => {
        if (data.code === 0) {
          this.templates = data.data;
        } else {
          this.$message.error(data.msg || i18n.t("roleConfig.fetchTemplatesFailed"));
        }
      });
    },
    selectTemplate(template) {
      if (this.loadingTemplate) return;
      this.pendingTemplate = template;
      this.templateScopes = ["base"];
      this.showTemplatePreview = true;
    },
    confirmTemplateApply() {
      if (!this.pendingTemplate || this.loadingTemplate) return;
      this.loadingTemplate = true;
      try {
        this.applyTemplateData(this.pendingTemplate, this.templateScopes);
        this.$message.success({
          message: `${this.pendingTemplate.agentName}${i18n.t("roleConfig.templateApplied")}`,
          showClose: true,
        });
        this.showTemplatePreview = false;
      } catch (error) {
        this.$message.error({
          message: i18n.t("roleConfig.applyTemplateFailed"),
          showClose: true,
        });
        console.error("应用模板失败:", error);
      } finally {
        this.loadingTemplate = false;
      }
    },
    applyTemplateData(templateData, scopes = ["base"]) {
      const rollbackState = this.cloneTtsDraft(this.lastValidTtsDraft) || this.captureTtsDraft();
      const currentLanguage = this.selectedLanguage;
      const selected = new Set(scopes);
      const next = { ...this.form, model: { ...this.form.model } };
      const assign = (target, key, value) => {
        if (value !== null && value !== undefined) target[key] = value;
      };
      if (selected.has("base")) {
        assign(next, "agentName", templateData.agentName);
        assign(next, "systemPrompt", templateData.systemPrompt);
        assign(next, "langCode", templateData.langCode);
      }
      if (selected.has("capabilities")) {
        ["vadModelId", "asrModelId", "llmModelId", "slmModelId", "vllmModelId", "intentModelId"]
          .forEach(key => assign(next.model, key, templateData[key]));
      }
      if (selected.has("legacyMemory")) {
        assign(next, "chatHistoryConf", templateData.chatHistoryConf);
        assign(next, "summaryMemory", templateData.summaryMemory);
        assign(next.model, "memModelId", templateData.memModelId);
      }
      if (selected.has("voice")) {
        assign(next, "ttsVoiceId", templateData.ttsVoiceId);
        assign(next.model, "ttsModelId", templateData.ttsModelId);
      }
      this.form = next;
      if (selected.has("voice") && templateData.ttsLanguage !== null && templateData.ttsLanguage !== undefined) {
        this.selectedLanguage = templateData.ttsLanguage;
      }
      if (selected.has("voice") && (templateData.ttsModelId || templateData.ttsVoiceId || templateData.ttsLanguage)) {
        this.fetchVoiceOptions(this.form.model.ttsModelId, {
          autoSelectVoice: true,
          preferredLanguage: templateData.ttsLanguage || (templateData.ttsVoiceId ? "" : currentLanguage),
          preferredVoiceId: templateData.ttsVoiceId || "",
          rollbackState,
          markTouched: true
        });
      }
    },
    buildCurrentFunctions(savedMappings) {
      if (!Array.isArray(savedMappings)) {
        throw new TypeError("Invalid agent function mappings");
      }
      return savedMappings.map((mapping) => {
        const pluginId = mapping.pluginId || mapping.id;
        const meta = this.pluginMetadataReady
          ? this.allFunctions.find((item) => item.id === pluginId)
          : null;
        return {
          id: pluginId,
          name: meta?.name || mapping.name || pluginId,
          params: this.normalizeFunctionParams(mapping.paramInfo ?? mapping.params, meta?.params || {}),
          fieldsMeta: meta?.fieldsMeta || []
        };
      }).filter((item) => item.id);
    },
    enrichCurrentFunctionsWithMetadata() {
      if (!this.agentFunctionsLoaded || !this.pluginMetadataReady) {
        return;
      }
      this.currentFunctions = this.currentFunctions.map((item) => {
        const meta = this.allFunctions.find((candidate) => candidate.id === item.id);
        if (!meta) {
          return {
            ...item,
            params: this.normalizeFunctionParams(item.params),
            fieldsMeta: item.fieldsMeta || []
          };
        }
        return {
          ...item,
          name: meta.name || item.name || item.id,
          params: this.normalizeFunctionParams(item.params, meta.params),
          fieldsMeta: meta.fieldsMeta || []
        };
      });
      this.originalFunctions = JSON.parse(JSON.stringify(this.currentFunctions));
    },
    fetchAgentConfig(agentId, options = {}) {
      const requestSeq = ++this.agentConfigFetchSeq;
      this.agentConfigLoaded = false;
      this.agentFunctionsLoaded = false;
      this.voiceFetchSeq += 1;
      this.voiceOptionsLoading = false;

      return new Promise((resolve) => {
        const handleFailure = (error) => {
          if (requestSeq !== this.agentConfigFetchSeq) {
            resolve(false);
            return;
          }
          this.agentConfigLoaded = false;
          this.agentFunctionsLoaded = false;
          if (options.showError !== false) {
            this.$message.error(error?.data?.msg || i18n.t("roleConfig.fetchConfigFailed"));
          }
          resolve(false);
        };

        Api.agent.getDeviceConfig(agentId, ({ data }) => {
          if (requestSeq !== this.agentConfigFetchSeq) {
            resolve(false);
            return;
          }
          if (data?.code !== 0 || !data.data) {
            handleFailure(data);
            return;
          }

          try {
            const agentData = data.data;
            if (agentData.functions != null && !Array.isArray(agentData.functions)) {
              throw new TypeError("Invalid agent function mappings");
            }
            if (agentData.contextProviders != null && !Array.isArray(agentData.contextProviders)) {
              throw new TypeError("Invalid context providers");
            }
            if (agentData.correctWordFileIds != null && !Array.isArray(agentData.correctWordFileIds)) {
              throw new TypeError("Invalid correct-word mappings");
            }
            this.tempSummaryMemory = "";
            this.ttsLanguageTouched = false;
            this.ttsVoiceTouched = false;
            this.form = {
              ...this.form,
              ...agentData,
              companionEnabled: Boolean(agentData.companionEnabled),
              personaId: agentData.personaId || "",
              personaVersion: agentData.personaVersion || "",
              companionOverlay: agentData.companionOverlay || "{}",
              model: {
                ttsModelId: agentData.ttsModelId,
                vadModelId: agentData.vadModelId,
                asrModelId: agentData.asrModelId,
                llmModelId: agentData.llmModelId,
                slmModelId: agentData.slmModelId,
                vllmModelId: agentData.vllmModelId,
                memModelId: agentData.memModelId,
                intentModelId: agentData.intentModelId,
              },
            };
            this.syncOverlayFormFromJson();
            this.handlePersonaChange(this.form.personaId);
            this.selectedLanguage = agentData.ttsLanguage || "";
            this.voiceOptions = [];
            this.voiceDetails = {};
            this.languageOptions = [];
            this.lastValidTtsDraft = this.captureTtsDraft();
            this.fetchVoiceOptions(agentData.ttsModelId, {
              preferredLanguage: agentData.ttsLanguage,
              preferredVoiceId: agentData.ttsVoiceId
            });

            this.ttsSettings = {
              volume: this.form.ttsVolume || 0,
              speed: this.form.ttsRate || 0,
              pitch: this.form.ttsPitch || 0
            };
            this.checkedReplacementWordIds = agentData.correctWordFileIds || [];
            this.currentContextProviders = agentData.contextProviders || [];
            this.currentFunctions = this.buildCurrentFunctions(agentData.functions || []);
            this.originalFunctions = JSON.parse(JSON.stringify(this.currentFunctions));
            this.agentFunctionsLoaded = true;
            this.agentConfigLoaded = true;
            this.$nextTick(() => {
              this.savedFormFingerprint = this.formFingerprint();
            });

            const metadataPromise = this.pluginMetadataReady
              ? Promise.resolve(true)
              : this.fetchAllFunctions({ showError: options.showError });
            metadataPromise.then((metadataReady) => {
              if (requestSeq === this.agentConfigFetchSeq && metadataReady) {
                this.enrichCurrentFunctionsWithMetadata();
                this.updateIntentOptionsVisibility();
              }
              resolve(true);
            }).catch(handleFailure);
          } catch (error) {
            handleFailure(error);
          }
        }, handleFailure);
      });
    },
    fetchModelOptions() {
      this.models.forEach((model) => {
        if (model.type != "LLM") {
          Api.model.getModelNames(model.type, "", ({ data }) => {
            if (data.code === 0) {
              this.$set(
                this.modelOptions,
                model.type,
                data.data.map((item) => ({
                  value: item.id,
                  label: item.modelName,
                  isHidden: false,
                }))
              );

              // 如果是意图识别选项，需要根据当前LLM类型更新可见性
              if (model.type === "Intent") {
                this.updateIntentOptionsVisibility();
              }
            } else {
              this.$message.error(data.msg || i18n.t("roleConfig.fetchModelsFailed"));
            }
          });
        } else {
          Api.model.getLlmModelCodeList("", ({ data }) => {
            if (data.code === 0) {
              let LLMdata = [];
              data.data.forEach((item) => {
                LLMdata.push({
                  value: item.id,
                  label: item.modelName,
                  isHidden: false,
                });
                this.llmModeTypeMap.set(item.id, item.type);
              });
              this.$set(this.modelOptions, model.type, LLMdata);
            } else {
              this.$message.error(data.msg || i18n.t("roleConfig.fetchModelsFailed"));
            }
          });
        }
      });
    },
    fetchVoiceOptions(modelId, options = {}) {
      const requestSeq = ++this.voiceFetchSeq;
      if (!modelId) {
        this.voiceOptionsLoading = false;
        this.voiceOptions = [];
        this.voiceDetails = {};
        this.languageOptions = [];
        this.selectedLanguage = '';
        this.lastValidTtsDraft = this.captureTtsDraft();
        return;
      }
      this.voiceOptionsLoading = true;
      Api.model.getModelVoices(modelId, "", ({ data }) => {
        if (requestSeq !== this.voiceFetchSeq) {
          return;
        }
        const draft = data.code === 0
          ? this.buildTtsDraft(modelId, data.data, options)
          : null;
        if (!draft) {
          this.handleVoiceOptionsFailure(requestSeq, options.rollbackState);
          return;
        }
        this.applyTtsDraft(draft, options);
        this.voiceOptionsLoading = false;
        this.lastValidTtsDraft = this.captureTtsDraft();
      }, () => {
        this.handleVoiceOptionsFailure(requestSeq, options.rollbackState);
      });
    },
    cloneTtsDraft(draft) {
      return draft ? JSON.parse(JSON.stringify(draft)) : null;
    },
    captureTtsDraft() {
      return {
        modelId: this.form.model.ttsModelId,
        language: this.selectedLanguage,
        storedLanguage: this.form.ttsLanguage,
        voiceId: this.form.ttsVoiceId,
        languageTouched: this.ttsLanguageTouched,
        voiceTouched: this.ttsVoiceTouched,
        voiceOptions: this.cloneTtsDraft(this.voiceOptions) || [],
        voiceDetails: this.cloneTtsDraft(this.voiceDetails) || {},
        languageOptions: this.cloneTtsDraft(this.languageOptions) || []
      };
    },
    restoreTtsDraft(draft) {
      const restored = this.cloneTtsDraft(draft);
      if (!restored) {
        return false;
      }
      this.form.model.ttsModelId = restored.modelId;
      this.selectedLanguage = restored.language;
      this.form.ttsLanguage = restored.storedLanguage;
      this.form.ttsVoiceId = restored.voiceId;
      this.ttsLanguageTouched = restored.languageTouched;
      this.ttsVoiceTouched = restored.voiceTouched;
      this.voiceOptions = restored.voiceOptions;
      this.voiceDetails = restored.voiceDetails;
      this.languageOptions = restored.languageOptions;
      this.lastValidTtsDraft = restored;
      return true;
    },
    splitVoiceLanguages(voice) {
      return voice && voice.languages
        ? voice.languages.split(/[、；;,，]/).map(lang => lang.trim()).filter(Boolean)
        : [];
    },
    buildTtsDraft(modelId, voices, options = {}) {
      if (!Array.isArray(voices) || voices.length === 0) {
        return null;
      }
      const voiceDetails = voices.reduce((result, voice) => {
        if (voice && voice.id) {
          result[voice.id] = voice;
        }
        return result;
      }, {});
      const validVoices = Object.values(voiceDetails);
      if (validVoices.length === 0) {
        return null;
      }

      const allLanguages = new Set();
      validVoices.forEach((voice) => {
        this.splitVoiceLanguages(voice).forEach((language) => allLanguages.add(language));
      });
      const languageOptions = Array.from(allLanguages).map((language) => ({
        value: language,
        label: language
      }));
      const languageExists = (language) => language
        && languageOptions.some((option) => option.value === language);
      const preferredVoiceId = options.preferredVoiceId || this.form.ttsVoiceId;
      const preferredVoiceLanguage = this.splitVoiceLanguages(voiceDetails[preferredVoiceId])[0] || "";
      const languageCandidates = [
        options.preferredLanguage,
        preferredVoiceLanguage,
        this.form.ttsLanguage,
        this.selectedLanguage,
        languageOptions[0]?.value
      ];
      const preferredVoiceHasNoLanguage = Boolean(
        voiceDetails[preferredVoiceId]
        && this.splitVoiceLanguages(voiceDetails[preferredVoiceId]).length === 0
      );
      let language = options.preferredLanguage === "" && preferredVoiceHasNoLanguage
        ? ""
        : languageCandidates.find(languageExists) || "";
      const filterVoices = (targetLanguage) => validVoices.filter((voice) => {
        const languages = this.splitVoiceLanguages(voice);
        return languages.length === 0 || languages.includes(targetLanguage);
      });
      let filteredVoices = filterVoices(language);
      if (filteredVoices.length === 0) {
        const fallbackVoice = validVoices.find((voice) => this.splitVoiceLanguages(voice).length > 0);
        if (fallbackVoice) {
          language = this.splitVoiceLanguages(fallbackVoice)[0];
          filteredVoices = filterVoices(language);
        } else {
          filteredVoices = validVoices;
        }
      }
      if (filteredVoices.length === 0) {
        return null;
      }

      const preferredVoice = filteredVoices.find((voice) => voice.id === preferredVoiceId);
      const voice = preferredVoice || (options.autoSelectVoice ? filteredVoices[0] : null);
      return {
        modelId,
        language,
        voiceId: voice?.id || preferredVoiceId || "",
        voiceDetails,
        languageOptions,
        voiceOptions: filteredVoices.map((item) => ({
          value: item.id,
          label: item.name,
          voiceDemo: item.voiceDemo,
          voice_demo: item.voice_demo,
          isClone: Boolean(item.isClone),
          train_status: item.trainStatus
        }))
      };
    },
    applyTtsDraft(draft, options = {}) {
      this.form.model.ttsModelId = draft.modelId;
      this.voiceDetails = draft.voiceDetails;
      this.languageOptions = draft.languageOptions;
      this.voiceOptions = draft.voiceOptions;
      this.selectedLanguage = draft.language;
      this.form.ttsLanguage = draft.language;
      this.form.ttsVoiceId = draft.voiceId;
      if (options.markTouched) {
        this.ttsLanguageTouched = true;
        this.ttsVoiceTouched = true;
      }
      this.ttsSettings = {
        volume: this.form.ttsVolume !== null && this.form.ttsVolume !== undefined ? this.form.ttsVolume : 0,
        speed: this.form.ttsRate !== null && this.form.ttsRate !== undefined ? this.form.ttsRate : 0,
        pitch: this.form.ttsPitch !== null && this.form.ttsPitch !== undefined ? this.form.ttsPitch : 0
      };
    },
    handleVoiceOptionsFailure(requestSeq, rollbackState) {
      if (requestSeq !== this.voiceFetchSeq) {
        return;
      }
      this.voiceOptionsLoading = false;
      if (!this.restoreTtsDraft(rollbackState)) {
        this.voiceOptions = [];
        this.voiceDetails = {};
        this.languageOptions = [];
      }
      this.$message.error(i18n.t("ttsModel.fetchVoicesFailed"));
    },
    getVoiceDefaultLanguage(voiceId) {
      if (!voiceId || !this.voiceDetails || !this.voiceDetails[voiceId]?.languages) {
        return "";
      }
      const languages = this.voiceDetails[voiceId].languages
        .split(/[、；;,，]/)
        .map(lang => lang.trim())
        .filter(Boolean);
      return languages[0] || "";
    },
    
    // 根据语言筛选音色
    filterVoicesByLanguage(options = {}) {
      if (!this.voiceDetails || Object.keys(this.voiceDetails).length === 0) {
        this.voiceOptions = [];
        return;
      }

      const allVoices = Object.values(this.voiceDetails);

      // 根据选中的语言筛选音色
      const filteredVoices = allVoices.filter(voice => {
        const languagesArray = this.splitVoiceLanguages(voice);
        if (languagesArray.length === 0) {
          // 未声明语言的合法音色由 provider 自行解释，不在前端强制过滤。
          return true;
        }
        return languagesArray.includes(this.selectedLanguage);
      });

      this.voiceOptions = filteredVoices.map((voice) => ({
        value: voice.id,
        label: voice.name,
        voiceDemo: voice.voiceDemo,
        voice_demo: voice.voice_demo,
        isClone: Boolean(voice.isClone),
        train_status: voice.trainStatus,
      }));

      // 检查当前选中的音色是否支持当前语言，如果不支持则选择第一个
      const currentVoiceSupportsLanguage = this.form.ttsVoiceId &&
        filteredVoices.some(voice => voice.id === this.form.ttsVoiceId);

      if (!currentVoiceSupportsLanguage && options.autoSelectVoice) {
        this.form.ttsVoiceId = filteredVoices.length > 0 ? filteredVoices[0].id : '';
        this.ttsVoiceTouched = true;
      }

      // 同步到ttsSettings（如果值为null，使用0作为显示默认值，但不修改form中的值）
      this.ttsSettings = {
        volume: this.form.ttsVolume !== null && this.form.ttsVolume !== undefined ? this.form.ttsVolume : 0,
        speed: this.form.ttsRate !== null && this.form.ttsRate !== undefined ? this.form.ttsRate : 0,
        pitch: this.form.ttsPitch !== null && this.form.ttsPitch !== undefined ? this.form.ttsPitch : 0
      };
    },
    handleLanguageChange() {
      this.ttsLanguageTouched = true;
      this.form.ttsLanguage = this.selectedLanguage;
      this.filterVoicesByLanguage({ autoSelectVoice: true });
      if (this.form.ttsVoiceId) {
        this.lastValidTtsDraft = this.captureTtsDraft();
      }
    },
    handleVoiceChange() {
      this.ttsVoiceTouched = true;
      if (this.selectedLanguage) {
        this.form.ttsLanguage = this.selectedLanguage;
        this.ttsLanguageTouched = true;
      }
      if (this.form.ttsVoiceId) {
        this.lastValidTtsDraft = this.captureTtsDraft();
      }
    },
    shouldSubmitTtsLanguage() {
      return this.ttsLanguageTouched;
    },

    getFunctionDisplayChar(name) {
      if (!name || name.length === 0) return "";

      for (let i = 0; i < name.length; i++) {
        const char = name[i];
        if (/[\u4e00-\u9fa5a-zA-Z0-9]/.test(char)) {
          return char;
        }
      }

      // 如果没有找到有效字符，返回第一个字符
      return name.charAt(0);
    },
    showFunctionIcons(type) {
      return type === "Intent" && this.form.model.intentModelId !== "Intent_nointent";
    },
    handleModelChange(type, value) {
      if (type === "Intent" && value !== "Intent_nointent") {
        this.fetchAllFunctions().then((metadataReady) => {
          if (metadataReady) {
            this.enrichCurrentFunctionsWithMetadata();
          }
        });
      }
      if (type === "Memory") {
        if (value === "Memory_nomem") {
          // 无记忆功能的模型，默认不记录聊天记录
          this.form.chatHistoryConf = 0;
        } else {
          // 有记忆功能的模型，默认记录文本和语音
          this.form.chatHistoryConf = 2;
        }
        // Changing provider controls future behavior only. Existing local summaries
        // remain intact until the user explicitly clears legacy memory.
      }
      if (type === "LLM") {
        // 当LLM类型改变时，更新意图识别选项的可见性
        this.updateIntentOptionsVisibility();
      }
      if (type === "TTS") {
        const rollbackState = this.cloneTtsDraft(this.lastValidTtsDraft);
        this.fetchVoiceOptions(value, {
          autoSelectVoice: true,
          preferredLanguage: rollbackState?.language || this.selectedLanguage,
          rollbackState,
          markTouched: true
        });
      }
    },
    parsePluginFields(fields) {
      if (Array.isArray(fields)) {
        return fields;
      }
      if (typeof fields !== "string" || !fields.trim()) {
        return [];
      }
      try {
        const parsed = JSON.parse(fields);
        return Array.isArray(parsed) ? parsed : [];
      } catch (error) {
        return [];
      }
    },
    fetchAllFunctions(options = {}) {
      if (this.pluginMetadataReady) {
        return Promise.resolve(true);
      }
      if (this.pluginMetadataLoading) {
        return this.pluginMetadataLoading;
      }

      this.pluginMetadataLoading = new Promise((resolve) => {
        let settled = false;
        const finish = (ready, error) => {
          if (settled) {
            return;
          }
          settled = true;
          this.pluginMetadataReady = ready;
          if (!ready && options.showError !== false) {
            this.$message.error(error?.data?.msg || error?.msg || i18n.t("roleConfig.fetchPluginsFailed"));
          }
          resolve(ready);
        };

        Api.model.getPluginFunctionList(null, ({ data }) => {
          if (data?.code !== 0) {
            finish(false, data);
            return;
          }
          try {
            this.allFunctions = (data.data || []).map((item) => {
              const fieldsMeta = this.parsePluginFields(item.fields);
              const params = fieldsMeta.reduce((result, field) => {
                if (field?.key) {
                  result[field.key] = field.default;
                }
                return result;
              }, {});
              return { ...item, fieldsMeta, params };
            });
            finish(true);
          } catch (error) {
            finish(false, error);
          }
        }, (error) => finish(false, error));
      }).finally(() => {
        this.pluginMetadataLoading = null;
      });

      return this.pluginMetadataLoading;
    },
    openFunctionDialog() {
      if (this.agentReloading || !this.agentFunctionsLoaded) {
        return;
      }
      if (this.pluginMetadataReady) {
        this.enrichCurrentFunctionsWithMetadata();
        this.showFunctionDialog = true;
        return;
      }
      this.fetchAllFunctions().then((metadataReady) => {
        if (metadataReady) {
          this.enrichCurrentFunctionsWithMetadata();
          this.showFunctionDialog = true;
        }
      });
    },
    openContextProviderDialog() {
      this.showContextProviderDialog = true;
    },
    openTtsAdvancedSettings() {
      this.showTtsAdvancedDialog = true;
    },
    handleTtsSettingsSave(settings) {
      const { replacementWordIds, changedTtsFields = [], ...ttsSettings } = settings;
      this.checkedReplacementWordIds = replacementWordIds;
      // 保存TTS设置
      this.ttsSettings = ttsSettings;
      const changedFields = new Set(changedTtsFields);
      if (changedFields.has("volume")) {
        this.form.ttsVolume = ttsSettings.volume;
      }
      if (changedFields.has("speed")) {
        this.form.ttsRate = ttsSettings.speed;
      }
      if (changedFields.has("pitch")) {
        this.form.ttsPitch = ttsSettings.pitch;
      }
    },
    handleUpdateContext(providers) {
      this.currentContextProviders = providers;
    },
    handleUpdateFunctions(selected) {
      this.currentFunctions = selected;
    },
    handleDialogClosed(saved) {
      if (!saved) {
        this.currentFunctions = JSON.parse(JSON.stringify(this.originalFunctions));
      } else {
        this.originalFunctions = JSON.parse(JSON.stringify(this.currentFunctions));
      }
      this.showFunctionDialog = false;
    },
    updateIntentOptionsVisibility() {
      // 根据当前选择的LLM类型更新意图识别选项的可见性
      const currentLlmId = this.form.model.llmModelId;
      if (!currentLlmId || !this.modelOptions["Intent"]) return;

      const llmType = this.llmModeTypeMap.get(currentLlmId);
      if (!llmType) return;

      this.modelOptions["Intent"].forEach((item) => {
        if (item.value === "Intent_function_call") {
          // 如果llmType是openai或ollama，允许选择function_call
          // 否则隐藏function_call选项
          if (llmType === "openai" || llmType === "ollama") {
            item.isHidden = false;
          } else {
            item.isHidden = true;
          }
        } else {
          // 其他意图识别选项始终可见
          item.isHidden = false;
        }
      });

      // 如果当前选择的意图识别是function_call，但LLM类型不支持，则设置为可选的第一项
      if (
        this.form.model.intentModelId === "Intent_function_call" &&
        llmType !== "openai" &&
        llmType !== "ollama"
      ) {
        // 找到第一个可见的选项
        const firstVisibleOption = this.modelOptions["Intent"].find(
          (item) => !item.isHidden
        );
        if (firstVisibleOption) {
          this.form.model.intentModelId = firstVisibleOption.value;
        } else {
          // 如果没有可见选项，设置为Intent_nointent
          this.form.model.intentModelId = "Intent_nointent";
        }
      }
    },
    // 检查是否有音频预览
    hasAudioPreview(item) {
      // 检查是否为克隆音频
      // 使用后端实际返回的 isClone 字段
      const isCloneAudio = Boolean(item.isClone);
      
      // 检查是否有有效的音频URL，只使用后端实际返回的字段
      const hasValidAudioUrl = !!((item.voice_demo || item.voiceDemo)?.trim());
      
      // 克隆音频始终显示播放按钮，普通音频需要有有效URL才显示
      return isCloneAudio || hasValidAudioUrl;
    },

    // 播放/暂停音频切换
    toggleAudioPlayback(voiceId) {
      // 如果点击的是当前正在播放的音频，则切换暂停/播放状态
      if (this.playingVoice && this.currentPlayingVoiceId === voiceId) {
        if (this.isPaused) {
          // 从暂停状态恢复播放
          this.currentAudio.play().catch((error) => {
            console.error("恢复播放失败:", error);
            this.$message.warning(this.$t('roleConfig.cannotResumeAudio'));
          });
          this.isPaused = false;
        } else {
          // 暂停播放
          this.currentAudio.pause();
          this.isPaused = true;
        }
        return;
      }

      // 否则开始播放新的音频
      this.playVoicePreview(voiceId);
    },

    // 播放音色预览
    playVoicePreview(voiceId = null) {
      // 如果传入了voiceId，则使用传入的，否则使用当前选中的
      const targetVoiceId = voiceId || this.form.ttsVoiceId;

      if (!targetVoiceId) {
        this.$message.warning(this.$t('roleConfig.selectVoiceFirst'));
        return;
      }

      // 停止当前正在播放的音频
      if (this.currentAudio) {
        this.currentAudio.pause();
        this.currentAudio = null;
      }

      // 重置播放状态
      this.isPaused = false;
      this.currentPlayingVoiceId = targetVoiceId;

      try {
        // 从保存的音色详情中获取音频URL
        const voiceDetail = this.voiceDetails[targetVoiceId];

        // 添加调试信息
        console.log("当前选择的音色ID:", targetVoiceId);
        console.log("音色详情:", voiceDetail);

        // 尝试多种可能的音频属性名
        let audioUrl = null;
        let isCloneAudio = false;

        if (voiceDetail) {
          // 使用后端实际返回的 isClone 字段判断是否为克隆音频
          isCloneAudio = Boolean(voiceDetail.isClone);
          console.log(
            "克隆音频判断结果:",
            isCloneAudio,
            "训练状态:",
            voiceDetail.train_status
          );

          // 获取音频URL
          if (isCloneAudio && voiceDetail.id) {
            // 对于克隆音频，使用后端提供的正确接口
            // 注意：这里需要通过两步获取音频URL
            // 1. 首先获取音频下载ID
            // 2. 然后使用这个ID构建播放URL
            // 由于异步操作，我们需要先请求getAudioId
            console.log("检测到克隆音频，准备获取音频URL:", voiceDetail.id);

            // 创建一个Promise来处理异步获取音频URL的操作
            const getCloneAudioUrl = () => {
              return new Promise((resolve) => {
                // 首先调用getAudioId接口获取临时UUID
                RequestService.sendRequest()
                  .url(`${getServiceUrl()}/voiceClone/audio/${voiceDetail.id}`)
                  .method("POST")
                  .success((res) => {
                    if (res.data.code === 0 && res.data.data) {
                      // 处理返回的数据格式，在res.data基础上再套一层.data
                      const audioId = res.data.data;
                      console.log("获取到的音频ID:", audioId);
                      // 使用返回的UUID构建播放URL
                      const playUrl = `${getServiceUrl()}/voiceClone/play/${audioId}`;
                      console.log("构建克隆音频播放URL:", playUrl);
                      resolve(playUrl);
                    } else {
                      console.error("获取音频ID失败:", res.msg);
                      resolve(null);
                    }
                  })
                  .networkFail((err) => {
                    console.error("请求音频ID接口失败:", err);
                    resolve(null);
                  })
                  .send();
              });
            };

            // 设置播放状态
            this.playingVoice = true;
            // 创建Audio实例
            this.currentAudio = new Audio();
            // 设置音量
            this.currentAudio.volume = 1.0;

            // 设置超时，防止加载过长时间
            const timeoutId = setTimeout(() => {
              if (this.currentAudio && this.playingVoice) {
                this.$message.warning(this.$t('roleConfig.audioLoadTimeout'));
                this.playingVoice = false;
              }
            }, 10000); // 10秒超时

            // 监听播放错误
            this.currentAudio.onerror = () => {
              clearTimeout(timeoutId);
              console.error("克隆音频播放错误");
              this.$message.warning(this.$t('roleConfig.cloneAudioPlayFailed'));
              this.playingVoice = false;
            };

            // 监听播放开始，清除超时
            this.currentAudio.onplay = () => {
              clearTimeout(timeoutId);
            };

            // 监听播放结束
            this.currentAudio.onended = () => {
              this.playingVoice = false;
            };

            // 处理异步获取URL并播放
            getCloneAudioUrl().then((url) => {
              if (url) {
                // 设置音频URL并播放
                this.currentAudio.src = url;
                this.currentAudio.play().catch((error) => {
                  clearTimeout(timeoutId);
                  console.error("播放克隆音频失败:", error);
                  this.$message.warning(this.$t('roleConfig.cannotPlayCloneAudio'));
                  this.playingVoice = false;
                });
              } else {
                clearTimeout(timeoutId);
                this.$message.warning(this.$t('roleConfig.getCloneAudioFailed'));
                this.playingVoice = false;
              }
            });

            // 返回，避免继续执行下面的普通音频播放逻辑
            return;
          } else {
            // 对于普通音频，只使用后端实际返回的字段
            audioUrl =
              voiceDetail.voiceDemo ||
              voiceDetail.voice_demo;
          }

          // 如果没有找到，尝试检查是否有URL格式的字段
          if (!audioUrl) {
            for (const key in voiceDetail) {
              const value = voiceDetail[key];
              if (
                typeof value === "string" &&
                (value.startsWith("http://") ||
                  value.startsWith("https://") ||
                  value.endsWith(".mp3") ||
                  value.endsWith(".wav") ||
                  value.endsWith(".ogg"))
              ) {
                audioUrl = value;
                console.log(`发现可能的音频URL在字段 '${key}':`, audioUrl);
                break;
              }
            }
          }
        }

        if (!audioUrl) {
          // 如果没有音频URL，显示友好的提示
          this.$message.warning(this.$t('roleConfig.noPreviewAudio'));
          return;
        }

        // 非克隆音频的处理逻辑
        if (!isCloneAudio) {
          // 设置播放状态
          this.playingVoice = true;

          // 创建并播放音频
          this.currentAudio = new Audio();
          this.currentAudio.src = audioUrl;

          // 设置音量
          this.currentAudio.volume = 1.0;

          // 设置超时，防止加载过长时间
          const timeoutId = setTimeout(() => {
            if (this.currentAudio && this.playingVoice) {
              this.$message.warning(this.$t('roleConfig.audioLoadTimeout'));
              this.playingVoice = false;
            }
          }, 10000); // 10秒超时

          // 监听播放错误
          this.currentAudio.onerror = () => {
            clearTimeout(timeoutId);
            console.error("音频播放错误");
            this.$message.warning(this.$t('roleConfig.audioPlayFailed'));
            this.playingVoice = false;
          };

          // 监听播放开始，清除超时
          this.currentAudio.onplay = () => {
            clearTimeout(timeoutId);
          };

          // 监听播放结束
          this.currentAudio.onended = () => {
            this.playingVoice = false;
          };

          // 开始播放音频
          this.currentAudio.play().catch((error) => {
            clearTimeout(timeoutId);
            console.error("播放失败:", error);
            this.$message.warning(this.$t('roleConfig.cannotPlayAudio'));
            this.playingVoice = false;
          });
        }
      } catch (error) {
        console.error("播放音频过程出错:", error);
        this.$message.error(this.$t('roleConfig.audioPlayError'));
        this.playingVoice = false;
      }
    },
    updateChatHistoryConf() {
      if (this.form.model.memModelId === "Memory_nomem") {
        this.form.chatHistoryConf = 0;
      }
    },
    // 加载功能状态
    async loadFeatureStatus() {
      try {
        // 确保featureManager已初始化完成
        await featureManager.waitForInitialization();
        const config = featureManager.getConfig();
        this.featureStatus.voiceprintRecognition = config.voiceprintRecognition || false;
        this.featureStatus.vad = config.vad || false;
        this.featureStatus.asr = config.asr || false;
      } catch (error) {
        console.error("加载功能状态失败:", error);
      }
    },
    handleClose(id) {
      this.dynamicTags = this.dynamicTags.filter((item) => item.id !== id);
    },

    showInput() {
      this.inputVisible = true;
      this.$nextTick(_ => {
        this.$refs.saveTagInput.$refs.input.focus();
      });
    },

    handleInputConfirm() {
      let inputValue = this.inputValue;
      if (inputValue) {
        const tag = { id: `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, tagName: inputValue };
        this.dynamicTags.push(tag);
      }
      this.inputVisible = false;
      this.inputValue = '';
    },
    getAgentTags(agentId, options = {}) {
      const requestSeq = ++this.agentTagsFetchSeq;
      this.agentTagsLoaded = false;
      if (!agentId) {
        this.dynamicTags = [];
        this.originalTagNames = [];
        this.agentTagsLoaded = true;
        return Promise.resolve(true);
      }

      return new Promise((resolve) => {
        const handleFailure = (error) => {
          if (requestSeq !== this.agentTagsFetchSeq) {
            resolve(false);
            return;
          }
          this.agentTagsLoaded = false;
          if (options.showError !== false) {
            this.$message.error(error?.data?.msg || i18n.t("roleConfig.fetchConfigFailed"));
          }
          resolve(false);
        };
        Api.agent.getAgentTags(agentId, ({ data }) => {
          if (requestSeq !== this.agentTagsFetchSeq) {
            resolve(false);
            return;
          }
          if (data?.code === 0) {
            try {
              this.dynamicTags = Array.isArray(data.data) ? data.data : [];
              this.originalTagNames = this.dynamicTags.map(tag => tag.tagName);
              this.agentTagsLoaded = true;
              resolve(true);
            } catch (error) {
              handleFailure(error);
            }
          } else {
            handleFailure(data);
          }
        }, handleFailure);
      });
    },
    isSameStringList(left, right) {
      if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
        return false;
      }
      return left.every((value, index) => value === right[index]);
    },
    handleSaveAgentTags(agentId, tagNames = this.dynamicTags.map(tag => tag.tagName)) {
      return new Promise((resolve, reject) => {
        Api.agent.saveAgentTags(agentId, { tagNames }, ({ data }) => {
          if (data.code === 0) {
            this.originalTagNames = [...tagNames];
            resolve();
          } else {
            reject(data.msg);
          }
        });
      });
    }
  },
  beforeDestroy() {
    this.agentReloadSeq += 1;
    this.agentConfigFetchSeq += 1;
    this.agentTagsFetchSeq += 1;
    this.currentVersionFetchSeq += 1;
    this.voiceFetchSeq += 1;
  },
  async mounted() {
    this.lastValidTtsDraft = this.captureTtsDraft();
    const agentId = this.$route.query.agentId;
    if (agentId) {
      await this.reloadAgentPage(agentId);
    }
    await this.loadPersonaOptions();
    this.fetchModelOptions();
    this.fetchTemplates();
    // 加载功能状态，确保featureManager已初始化
    await this.loadFeatureStatus();
  },
};
</script>

<style lang="scss" scoped>
::v-deep .el-radio-group {
  .is-active {
    .el-radio-button__inner {
      &:hover {
        color: #fff !important;
      }
    }
  }
}
.welcome {
  min-width: 900px;
  height: 100vh;
  display: flex;
  position: relative;
  flex-direction: column;
  background: #eff4ff;
  background-size: cover;
  -webkit-background-size: cover;
  -o-background-size: cover;
  overflow: hidden;
}

.operation-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
}

.page-title {
  font-size: 24px;
  margin: 0;
  color: #2c3e50;
}

.main-wrapper {
  height: calc(100vh - 63px - 35px - 60px);
  margin: 0 22px;
  border-radius: 15px;
  position: relative;
  display: flex;
  flex-direction: column;
}

.content-panel {
  flex: 1;
  display: flex;
  overflow: hidden;
  height: 100%;
  border-radius: 15px;
  background: transparent;
  border: 1px solid #fff;
}

.content-area {
  flex: 1;
  height: 100%;
  min-width: 600px;
  overflow: auto;
  background-color: white;
  display: flex;
  flex-direction: column;
}

.config-card {
  background: white;
  border: none;
  box-shadow: none;
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow-y: auto;
}

.config-header {
  position: relative;
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 0 0 5px 0;
  font-weight: 700;
  font-size: 19px;
  color: #3d4566;
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 13px;
  flex-shrink: 0;
}

.header-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  padding-bottom: 4px;
  &::-webkit-scrollbar {
      height: 6px;
      background: #e6ebff;
    }
    &::-webkit-scrollbar-thumb {
      background: #5778ff;
      border-radius: 8px;
    }
}

.header-tags .el-tag {
  flex-shrink: 0;
}

.current-version-tag {
  flex-shrink: 0;
  padding: 3px 9px;
  border: 1px solid #dfe7ff;
  border-radius: 999px;
  background: #f4f7ff;
  color: #5778ff;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.5;
}

.more-tag {
  cursor: pointer;
  flex-shrink: 0;
}

.all-tags-popover {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px;
}

.header-icon {
  width: 37px;
  height: 37px;
  background: #5778ff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-icon img {
  width: 19px;
  height: 19px;
}

.divider {
  height: 1px;
  background: #e8f0ff;
}

.form-content {
  padding: 2vh 0;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.form-column {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-input {
  width: 100%;
}

.form-select {
  flex: 1;
  width: 100%;
  height: 36px;
}

.play-button {
  color: #409eff;
  transition: color 0.3s;
}

.play-button:hover {
  color: #66b1ff;
}

.play-button.is-loading {
  color: #909399;
}

.form-textarea {
  width: 100%;
}

.voice-select-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
}

.template-container {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.template-item {
  height: 4vh;
  min-width: 60px;
  padding: 0 12px;
  border-radius: 8px;
  background: #e6ebff;
  line-height: 4vh;
  font-weight: 400;
  font-size: 11px;
  text-align: center;
  color: #5778ff;
  cursor: pointer;
  transition: background-color 0.3s ease;
  white-space: nowrap;
}

.template-item:hover {
  background-color: #d0d8ff;
}

.model-select-wrapper {
  display: flex;
  align-items: center;
  width: 100%;
}

.legacy-memory-wrapper {
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #e3e9f5;
  border-radius: 8px;
  background: #fafbfe;
  box-sizing: border-box;
}

.legacy-memory-wrapper .form-select {
  flex: none;
  width: 100%;
}

.legacy-memory-item ::v-deep .el-form-item__label {
  width: 94px !important;
  white-space: nowrap;
}

.legacy-memory-item ::v-deep .el-form-item__content {
  margin-left: 94px !important;
}

.model-row {
  display: flex;
  gap: 20px;
  margin-bottom: 6px;
}

.model-row .model-item {
  flex: 1;
  margin-bottom: 0;
}

.model-row .language-select-item {
  flex: 0 0 35%;
  max-width: 35%;
}

.model-row .language-select-item .language-select {
  width: 100%;
}

.model-row .el-form-item__label {
  font-size: 12px !important;
  color: #3d4566 !important;
  font-weight: 400;
  line-height: 22px;
  padding-bottom: 2px;
}

.function-icons {
  display: flex;
  align-items: center;
  margin-left: auto;
  padding-left: 10px;
}

.icon-dot {
  width: 25px;
  height: 25px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #5778ff;
  font-weight: bold;
  font-size: 12px;
  margin-right: 8px;
  position: relative;
  background-color: #e6ebff;
}

::v-deep .el-form-item__label {
  font-size: 12px !important;
  color: #3d4566 !important;
  font-weight: 400;
  line-height: 22px;
  padding-bottom: 2px;
}

::v-deep .el-textarea .el-input__count {
  color: #909399;
  background: none;
  position: absolute;
  font-size: 12px;
  right: 3%;
}

.custom-close-btn {
  position: absolute;
  top: 25%;
  right: 0;
  transform: translateY(-50%);
  width: 35px;
  height: 35px;
  border-radius: 50%;
  border: 2px solid #cfcfcf;
  background: none;
  font-size: 30px;
  font-weight: lighter;
  color: #cfcfcf;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
  padding: 0;
  outline: none;
}

.custom-close-btn:hover {
  color: #409eff;
  border-color: #409eff;
}

.edit-function-btn {
  background: #e6ebff;
  color: #5778ff;
  border: 1px solid #adbdff;
  border-radius: 18px;
  padding: 10px 20px;
  transition: all 0.3s;
}

.edit-function-btn.active-btn {
  background: #5778ff;
  color: white;
}

.chat-history-options {
  display: flex;
  gap: 10px;
  min-width: 250px;
  justify-content: flex-end;
}

.chat-history-options ::v-deep .el-radio-button {
  border-color: #5778ff;
}

.chat-history-options ::v-deep .el-radio-button .el-radio-button__inner {
  color: #5778ff;
  border-color: #5778ff;
  background-color: transparent;
}

.chat-history-options ::v-deep .el-radio-button.is-active .el-radio-button__inner {
  background-color: #5778ff;
  border-color: #5778ff;
  color: white;
}

.chat-history-options ::v-deep .el-radio-button .el-radio-button__inner:hover {
  color: #5778ff;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.header-actions .hint-text {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #979db1;
  font-size: 12px;
  margin-right: 8px;
}

.header-actions .hint-text img {
  width: 16px;
  height: 16px;
}

.header-actions .save-btn {
  background: #5778ff;
  color: white;
  border: none;
  border-radius: 18px;
  padding: 8px 16px;
  height: 32px;
  font-size: 14px;
}

.header-actions .history-btn {
  background: #ffffff;
  color: #4d5b7c;
  border: 1px solid #d8dce8;
  border-radius: 18px;
  padding: 8px 16px;
  height: 32px;
  font-size: 14px;
}

.header-actions .reset-btn {
  background: #e6ebff;
  color: #5778ff;
  border: 1px solid #adbdff;
  border-radius: 18px;
  padding: 8px 16px;
  height: 32px;
}

.header-actions .custom-close-btn {
  position: static;
  transform: none;
  width: 32px;
  height: 32px;
  margin-left: 8px;
}

.save-state-tag {
  margin-left: 6px;
  padding: 3px 8px;
  border-radius: 10px;
  background: #eef9f3;
  color: #46a678;
  font-size: 11px;
}

.save-state-tag.dirty {
  background: #fff6e8;
  color: #d4932d;
}

.context-provider-item ::v-deep .el-form-item__label {
  line-height: 42px !important;
}

.doc-link {
  color: #5778ff;
  text-decoration: none;
  margin-left: 4px;

  &:hover {
    text-decoration: underline;
  }
}

.slider-wrapper {
  width: 100%;
  padding-right: 12px;
}

.companion-config {
  display: flex;
  flex-direction: column;
  width: 100%;
  gap: 8px;
}

.companion-heading,
.overlay-row,
.advanced-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.overlay-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid #e2e7f2;
  background: #f8faff;
  border-radius: 8px;
}

.overlay-editor.disabled {
  opacity: .72;
}

.overlay-row > * {
  flex: 1;
}

.proactive-settings {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: 10px;
  color: #7b849b;
  font-size: 12px;
}

.persona-option-meta {
  float: right;
  color: #909399;
  font-size: 12px;
}

.companion-summary {
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
}

.persona-state-hint {
  color: #909399;
  margin-top: 3px;
}

.effective-config {
  margin: 0 0 16px;
  padding: 12px 16px;
  border: 1px solid #dce6ff;
  border-radius: 10px;
  background: linear-gradient(135deg, #f7f9ff 0%, #f3fbff 100%);
}

.effective-config__title {
  color: #27345c;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}

.effective-config__items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.effective-config__items span {
  padding: 5px 9px;
  border: 1px solid #dce5f7;
  border-radius: 7px;
  background: #fff;
  color: #59627d;
  font-size: 12px;
}

.effective-config__items b {
  color: #697492;
  font-weight: 500;
  margin-right: 6px;
}

.effective-config__hint {
  margin-top: 8px;
  color: #9098ad;
  font-size: 11px;
}

.config-section-title {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 4px 0 10px;
  color: #26345c;
  font-size: 13px;
  font-weight: 600;
}

.config-section-title span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 6px;
  background: #e9efff;
  color: #5778ff;
  font-size: 11px;
}

.config-subsection-title {
  margin: 6px 0 8px 72px;
  color: #697492;
  font-size: 12px;
  font-weight: 600;
}

.advanced-section {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid #e8edf7;
}

.advanced-config-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 0 0 12px 72px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f7f8fb;
  color: #8a92a7;
  font-size: 11px;
}

.legacy-memory-controls {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 7px;
  width: 100%;
  margin-top: 0;
}

.legacy-memory-controls ::v-deep .el-alert {
  padding: 7px 10px;
}

.legacy-memory-controls ::v-deep .el-alert__title {
  line-height: 18px;
}

.legacy-memory-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 28px;
}

.intent-compatibility-alert {
  margin-top: 8px;
}

.danger-text-button {
  color: #f56c6c;
  padding: 0;
}

.template-scope-options {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin: 18px 0;
}

.template-preview-list {
  border: 1px solid #e5e9f2;
  border-radius: 8px;
  overflow: hidden;
}

.template-preview-list > div {
  display: grid;
  grid-template-columns: 95px 1fr;
  gap: 12px;
  padding: 9px 12px;
  color: #606a82;
  font-size: 12px;
  border-bottom: 1px solid #eef1f6;
}

.template-preview-list > div:last-child {
  border-bottom: 0;
}

.memory-edit-panel {
  margin: 14px 0;
  padding: 12px;
  border: 1px solid #dfe7f6;
  border-radius: 8px;
  background: #f8faff;
}

.memory-edit-row {
  display: grid;
  grid-template-columns: 60px minmax(220px, 1fr) 70px 210px;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  color: #66708a;
  font-size: 12px;
}

.memory-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}

.memory-empty {
  padding: 28px;
  text-align: center;
  color: #a2a8b7;
}

.companion-reset {
  color: #f56c6c;
  margin-left: 8px;
}

.slider-hint {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.5;
}

.tts-slider {
  width: 100%;
}

.tts-slider ::v-deep .el-slider__input {
  width: 80px;
}

.tts-slider ::v-deep .el-input__inner {
  text-align: center;
  padding: 0 8px;
}
.custom-tag {
  background: #e6ebff;
  color: #5778ff;
  border-radius: 8px;
  font-size: 12px;
  font-weight: normal;
  border: none;
}
.custom-tag-btn {
  background: #e6ebff;
  color: #5778ff;
  border-radius: 8px;
  font-weight: normal;
  border: 1px solid #e6ebff;
  &:hover {
    background-color: #d0d8ff;
  }
}
.input-new-tag {
  width: 90px;
  &::v-deep(.el-input__inner) {
    width: 90px !important;
  }
}

</style>

<style>
.custom-tooltip {
  max-width: 400px !important;
  word-break: break-word;
}
</style>
