# Voice2Claim — API Integration Design

**Date:** 2026-07-18
**Topic:** Wire `index.html` to the documented Voice2Claim backend (`docs/v2c_apidoc.md`)
**Status:** Approved (all 5 design sections)
**File touched:** `index.html` only

---

## 1. Architecture Overview

### Goal

Wire the existing single-file Alpine.js `index.html` to the documented Voice2Claim backend at `https://api.dathoc.net/api`, replacing the relative-path + MQTT two-step flow with a synchronous Bearer-session + `process-voice` flow.

### Decisions locked from brainstorming

1. **Drop MQTT entirely** — rely on the synchronous `process-voice` response (the API doc's core feature).
2. **Lazy `/activate` with `localStorage` cache** + 401 interceptor that transparently re-activates and retries once.
3. **Resource-grouped `api` object** — `api.activate()`, `api.cases.list()`, `api.cases.get(id)`, `api.cases.create(body)`, `api.claims.processVoice(formData)`.
4. **Map structured fields per the API doc strictly** (decision 1A) — drop reads of `location`, `diagnosis`, `patient_name`, `damage_description`. Map only `vehicle_plate`, `damage_items[]` (joined), `estimated_cost`.
5. **Drop the pre-create empty case pattern** — `currentCaseId` is set ONLY from the `process-voice` response.
6. **Always stream audio from `BASE_URL + file_path`** via authenticated `fetch` → blob → WaveSurfer `loadBlob` (decision 3B).
7. **Inline processing status + toast on error**, with **localized human-friendly messages** keyed by `error.code` — never the raw `error.message` from the server.
8. **`BASE_URL = 'https://api.dathoc.net/api'`** (hardcoded prod). Delete `sampleTemplates` and the 4 fake sidebar incidents.
9. **`template_type` dropdown reduced to exactly 2 options**: `auto_claim`, `medical_claim`.

### File touched

`index.html` only. No new files, no build step, no dependencies added. Stays a single-file deployable demo.

### Alpine.js reactivity commitments

(Per current Alpine.js docs at alpinejs.dev, confirmed via Context7.)

- **Array updates:** `this.recordings.unshift(...)` is reactive (mutation method, confirmed by docs). `this.recordings = newArray` (full replacement) is also reactive.
- **Object property updates:** Alpine tracks direct property assignment (`this.currentCaseId = id`). To update a nested entry in `this.recordings`, replace the array entry with a fresh object: `this.recordings[i] = { ...rec, transcript: newTranscript }`. Never mutate a property of a nested object without reassigning the parent.
- **`this` binding in async:** all `fetch`/async callbacks use arrow functions (`async () => { ... }`) so `this` stays bound to the Alpine component. No `.bind(this)` inside arrow callbacks.
- **`x-model` fields:** ensure every `claimForm[field.id]` key exists (even as `''`) before the input renders — the existing `hydrateClaimForm()` already does this; pattern preserved.
- **`x-for :key`:** preserve on every template loop. New loops (toasts) get `:key="toast.id"`.

### Header reality

The API doc lists `Authorization`, `Accept-Language`, `Origin`, `User-Agent` as required. In browser `fetch`, `Origin` and `User-Agent` are set by the browser and cannot be overridden from JS. The client only injects `Authorization` and `Accept-Language`. A real browser request always sends a real `User-Agent` and the correct `Origin`. The doc's warning about overriding `User-Agent` applies to Axios/Postman, not browser fetch.

### High-level data flow

```
bootstrap() → loadIncidents() → api.cases.list() → render sidebar
            ↓ user picks a case
            → api.cases.get(id) → render recordings/images/report
            ↓ user records or uploads audio
            → api.claims.processVoice(formData)
            → response carries full CaseResponse (id, recordings, transcript, suggested_actions)
            → update currentCaseId, recordings, images, claim form (all reactive assignments)
            ↓ user edits/exports claim
            → api.claim.pdf / api.claim.share (kept as-is, just routed through api wrapper)
```

### Out of scope (kept as-is)

The PDF/share endpoints (`/api/claim/pdf`, `/api/claim/share`) aren't in the new API doc but aren't documented as removed either. We route them through the `api` wrapper for headers/errors but don't change their request shape. If the backend later drops them, that's a separate change.

---

## 2. API Client

A single `api` object defined at the top of the `<script>` block, before `claimFlow()`. ~90 lines.

### Constants

```js
const BASE_URL = 'https://api.dathoc.net/api';
const STORAGE_KEY = 'v2c_session_id';
```

(`navigator.userAgent` is used implicitly by the browser — no JS constant needed.)

### Session store

A tiny module-pattern helper:

```js
const session = {
    get() { return localStorage.getItem(STORAGE_KEY); },
    set(id) { localStorage.setItem(STORAGE_KEY, id); },
    clear() { localStorage.removeItem(STORAGE_KEY); },
};
```

### Typed error

```js
class ApiError extends Error {
    constructor(code, message, status) {
        super(message);
        this.code = code;       // 'SESSION_EXPIRED', 'INVALID_FILE_TYPE', etc.
        this.status = status;   // HTTP status
        this.name = 'ApiError';
    }
}
```

### Core `request()` helper

The only place that touches `fetch`:

```js
async function request(path, { method = 'GET', body, isForm = false, retries = 0 } = {}) {
    const headers = {
        'Authorization': `Bearer ${session.get() || ''}`,
        'Accept-Language': window.AlpineI18n ? AlpineI18n.locale : 'vi',
    };
    if (!isForm) headers['Content-Type'] = 'application/json';

    const resp = await fetch(BASE_URL + path, { method, headers, body });

    // 401 → re-activate once and retry
    if (resp.status === 401 && retries < 1) {
        await api.activate();
        return request(path, { method, body, isForm, retries: retries + 1 });
    }

    // Non-2xx → parse standardized envelope and throw ApiError
    if (!resp.ok) {
        let code = 'UNKNOWN', message = '';
        try {
            const data = await resp.json();
            code = data.error?.code || 'UNKNOWN';
            message = data.error?.message || '';
        } catch (_) { /* keep defaults */ }
        throw new ApiError(code, message, resp.status);
    }

    // Blob or JSON
    const ct = resp.headers.get('Content-Type') || '';
    if (ct.includes('application/json')) return resp.json();
    return resp.blob();
}
```

### Resource-grouped `api` object

```js
const api = {
    async activate() {
        const fingerprint = 'fp_' + Math.random().toString(36).slice(2);
        const data = await request('/activate', {
            method: 'POST',
            body: JSON.stringify({ fingerprint }),
        });
        session.set(data.session_id);
        return data.session_id;
    },

    cases: {
        async list() {
            const data = await request('/cases');
            return data.data; // unwrap { data: [...] }
        },
        async get(id) {
            return request(`/cases/${id}`);
        },
        // create(body) is documented in the API doc (§4.5) but unused in our flow
        // (we dropped the pre-create empty case pattern). Kept here for completeness
        // and future use (e.g., manual case creation UI). Not called by claimFlow().
        async create(body) {
            return request('/cases', { method: 'POST', body: JSON.stringify(body) });
        },
    },

    claims: {
        async processVoice(formData) {
            return request('/claims/process-voice', {
                method: 'POST',
                body: formData,
                isForm: true,
            });
        },
    },

    // PDF/share endpoints — kept on the api object for consistent headers/errors
    claim: {
        async pdf(payload) { /* POST, returns blob */ },
        async share(payload) { /* POST */ },
    },
};
```

### Behavioral notes

- **Lazy activation:** `api.activate()` is called inside `request()` only on the first 401 — never preemptively. The very first call (`api.cases.list()` in `bootstrap()`) may trigger a transparent activate + retry.
- **401 retry cap:** exactly one retry. A second 401 throws `ApiError('SESSION_EXPIRED', ...)`, which the UI surfaces as a toast.
- **`Accept-Language`** reads from `AlpineI18n.locale` so it always matches the current UI language; falls back to `'vi'` if i18n isn't ready yet.
- **`isForm` flag** prevents setting `Content-Type: application/json` on multipart uploads (browser needs to set the boundary itself).
- **No timeout** in v1; can add `AbortController` later if needed.

### Removed

Every direct `fetch('/api/...')` call in the existing code (~8 sites) is replaced by an `api.*` call. The `mqtt` CDN script and `initMQTT()` / `handleTranscript()` / `handleFailed()` / `handleAnnotations()` methods are deleted.

---

## 3. Component State Changes

Diff against the existing `claimFlow()` Alpine component. Grouped by what's **added**, **modified**, **removed**.

### Added state

```js
toasts: [],            // [{ id, code, message }] — top-right stack, auto-dismiss
isProcessing: false,    // true while process-voice is in flight
processingStatus: '',  // i18n key shown inline, e.g. 'processing.transcribing'
```

### Modified state (existing fields, new semantics)

```js
currentCaseId: null,   // now set ONLY from process-voice response (was: from POST /cases)
recordings: [],        // now populated from CaseResponse.recordings (was: from upload + MQTT)
images: [],            // now populated from CaseResponse.images
selectedTemplate: 'auto_claim',  // was 'vehicle'; dropdown now 2 options
```

### Removed state

```js
mqttClient: null,      // deleted
audioChunks: [],       // kept only during active recording; not stored long-term
sampleTemplates: {},  // deleted entirely (4 hardcoded date entries)
```

### Added methods

```js
pushToast(code) {
    const msg = this.t(`errors.${code}`) || this.t('errors.UNKNOWN');
    const id = Date.now() + Math.random();
    this.toasts.push({ id, code, message: msg });
    setTimeout(() => {
        this.toasts = this.toasts.filter(t => t.id !== id);  // full replacement = reactive
    }, 5000);
},
t(key) {
    return window.AlpineI18n ? AlpineI18n.t(key) : key;
},
```

### Modified methods

#### `bootstrap()` — drop `initMQTT()`; keep `loadIncidents()` + `hydrateClaimForm()`

```js
async bootstrap() {
    await this.$nextTick();
    await this.loadIncidents();
    this.hydrateClaimForm();
}
```

#### `loadIncidents()` — use `api.cases.list()`, map to existing sidebar shape

```js
async loadIncidents() {
    try {
        const cases = await api.cases.list();
        this.incidents = cases.map(c => {
            const raw = c.recordings?.[0]?.transcript?.raw_text || '';
            return {
                id: c.id,
                title: c.title,
                created_at: c.created_at,
                recording_count: (c.recordings || []).length,
                snippet: raw ? raw.slice(0, 80) + '…' : '',
            };
        });
        if (this.incidents.length && !this.selectedIncidentId) {
            this.selectIncident(this.incidents[0].id);
        }
    } catch (e) {
        this.pushToast(e.code || 'UNKNOWN');
    }
}
```

#### `loadCaseDetail(id)` — use `api.cases.get()`, map recordings/images directly (Alpine reactive full-array replacement)

```js
async loadCaseDetail(caseId) {
    try {
        const data = await api.cases.get(caseId);
        this.recordings = (data.recordings || []).map(r => ({
            id: r.id,
            file_path: r.file_path,
            duration_sec: r.duration_sec,
            status: r.status,
            template_type: r.template_type,
            transcript: r.transcript,
            image_id: null,
        }));
        this.images = (data.images || []).map(img => ({
            id: img.id,
            file_path: img.file_path,
            status: img.status,
            annotations: img.annotations || [],
        }));
        if (this.recordings.length) this.selectRecording(this.recordings[0].id);
        else this.selectedRecordingId = null;
    } catch (e) {
        this.pushToast(e.code || 'UNKNOWN');
    }
}
```

#### `uploadAudio()` (called from `MediaRecorder.onstop`) — drop the 2-step create+upload, call `process-voice`

```js
async uploadAudio() {
    const chunks = this.audioChunks;
    if (!chunks?.length) return;
    const blob = new Blob(chunks, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('audio', blob, `recording_${Date.now()}.webm`);
    formData.append('template_type', this.selectedTemplate);  // 'auto_claim' or 'medical_claim'
    this.isProcessing = true;
    this.processingStatus = 'processing.transcribing';
    try {
        const data = await api.claims.processVoice(formData);
        this.currentCaseId = data.id;
        this.recordings = (data.recordings || []).map(r => ({
            id: r.id,
            file_path: r.file_path,
            duration_sec: r.duration_sec,
            status: r.status,
            template_type: r.template_type,
            transcript: r.transcript,
            image_id: null,
        }));
        this.images = (data.images || []).map(img => ({
            id: img.id,
            file_path: img.file_path,
            status: img.status,
            annotations: img.annotations || [],
        }));
        if (this.recordings.length) this.selectRecording(this.recordings[0].id);
        await this.loadIncidents();  // refresh sidebar
    } catch (e) {
        this.pushToast(e.code || 'UNKNOWN');
    } finally {
        this.isProcessing = false;
        this.processingStatus = '';
    }
}
```

#### `uploadAudioFile(event)` — same `process-voice` pattern, iterate files, one call per file (no pre-create)

```js
async uploadAudioFile(event) {
    const files = event.target.files;
    for (const file of files) {
        if (!this.validateAudioFile(file)) continue;
        const formData = new FormData();
        formData.append('audio', file);
        formData.append('template_type', this.selectedTemplate);
        this.isProcessing = true;
        this.processingStatus = 'processing.transcribing';
        try {
            const data = await api.claims.processVoice(formData);
            this.currentCaseId = data.id;
            this.recordings = (data.recordings || []).map(r => ({
                id: r.id,
                file_path: r.file_path,
                duration_sec: r.duration_sec,
                status: r.status,
                template_type: r.template_type,
                transcript: r.transcript,
                image_id: null,
            }));
            this.images = (data.images || []).map(img => ({
                id: img.id,
                file_path: img.file_path,
                status: img.status,
                annotations: img.annotations || [],
            }));
            if (this.recordings.length) this.selectRecording(this.recordings[0].id);
            await this.loadIncidents();
        } catch (e) {
            this.pushToast(e.code || 'UNKNOWN');
        } finally {
            this.isProcessing = false;
            this.processingStatus = '';
        }
    }
    event.target.value = '';
}
```

#### `loadWaveform(id)` — stream from `BASE_URL + file_path` via authenticated fetch (decision 3B)

```js
async loadWaveform(id) {
    if (typeof WaveSurfer === 'undefined') return;
    await this.$nextTick();
    const container = this.$refs.waveform;
    if (!container) return;
    if (this.wavesurfer) {
        try { this.wavesurfer.destroy(); } catch (e) {}
        this.wavesurfer = null;
    }
    this.wavesurfer = this.initWaveSurfer(container);
    try {
        const rec = this.recordings.find(r => r.id === id);
        if (!rec?.file_path) return;
        // file_path from API doc example: "./uploads/1784377898_giamdinh_01.wav"
        // Strip leading "./" and pass to request(), which prepends BASE_URL.
        // → resolves to https://api.dathoc.net/api/uploads/1784377898_giamdinh_01.wav
        const relative = rec.file_path.replace(/^\.\//, '');
        const blob = await request('/' + relative);  // authenticated fetch, returns blob
        this.wavesurfer.loadBlob(blob);
    } catch (e) {
        console.error('loadWaveform failed:', e);
    }
}
```

**⚠ Assumption to verify:** the API doc shows `file_path = "./uploads/1784377898_giamdinh_01.wav"` but does not document an audio-fetch endpoint. We assume the audio file is reachable at `BASE_URL + '/' + relative` (i.e., under `/api/uploads/...`). If the backend serves uploads from a different path (e.g., `https://api.dathoc.net/uploads/...` outside `/api`), `loadWaveform` will 404. **Verify this against the live backend before shipping.** If wrong, the fix is a one-line `AUDIO_BASE_URL` constant.

#### `currentClaimSourceValues()` — strict per API doc (decision 1A), drop fallback reads

```js
currentClaimSourceValues() {
    if (this.activeQuickAccess !== 'current') return {};  // sampleTemplates removed
    const rec = this.recordings.find(r => r.id === this.selectedRecordingId);
    if (!rec?.transcript) return {};
    const s = rec.transcript.structured || {};
    const txt = rec.transcript.raw_text || '';
    const values = {};
    if (s.vehicle_plate) values.vehiclePlate = s.vehicle_plate;
    if (Array.isArray(s.damage_items)) values.vehicleDamage = s.damage_items.join('\n');
    if (s.estimated_cost) values.estimatedAmount = this.formatVND(s.estimated_cost);
    if (txt && Object.keys(values).length === 0) values.accidentDescription = txt;
    return values;
}
```

#### `formatVND(n)` — new helper

```js
formatVND(n) {
    return new Intl.NumberFormat('vi-VN').format(n) + ' ₫';
}
```

#### `validateAudioFile(file)` — new pre-flight check

```js
validateAudioFile(file) {
    const ALLOWED_AUDIO = ['wav', 'mp3', 'm4a', 'ogg', 'flac', 'webm'];
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_AUDIO.includes(ext)) {
        this.pushToast('INVALID_FILE_TYPE');
        return false;
    }
    return true;
}
```

### Removed methods

```js
initMQTT()              // deleted
handleTranscript(data)  // deleted (process-voice is synchronous)
handleFailed(data)      // deleted
handleAnnotations(data) // deleted
```

### Removed markup

- The **4 fake sidebar `<div class="audio-item">` blocks** (lines ~1214–1281) — removed; the `<template x-for="incident in incidents">` already renders real incidents. The `x-show="incidents.length === 0"` empty-state block stays.
- The **`sampleTemplates` block** (~60 lines, lines 1789–1851) — all 4 date entries deleted. The `activeQuickAccess` quick-access dropdown keeps only the `"current"` option; the `<template x-for="d in Object.keys(sampleTemplates)">` loop is removed, leaving just the "Current" button.

---

## 4. Markup & i18n Changes

### Markup additions

#### Toast container — top-right fixed stack, added just before `</body>`

```html
<div class="toast-container" x-show="toasts.length > 0"
     style="position:fixed;top:16px;right:16px;z-index:1000;display:flex;flex-direction:column;gap:8px;">
    <template x-for="toast in toasts" :key="toast.id">
        <div class="toast" x-text="toast.message"
             style="background:#f5576c;color:white;padding:12px 16px;border-radius:8px;
                    box-shadow:0 4px 12px rgba(0,0,0,0.15);font-size:13px;max-width:320px;"></div>
    </template>
</div>
```

#### Processing indicator — inline next to the record button

```html
<button class="record-btn" id="recordBtn" @click="toggleRecording()" :disabled="isProcessing">
    <!-- existing icon -->
    <span x-text="isProcessing
        ? $t('processing.transcribing')
        : (isRecording
            ? $t('record.recording_info', { sec: recordingSeconds })
            : $t('record.start_info'))"></span>
</button>
<span x-show="isProcessing" class="processing-spinner" x-text="$t(processingStatus)"></span>
```

*(CSS for `.processing-spinner` — small inline-loading text with a pulsing dot; ~5 lines added to the `<style>` block.)*

### Markup modifications

#### Template dropdown — reduce from 4 options to 2 (decision 9)

```html
<select x-model="selectedTemplate">
    <option value="auto_claim" x-text="$t('report.template_auto')"></option>
    <option value="medical_claim" x-text="$t('report.template_medical')"></option>
</select>
```

Removes the `vehicle`/`medical`/`fire`/`injury` options and their i18n keys (`report.template_vehicle`, `report.template_fire`, `report.template_injury`).

#### Quick-access dropdown — keep only the "Current" button

```html
<button class="quick-access-btn" :class="{ 'active': activeQuickAccess === 'current' }"
        @click="selectQuickAccess('current')">
    <span x-text="$t('report.current')"></span>
</button>
<!-- template loop over Object.keys(sampleTemplates) deleted -->
```

### Markup deletions

- The **MQTT script tag**: `<script src="https://cdn.jsdelivr.net/npm/mqtt@..."></script>` (if present) — removed.
- The **4 fake sidebar `<div class="audio-item">` blocks** (lines 1214–1281) — removed; the `<template x-for>` already renders real incidents.
- The **`<template x-for="d in Object.keys(sampleTemplates)">`** block — removed.

### i18n additions (both `vi` and `en` locales)

#### New `processing.*` block

Only `processing.transcribing` is set in code today. `processing.extracting` and `processing.saving` are reserved for future granular status if the backend ever streams progress (currently the synchronous `process-voice` call doesn't expose intermediate stages). Defined now so i18n doesn't lag behind if we add them later.

| Key | VI | EN |
|-----|----|----|
| `processing.transcribing` | "Đang xử lý giọng nói…" | "Processing voice…" |
| `processing.extracting` | "Đang trích xuất thông tin…" | "Extracting information…" |
| `processing.saving` | "Đang lưu hồ sơ…" | "Saving case…" |

#### New `errors.*` block — every documented error code gets a human-friendly message (decision 7)

These are **never** the raw server message:

| Key | VI | EN |
|-----|----|----|
| `errors.UNAUTHORIZED` | "Vui lòng đăng nhập lại." | "Please sign in again." |
| `errors.SESSION_EXPIRED` | "Phiên đã hết hạn, đang tự động kết nối lại…" | "Session expired, reconnecting…" |
| `errors.INVALID_INPUT` | "Dữ liệu không hợp lệ, vui lòng kiểm tra lại." | "Invalid input, please check and try again." |
| `errors.ASR_FAILED` | "Không thể nhận dạng giọng nói, vui lòng thử lại." | "Could not transcribe the audio, please try again." |
| `errors.LLM_FAILED` | "Hệ thống trích xuất thông tin gặp lỗi, vui lòng thử lại." | "Information extraction failed, please try again." |
| `errors.DB_ERROR` | "Lỗi lưu trữ dữ liệu, vui lòng thử lại." | "Storage error, please try again." |
| `errors.BOT_DETECTED` | "Truy cập bị từ chối." | "Access denied." |
| `errors.INVALID_FILE_TYPE` | "Định dạng file không được hỗ trợ. Hỗ trợ: .wav, .mp3, .m4a, .ogg, .flac, .webm" | "Unsupported file format. Supported: .wav, .mp3, .m4a, .ogg, .flac, .webm" |
| `errors.NOT_FOUND` | "Không tìm thấy hồ sơ." | "Case not found." |
| `errors.UNKNOWN` | "Đã xảy ra lỗi, vui lòng thử lại." | "Something went wrong, please try again." |

#### Modified `report.template_*` keys (renamed, not removed)

| Key | VI | EN |
|-----|----|----|
| `report.template_auto` | "Giám định xe/others" | "Auto Claim" |
| `report.template_medical` | "Giám định y tế" | "Medical Claim" |

*(The old `report.template_vehicle` key is removed; `report.template_medical` is repurposed for `medical_claim`.)*

### What stays unchanged in markup

- Header, sidebar skeleton, audio player card structure, image preview, report card structure, recordings list, completed-actions panel — all keep their current markup.
- The `claimFormSchema` JSON, `requiredClaimFieldIds`, `missingClaimFields` getter, `hasClaimData` getter, `claimEditMode` / `saveClaimForm` / `cancelClaimEdit` / `downloadClaimPdf` / `shareClaimPdf` — unchanged (PDF/share just get routed through the `api` wrapper internally).
- `alpinejs-i18n` loading and locale-toggle button — unchanged.

---

## 5. Error Handling, Testing & Migration Plan

### Error handling strategy

**Single funnel:** every `api.*` call is wrapped in `try/catch` at the call site. The catch handler is always:

```js
} catch (e) {
    this.pushToast(e.code || 'UNKNOWN');
}
```

No `alert()`, no `console.error`-only paths. `ApiError` carries `.code` so the toast lookup is deterministic.

### The 4 documented problem cases (from `docs/v2c_apidoc.md` §6)

| Symptom | Code | UX |
|---------|------|----|
| 403 + `BOT_DETECTED` | `BOT_DETECTED` | Toast "Access denied" — nothing the user can do, but we still surface it. (Browser sends real `User-Agent` + `Origin` automatically, so this should never trigger from our client.) |
| 403 + `INVALID_ORIGIN` | *(not in error code list)* | Falls through to `UNKNOWN` toast. Shouldn't happen since `Origin` is browser-set. |
| 401 + `SESSION_EXPIRED` | `SESSION_EXPIRED` | `request()` intercepts **before** the catch — re-activates transparently and retries once. The user only sees a toast if the retry also 401s. |
| 400 + `INVALID_FILE_TYPE` | `INVALID_FILE_TYPE` | Toast with the supported-formats list (already in the i18n string). The file picker `accept=".wav,.mp3,.m4a,.ogg,.flac,.webm"` prevents most cases. |

### Pre-flight file validation

Cheap, avoids a round-trip:

```js
const ALLOWED_AUDIO = ['wav', 'mp3', 'm4a', 'ogg', 'flac', 'webm'];
validateAudioFile(file) {
    const ext = file.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_AUDIO.includes(ext)) {
        this.pushToast('INVALID_FILE_TYPE');
        return false;
    }
    return true;
}
```

Called in `uploadAudioFile()` before building `FormData`. Recording (`MediaRecorder`) always produces `audio/webm` so it's always valid.

### Processing-failure recovery

If `process-voice` fails mid-recording, `isProcessing` is reset in `finally`, the recording is **not** added to `recordings` (no orphaned "transcribing" status entry), and the user can re-record or re-upload immediately. The local `audioChunks` are cleared on the next `startRecording()`.

### Testing approach

No test framework in the project today, and adding one is out of scope for this change. Verification is **manual + behavioral**:

1. **Session flow:** open fresh (clear `localStorage`) → first `loadIncidents()` triggers transparent `/activate` + retry → sidebar loads.
2. **401 retry:** manually corrupt `localStorage.v2c_session_id` → any call → transparent re-activate + retry succeeds; user sees no toast.
3. **Session-expired dead-end:** corrupt `session_id` and stub `/activate` to return 401 → user sees `SESSION_EXPIRED` toast.
4. **Record → process-voice:** record 5s → stop → spinner shows → response arrives → sidebar updates, recording selected, waveform loads from `BASE_URL + file_path`, claim form hydrates with `vehicle_plate` / `damage_items` / `estimated_cost`.
5. **Upload file:** pick `.wav` → process-voice → same as above. Pick `.txt` → pre-flight `INVALID_FILE_TYPE` toast, no network call.
6. **Template dropdown:** only 2 options; switching to `medical_claim` before recording sends `template_type: 'medical_claim'` in form data (verify in Network tab).
7. **Locale toggle:** switch VI ↔ EN → next API call sends matching `Accept-Language` header.
8. **Sidebar from `GET /cases`:** reload page → sidebar populated from backend, no fake entries.
9. **Removed code grep:** `rg "sampleTemplates|initMQTT|mqttClient|/api/cases.*upload" index.html` returns nothing.
10. **Lint/typecheck:** none configured — skip. (No `package.json` scripts exist; README has no lint instructions.)

### Migration / rollout

Single-file deploy — no build step, no versioned migration. The change ships as one commit to `index.html`:

1. Edit `index.html` in place (add `api` object + `ApiError` + `session` helpers + new state + new methods; modify existing methods; delete MQTT + `sampleTemplates` + fake sidebar items; update markup; add i18n keys).
2. Open `index.html` locally against the live `https://api.dathoc.net/api` backend — no local server needed since `BASE_URL` is hardcoded prod.
3. Run the 10 manual checks above.
4. Commit once all pass. No PR branching strategy specified — single commit on `main` is fine unless the team prefers a feature branch.

### Rollback

`git revert` the single commit. The old relative-path + MQTT flow is restored. No data migration either direction (no schema changes, `localStorage` key `v2c_session_id` is new and harmless if the old code runs).

### Risk surface

- **Backend contract drift:** if the backend's `structured` block emits fields not in the doc (`location`, `diagnosis`, etc.), decision 1A means they're ignored. Acceptable per the user's choice.
- **`process-voice` latency:** synchronous call could take 5–15s for long audio. Spinner + disabled record button prevents double-submits. If this becomes a real UX problem, a future change can add long-polling on `GET /cases/{id}` — out of scope here.
- **PDF/share endpoints:** not in the new doc. If the backend drops them, `downloadClaimPdf` / `shareClaimPdf` will throw `ApiError('UNKNOWN', ...)`. The toast will say "Something went wrong" — graceful failure, no crash.

### Done criteria (full)

- [ ] All `fetch('/api/...')` replaced by `api.*` calls
- [ ] `mqtt` script + `initMQTT` / `handleTranscript` / `handleFailed` / `handleAnnotations` removed
- [ ] `sampleTemplates` + 4 fake sidebar items removed
- [ ] `template_type` dropdown has exactly 2 options
- [ ] `BASE_URL` hardcoded to prod
- [ ] Toast container + 10 `errors.*` i18n keys present (VI + EN)
- [ ] 3 `processing.*` i18n keys present (VI + EN)
- [ ] `request()` handles 401 → activate → retry once
- [ ] All async callbacks use arrow functions (preserve `this`)
- [ ] `loadWaveform` streams via authenticated `request()` from `BASE_URL + file_path`
- [ ] 10 manual verification checks pass