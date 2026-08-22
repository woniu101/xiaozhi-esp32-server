import { getServiceUrl } from '../api';
import RequestService from '../httpRequest';

export default {
    // 获取音色
    getVoiceList(params, callback) {
        const queryParams = new URLSearchParams({
            ttsModelId: params.ttsModelId,
            page: params.page || 1,
            limit: params.limit || 10,
            name: params.name || ''
        }).toString();

        RequestService.sendRequest()
            .url(`${getServiceUrl()}/ttsVoice?${queryParams}`)
            .method('GET')
            .success((res) => {
                RequestService.clearRequestTime();
                callback(res.data || []);
            })
            .networkFail((err) => {
                console.error('获取音色列表失败:', err);
                RequestService.reAjaxFun(() => {
                    this.getVoiceList(params, callback);
                });
            }).send();
    },
    // 音色保存
    saveVoice(params, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/ttsVoice`)
            .method('POST')
            .data(JSON.stringify({
                languages: params.languageType,
                name: params.voiceName,
                remark: params.remark,
                referenceAudio: params.referenceAudio,
                referenceText: params.referenceText,
                sort: params.sort,
                ttsModelId: params.ttsModelId,
                ttsVoice: params.voiceCode,
                voiceDemo: params.voiceDemo || ''
            }))
            .success((res) => {
                callback(res.data);
            })
            .networkFail((err) => {
                console.error('保存音色失败:', err);
                RequestService.reAjaxFun(() => {
                    this.saveVoice(params, callback);
                });
            }).send();
    },
    // 音色删除
    deleteVoice(ids, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/ttsVoice/delete`)
            .method('POST')
            .data(ids)
            .success((res) => {
                RequestService.clearRequestTime()
                callback(res);
            })
            .networkFail((err) => {
                console.error('删除音色失败:', err);
                RequestService.reAjaxFun(() => {
                    this.deleteVoice(ids, callback);
                });
            }).send();
    },
    // 音色修改
    updateVoice(params, callback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/ttsVoice/${params.id}`)
            .method('PUT')
            .data(JSON.stringify({
                languages: params.languageType,
                name: params.voiceName,
                remark: params.remark,
                referenceAudio: params.referenceAudio,
                referenceText: params.referenceText,
                sort: params.sort,
                ttsModelId: params.ttsModelId,
                ttsVoice: params.voiceCode,
                voiceDemo: params.voiceDemo || ''
            }))
            .success((res) => {
                callback(res.data);
            })
            .networkFail((err) => {
                console.error('修改音色失败:', err);
                RequestService.reAjaxFun(() => {
                    this.updateVoice(params, callback);
                });
            }).send();
    },

    getIndexRemoteVoices(ttsModelId, callback, errorCallback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/ttsVoice/indexTts/${ttsModelId}/voices`)
            .method('GET')
            .success((res) => callback(res.data))
            .fail(errorCallback)
            .networkFail(errorCallback)
            .send();
    },

    syncIndexRemoteVoices(ttsModelId, callback, errorCallback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/ttsVoice/indexTts/${ttsModelId}/sync`)
            .method('POST')
            .success((res) => callback(res.data))
            .fail(errorCallback)
            .networkFail(errorCallback)
            .send();
    },

    registerIndexVoice(ttsModelId, formData, callback, errorCallback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/ttsVoice/indexTts/${ttsModelId}/voices`)
            .method('POST')
            .data(formData)
            .success((res) => callback(res.data))
            .fail(errorCallback)
            .networkFail(errorCallback)
            .send();
    },

    deleteIndexVoice(ttsModelId, voiceId, callback, errorCallback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/ttsVoice/indexTts/${ttsModelId}/voices/${encodeURIComponent(voiceId)}`)
            .method('DELETE')
            .success((res) => callback(res.data))
            .fail(errorCallback)
            .networkFail(errorCallback)
            .send();
    },

    previewIndexVoice(ttsModelId, params, callback, errorCallback) {
        RequestService.sendRequest()
            .url(`${getServiceUrl()}/ttsVoice/indexTts/${ttsModelId}/preview`)
            .method('POST')
            .data(JSON.stringify(params))
            .type('arraybuffer')
            .success(callback)
            .fail(errorCallback)
            .networkFail(errorCallback)
            .send();
    }
}
