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
  importJob(jobId, callback, onFailure) {
    request('GET', `/persona/import/jobs/${encoded(jobId)}`, undefined, callback, onFailure)
  },
  cancelImport(jobId, callback, onFailure) {
    request('POST', `/persona/import/jobs/${encoded(jobId)}/cancel`, {}, callback, onFailure)
  },
  publish(personaId, version, visibility, callback, onFailure) {
    request('POST', `/persona/${encoded(personaId)}/versions/${encoded(version)}/publish`, { visibility }, callback, onFailure)
  },
  rollback(personaId, version, callback, onFailure) {
    request('POST', `/persona/${encoded(personaId)}/versions/${encoded(version)}/rollback`, {}, callback, onFailure)
  },
  archive(personaId, version, callback, onFailure) {
    request('POST', `/persona/${encoded(personaId)}/versions/${encoded(version)}/archive`, {}, callback, onFailure)
  },
  rerunTest(personaId, version, conversationSamples, callback, onFailure) {
    request('POST', `/persona/${encoded(personaId)}/versions/${encoded(version)}/test`, { conversationSamples: conversationSamples || [] }, callback, onFailure)
  },
  testRuns(personaId, version, callback, onFailure) {
    request('GET', `/persona/${encoded(personaId)}/versions/${encoded(version)}/tests`, undefined, callback, onFailure)
  },
  audit(personaId, callback, onFailure) {
    request('GET', `/persona/${encoded(personaId)}/audit`, undefined, callback, onFailure)
  }
}
