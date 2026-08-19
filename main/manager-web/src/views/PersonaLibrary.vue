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
                    <el-tag class="state-tag" size="mini" effect="dark" :type="item.publishedVersion ? 'success' : 'info'">
                      {{ item.publishedVersion ? $t('persona.published') : $t('persona.draft') }}
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
                    <el-button size="small" icon="el-icon-files" @click="showDetail(item)">{{ $t('persona.manageVersions') }}</el-button>
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
        <div class="preview-actions" v-if="currentJob.status === 'ready'">
          <el-select v-model="publishVisibility"><el-option value="private" :label="$t('persona.private')" /><el-option value="shared" :label="$t('persona.shared')" /></el-select>
          <el-button type="success" :loading="publishing" @click="publishCompiled">{{ $t('persona.publish') }}</el-button>
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
        <el-descriptions-item :label="$t('persona.publishedVersion')">{{ detail.publishedVersion || '-' }}</el-descriptions-item>
      </el-descriptions>
      <div class="section-head"><h3>{{ $t('persona.versions') }}</h3>
        <div class="diff-controls">
          <el-select v-model="diffFrom" size="mini" :placeholder="$t('persona.fromVersion')"><el-option v-for="item in versions" :key="`from-${item.version}`" :value="item.version" :label="item.version" /></el-select>
          <span>→</span>
          <el-select v-model="diffTo" size="mini" :placeholder="$t('persona.toVersion')"><el-option v-for="item in versions" :key="`to-${item.version}`" :value="item.version" :label="item.version" /></el-select>
          <el-button size="mini" :disabled="!diffFrom || !diffTo || diffFrom === diffTo" @click="showDiff">{{ $t('persona.compare') }}</el-button>
        </div>
      </div>
      <el-table :data="versions" v-loading="loadingVersions" class="versions-table">
        <el-table-column prop="version" :label="$t('persona.version')" min-width="130" />
        <el-table-column prop="status" :label="$t('persona.status')" width="100" />
        <el-table-column prop="qualityScore" :label="$t('persona.score')" width="90" />
        <el-table-column prop="testStatus" :label="$t('persona.test')" width="100" />
        <el-table-column :label="$t('persona.actions')" width="310">
          <template slot-scope="scope">
            <el-button type="text" @click="viewVersion(scope.row)">{{ $t('persona.preview') }}</el-button>
            <el-button v-if="detail.owned" type="text" :loading="scope.row._testing" @click="rerunTest(scope.row)">{{ $t('persona.rerunTest') }}</el-button>
            <el-button v-if="detail.owned && scope.row.status !== 'published' && scope.row.status !== 'archived'" type="text" @click="publishVersion(scope.row)">{{ $t('persona.publish') }}</el-button>
            <el-button v-if="detail.owned && scope.row.status === 'published' && detail.publishedVersion !== scope.row.version" type="text" @click="rollbackVersion(scope.row)">{{ $t('persona.rollback') }}</el-button>
            <el-button v-if="detail.owned && detail.publishedVersion !== scope.row.version" type="text" class="danger" @click="archiveVersion(scope.row)">{{ $t('persona.archive') }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-collapse v-if="detail.owned" class="audit-collapse">
        <el-collapse-item :title="$t('persona.auditTrail')">
          <el-table :data="auditItems" size="mini">
            <el-table-column prop="createdAt" :label="$t('persona.time')" width="170" />
            <el-table-column prop="action" :label="$t('persona.action')" width="210" />
            <el-table-column prop="targetId" :label="$t('persona.target')" />
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </el-dialog>

    <el-dialog :title="$t('persona.versionPreview')" :visible.sync="versionDialog" width="800px">
      <el-tabs><el-tab-pane :label="$t('persona.runtimePrompt')"><pre>{{ versionDetail.runtimePrompt }}</pre></el-tab-pane>
        <el-tab-pane :label="$t('persona.canonicalSpec')"><pre>{{ pretty(versionDetail.canonicalSpec) }}</pre></el-tab-pane>
        <el-tab-pane :label="$t('persona.testReport')"><pre>{{ pretty(versionDetail.testReport) }}</pre></el-tab-pane></el-tabs>
    </el-dialog>
    <el-dialog :title="$t('persona.versionDiff')" :visible.sync="diffDialog" width="800px">
      <el-table :data="diffResult.changes || []">
        <el-table-column prop="path" :label="$t('persona.field')" width="180" />
        <el-table-column :label="$t('persona.before')"><template slot-scope="scope"><pre class="diff-value">{{ pretty(scope.row.before) }}</pre></template></el-table-column>
        <el-table-column :label="$t('persona.after')"><template slot-scope="scope"><pre class="diff-value">{{ pretty(scope.row.after) }}</pre></template></el-table-column>
      </el-table>
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
      publishing: false, publishVisibility: 'private',
      detailDialog: false, detail: {}, versions: [], loadingVersions: false,
      versionDialog: false, versionDetail: {},
      agentDialog: false, agents: [], selectedAgentId: '', bindingPersonaId: '',
      diffFrom: '', diffTo: '', diffDialog: false, diffResult: {},
      auditItems: []
    }
  },
  computed: {
    filteredPersonas() {
      const query = this.localKeyword.toLowerCase()
      if (!query) return this.personas
      return this.personas.filter(item => `${item.displayName} ${item.personaId} ${item.description}`.toLowerCase().includes(query))
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
    }
  },
  mounted() {
    this.loadPersonas()
    this.loadHealth()
    const activeJobId = window.localStorage.getItem('personaImportJobId')
    if (activeJobId) this.resumeJob(activeJobId)
  },
  beforeDestroy() { this.stopPolling() },
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
    publishCompiled() {
      const result = this.currentJob.compileResult
      this.publishing = true
      Api.persona.publish(result.personaId, this.compiledVersion, this.publishVisibility, () => {
        this.publishing = false; window.localStorage.removeItem('personaImportJobId'); this.$message.success(this.$t('persona.publishSuccess')); this.progressDialog = false; this.loadPersonas()
      }, () => { this.publishing = false })
    },
    showDetail(item) {
      this.detail = item; this.detailDialog = true; this.loadingVersions = true
      Api.persona.detail(item.personaId, (response) => {
        this.detail = this.ok(response) || item
        if (this.detail.owned) Api.persona.audit(item.personaId, (auditResponse) => { this.auditItems = this.ok(auditResponse) || [] })
        else this.auditItems = []
      }, () => {})
      Api.persona.versions(item.personaId, (response) => { this.versions = this.ok(response) || []; this.diffTo = this.versions[0]?.version || ''; this.diffFrom = this.versions[1]?.version || ''; this.loadingVersions = false }, () => { this.loadingVersions = false })
    },
    viewVersion(row) { Api.persona.version(this.detail.personaId, row.version, (response) => { this.versionDetail = this.ok(response) || {}; this.versionDialog = true }) },
    showDiff() { Api.persona.diff(this.detail.personaId, this.diffFrom, this.diffTo, (response) => { this.diffResult = this.ok(response) || {}; this.diffDialog = true }) },
    rerunTest(row) {
      this.$set(row, '_testing', true)
      Api.persona.rerunTest(this.detail.personaId, row.version, (response) => {
        this.$set(row, '_testing', false); const report = this.ok(response) || {}; this.$message[report.status === 'passed' ? 'success' : 'warning'](this.$t(report.status === 'passed' ? 'persona.testPassed' : 'persona.testFailed')); this.showDetail(this.detail)
      }, () => this.$set(row, '_testing', false))
    },
    publishVersion(row) { Api.persona.publish(this.detail.personaId, row.version, this.detail.visibility || 'private', () => { this.$message.success(this.$t('persona.publishSuccess')); this.showDetail(this.detail); this.loadPersonas() }) },
    rollbackVersion(row) { Api.persona.rollback(this.detail.personaId, row.version, () => { this.$message.success(this.$t('persona.rollbackSuccess')); this.showDetail(this.detail); this.loadPersonas() }) },
    archiveVersion(row) { this.$confirm(this.$t('persona.archiveConfirm'), this.$t('message.info'), { type: 'warning' }).then(() => Api.persona.archive(this.detail.personaId, row.version, () => { this.$message.success(this.$t('persona.archiveSuccess')); this.showDetail(this.detail) })).catch(() => {}) },
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
.danger { color: #f56c6c; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-top: 20px; gap: 14px; }
.section-head h3 { margin: 0; color: #33415c; }
.diff-controls { display: flex; align-items: center; gap: 6px; }
.diff-controls .el-select { width: 130px; }
.diff-value { max-height: 180px; font-size: 11px; }
.audit-collapse { margin-top: 20px; }
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
  .diff-controls { width: 100%; flex-wrap: wrap; }
  .compiler-help { align-items: flex-start; flex-wrap: wrap; }
}
</style>
