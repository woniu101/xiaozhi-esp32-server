import { getServiceUrl } from '../api';
import RequestService from '../httpRequest';

function request(method, path, data, callback, fail, options = {}) {
  const builder = RequestService.sendRequest()
    .url(`${getServiceUrl()}${path}`)
    .method(method)
    .data(data || {})
    .success(callback)
    .fail(fail)
    .networkFail(fail);
  if (options.formData) {
    builder.header({});
  }
  if (options.responseType) {
    builder.type(options.responseType);
  }
  builder.send();
}

export default {
  list(callback, fail) {
    request('GET', '/character-style', null, callback, fail);
  },
  get(styleId, callback, fail) {
    request('GET', `/character-style/${styleId}`, null, callback, fail);
  },
  importGithub(payload, callback, fail) {
    request('POST', '/character-style/import/github', payload, callback, fail);
  },
  importZip({ name, styleId, file }, callback, fail) {
    const form = new FormData();
    form.append('name', name);
    if (styleId) form.append('styleId', styleId);
    form.append('file', file);
    request('POST', '/character-style/import/zip', form, callback, fail, { formData: true });
  },
  bind(styleId, agentId, callback, fail) {
    request('PUT', `/character-style/${styleId}/agents/${agentId}`, null, callback, fail);
  },
  unbind(agentId, callback, fail) {
    request('DELETE', `/character-style/agents/${agentId}`, null, callback, fail);
  },
  remove(styleId, callback, fail) {
    request('DELETE', `/character-style/${styleId}`, null, callback, fail);
  },
  updateSignatures(styleId, payload, callback, fail) {
    request('PUT', `/character-style/${styleId}/signatures`, payload, callback, fail);
  },
  trialSignatureContext(styleId, payload, callback, fail) {
    request('POST', `/character-style/${styleId}/signatures/trial`, payload, callback, fail);
  },
  uploadSignatureAudio(styleId, itemId, file, callback, fail) {
    const form = new FormData();
    form.append('file', file);
    request(
      'POST',
      `/character-style/${styleId}/signatures/${itemId}/audio`,
      form,
      callback,
      fail,
      { formData: true }
    );
  },
  deleteSignatureAudio(styleId, itemId, callback, fail) {
    request(
      'DELETE',
      `/character-style/${styleId}/signatures/${itemId}/audio`,
      null,
      callback,
      fail
    );
  },
  getSignatureAudio(styleId, itemId, callback, fail) {
    request(
      'GET',
      `/character-style/${styleId}/signatures/${itemId}/audio`,
      null,
      callback,
      fail,
      { responseType: 'arraybuffer' }
    );
  }
};
