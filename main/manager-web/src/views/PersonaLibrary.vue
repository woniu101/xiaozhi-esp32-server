<template>
  <div class="persona-page">
    <HeaderBar />
    <main class="page-body">
      <el-card shadow="never" class="library-card">
        <div class="page-head">
          <div class="page-head-copy">
            <span class="page-kicker">COMPANION CORE</span>
            <h2>{{ $t('persona.title') }}</h2>
            <p>{{ $t('persona.subtitle') }}</p>
          </div>
          <div class="head-actions">
            <el-tooltip :content="compilerMessage" placement="bottom">
              <button class="compiler-status" :class="`is-${compilerState}`" type="button" @click="loadHealth">
                <span class="status-dot"></span>
                {{ $t(`persona.compiler_${compilerState}`) }}
                <i class="el-icon-refresh"></i>
              </button>
            </el-tooltip>
            <el-button icon="el-icon-link" @click="openUrlImport">{{ $t('persona.importUrl') }}</el-button>
            <el-button type="primary" icon="el-icon-upload2" @click="$refs.zipInput.click()">
              {{ $t('persona.uploadZip') }}
            </el-button>
            <input ref="zipInput" class="hidden-input" type="file" accept=".zip,application/zip" @change="uploadZip" />
          </div>
        </div>

        <el-alert
          :title="$t('persona.identityNotice')"
          type="info"
          :closable="false"
          show-icon
          class="identity-notice"
        />

        <el-tabs v-model="activeTab" @tab-click="loadActiveTab">
          <el-tab-pane :label="$t('persona.myLibrary')" name="mine">
            <div class="toolbar tab-toolbar">
              <el-input v-model.trim="localKeyword" clearable prefix-icon="el-icon-search"
                :placeholder="$t('persona.searchMine')" />
              <el-button icon="el-icon-refresh" @click="loadPersonas">{{ $t('persona.refresh') }}</el-button>
            </div>
            <div v-loading="loadingMine" class="content-stage">
              <div v-if="filteredPersonas.length" class="persona-grid">
                <article v-for="item in filteredPersonas" :key="item.personaId" class="persona-card owned-card">
                  <div class="card-visual" :class="accentClass(item.personaId)">
                    <span class="visual-label">MY PERSONA</span>
                    <div class="avatar">
                      {{ displayInitial(item.displayName || item.personaId) }}
                    </div>
                    <el-tag class="state-tag" size="mini" effect="dark" :type="item.pendingVersion ? 'warning' : (item.publishedVersion ? 'success' : 'info')">
                      {{ item.pendingVersion ? $t('persona.updatePending') : (item.publishedVersion ? $t('persona.enabled') : $t('persona.notEnabled')) }}
                    </el-tag>
                  </div>
                  <div class="card-content">
                    <div class="card-heading owned-heading">
                      <h3 :title="item.displayName || item.personaId">{{ item.displayName || item.personaId }}</h3>
                      <span :title="item.personaId">{{ item.personaId }}</span>
                    </div>
                    <p class="card-description">{{ item.description || $t('persona.noDescription') }}</p>
                    <div class="card-meta">
                      <span><i class="el-icon-connection"></i>{{ $t('persona.ceiling') }} · {{ item.relationshipCeiling || '-' }}</span>
                      <span v-if="item.personaKind"><i class="el-icon-user"></i>{{ kindLabel(item.personaKind) }}</span>
                    </div>
                  </div>
                  <div class="card-actions">
                    <el-button size="small" icon="el-icon-setting" @click="showDetail(item)">{{ $t('persona.managePersona') }}</el-button>
                    <el-button v-if="item.owned" size="small" icon="el-icon-upload2" @click="openUpgradeDialog(item)">
                      {{ $t('persona.importNewVersion') }}
                    </el-button>
                    <el-button v-if="item.publishedVersion" size="small" type="primary" icon="el-icon-link" @click="bindPersona(item)">
                      {{ $t('persona.bindAgent') }}
                    </el-button>
                  </div>
                </article>
              </div>
              <el-empty v-else-if="!loadingMine" class="library-empty" :description="$t('persona.emptyMine')" />
            </div>
          </el-tab-pane>

          <el-tab-pane :label="$t('persona.onlineGallery')" name="gallery">
            <div class="toolbar tab-toolbar">
              <el-input v-model.trim="galleryKeyword" clearable prefix-icon="el-icon-search"
                :placeholder="$t('persona.searchGallery')" @keyup.enter.native="loadGallery" />
              <el-button type="primary" icon="el-icon-search" @click="loadGallery">{{ $t('persona.search') }}</el-button>
            </div>
            <div v-loading="loadingGallery" class="content-stage">
              <div v-if="gallery.length" class="persona-grid gallery-grid">
                <article v-for="item in gallery" :key="item.externalId" class="persona-card gallery-card">
                  <div class="card-visual" :class="accentClass(item.externalId || item.name)">
                    <span class="visual-label">DOT-SKILL</span>
                    <div class="avatar">
                      {{ displayInitial(item.name) }}
                    </div>
                    <el-tag class="source-tag" size="mini" effect="dark">dot-skill</el-tag>
                  </div>
                  <div class="card-content">
                    <div class="card-heading">
                      <h3 :title="item.name">{{ item.name }}</h3>
                      <span>{{ item.personaMode || item.type || 'dot-skill persona' }}</span>
                    </div>
                    <p class="card-description">{{ item.description || item.descriptionEn || $t('persona.noDescription') }}</p>
                    <div class="tag-row">
                      <span v-for="tag in galleryTags(item)" :key="tag" class="skill-tag">{{ tag }}</span>
                    </div>
                  </div>
                  <div class="card-actions">
                    <el-button size="small" icon="el-icon-view" @click="openExternal(item.galleryUrl)">{{ $t('persona.viewSource') }}</el-button>
                    <el-button size="small" type="primary" icon="el-icon-download" @click="startGalleryImport(item)">{{ $t('persona.oneClickImport') }}</el-button>
                  </div>
                </article>
              </div>
              <el-empty v-else-if="!loadingGallery" class="library-empty" :description="$t('persona.emptyGallery')" />
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </main>

    <el-dialog :title="$t('persona.importUrlTitle')" :visible.sync="urlDialog" width="520px">
      <el-form label-position="top">
        <el-form-item :label="$t('persona.githubUrl')">
          <el-input v-model.trim="urlForm.url" placeholder="https://github.com/owner/repository" />
        </el-form-item>
        <el-form-item :label="$t('persona.gitRef')">
          <el-input v-model.trim="urlForm.ref" :placeholder="$t('persona.gitRefHint')" />
        </el-form-item>
      </el-form>
      <span slot="footer">
        <el-button @click="urlDialog = false">{{ $t('button.cancel') }}</el-button>
        <el-button type="primary" :loading="creatingJob" @click="submitUrlImport">{{ $t('persona.beginInspect') }}</el-button>
      </span>
    </el-dialog>

    <el-dialog :title="$t('persona.importProgress')" :visible.sync="progressDialog" width="620px" :close-on-click-modal="false">
      <el-steps :active="jobStep" align-center finish-status="success">
        <el-step :title="$t('persona.stepSource')" />
        <el-step :title="$t('persona.stepCompile')" />
        <el-step :title="$t('persona.stepReady')" />
      </el-steps>
      <el-progress :percentage="Number(currentJob.progress || 0)" :status="currentJob.status === 'failed' ? 'exception' : undefined" />
      <div class="job-status" :class="{ 'is-error': currentJob.status === 'failed' || currentJob.status === 'validation_failed' }">
        <div class="job-status-title">
          <i :class="jobStatusIcon"></i>
          <strong>{{ statusText(currentJob.status) }}</strong>
        </div>
        <span v-if="currentJob.errorMessage">{{ currentJob.errorMessage }}</span>
        <div v-if="compilerFailure" class="compiler-help">
          <i class="el-icon-warning-outline"></i>
          <span>{{ $t('persona.compilerFailureHelp') }}</span>
          <el-button type="text" size="mini" @click="loadHealth">{{ $t('persona.recheckCompiler') }}</el-button>
        </div>
      </div>
      <div v-if="currentJob.compileResult" class="compile-preview">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="$t('persona.personaId')">{{ currentJob.compileResult.personaId }}</el-descriptions-item>
          <el-descriptions-item :label="$t('persona.version')">{{ compiledVersion }}</el-descriptions-item>
          <el-descriptions-item :label="$t('persona.score')">{{ reportScore }}</el-descriptions-item>
          <el-descriptions-item :label="$t('persona.publishGate')">{{ currentJob.compileResult.publishable ? 'PASS' : 'BLOCKED' }}</el-descriptions-item>
        </el-descriptions>
        <el-collapse>
          <el-collapse-item :title="$t('persona.runtimePrompt')"><pre>{{ currentJob.compileResult.runtimePrompt }}</pre></el-collapse-item>
          <el-collapse-item :title="$t('persona.canonicalSpec')"><pre>{{ pretty(currentJob.compileResult.canonicalSpec) }}</pre></el-collapse-item>
          <el-collapse-item :title="$t('persona.validationReport')"><pre>{{ pretty(currentJob.compileResult.validationReport) }}</pre></el-collapse-item>
          <el-collapse-item :title="$t('persona.testReport')"><pre>{{ pretty(currentJob.compileResult.testReport) }}</pre></el-collapse-item>
          <el-collapse-item :title="$t('persona.judgeReport')"><pre>{{ pretty(currentJob.compileResult.judgeReport) }}</pre></el-collapse-item>
        </el-collapse>
        <el-alert v-if="currentJob.compileResult.recompileUnchanged" type="success" :closable="false" show-icon
          :title="$t('persona.recompileUnchanged')" class="recompile-result" />
        <el-alert v-else-if="currentJob.compileResult.recompiled" type="success" :closable="false" show-icon
          :title="$t('persona.recompileCreated', {
            version: compiledVersion,
            count: currentJob.compileResult.inheritedSignatureAudioCount || 0
          })" class="recompile-result" />
        <div class="preview-actions" v-if="currentJob.status === 'ready' && !currentJob.compileResult.recompileUnchanged">
          <el-button v-if="currentJob.compileResult.recompiled" icon="el-icon-document-copy" @click="showRecompileDiff">
            {{ $t('persona.reviewRevisionDiff') }}
          </el-button>
          <el-button type="success" :loading="publishing" @click="applyCompiled">{{ $t('persona.applyUpdate') }}</el-button>
        </div>
      </div>
      <span v-if="cancelableJob" slot="footer">
        <el-button type="danger" plain @click="cancelCurrentImport">{{ $t('persona.cancelImport') }}</el-button>
      </span>
    </el-dialog>

    <el-dialog :title="detail.displayName || detail.personaId" :visible.sync="detailDialog" width="860px">
      <el-descriptions :column="2" border>
        <el-descriptions-item :label="$t('persona.personaId')">{{ detail.personaId }}</el-descriptions-item>
        <el-descriptions-item :label="$t('persona.ceiling')">{{ detail.relationshipCeiling }}</el-descriptions-item>
        <el-descriptions-item :label="$t('persona.currentVersion')">{{ detail.publishedVersion || $t('persona.notEnabled') }}</el-descriptions-item>
      </el-descriptions>
      <div v-if="detail.owned" class="version-management-bar">
        <div>
          <strong>{{ $t('persona.upgradeTitle') }}</strong>
          <span>{{ $t('persona.upgradeBehaviorHint') }}</span>
        </div>
        <el-button size="small" type="primary" plain icon="el-icon-upload2" @click="openUpgradeDialog(detail)">
          {{ $t('persona.importNewVersion') }}
        </el-button>
      </div>
      <div class="section-head"><h3>{{ $t('persona.lifecycleTitle') }}</h3>
        <el-button v-if="currentLifecycle && candidateLifecycle" size="mini" icon="el-icon-document-copy"
          @click="comparePendingUpdate">{{ $t('persona.comparePending') }}</el-button>
      </div>
      <el-table :data="versions" v-loading="loadingVersions" class="versions-table">
        <el-table-column :label="$t('persona.lifecycleRole')" width="105">
          <template slot-scope="scope"><el-tag size="mini" :type="lifecycleTagType(scope.row.lifecycleRole)">{{ lifecycleLabel(scope.row.lifecycleRole) }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="version" :label="$t('persona.internalVersion')" min-width="125" />
        <el-table-column prop="qualityScore" :label="$t('persona.score')" width="72" />
        <el-table-column prop="testStatus" :label="$t('persona.test')" width="82" />
        <el-table-column :label="$t('persona.actions')" min-width="355">
          <template slot-scope="scope">
            <div class="version-actions">
              <el-button type="text" @click="viewVersion(scope.row)">{{ $t('persona.preview') }}</el-button>
              <el-button v-if="detail.owned" type="text" icon="el-icon-microphone" @click="openSignatureManager(scope.row)">
                {{ $t('persona.signatureManager') }}
              </el-button>
              <el-button v-if="detail.owned && scope.row.lifecycleRole !== 'previous'" type="text"
                @click="openRecompileDialog(scope.row)">{{ $t('persona.recompile') }}</el-button>
              <el-button v-if="detail.owned" type="text" :loading="scope.row._testing" @click="rerunTest(scope.row)">{{ $t('persona.rerunTest') }}</el-button>
              <el-button v-if="detail.owned" type="text" @click="openConversationTest(scope.row)">{{ $t('persona.conversationTest') }}</el-button>
              <el-button v-if="detail.owned && scope.row.lifecycleRole === 'candidate'" type="text" @click="applyVersion(scope.row)">{{ $t('persona.applyUpdate') }}</el-button>
              <el-button v-if="detail.owned && scope.row.lifecycleRole === 'previous'" type="text" @click="restorePrevious">{{ $t('persona.restorePrevious') }}</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="detail.owned" class="persona-danger-zone">
        <div>
          <strong>{{ $t('persona.deletePersona') }}</strong>
          <span>{{ $t('persona.deletePersonaHint') }}</span>
        </div>
        <el-button type="danger" plain size="small" icon="el-icon-delete" @click="deletePersona(detail)">
          {{ $t('persona.deletePersona') }}
        </el-button>
      </div>
    </el-dialog>

    <el-dialog :title="$t('persona.upgradeTitle')" :visible.sync="upgradeDialog" width="560px">
      <el-alert type="info" :closable="false" show-icon
        :title="$t('persona.upgradeTargetHint', { id: upgradeTarget.personaId || '-' })" />
      <div class="upgrade-options">
        <button v-if="upgradeTarget.sourceUrl" class="upgrade-option" type="button" :disabled="creatingJob" @click="startUpgradeFromSource">
          <i class="el-icon-link"></i>
          <span><strong>{{ $t('persona.upgradeFromSource') }}</strong><small>{{ upgradeTarget.sourceUrl }}</small></span>
          <i class="el-icon-arrow-right"></i>
        </button>
        <button class="upgrade-option" type="button" :disabled="creatingJob" @click="chooseUpgradeZip">
          <i class="el-icon-upload2"></i>
          <span><strong>{{ $t('persona.upgradeFromZip') }}</strong><small>{{ $t('persona.upgradeZipHint') }}</small></span>
          <i class="el-icon-arrow-right"></i>
        </button>
      </div>
      <input ref="upgradeZipInput" class="hidden-input" type="file" accept=".zip,application/zip" @change="uploadUpgradeZip" />
    </el-dialog>

    <el-dialog :title="$t('persona.recompileTitle')" :visible.sync="recompileDialog" width="600px">
      <el-alert type="info" :closable="false" show-icon
        :title="$t('persona.recompileHint', { version: recompileTarget.version || '-' })" />
      <el-descriptions :column="1" border size="small" class="recompile-source">
        <el-descriptions-item :label="$t('persona.version')">{{ recompileTarget.version || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="$t('persona.compilerVersion')">{{ recompileTarget.compilerVersion || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="$t('persona.sourceCommit')">{{ recompileTarget.sourceCommit || '-' }}</el-descriptions-item>
      </el-descriptions>
      <el-checkbox v-model="inheritSignatureAudio" class="recompile-inherit">
        {{ $t('persona.inheritSignatureAudio') }}
      </el-checkbox>
      <p class="recompile-note">{{ $t('persona.inheritSignatureAudioHint') }}</p>
      <div class="upgrade-options">
        <button class="upgrade-option" type="button" :disabled="creatingJob" @click="startRecompile">
          <i class="el-icon-refresh"></i>
          <span><strong>{{ $t('persona.recompileFromSnapshot') }}</strong><small>{{ $t('persona.recompileFromSnapshotHint') }}</small></span>
          <i class="el-icon-arrow-right"></i>
        </button>
        <button class="upgrade-option" type="button" :disabled="creatingJob" @click="chooseRecompileZip">
          <i class="el-icon-upload2"></i>
          <span><strong>{{ $t('persona.recompileFromZip') }}</strong><small>{{ $t('persona.recompileZipHint') }}</small></span>
          <i class="el-icon-arrow-right"></i>
        </button>
      </div>
      <input ref="recompileZipInput" class="hidden-input" type="file" accept=".zip,application/zip" @change="uploadRecompileZip" />
    </el-dialog>

    <el-dialog :title="$t('persona.versionPreview')" :visible.sync="versionDialog" width="800px">
      <el-tabs><el-tab-pane :label="$t('persona.runtimePrompt')"><pre>{{ versionDetail.runtimePrompt }}</pre></el-tab-pane>
        <el-tab-pane :label="$t('persona.canonicalSpec')"><pre>{{ pretty(versionDetail.canonicalSpec) }}</pre></el-tab-pane>
        <el-tab-pane :label="$t('persona.testReport')"><pre>{{ pretty(versionDetail.testReport) }}</pre></el-tab-pane></el-tabs>
    </el-dialog>
    <el-dialog :title="$t('persona.signatureManager')" :visible.sync="signatureDialog" width="920px" append-to-body>
      <div class="signature-toolbar">
        <div>
          <strong>{{ detail.displayName || detail.personaId }} · {{ signatureVersion }}</strong>
          <span>{{ $t('persona.signatureManagerHint') }}</span>
        </div>
        <el-button type="primary" size="small" icon="el-icon-plus" @click="editSignature()">
          {{ $t('persona.addSignature') }}
        </el-button>
      </div>
      <div v-loading="loadingSignatures" class="signature-list">
        <el-empty v-if="!loadingSignatures && !signatures.length" :description="$t('persona.emptySignatures')" />
        <article v-for="item in signatures" :key="item.id" class="signature-card"
          :class="{ 'is-disabled': item.enabled === false }">
          <div class="signature-copy">
            <div class="signature-title">
              <strong>{{ item.display_text }}</strong>
              <el-tag size="mini" :type="item.origin === 'skill' ? 'info' : 'success'">
                {{ item.origin === 'skill' ? 'Skill' : $t('persona.customSignature') }}
              </el-tag>
              <el-tag size="mini" :type="item.enabled === false ? 'danger' : 'success'">
                {{ item.enabled === false ? $t('persona.signatureDisabled') : $t('persona.signatureEnabled') }}
              </el-tag>
              <code>{{ item.id }}</code>
            </div>
            <p>{{ item.semantic_rule }}</p>
            <small v-if="item.explicit_aliases && item.explicit_aliases.length">
              {{ $t('persona.signatureAliases') }}：{{ item.explicit_aliases.join('、') }}
            </small>
          </div>
          <div class="signature-variants">
            <div v-for="variant in signatureVariants" :key="`${item.id}-${variant}`" class="signature-variant">
              <span>{{ signatureVariantLabel(variant) }}</span>
              <template v-if="assetFor(item, variant)">
                <el-button type="text" icon="el-icon-video-play" @click="previewSignatureAsset(assetFor(item, variant))">
                  {{ $t('persona.listen') }}
                </el-button>
                <el-button type="text" :disabled="item.enabled === false" @click="chooseSignatureAsset(item, variant)">{{ $t('persona.replaceAudio') }}</el-button>
                <el-button type="text" class="danger" @click="removeSignatureAsset(assetFor(item, variant))">
                  {{ $t('persona.deleteAudio') }}
                </el-button>
              </template>
              <el-button v-else type="text" icon="el-icon-upload2" :disabled="item.enabled === false" @click="chooseSignatureAsset(item, variant)">
                {{ $t('persona.uploadAudio') }}
              </el-button>
            </div>
          </div>
          <div class="signature-actions">
            <el-button size="mini" plain :type="item.enabled === false ? 'success' : 'warning'"
              :loading="item._toggling" @click="toggleSignature(item)">
              {{ item.enabled === false ? $t('persona.enableSignature') : $t('persona.disableSignature') }}
            </el-button>
            <el-button size="mini" plain @click="editSignature(item)">{{ $t('persona.editRule') }}</el-button>
          </div>
        </article>
      </div>
      <input ref="signatureAudioInput" class="hidden-input" type="file" accept=".wav,.mp3,.ogg,audio/wav,audio/mpeg,audio/ogg" @change="uploadSignatureAudio" />
    </el-dialog>
    <el-dialog :title="$t('persona.editSignature')" :visible.sync="signatureEditorDialog" width="700px"
      top="4vh" custom-class="signature-editor-dialog" append-to-body>
      <el-alert v-if="signatureRuleReadOnly" type="info" :closable="false" show-icon
        :title="$t('persona.skillSignatureReadOnly')" class="signature-editor-alert" />
      <el-alert v-else-if="signatureForm.origin === 'skill' && signatureForm.customizing" type="warning" :closable="false" show-icon
        :title="$t('persona.skillSignatureOverrideHint')" class="signature-editor-alert" />
      <el-form class="signature-editor-form" label-position="top" size="small">
        <el-form-item :label="$t('persona.signatureId')">
          <el-input v-model.trim="signatureForm.id" :disabled="signatureForm.editing" placeholder="ciallo" />
        </el-form-item>
        <el-form-item :label="$t('persona.signatureText')">
          <el-input v-model.trim="signatureForm.displayText" :disabled="signatureRuleReadOnly" placeholder="Ciallo～(∠・ω< )⌒★" />
        </el-form-item>
        <el-form-item :label="$t('persona.signatureAliases')">
          <el-input v-model.trim="signatureForm.aliasesText" :disabled="signatureRuleReadOnly" :placeholder="$t('persona.signatureAliasesHint')" />
        </el-form-item>
        <el-form-item :label="$t('persona.signatureRule')">
          <el-input v-model.trim="signatureForm.semanticRule" :disabled="signatureRuleReadOnly" type="textarea" :rows="4" :placeholder="$t('persona.signatureRuleHint')" />
        </el-form-item>
        <el-form-item :label="$t('persona.signatureExamples')">
          <el-input v-model="signatureForm.examplesText" :disabled="signatureRuleReadOnly" type="textarea" :rows="2" :placeholder="$t('persona.signatureExamplesHint')" />
        </el-form-item>
      </el-form>
      <section class="signature-editor-assets">
        <div class="signature-editor-assets-head">
          <div><strong>{{ $t('persona.signatureRecordings') }}</strong><span>{{ $t('persona.signatureAudioAnchorHint') }}</span></div>
          <el-tag v-if="!signatureForm.editing" size="mini" type="info">{{ $t('persona.saveBeforeUpload') }}</el-tag>
        </div>
        <div v-for="variant in signatureVariants" :key="`editor-${variant}`" class="signature-variant">
          <span>{{ signatureVariantLabel(variant) }}</span>
          <template v-if="assetFor(signatureEditorItem, variant)">
            <el-button type="text" icon="el-icon-video-play" @click="previewSignatureAsset(assetFor(signatureEditorItem, variant))">{{ $t('persona.listen') }}</el-button>
            <el-button type="text" @click="chooseSignatureAsset(signatureEditorItem, variant)">{{ $t('persona.replaceAudio') }}</el-button>
            <el-button type="text" class="danger" @click="removeSignatureAsset(assetFor(signatureEditorItem, variant))">{{ $t('persona.deleteAudio') }}</el-button>
          </template>
          <el-button v-else type="text" icon="el-icon-upload2" :disabled="!signatureForm.editing"
            @click="chooseSignatureAsset(signatureEditorItem, variant)">{{ $t('persona.uploadAudio') }}</el-button>
        </div>
      </section>
      <span slot="footer">
        <el-button @click="signatureEditorDialog = false">{{ $t('button.close') }}</el-button>
        <el-button v-if="signatureRuleReadOnly" type="primary" plain @click="signatureForm.customizing = true">{{ $t('persona.customizeSignatureRule') }}</el-button>
        <el-button v-else type="primary" :loading="savingSignature" @click="saveSignature">{{ $t('button.save') }}</el-button>
      </span>
    </el-dialog>
    <el-dialog :title="$t('persona.versionDiff')" :visible.sync="diffDialog" width="800px">
      <el-table :data="diffResult.changes || []">
        <el-table-column prop="path" :label="$t('persona.field')" width="180" />
        <el-table-column :label="$t('persona.before')"><template slot-scope="scope"><pre class="diff-value">{{ pretty(scope.row.before) }}</pre></template></el-table-column>
        <el-table-column :label="$t('persona.after')"><template slot-scope="scope"><pre class="diff-value">{{ pretty(scope.row.after) }}</pre></template></el-table-column>
      </el-table>
    </el-dialog>
    <el-dialog :title="$t('persona.conversationTest')" :visible.sync="conversationTestDialog" width="760px">
      <el-alert type="info" :closable="false" show-icon :title="$t('persona.conversationTestHint')" />
      <el-input v-model="conversationSamplesJson" type="textarea" :rows="13"
        class="conversation-samples" :placeholder="$t('persona.conversationTestPlaceholder')" />
      <pre v-if="conversationTestReport" class="conversation-report">{{ pretty(conversationTestReport) }}</pre>
      <span slot="footer">
        <el-button @click="conversationTestDialog = false">{{ $t('button.cancel') }}</el-button>
        <el-button type="primary" :loading="conversationTestRunning" @click="runConversationTest">
          {{ $t('persona.runConversationTest') }}
        </el-button>
      </span>
    </el-dialog>
    <el-dialog :title="$t('persona.chooseAgent')" :visible.sync="agentDialog" width="500px">
      <el-select v-model="selectedAgentId" filterable style="width:100%" :placeholder="$t('persona.chooseAgentHint')">
        <el-option v-for="agent in agents" :key="agent.id" :value="agent.id" :label="agent.agentName || agent.name || agent.id" />
      </el-select>
      <span slot="footer">
        <el-button @click="agentDialog = false">{{ $t('button.cancel') }}</el-button>
        <el-button type="primary" :disabled="!selectedAgentId" @click="continueBinding">{{ $t('persona.continueConfig') }}</el-button>
      </span>
    </el-dialog>
    <VersionFooter />
  </div>
</template>

<script>
import Api from '@/apis/api'
import HeaderBar from '@/components/HeaderBar.vue'
import VersionFooter from '@/components/VersionFooter.vue'

const TERMINAL_IMPORT_STATUSES = ['ready', 'validation_failed', 'failed', 'cancelled']

export default {
  name: 'PersonaLibrary',
  components: { HeaderBar, VersionFooter },
  data() {
    return {
      activeTab: 'mine', loadingMine: false, loadingGallery: false,
      personas: [], gallery: [], localKeyword: '', galleryKeyword: '',
      compilerState: 'checking', compilerMessage: '',
      urlDialog: false, creatingJob: false, urlForm: { url: '', ref: '' },
      progressDialog: false, currentJob: {}, pollTimer: null,
      publishing: false,
      detailDialog: false, detail: {}, versions: [], loadingVersions: false,
      versionDialog: false, versionDetail: {},
      agentDialog: false, agents: [], selectedAgentId: '', bindingPersonaId: '',
      diffDialog: false, diffResult: {},
      conversationTestDialog: false, conversationTestRow: null,
      conversationSamplesJson: '', conversationTestRunning: false, conversationTestReport: null,
      upgradeDialog: false, upgradeTarget: {},
      recompileDialog: false, recompileTarget: {}, inheritSignatureAudio: true,
      signatureDialog: false, signatureEditorDialog: false, signatureVersion: '',
      signatures: [], loadingSignatures: false, savingSignature: false,
      signatureVariants: ['classic', 'playful', 'soft'], signatureUploadTarget: null,
      signatureForm: {
        id: '', displayText: '', aliasesText: '', semanticRule: '', examplesText: '',
        editing: false, origin: 'custom', customizing: true, item: null
      },
      signatureAudio: null, signatureAudioUrl: ''
    }
  },
  computed: {
    filteredPersonas() {
      const query = this.localKeyword.toLowerCase()
      if (!query) return this.personas
      return this.personas.filter(item => `${item.displayName} ${item.personaId} ${item.description}`.toLowerCase().includes(query))
    },
    currentLifecycle() {
      return this.versions.find(item => item.lifecycleRole === 'current') || null
    },
    candidateLifecycle() {
      return this.versions.find(item => item.lifecycleRole === 'candidate') || null
    },
    jobStep() {
      const status = this.currentJob.status
      if (status === 'ready') return 3
      if (['compiling', 'validating', 'validation_failed'].includes(status)) return 2
      return 1
    },
    compiledVersion() {
      return this.currentJob.compileResult?.version || this.currentJob.compileResult?.suggestedVersion || '-'
    },
    reportScore() {
      return this.currentJob.compileResult?.testReport?.score ?? '-'
    },
    cancelableJob() {
      return Boolean(this.currentJob.id)
        && !['ready', 'validation_failed', 'failed', 'cancelled'].includes(this.currentJob.status)
    },
    compilerFailure() {
      return this.currentJob.status === 'failed'
        && /compiler/i.test(`${this.currentJob.errorCode || ''} ${this.currentJob.errorMessage || ''}`)
    },
    jobStatusIcon() {
      if (this.currentJob.status === 'ready') return 'el-icon-circle-check'
      if (['failed', 'validation_failed'].includes(this.currentJob.status)) return 'el-icon-circle-close'
      if (this.currentJob.status === 'cancelled') return 'el-icon-warning-outline'
      return 'el-icon-loading'
    },
    signatureRuleReadOnly() {
      return this.signatureForm.editing
        && this.signatureForm.origin === 'skill'
        && !this.signatureForm.customizing
    },
    signatureEditorItem() {
      return this.signatureForm.item || {
        id: this.signatureForm.id,
        asset_metadata: []
      }
    }
  },
  mounted() {
    this.loadPersonas()
    this.loadHealth()
    const activeJobId = window.localStorage.getItem('personaImportJobId')
    if (activeJobId) this.resumeJob(activeJobId)
  },
  beforeDestroy() { this.stopPolling(); this.stopSignatureAudio() },
  methods: {
    ok(response) { return response?.data?.code === 0 ? response.data.data : null },
    loadActiveTab() { if (this.activeTab === 'gallery') this.loadGallery(); else this.loadPersonas() },
    loadPersonas() {
      this.loadingMine = true
      Api.persona.list((response) => { this.personas = this.ok(response) || []; this.loadingMine = false }, () => { this.loadingMine = false })
    },
    loadHealth() {
      this.compilerState = 'checking'
      this.compilerMessage = this.$t('persona.compilerCheckingHint')
      Api.persona.health((response) => {
        const health = this.ok(response) || {}
        const compiler = health.compiler || {}
        this.compilerState = compiler.status === 'up' ? 'online' : 'offline'
        this.compilerMessage = compiler.message || (this.compilerState === 'online'
          ? this.$t('persona.compilerOnlineHint')
          : this.$t('persona.compilerOfflineHint'))
      }, () => {
        this.compilerState = 'offline'
        this.compilerMessage = this.$t('persona.compilerOfflineHint')
      })
    },
    loadGallery() {
      this.loadingGallery = true
      Api.persona.gallery(this.galleryKeyword, (response) => { this.gallery = this.ok(response) || []; this.loadingGallery = false }, () => { this.loadingGallery = false })
    },
    openUrlImport() { this.urlForm = { url: '', ref: '' }; this.urlDialog = true },
    submitUrlImport() {
      if (!/^https:\/\/github\.com\//i.test(this.urlForm.url)) return this.$message.error(this.$t('persona.githubRequired'))
      this.creatingJob = true
      Api.persona.importUrl(this.urlForm.url, this.urlForm.ref, (response) => { this.creatingJob = false; this.urlDialog = false; this.watchJob(this.ok(response)) }, () => { this.creatingJob = false })
    },
    uploadZip(event) {
      const file = event.target.files?.[0]
      event.target.value = ''
      if (!file) return
      if (!file.name.toLowerCase().endsWith('.zip') || file.size > 10 * 1024 * 1024) return this.$message.error(this.$t('persona.zipInvalid'))
      this.creatingJob = true
      Api.persona.importUpload(file, (response) => { this.creatingJob = false; this.watchJob(this.ok(response)) }, () => { this.creatingJob = false })
    },
    startGalleryImport(item) {
      this.urlForm = { url: item.skillRepo, ref: '' }
      this.submitUrlImport()
    },
    watchJob(jobId) {
      if (!jobId) return
      window.localStorage.setItem('personaImportJobId', jobId)
      this.currentJob = { id: jobId, status: 'queued', progress: 0 }
      this.progressDialog = true
      this.pollJob()
    },
    resumeJob(jobId) {
      if (!jobId) return
      Api.persona.importJob(jobId, (response) => {
        const job = this.ok(response)
        if (!job || TERMINAL_IMPORT_STATUSES.includes(job.status)) {
          window.localStorage.removeItem('personaImportJobId')
          return
        }
        this.currentJob = job
        this.progressDialog = true
        this.pollTimer = window.setTimeout(this.pollJob, 1500)
      }, () => {})
    },
    pollJob() {
      this.stopPolling()
      const jobId = this.currentJob.id
      Api.persona.importJob(jobId, (response) => {
        const job = this.ok(response)
        if (job) this.currentJob = job
        if (job && !TERMINAL_IMPORT_STATUSES.includes(job.status)) {
          this.pollTimer = window.setTimeout(this.pollJob, 1500)
        } else if (job) {
          window.localStorage.removeItem('personaImportJobId')
          this.loadPersonas()
          if (this.detailDialog && this.detail.personaId === job.expectedPersonaId) this.showDetail(this.detail)
        }
      }, () => { this.pollTimer = window.setTimeout(this.pollJob, 3000) })
    },
    stopPolling() { if (this.pollTimer) window.clearTimeout(this.pollTimer); this.pollTimer = null },
    cancelCurrentImport() {
      Api.persona.cancelImport(this.currentJob.id, () => {
        this.stopPolling()
        window.localStorage.removeItem('personaImportJobId')
        this.currentJob = { ...this.currentJob, status: 'cancelled', progress: 100 }
        this.$message.success(this.$t('persona.importCancelled'))
      })
    },
    applyCompiled() {
      const result = this.currentJob.compileResult
      this.publishing = true
      Api.persona.applyUpdate(result.personaId, this.compiledVersion, () => {
        this.publishing = false; window.localStorage.removeItem('personaImportJobId'); this.$message.success(this.$t('persona.publishSuccess')); this.progressDialog = false; this.loadPersonas()
      }, () => { this.publishing = false })
    },
    showDetail(item) {
      this.detail = item; this.detailDialog = true; this.loadingVersions = true
      Api.persona.detail(item.personaId, (response) => {
        this.detail = this.ok(response) || item
      }, () => {})
      Api.persona.versions(item.personaId, (response) => { this.versions = this.ok(response) || []; this.loadingVersions = false }, () => { this.loadingVersions = false })
    },
    viewVersion(row) { Api.persona.version(this.detail.personaId, row.version, (response) => { this.versionDetail = this.ok(response) || {}; this.versionDialog = true }) },
    openSignatureManager(row) {
      this.signatureVersion = row.version
      this.signatureDialog = true
      this.loadSignatures()
    },
    loadSignatures() {
      if (!this.detail.personaId || !this.signatureVersion) return
      this.loadingSignatures = true
      Api.persona.signatures(this.detail.personaId, this.signatureVersion, (response) => {
        this.signatures = this.ok(response) || []
        if (this.signatureForm.editing) {
          const current = this.signatures.find(item => item.id === this.signatureForm.id)
          if (current) this.signatureForm.item = current
        }
        this.loadingSignatures = false
      }, () => { this.loadingSignatures = false })
    },
    editSignature(item) {
      this.signatureForm = item ? {
        id: item.id,
        displayText: item.display_text || '',
        aliasesText: (item.explicit_aliases || []).join('、'),
        semanticRule: item.semantic_rule || '',
        examplesText: (item.positive_examples || []).join('\n'),
        editing: true,
        origin: item.origin || 'custom',
        customizing: item.origin !== 'skill',
        item
      } : {
        id: '', displayText: '', aliasesText: '', semanticRule: '', examplesText: '',
        editing: false, origin: 'custom', customizing: true, item: null
      }
      this.signatureEditorDialog = true
    },
    saveSignature() {
      const form = this.signatureForm
      if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(form.id)) return this.$message.error(this.$t('persona.signatureIdInvalid'))
      if (!form.displayText || !form.semanticRule) return this.$message.error(this.$t('persona.signatureRequired'))
      const splitValues = value => String(value || '').split(/[、,，\n]/).map(item => item.trim()).filter(Boolean)
      this.savingSignature = true
      Api.persona.saveSignature(this.detail.personaId, this.signatureVersion, form.id, {
        displayText: form.displayText,
        semanticRule: form.semanticRule,
        explicitAliases: splitValues(form.aliasesText),
        positiveExamples: splitValues(form.examplesText),
        ambiguityPolicy: '上下文不能唯一确定时不触发',
        fallback: 'tts',
        styleMap: { neutral: 'classic', restrained: 'classic', happy: 'playful', excited: 'playful', warm: 'soft', soft: 'soft' }
      }, (response) => {
        this.savingSignature = false
        const saved = this.ok(response)
        if (saved) {
          this.signatureForm.editing = true
          this.signatureForm.origin = saved.origin || 'custom'
          this.signatureForm.customizing = true
          this.signatureForm.item = saved
        }
        this.$message.success(this.$t('persona.signatureSaved'))
        this.loadSignatures()
      }, () => { this.savingSignature = false })
    },
    toggleSignature(item) {
      this.$set(item, '_toggling', true)
      Api.persona.setSignatureEnabled(
        this.detail.personaId,
        this.signatureVersion,
        item.id,
        item.enabled === false,
        () => {
          this.$set(item, '_toggling', false)
          this.$message.success(this.$t('persona.signatureToggleSuccess'))
          this.loadSignatures()
        },
        () => { this.$set(item, '_toggling', false) }
      )
    },
    assetFor(item, variant) {
      return (item.asset_metadata || []).find(asset => asset.variant === variant) || null
    },
    signatureVariantLabel(variant) {
      return this.$t(`persona.signatureVariant_${variant}`)
    },
    chooseSignatureAsset(item, variant) {
      this.signatureUploadTarget = { signatureKey: item.id, variant }
      const input = this.$refs.signatureAudioInput
      if (input) { input.value = ''; input.click() }
    },
    uploadSignatureAudio(event) {
      const file = event.target.files?.[0]
      const target = this.signatureUploadTarget
      event.target.value = ''
      if (!file || !target) return
      if (!/\.(wav|mp3|ogg)$/i.test(file.name) || file.size > 5 * 1024 * 1024) {
        return this.$message.error(this.$t('persona.signatureAudioInvalid'))
      }
      Api.persona.uploadSignatureAsset(this.detail.personaId, this.signatureVersion, target.signatureKey, target.variant, file, (response) => {
        const saved = this.ok(response)
        if (saved && this.signatureForm.id === saved.id) this.signatureForm.item = saved
        this.$message.success(this.$t('persona.signatureAudioSaved'))
        this.loadSignatures()
      })
    },
    previewSignatureAsset(asset) {
      this.stopSignatureAudio()
      Api.persona.previewSignatureAsset(asset.assetId, (response) => {
        const blob = response.data instanceof Blob ? response.data : new Blob([response.data], { type: asset.contentType || 'audio/wav' })
        this.signatureAudioUrl = URL.createObjectURL(blob)
        this.signatureAudio = new Audio(this.signatureAudioUrl)
        this.signatureAudio.onended = () => this.stopSignatureAudio()
        this.signatureAudio.onerror = () => { this.stopSignatureAudio(); this.$message.error(this.$t('persona.signaturePreviewFailed')) }
        this.signatureAudio.play().catch(() => { this.stopSignatureAudio(); this.$message.error(this.$t('persona.signaturePreviewFailed')) })
      })
    },
    stopSignatureAudio() {
      if (this.signatureAudio) { this.signatureAudio.pause(); this.signatureAudio = null }
      if (this.signatureAudioUrl) { URL.revokeObjectURL(this.signatureAudioUrl); this.signatureAudioUrl = '' }
    },
    removeSignatureAsset(asset) {
      this.$confirm(this.$t('persona.deleteSignatureAudioConfirm'), this.$t('message.info'), { type: 'warning' })
        .then(() => Api.persona.deleteSignatureAsset(asset.assetId, () => { this.stopSignatureAudio(); this.loadSignatures() }))
        .catch(() => {})
    },
    comparePendingUpdate() {
      if (!this.currentLifecycle || !this.candidateLifecycle) return
      Api.persona.diff(this.detail.personaId, this.currentLifecycle.version, this.candidateLifecycle.version, (response) => {
        this.diffResult = this.ok(response) || {}
        this.diffDialog = true
      })
    },
    showRecompileDiff() {
      const result = this.currentJob.compileResult || {}
      if (!result.personaId || !result.previousVersion || !this.compiledVersion) return
      Api.persona.diff(result.personaId, result.previousVersion, this.compiledVersion, (response) => {
        this.diffResult = this.ok(response) || {}
        this.diffDialog = true
      })
    },
    rerunTest(row) {
      this.$set(row, '_testing', true)
      Api.persona.rerunTest(this.detail.personaId, row.version, [], (response) => {
        this.$set(row, '_testing', false); const report = this.ok(response) || {}; this.$message[report.status === 'passed' ? 'success' : 'warning'](this.$t(report.status === 'passed' ? 'persona.testPassed' : 'persona.testFailed')); this.showDetail(this.detail)
      }, () => this.$set(row, '_testing', false))
    },
    openConversationTest(row) {
      this.conversationTestRow = row
      this.conversationTestReport = null
      this.conversationSamplesJson = '[\n  {\n    "scene": "安慰",\n    "user": "今天有点累",\n    "assistant": "那先歇一会儿，别硬撑。",\n    "expected": { "maxQuestions": 0, "forbidden": ["作为AI"] }\n  }\n]'
      this.conversationTestDialog = true
    },
    runConversationTest() {
      let samples
      try {
        samples = JSON.parse(this.conversationSamplesJson)
        if (!Array.isArray(samples) || samples.length === 0 || samples.length > 500
          || samples.some(item => !item || typeof item !== 'object' || Array.isArray(item))) {
          throw new TypeError('invalid samples')
        }
      } catch (error) {
        return this.$message.error(this.$t('persona.conversationTestInvalid'))
      }
      this.conversationTestRunning = true
      Api.persona.rerunTest(this.detail.personaId, this.conversationTestRow.version, samples, (response) => {
        this.conversationTestRunning = false
        const report = this.ok(response) || {}
        this.conversationTestReport = report.conversationReport || report
        this.$message[report.status === 'passed' ? 'success' : 'warning'](
          this.$t(report.status === 'passed' ? 'persona.testPassed' : 'persona.testFailed'))
        this.showDetail(this.detail)
      }, () => { this.conversationTestRunning = false })
    },
    applyVersion(row) {
      Api.persona.applyUpdate(this.detail.personaId, row.version, () => {
        this.$message.success(this.$t('persona.publishSuccess'))
        this.showDetail(this.detail)
        this.loadPersonas()
      })
    },
    restorePrevious() {
      this.$confirm(this.$t('persona.restorePreviousConfirm'), this.$t('message.info'), { type: 'warning' })
        .then(() => Api.persona.restorePrevious(this.detail.personaId, () => {
          this.$message.success(this.$t('persona.rollbackSuccess'))
          this.showDetail(this.detail)
          this.loadPersonas()
        }))
        .catch(() => {})
    },
    openUpgradeDialog(item) {
      this.upgradeTarget = { ...item }
      this.upgradeDialog = true
    },
    openRecompileDialog(row) {
      this.recompileTarget = { ...row }
      this.inheritSignatureAudio = true
      this.recompileDialog = true
    },
    startRecompile() {
      const target = this.recompileTarget
      if (!this.detail.personaId || !target.version) return
      this.creatingJob = true
      Api.persona.recompile(this.detail.personaId, target.version, this.inheritSignatureAudio, (response) => {
        this.creatingJob = false
        this.recompileDialog = false
        this.watchJob(this.ok(response))
      }, () => { this.creatingJob = false })
    },
    chooseRecompileZip() {
      this.$refs.recompileZipInput?.click()
    },
    uploadRecompileZip(event) {
      const file = event.target.files?.[0]
      event.target.value = ''
      if (!file) return
      if (!file.name.toLowerCase().endsWith('.zip') || file.size > 10 * 1024 * 1024) {
        return this.$message.error(this.$t('persona.zipInvalid'))
      }
      const target = this.recompileTarget
      this.creatingJob = true
      Api.persona.recompileUpload(this.detail.personaId, target.version, this.inheritSignatureAudio, file, (response) => {
        this.creatingJob = false
        this.recompileDialog = false
        this.watchJob(this.ok(response))
      }, () => { this.creatingJob = false })
    },
    startUpgradeFromSource() {
      const personaId = this.upgradeTarget.personaId
      if (!personaId) return
      this.creatingJob = true
      Api.persona.upgradeFromSource(personaId, (response) => {
        this.creatingJob = false
        this.upgradeDialog = false
        this.watchJob(this.ok(response))
      }, () => { this.creatingJob = false })
    },
    chooseUpgradeZip() {
      this.$refs.upgradeZipInput?.click()
    },
    uploadUpgradeZip(event) {
      const file = event.target.files?.[0]
      event.target.value = ''
      if (!file) return
      if (!file.name.toLowerCase().endsWith('.zip') || file.size > 10 * 1024 * 1024) {
        return this.$message.error(this.$t('persona.zipInvalid'))
      }
      const personaId = this.upgradeTarget.personaId
      this.creatingJob = true
      Api.persona.upgradeUpload(personaId, file, (response) => {
        this.creatingJob = false
        this.upgradeDialog = false
        this.watchJob(this.ok(response))
      }, () => { this.creatingJob = false })
    },
    deletePersona(item) {
      Api.persona.usage(item.personaId, (response) => {
        const usage = this.ok(response) || {}
        return this.$prompt(
          this.$t('persona.deleteConfirm', {
            name: item.displayName || item.personaId,
            id: item.personaId,
            count: usage.bindingCount || 0
          }),
          this.$t('persona.deletePersona'),
          {
            type: 'warning',
            confirmButtonText: this.$t('persona.confirmDelete'),
            cancelButtonText: this.$t('button.cancel'),
            inputPlaceholder: item.personaId,
            inputValidator: value => value === item.personaId || this.$t('persona.deleteIdMismatch')
          }
        ).then(() => {
          Api.persona.remove(item.personaId, item.personaId, () => {
            this.detailDialog = false
            this.$message.success(this.$t('persona.deleteSuccess'))
            this.loadPersonas()
          })
        }).catch(() => {})
      })
    },
    lifecycleLabel(role) { return this.$t(`persona.lifecycle_${role || 'candidate'}`) },
    lifecycleTagType(role) { return ({ current: 'success', candidate: 'warning', previous: 'info' })[role] || 'info' },
    bindPersona(item) {
      this.bindingPersonaId = item.personaId; this.selectedAgentId = ''; this.agentDialog = true
      Api.agent.getAgentList(({ data }) => { this.agents = data?.code === 0 && Array.isArray(data.data) ? data.data : [] })
    },
    continueBinding() {
      this.$router.push({ path: '/role-config', query: { agentId: this.selectedAgentId, personaId: this.bindingPersonaId } })
    },
    displayInitial(value) {
      const text = String(value || 'P').trim()
      return Array.from(text)[0]?.toUpperCase() || 'P'
    },
    accentClass(value) {
      const text = String(value || 'persona')
      let hash = 0
      for (let index = 0; index < text.length; index += 1) hash = ((hash << 5) - hash) + text.charCodeAt(index)
      return `accent-${Math.abs(hash) % 6}`
    },
    galleryTags(item) {
      const values = [...(item.tags || []), ...(item.personality || [])]
      return [...new Set(values.filter(Boolean))].slice(0, 4)
    },
    kindLabel(value) {
      const key = `persona.kind_${value || 'unverified'}`
      const translated = this.$t(key)
      return translated === key ? value : translated
    },
    openExternal(url) { window.open(url, '_blank', 'noopener') },
    pretty(value) { return value ? JSON.stringify(value, null, 2) : '' },
    statusText(status) { return this.$t(`persona.status_${status || 'queued'}`) }
  }
}
</script>

<style lang="scss" scoped>
.persona-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  color: #263553;
  background:
    radial-gradient(circle at 12% 0, rgba(91, 142, 255, .09), transparent 30%),
    #f5f8ff;
}

.page-body {
  width: 100%;
  max-width: 1680px;
  margin: 0 auto;
  padding: 24px 28px 36px;
  box-sizing: border-box;
  flex: 1;
}

.library-card {
  min-height: calc(100vh - 132px);
  overflow: visible;
  border: 1px solid #e7edf8;
  border-radius: 20px;
  box-shadow: 0 14px 40px rgba(40, 72, 132, .06);
}

::v-deep .library-card > .el-card__body { padding: 26px 30px 32px; }

.toolbar,
.card-actions,
.preview-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.page-head {
  display: grid;
  grid-template-columns: minmax(360px, 1fr) minmax(420px, 620px) minmax(360px, 1fr);
  align-items: center;
  gap: 20px;
}
.page-head-copy {
  grid-column: 2;
  min-width: 0;
  text-align: center;
}
.page-kicker {
  display: block;
  margin-bottom: 6px;
  color: #4e82ef;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .14em;
}
.page-head h2 { margin: 0; color: #1f3154; font-size: 25px; line-height: 1.25; }
.page-head p { margin: 7px 0 0; color: #7482a2; line-height: 1.6; }
.head-actions {
  grid-column: 3;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.compiler-status {
  height: 36px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 12px;
  border: 1px solid #dfe6f2;
  border-radius: 18px;
  color: #6c7891;
  background: #fff;
  cursor: pointer;
  transition: .2s ease;
}
.compiler-status:hover { border-color: #9dbdff; color: #3978ec; background: #f7faff; }
.compiler-status .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #aab4c6; box-shadow: 0 0 0 4px rgba(170, 180, 198, .14); }
.compiler-status .el-icon-refresh { margin-left: 2px; font-size: 12px; }
.compiler-status.is-online .status-dot { background: #38b77a; box-shadow: 0 0 0 4px rgba(56, 183, 122, .13); }
.compiler-status.is-online { color: #23885b; border-color: #ccebdd; background: #f6fcf9; }
.compiler-status.is-offline .status-dot { background: #ef6a72; box-shadow: 0 0 0 4px rgba(239, 106, 114, .13); }
.compiler-status.is-offline { color: #c94c56; border-color: #f2cdd1; background: #fff8f8; }
.compiler-status.is-checking .el-icon-refresh { animation: rotating 1.2s linear infinite; }

.identity-notice { margin: 20px 0 6px; }
::v-deep .identity-notice.el-alert { border: 1px solid #e4ebf7; background: #f8faff; }
::v-deep .identity-notice .el-alert__title { color: #657494; font-size: 13px; }
::v-deep .library-card .el-tabs__header { margin: 0 0 18px; }
::v-deep .library-card .el-tabs__item { height: 52px; line-height: 52px; font-weight: 600; }
::v-deep .library-card .el-tabs__active-bar { height: 3px; border-radius: 3px 3px 0 0; }

.tab-toolbar {
  min-height: 44px;
  justify-content: center;
  margin-bottom: 18px;
  padding: 2px 0;
}
.tab-toolbar .el-input { width: min(440px, 100%); }
.content-stage { position: relative; min-height: 400px; }

.persona-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  align-items: stretch;
  gap: 20px;
}

.persona-card {
  min-width: 0;
  min-height: 320px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-sizing: border-box;
  border: 1px solid #e3e9f4;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(45, 73, 125, .055);
  transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
}
.persona-card:hover {
  border-color: #a9c2f4;
  box-shadow: 0 18px 38px rgba(47, 89, 172, .14);
  transform: translateY(-4px);
}
.gallery-card { min-height: 320px; }

.card-visual {
  position: relative;
  height: 60px;
  flex: 0 0 60px;
  overflow: visible;
  isolation: isolate;
}
.card-visual::before,
.card-visual::after {
  position: absolute;
  z-index: 0;
  content: '';
  border-radius: 50%;
  background: rgba(255, 255, 255, .14);
}
.card-visual::before { width: 116px; height: 116px; top: -68px; right: 42px; }
.card-visual::after { width: 76px; height: 76px; right: -18px; bottom: -34px; }
.card-visual.accent-0 { background: linear-gradient(125deg, #547ff2, #7668e8); }
.card-visual.accent-1 { background: linear-gradient(125deg, #ff8065, #f4aa48); }
.card-visual.accent-2 { background: linear-gradient(125deg, #28a986, #48c5ab); }
.card-visual.accent-3 { background: linear-gradient(125deg, #9861dd, #cd67ba); }
.card-visual.accent-4 { background: linear-gradient(125deg, #3d9fda, #47c2d5); }
.card-visual.accent-5 { background: linear-gradient(125deg, #dc668a, #f48b6f); }
.visual-label {
  position: absolute;
  z-index: 1;
  top: 17px;
  left: 20px;
  color: rgba(255, 255, 255, .82);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .12em;
}
.avatar {
  position: absolute;
  z-index: 1;
  left: 20px;
  bottom: -72px;
  width: 58px;
  height: 58px;
  display: grid;
  place-items: center;
  border: 4px solid #fff;
  border-radius: 18px;
  color: #35496f;
  background: rgba(255, 255, 255, .96);
  font-size: 24px;
  font-weight: 750;
  line-height: 1;
  box-shadow: 0 8px 18px rgba(47, 66, 105, .2);
}
.state-tag,
.source-tag {
  position: absolute;
  z-index: 1;
  top: 14px;
  right: 16px;
  border-color: rgba(255, 255, 255, .38);
  border-radius: 12px;
  color: #fff;
  background: rgba(24, 36, 70, .18);
  backdrop-filter: blur(6px);
}
.card-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 17px 20px 16px;
}
.card-heading {
  min-width: 0;
  min-height: 44px;
  padding-left: 74px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: center;
  text-align: left;
}
.card-heading h3 {
  margin: 0 0 4px;
  overflow: hidden;
  color: #1f3153;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-heading > span {
  display: block;
  overflow: hidden;
  color: #98a3b8;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-description {
  min-height: 66px;
  margin: 16px 0 13px;
  overflow: hidden;
  color: #5b6b88;
  font-size: 14px;
  line-height: 1.58;
  text-align: left;
  word-break: break-word;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}

.card-meta {
  min-height: 29px;
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}
.card-meta span,
.skill-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  border: 1px solid #e3eaf6;
  border-radius: 10px;
  color: #687895;
  background: #f5f8fd;
  font-size: 11px;
  line-height: 1;
}
.card-meta i { color: #88a3d7; }
.tag-row { min-height: 29px; display: flex; flex-wrap: wrap; gap: 6px; align-content: flex-start; }
.skill-tag { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.card-actions {
  justify-content: flex-end;
  margin-top: auto;
  padding: 13px 18px;
  border-top: 1px solid #e9eef7;
  background: #f8faff;
}
.card-actions .el-button { min-width: 92px; margin-left: 0; border-radius: 9px; }
.card-actions .el-button + .el-button { margin-left: 0; }

.library-empty {
  min-height: 390px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 1px dashed #dfe7f5;
  border-radius: 16px;
  background: linear-gradient(180deg, #fbfcff, #fff);
}
.hidden-input { display: none; }

.job-status {
  margin: 18px 0;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px solid #e7ecf4;
  border-radius: 10px;
  color: #5d6b85;
  background: #f7f9fc;
}
.job-status.is-error { border-color: #f1c8cd; color: #a84049; background: #fff7f8; }
.job-status-title { display: flex; align-items: center; gap: 8px; color: #2f3e59; }
.job-status.is-error .job-status-title { color: #c44751; }
.compiler-help {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(196, 71, 81, .14);
  color: #7f5960;
  font-size: 12px;
}
.compiler-help .el-button { margin-left: auto; }

.compile-preview { margin-top: 18px; }
.compile-preview pre,
.versionDialog pre,
pre {
  max-height: 360px;
  overflow: auto;
  padding: 12px;
  border-radius: 8px;
  color: #d8e3f7;
  background: #111827;
  white-space: pre-wrap;
  word-break: break-word;
}
.preview-actions { justify-content: flex-end; margin-top: 16px; }
.versions-table { margin-top: 18px; }
.version-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  column-gap: 13px;
  row-gap: 2px;
}
.version-actions .el-button { margin-left: 0; padding: 7px 0; }
.danger { color: #f56c6c; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-top: 20px; gap: 14px; }
.section-head h3 { margin: 0; color: #33415c; }
.version-management-bar,
.persona-danger-zone {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-top: 18px;
  padding: 14px 16px;
  border: 1px solid #e3eaf6;
  border-radius: 12px;
  background: #f8faff;
}
.version-management-bar > div,
.persona-danger-zone > div { min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.version-management-bar strong,
.persona-danger-zone strong { color: #33415c; font-size: 14px; }
.version-management-bar span,
.persona-danger-zone span { color: #7b88a2; font-size: 12px; line-height: 1.5; }
.persona-danger-zone { margin-top: 20px; border-color: #f1d8da; background: #fffafa; }
.persona-danger-zone strong { color: #b94e57; }
.upgrade-options { display: grid; gap: 12px; margin-top: 18px; }
.upgrade-option {
  width: 100%;
  min-height: 72px;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 20px;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid #e0e7f3;
  border-radius: 12px;
  color: #49617f;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition: .2s ease;
}
.upgrade-option:hover { border-color: #8eb2fa; color: #3978ec; background: #f7faff; transform: translateY(-1px); }
.upgrade-option:disabled { opacity: .6; cursor: wait; transform: none; }
.upgrade-option > i:first-child { font-size: 23px; text-align: center; }
.upgrade-option span { min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.upgrade-option strong { color: #2d405f; font-size: 14px; }
.upgrade-option small { overflow: hidden; color: #8794aa; text-overflow: ellipsis; white-space: nowrap; }
.diff-controls { display: flex; align-items: center; gap: 6px; }
.diff-controls .el-select { width: 130px; }
.diff-value { max-height: 180px; font-size: 11px; }
.audit-collapse { margin-top: 20px; }
.conversation-samples { margin-top: 16px; }
.conversation-report { margin-top: 16px; max-height: 260px; }
.recompile-result { margin-top: 14px; }
.recompile-source { margin: 16px 0 14px; }
.recompile-inherit { color: #344967; font-weight: 600; }
.recompile-note { margin: 7px 0 16px 24px; color: #7c8aa2; font-size: 12px; line-height: 1.55; }
.signature-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding: 14px 16px;
  border: 1px solid #e3eaf6;
  border-radius: 12px;
  background: #f8faff;
}
.signature-toolbar > div { min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.signature-toolbar strong { color: #2f4263; }
.signature-toolbar span { color: #7887a2; font-size: 12px; line-height: 1.5; }
.signature-list { min-height: 180px; display: grid; gap: 12px; }
.signature-card {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(290px, .85fr) 88px;
  align-items: start;
  column-gap: 24px;
  padding: 16px 18px;
  border: 1px solid #e3e9f4;
  border-radius: 13px;
  background: #fff;
}
.signature-card.is-disabled { border-style: dashed; background: #fafbfc; }
.signature-card.is-disabled .signature-copy,
.signature-card.is-disabled .signature-variants { opacity: .62; }
.signature-title { min-width: 0; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.signature-title strong { color: #203657; font-size: 17px; }
.signature-title code { color: #7b8aa5; font-size: 11px; }
.signature-copy p { margin: 9px 0 6px; color: #5f6e88; font-size: 13px; line-height: 1.6; }
.signature-copy small { color: #8a96aa; }
.signature-variants { display: grid; gap: 6px; }
.signature-variant {
  min-height: 34px;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 2px 9px;
  border-radius: 8px;
  background: #f7f9fd;
}
.signature-variant > span { width: 58px; color: #5e6e8b; font-size: 12px; font-weight: 600; }
.signature-variant .el-button { margin: 0; padding: 6px 0; }
.signature-actions {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-self: end;
  width: 80px;
  gap: 7px;
}
.signature-actions .el-button { margin: 0; }
.signature-editor-alert { margin-bottom: 10px; }
.signature-editor-form { margin: 0; }
::v-deep .signature-editor-form .el-form-item { margin-bottom: 10px; }
::v-deep .signature-editor-form .el-form-item__label {
  padding-bottom: 4px;
  color: #4b5870;
  line-height: 22px;
}
::v-deep .signature-editor-dialog .el-dialog__header { padding: 16px 22px 12px; }
::v-deep .signature-editor-dialog .el-dialog__body {
  max-height: calc(92vh - 116px);
  overflow-y: auto;
  padding: 8px 22px 6px;
}
::v-deep .signature-editor-dialog .el-dialog__footer { padding: 10px 22px 16px; }
.signature-editor-assets {
  display: grid;
  gap: 4px;
  margin-top: 2px;
  padding: 10px 12px;
  border: 1px solid #dfe7f3;
  border-radius: 11px;
  background: #fafcff;
}
.signature-editor-assets-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 1px;
}
.signature-editor-assets-head > div { display: flex; flex-direction: column; gap: 3px; }
.signature-editor-assets-head strong { color: #2f4263; font-size: 14px; }
.signature-editor-assets-head span { color: #8290a7; font-size: 12px; line-height: 1.4; }
::v-deep .el-dialog { max-width: calc(100vw - 32px); border-radius: 14px; }

@media (max-width: 1180px) {
  .page-body { padding: 18px; }
  ::v-deep .library-card > .el-card__body { padding: 22px; }
  .page-head { grid-template-columns: 1fr; }
  .page-head-copy,
  .head-actions { grid-column: 1; }
  .head-actions { justify-content: center; }
  .persona-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 760px) {
  .page-body { padding: 12px; }
  ::v-deep .library-card > .el-card__body { padding: 18px 14px 24px; }
  .head-actions { width: 100%; justify-content: center; }
  .compiler-status { order: 3; }
  .tab-toolbar { align-items: stretch; }
  .tab-toolbar .el-input { flex: 1; width: auto; }
  .persona-grid { grid-template-columns: 1fr; }
  .persona-card, .gallery-card { min-height: 0; }
  .card-description { min-height: 66px; }
  .section-head { align-items: flex-start; flex-direction: column; }
  .version-management-bar,
  .persona-danger-zone { align-items: flex-start; flex-direction: column; }
  .diff-controls { width: 100%; flex-wrap: wrap; }
  .compiler-help { align-items: flex-start; flex-wrap: wrap; }
  .signature-toolbar { align-items: flex-start; flex-direction: column; }
  .signature-card { grid-template-columns: 1fr; gap: 12px; padding: 14px; }
  .signature-actions { width: auto; flex-direction: row; justify-self: end; }
}
</style>
