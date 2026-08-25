import { getServiceUrl } from '../api'
import RequestService from '../httpRequest'
import { showDanger } from '../../utils/index'
import i18n from '../../i18n'

function request(method, path, data, callback, onFailure, headers) {
  const builder = RequestService.sendRequest()
    .url(`${getServiceUrl()}${path}`)
    .method(method)
    .success((response) => {
      RequestService.clearRequestTime()
      if (callback) callback(response)
    })
    .fail((error) => {
      RequestService.clearRequestTime()
      showDanger(error?.data?.msg || i18n.t('persona.operationFailed'))
      if (onFailure) onFailure(error)
    })
    .networkFail((error) => {
      RequestService.clearRequestTime()
      showDanger(i18n.t('persona.serviceUnavailable'))
      if (onFailure) onFailure(error)
    })
  if (data !== undefined) builder.data(data)
  if (headers) builder.header(headers)
  builder.send()
}

function encoded(value) {
  return encodeURIComponent(value || '')
}

export default {
  list(callback, onFailure) {
    request('GET', '/persona', undefined, callback, onFailure)
  },
  options(callback, onFailure) {
    request('GET', '/persona/options', undefined, callback, onFailure)
  },
  health(callback, onFailure) {
    request('GET', '/persona/health', undefined, callback, onFailure)
  },
  gallery(keyword, callback, onFailure) {
    request('GET', `/persona/gallery?keyword=${encoded(keyword)}`, undefined, callback, onFailure)
  },
  refreshGallery(callback, onFailure) {
    request('POST', '/persona/gallery/refresh', {}, callback, onFailure)
  },
  detail(personaId, callback, onFailure) {
    request('GET', `/persona/${encoded(personaId)}`, undefined, callback, onFailure)
  },
  versions(personaId, callback, onFailure) {
    request('GET', `/persona/${encoded(personaId)}/versions`, undefined, callback, onFailure)
  },
  version(personaId, version, callback, onFailure) {
    request('GET', `/persona/${encoded(personaId)}/versions/${encoded(version)}`, undefined, callback, onFailure)
  },
  diff(personaId, from, to, callback, onFailure) {
    request('GET', `/persona/${encoded(personaId)}/diff?from=${encoded(from)}&to=${encoded(to)}`, undefined, callback, onFailure)
  },
  importUrl(url, ref, callback, onFailure) {
    request('POST', '/persona/import/url', { url, ref }, callback, onFailure)
  },
  importUpload(file, callback, onFailure) {
    const form = new FormData()
    form.append('file', file)
    request('POST', '/persona/import/upload', form, callback, onFailure, {})
  },
  upgradeFromSource(personaId, callback, onFailure) {
    request('POST', `/persona/${encoded(personaId)}/upgrade/source`, {}, callback, onFailure)
  },
  upgradeUpload(personaId, file, callback, onFailure) {
    const form = new FormData()
    form.append('file', file)
    request('POST', `/persona/${encoded(personaId)}/upgrade/upload`, form, callback, onFailure, {})
  },
  recompile(personaId, version, inheritSignatureAudio, callback, onFailure) {
    request('POST', `/persona/${encoded(personaId)}/versions/${encoded(version)}/recompile`,
      { inheritSignatureAudio: inheritSignatureAudio !== false }, callback, onFailure)
  },
  recompileUpload(personaId, version, inheritSignatureAudio, file, callback, onFailure) {
    const form = new FormData()
    form.append('inheritSignatureAudio', inheritSignatureAudio !== false ? 'true' : 'false')
    form.append('file', file)
    request('POST', `/persona/${encoded(personaId)}/versions/${encoded(version)}/recompile/upload`,
      form, callback, onFailure, {})
  },
  importJob(jobId, callback, onFailure) {
    request('GET', `/persona/import/jobs/${encoded(jobId)}`, undefined, callback, onFailure)
  },
  cancelImport(jobId, callback, onFailure) {
    request('POST', `/persona/import/jobs/${encoded(jobId)}/cancel`, {}, callback, onFailure)
  },
  applyUpdate(personaId, version, callback, onFailure) {
    request('POST', `/persona/${encoded(personaId)}/versions/${encoded(version)}/apply`, {}, callback, onFailure)
  },
  restorePrevious(personaId, callback, onFailure) {
    request('POST', `/persona/${encoded(personaId)}/restore-previous`, {}, callback, onFailure)
  },
  usage(personaId, callback, onFailure) {
    request('GET', `/persona/${encoded(personaId)}/usage`, undefined, callback, onFailure)
  },
  remove(personaId, confirmation, callback, onFailure) {
    request('DELETE', `/persona/${encoded(personaId)}?confirmation=${encoded(confirmation)}`, undefined, callback, onFailure)
  },
  rerunTest(personaId, version, conversationSamples, callback, onFailure) {
    request('POST', `/persona/${encoded(personaId)}/versions/${encoded(version)}/test`, { conversationSamples: conversationSamples || [] }, callback, onFailure)
  },
  testRuns(personaId, version, callback, onFailure) {
    request('GET', `/persona/${encoded(personaId)}/versions/${encoded(version)}/tests`, undefined, callback, onFailure)
  },
  signatures(personaId, version, callback, onFailure) {
    request('GET', `/persona/${encoded(personaId)}/versions/${encoded(version)}/signatures`, undefined, callback, onFailure)
  },
  saveSignature(personaId, version, signatureKey, data, callback, onFailure) {
    request('POST', `/persona/${encoded(personaId)}/versions/${encoded(version)}/signatures/${encoded(signatureKey)}`, data, callback, onFailure)
  },
  setSignatureEnabled(personaId, version, signatureKey, enabled, callback, onFailure) {
    request('POST', `/persona/${encoded(personaId)}/versions/${encoded(version)}/signatures/${encoded(signatureKey)}/enabled`, { enabled }, callback, onFailure)
  },
  uploadSignatureAsset(personaId, version, signatureKey, variant, file, callback, onFailure) {
    const form = new FormData()
    form.append('file', file)
    request('POST', `/persona/${encoded(personaId)}/versions/${encoded(version)}/signatures/${encoded(signatureKey)}/assets/${encoded(variant)}`, form, callback, onFailure, {})
  },
  deleteSignatureAsset(assetId, callback, onFailure) {
    request('DELETE', `/persona/signature-assets/${encoded(assetId)}`, undefined, callback, onFailure)
  },
  previewSignatureAsset(assetId, callback, onFailure) {
    RequestService.sendRequest()
      .url(`${getServiceUrl()}/persona/signature-assets/${encoded(assetId)}/play`)
      .method('GET')
      .type('blob')
      .success(callback)
      .fail(onFailure)
      .networkFail(onFailure)
      .send()
  }
}
