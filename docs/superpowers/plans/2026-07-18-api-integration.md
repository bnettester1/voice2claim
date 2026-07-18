# Voice2Claim API Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing single-file `index.html` Alpine.js app to the documented Voice2Claim backend at `https://api.dathoc.net/api`, replacing the relative-path + MQTT two-step flow with a synchronous Bearer-session + `process-voice` flow.

**Architecture:** A resource-grouped `api` object wraps every backend call, injecting `Authorization` + `Accept-Language` headers, transparently re-activating on 401, and throwing typed `ApiError` instances. The Alpine component (`claimFlow()`) drops MQTT and the pre-create empty-case pattern, calling `api.claims.processVoice(formData)` directly for both recording and file-upload paths. Error UX is a localized toast keyed by `error.code` (never the raw server message).

**Tech Stack:** Vanilla JS, Alpine.js 3.13.5, alpinejs-i18n 2.5.3, WaveSurfer 7. No build step, no new dependencies, single-file deployable.

**Spec:** `docs/superpowers/specs/2026-07-18-api-integration-design.md`

**File touched:** `index.html` (only).

---

## File Structure

Only `index.html` is modified. Changes land in three regions of that file:

1. **Markup region (lines ~1165–1587)** — toast container, template dropdown (2 options), processing indicator, removal of 4 fake sidebar items + quick-access template loop.
2. **i18n region (lines ~1593–1759)** — add `processing.*` and `errors.*` blocks (VI + EN), remove `template_vehicle`/`template_fire`/`template_injury`, add `template_auto`.
3. **JS region (lines ~1760–2457)** — add `BASE_URL`, `STORAGE_KEY`, `session`, `ApiError`, `request()`, `api`; modify `claimFlow()` state + methods; remove MQTT + `sampleTemplates`.

No new files. No tests (project has no test framework — verification is manual per the spec §5).

---

## Task Order

Tasks are ordered so each commit leaves the page in a working state (no broken markup, no dangling references):

1. **Task 1:** Add `BASE_URL`, `STORAGE_KEY`, `session`, `ApiError`, `request()`, `api` (the API client scaffolding, unused at first).
2. **Task 2:** Add `processing.*` + `errors.*` i18n keys (VI + EN), add `template_auto`, remove unused template keys.
3. **Task 3:** Add new Alpine state (`toasts`, `isProcessing`, `processingStatus`), `pushToast`, `t`, `formatVND`, `validateAudioFile` methods.
4. **Task 4:** Rewrite `bootstrap()`, `loadIncidents()`, `loadCaseDetail()` to use `api.*` and arrow-function `this` binding.
5. **Task 5:** Rewrite `uploadAudio()` and `uploadAudioFile()` to use `api.claims.processVoice()`.
6. **Task 6:** Rewrite `loadWaveform()` to stream from `BASE_URL + file_path` via authenticated `request()`.
7. **Task 7:** Rewrite `currentClaimSourceValues()` to strict API-doc mapping; remove `sampleTemplates` + `activeQuickAccess` sample loop.
8. **Task 8:** Update markup: toast container, template dropdown (2 options), processing indicator, remove 4 fake sidebar items + quick-access template loop.
9. **Task 9:** Remove MQTT script tag + `initMQTT`/`handleTranscript`/`handleFailed`/`handleAnnotations` methods.
10. **Task 10:** Route `downloadClaimPdf`/`shareClaimPdf` through `api.claim.*` (no behavior change, just headers + error envelope).
11. **Task 11:** Manual verification against the 10 checks in spec §5.

Each task ends with a commit. Tasks 1–3 are additive (page still works the old way). Task 4–7 switch call sites (page now hits the real backend). Tasks 8–10 are cleanup. Task 11 is verification.

---

## Task 1: Add API Client Scaffolding

**Files:**
- Modify: `index.html` (insert a new `<script>` block after line 1759, before the Alpine `<script defer>` tag at line 1760)

- [ ] **Step 1: Insert the API client block**

Open `index.html`. Find the closing `</script>` of the i18n block at line 1759:

```html
        document.addEventListener('alpine-i18n:locale-change', function () {
            const loc = window.AlpineI18n.locale;
            document.documentElement.lang = loc;
            localStorage.setItem('v2c_locale', loc);
        });
    </script>
```

Immediately after that `</script>` and before the Alpine `<script defer>` tag, insert:

```html
    <script>
        const BASE_URL = 'https://api.dathoc.net/api';
        const STORAGE_KEY = 'v2c_session_id';

        const session = {
            get() { return localStorage.getItem(STORAGE_KEY); },
            set(id) { localStorage.setItem(STORAGE_KEY, id); },
            clear() { localStorage.removeItem(STORAGE_KEY); },
        };

        class ApiError extends Error {
            constructor(code, message, status) {
                super(message);
                this.code = code;
                this.status = status;
                this.name = 'ApiError';
            }
        }

        async function request(path, { method = 'GET', body, isForm = false, retries = 0 } = {}) {
            const headers = {
                'Authorization': `Bearer ${session.get() || ''}`,
                'Accept-Language': window.AlpineI18n ? AlpineI18n.locale : 'vi',
            };
            if (!isForm) headers['Content-Type'] = 'application/json';

            const resp = await fetch(BASE_URL + path, { method, headers, body });

            if (resp.status === 401 && retries < 1) {
                await api.activate();
                return request(path, { method, body, isForm, retries: retries + 1 });
            }

            if (!resp.ok) {
                let code = 'UNKNOWN', message = '';
                try {
                    const data = await resp.json();
                    code = data.error?.code || 'UNKNOWN';
                    message = data.error?.message || '';
                } catch (_) { /* keep defaults */ }
                throw new ApiError(code, message, resp.status);
            }

            const ct = resp.headers.get('Content-Type') || '';
            if (ct.includes('application/json')) return resp.json();
            return resp.blob();
        }

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
                    return data.data;
                },
                async get(id) {
                    return request(`/cases/${id}`);
                },
                // create() is documented (§4.5) but unused in our flow (we dropped pre-create).
                // Kept for completeness and future manual-case-creation UI.
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

            claim: {
                async pdf(payload) {
                    return request('/claim/pdf', {
                        method: 'POST',
                        body: JSON.stringify(payload),
                    });
                },
                async share(payload) {
                    return request('/claim/share', {
                        method: 'POST',
                        body: JSON.stringify(payload),
                    });
                },
            },
        };
    </script>
```

- [ ] **Step 2: Verify the file parses**

Open `index.html` in a browser with DevTools open. The page should load with no console errors (the API client is defined but not yet called). Confirm `typeof api === 'object'` and `typeof request === 'function'` in the console.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "feat(api): add api client scaffolding (BASE_URL, session, ApiError, request, api)"
```

---

## Task 2: Add `processing.*` and `errors.*` i18n Keys

**Files:**
- Modify: `index.html` i18n VI block (lines 1594–1669) and EN block (lines 1670–1744)

- [ ] **Step 1: Add processing + errors keys to the VI block**

Find the VI `report: { ... }` block ending at line 1661 with `},`. Right after that `},` (before `recordings: { ... }` on line 1662), insert:

```js
                processing: {
                    transcribing: 'Đang xử lý giọng nói…',
                    extracting: 'Đang trích xuất thông tin…',
                    saving: 'Đang lưu hồ sơ…',
                },
                errors: {
                    UNAUTHORIZED: 'Vui lòng đăng nhập lại.',
                    SESSION_EXPIRED: 'Phiên đã hết hạn, đang tự động kết nối lại…',
                    INVALID_INPUT: 'Dữ liệu không hợp lệ, vui lòng kiểm tra lại.',
                    ASR_FAILED: 'Không thể nhận dạng giọng nói, vui lòng thử lại.',
                    LLM_FAILED: 'Hệ thống trích xuất thông tin gặp lỗi, vui lòng thử lại.',
                    DB_ERROR: 'Lỗi lưu trữ dữ liệu, vui lòng thử lại.',
                    BOT_DETECTED: 'Truy cập bị từ chối.',
                    INVALID_FILE_TYPE: 'Định dạng file không được hỗ trợ. Hỗ trợ: .wav, .mp3, .m4a, .ogg, .flac, .webm',
                    NOT_FOUND: 'Không tìm thấy hồ sơ.',
                    UNKNOWN: 'Đã xảy ra lỗi, vui lòng thử lại.',
                },
```

- [ ] **Step 2: Remove old template keys and add `template_auto` in VI block**

In the same VI block, find the `report: { ... }` block. Replace these 4 lines (1612–1615):

```js
                    template_vehicle: '🚗 Giám định tai nạn xe ô tô',
                    template_medical: '🏥 Đơn bệnh / Giám định y tế',
                    template_fire: '🔥 Giám định hỏa hoạn, bão lũ',
                    template_injury: '🩹 Giám định thương tật',
```

with these 2 lines:

```js
                    template_auto: '🚗 Giám định xe / tài sản',
                    template_medical: '🏥 Giám định y tế',
```

- [ ] **Step 3: Add processing + errors keys to the EN block**

Find the EN `recordings: { ... }` line at 1737. Right before it (after the EN `report: { ... }` block closes with `},` at line 1736), insert:

```js
                processing: {
                    transcribing: 'Processing voice…',
                    extracting: 'Extracting information…',
                    saving: 'Saving case…',
                },
                errors: {
                    UNAUTHORIZED: 'Please sign in again.',
                    SESSION_EXPIRED: 'Session expired, reconnecting…',
                    INVALID_INPUT: 'Invalid input, please check and try again.',
                    ASR_FAILED: 'Could not transcribe the audio, please try again.',
                    LLM_FAILED: 'Information extraction failed, please try again.',
                    DB_ERROR: 'Storage error, please try again.',
                    BOT_DETECTED: 'Access denied.',
                    INVALID_FILE_TYPE: 'Unsupported file format. Supported: .wav, .mp3, .m4a, .ogg, .flac, .webm',
                    NOT_FOUND: 'Case not found.',
                    UNKNOWN: 'Something went wrong, please try again.',
                },
```

- [ ] **Step 4: Remove old template keys and add `template_auto` in EN block**

In the same EN block, find the `report: { ... }` block. Replace these 4 lines (1687–1690):

```js
                    template_vehicle: '🚗 Vehicle Accident Assessment',
                    template_medical: '🏥 Medical Assessment',
                    template_fire: '🔥 Fire / Storm Assessment',
                    template_injury: '🩹 Injury Assessment',
```

with these 2 lines:

```js
                    template_auto: '🚗 Vehicle / Property Claim',
                    template_medical: '🏥 Medical Claim',
```

- [ ] **Step 5: Verify both locales parse**

Reload `index.html` in the browser. Open the console and run:

```js
AlpineI18n.t('errors.NOT_FOUND')         // → "Không tìm thấy hồ sơ."  (VI is default)
AlpineI18n.t('processing.transcribing')  // → "Đang xử lý giọng nói…"
$locale('en'); AlpineI18n.t('errors.NOT_FOUND')  // → "Case not found."
$locale('vi');
```

All three must return the expected strings. No console errors.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "feat(i18n): add processing.* and errors.* keys (VI+EN); reduce template_type to auto/medical"
```

---

## Task 3: Add New Alpine State + Helper Methods

**Files:**
- Modify: `index.html` `claimFlow()` return object (lines 1762–1855 for the state; methods added near `bootstrap()` at line 1856)

- [ ] **Step 1: Add new state fields**

Find the `return {` block of `claimFlow()` at line 1763. After `mqttClient: null,` (line 1854 — will be removed in Task 9, leave it for now), add three new fields. Actually, add them right after `completedActions: [],` (line 1853) so they're grouped:

```js
                completedActions: [],
                toasts: [],
                isProcessing: false,
                processingStatus: '',
                mqttClient: null,
```

- [ ] **Step 2: Add helper methods**

Find the `async bootstrap() {` block at line 1856. Insert the following methods **before** `async bootstrap()`:

```js
                pushToast(code) {
                    const msg = this.t(`errors.${code}`) || this.t('errors.UNKNOWN');
                    const id = Date.now() + Math.random();
                    this.toasts.push({ id, code, message: msg });
                    setTimeout(() => {
                        this.toasts = this.toasts.filter(t => t.id !== id);
                    }, 5000);
                },

                t(key) {
                    return window.AlpineI18n ? AlpineI18n.t(key) : key;
                },

                formatVND(n) {
                    return new Intl.NumberFormat('vi-VN').format(n) + ' ₫';
                },

                validateAudioFile(file) {
                    const ALLOWED_AUDIO = ['wav', 'mp3', 'm4a', 'ogg', 'flac', 'webm'];
                    const ext = (file.name.split('.').pop() || '').toLowerCase();
                    if (!ALLOWED_AUDIO.includes(ext)) {
                        this.pushToast('INVALID_FILE_TYPE');
                        return false;
                    }
                    return true;
                },

```

- [ ] **Step 3: Change `selectedTemplate` default**

Find `selectedTemplate: 'vehicle',` at line 1781. Change it to:

```js
                selectedTemplate: 'auto_claim',
```

- [ ] **Step 4: Verify the page still loads**

Reload the browser. No console errors. The new methods are defined but not yet called. `typeof claimFlow` still works (Alpine bootstraps the page).

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat(state): add toasts/isProcessing/processingStatus + pushToast/t/formatVND/validateAudioFile"
```

---

## Task 4: Rewrite `bootstrap`, `loadIncidents`, `loadCaseDetail` to Use `api.*`

**Files:**
- Modify: `index.html` lines 1856–1955 (`bootstrap`, `loadIncidents`, `selectIncident`, `loadCaseDetail`)

- [ ] **Step 1: Rewrite `bootstrap()`**

Find the `async bootstrap()` at line 1856:

```js
                async bootstrap() {
                    await this.$nextTick();
                    this.initMQTT();
                    await this.loadIncidents();
                    this.hydrateClaimForm();
                }
```

Replace with (drop `this.initMQTT()` — the method itself is removed in Task 9):

```js
                async bootstrap() {
                    await this.$nextTick();
                    await this.loadIncidents();
                    this.hydrateClaimForm();
                }
```

- [ ] **Step 2: Rewrite `loadIncidents()`**

Find `async loadIncidents()` at line 1901. Replace its entire body (lines 1901–1920):

```js
                async loadIncidents() {
                    try {
                        const cases = await api.cases.list();
                        this.incidents = cases.map(c => {
                            const raw = (c.recordings && c.recordings[0] && c.recordings[0].transcript)
                                ? (c.recordings[0].transcript.raw_text || '')
                                : '';
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

- [ ] **Step 3: Rewrite `loadCaseDetail()`**

Find `async loadCaseDetail(caseId)` at line 1927. Replace its entire body (lines 1927–1955):

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
                        if (this.recordings.length) {
                            this.selectRecording(this.recordings[0].id);
                        } else {
                            this.selectedRecordingId = null;
                        }
                    } catch (e) {
                        this.pushToast(e.code || 'UNKNOWN');
                    }
                }
```

- [ ] **Step 4: Verify with a fresh session**

In the browser DevTools, clear `localStorage` (`localStorage.clear()`) and reload. Watch the Network tab:

- A `GET https://api.dathoc.net/api/cases` fires; if it 401s, a `POST /activate` fires first, then `/cases` retries.
- The sidebar should populate with real cases from the backend (or show the empty-state if none).
- No console errors.

If the sidebar populates, click a case — `GET /cases/{id}` fires and the recordings list + report panel update. If the backend is unreachable, a red toast appears with a localized message.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "refactor(api): bootstrap/loadIncidents/loadCaseDetail now use api.* with 401 retry"
```

---

## Task 5: Rewrite `uploadAudio` + `uploadAudioFile` to Use `process-voice`

**Files:**
- Modify: `index.html` lines 2273–2301 (`uploadAudio`) and 2332–2384 (`uploadAudioFile`)

- [ ] **Step 1: Rewrite `uploadAudio()`**

Find `async uploadAudio()` at line 2273. Replace its entire body (lines 2273–2301):

```js
                async uploadAudio() {
                    const chunks = this.audioChunks;
                    if (!chunks || chunks.length === 0) {
                        console.warn('No audio chunks to upload');
                        return;
                    }
                    const blob = new Blob(chunks, { type: 'audio/webm' });
                    const formData = new FormData();
                    formData.append('audio', blob, `recording_${Date.now()}.webm`);
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
                        if (this.recordings.length) {
                            this.selectRecording(this.recordings[0].id);
                        }
                        await this.loadIncidents();
                    } catch (e) {
                        this.pushToast(e.code || 'UNKNOWN');
                    } finally {
                        this.isProcessing = false;
                        this.processingStatus = '';
                    }
                }
```

- [ ] **Step 2: Rewrite `uploadAudioFile(event)`**

Find `async uploadAudioFile(event)` at line 2332. Replace its entire body (lines 2332–2384) — including the old MQTT block at the top that's already dead code (the `if (this.mqttClient)` block):

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
                            if (this.recordings.length) {
                                this.selectRecording(this.recordings[0].id);
                            }
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

- [ ] **Step 3: Update the file picker `accept` attribute**

Find the audio file input at line 1315:

```html
<input type="file" accept="audio/*" hidden @change="uploadAudioFile($event)">
```

Change `accept="audio/*"` to the explicit list (matches the API doc's supported formats):

```html
<input type="file" accept=".wav,.mp3,.m4a,.ogg,.flac,.webm" hidden @change="uploadAudioFile($event)">
```

- [ ] **Step 4: Verify the recording flow**

In the browser, click the record button, record 3–5 seconds of speech, click stop. Watch the Network tab:

- `POST /claims/process-voice` fires with `multipart/form-data` body containing `audio` (the `.webm` blob) and `template_type` (`auto_claim`).
- While in flight, the record button shows "Đang xử lý giọng nói…" and is disabled (`:disabled="isProcessing"` — wait, that's added in Task 8; for now it just shows the text).
- On success: `currentCaseId` is set, recordings list updates, the sidebar refreshes, the first recording auto-selects.
- On failure: a red toast appears with a localized message.

Then test the upload path: click "Upload audio", pick a `.wav` file — same flow. Pick a `.txt` file — a toast says "Định dạng file không được hỗ trợ…" and no network call fires.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "refactor(api): uploadAudio/uploadAudioFile call api.claims.processVoice; drop pre-create"
```

---

## Task 6: Rewrite `loadWaveform` to Stream from `BASE_URL + file_path`

**Files:**
- Modify: `index.html` lines 1967–1996 (`loadWaveform`)

- [ ] **Step 1: Rewrite `loadWaveform(id)`**

Find `async loadWaveform(id)` at line 1967. Replace its entire body (lines 1967–1996):

```js
                async loadWaveform(id) {
                    if (typeof WaveSurfer === 'undefined') {
                        console.warn('WaveSurfer script not loaded');
                        return;
                    }
                    await this.$nextTick();
                    const container = this.$refs.waveform;
                    if (!container) return;
                    if (this.wavesurfer) {
                        try { this.wavesurfer.destroy(); } catch (e) { }
                        this.wavesurfer = null;
                    }
                    this.wavesurfer = this.initWaveSurfer(container);
                    try {
                        const rec = this.recordings.find(r => r.id === id);
                        if (!rec || !rec.file_path) return;
                        // file_path from API: "./uploads/foo.wav" → strip "./" → request prepends BASE_URL
                        const relative = rec.file_path.replace(/^\.\//, '');
                        const blob = await request('/' + relative);
                        if (blob.size < 100) {
                            console.warn('Audio blob too small, likely empty recording');
                        }
                        this.wavesurfer.loadBlob(blob);
                    } catch (e) {
                        console.error('loadWaveform failed:', e);
                    }
                }
```

- [ ] **Step 2: Verify waveform playback**

In the browser, reload the page so the sidebar loads from `GET /cases`. Click a case that has at least one recording. Watch the Network tab:

- `GET https://api.dathoc.net/api/uploads/<file>` fires (with `Authorization` + `Accept-Language` headers).
- If it 401s, a transparent `/activate` + retry happens.
- On success, WaveSurfer renders the waveform and the play button works.

If the audio URL 404s, the spec §3 assumption is wrong — note this in the verification log. The fix is to add a separate `AUDIO_BASE_URL` constant and update this one line. Do **not** proceed to the next task until waveform playback works against the live backend.

- [ ] **Step 3: Commit**

```bash
git add index.html
git commit -m "refactor(api): loadWaveform streams via authenticated request() from BASE_URL + file_path"
```

---

## Task 7: Strict API-doc Mapping in `currentClaimSourceValues`; Remove `sampleTemplates`

**Files:**
- Modify: `index.html` lines 1789–1851 (`sampleTemplates` state) and 2104–2121 (`currentClaimSourceValues`)

- [ ] **Step 1: Delete the entire `sampleTemplates` block**

Find the `sampleTemplates: {` block starting at line 1789. Delete the entire block (lines 1789–1851) — all 4 date entries (`'17/07'`, `'16/07'`, `'15/07'`, `'14/07'`) and the closing `},`. The next line after the deletion should be `selectedActions: [],`.

- [ ] **Step 2: Rewrite `currentClaimSourceValues()`**

Find `currentClaimSourceValues()` at line 2104. Replace its entire body (lines 2104–2121):

```js
                currentClaimSourceValues() {
                    if (this.activeQuickAccess !== 'current') return {};
                    const rec = this.recordings.find(r => r.id === this.selectedRecordingId);
                    if (!rec || !rec.transcript) return {};
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

- [ ] **Step 3: Verify the claim form hydrates**

In the browser, load a case that has a recording with a populated `transcript.structured` block (e.g., one with `vehicle_plate` set). The report panel should auto-fill:

- `vehiclePlate` with the plate
- `vehicleDamage` with `damage_items` joined by newline
- `estimatedAmount` with the VND-formatted cost

If `structured` is empty but `raw_text` exists, only `accidentDescription` fills. If neither, the form stays blank (adjuster fills manually).

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "refactor(api): currentClaimSourceValues uses strict API-doc mapping; drop sampleTemplates"
```

---

## Task 8: Markup — Toasts, Template Dropdown, Processing Indicator, Fake Sidebar Removal

**Files:**
- Modify: `index.html` markup region (lines ~1165–1587)

- [ ] **Step 1: Add the toast container**

Find the closing `</main>` tag at line 1586, then the closing `</div>` for `.main-layout` at line 1588. Right **before** that closing `</div>` (line 1588), insert the toast container so it's a sibling of `.main-layout` but inside `<body>`:

Actually — the toast container should be a direct child of `<body>` (not nested in `.main-layout`) so it can be `position: fixed`. Insert it **right after** the closing `</div>` on line 1588 (so it comes after `.main-layout` closes but before the `<script>` tags start):

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

- [ ] **Step 2: Replace the template dropdown with 2 options**

Find the template `<select>` element around line 1379–1384:

```html
                        <select x-model="selectedTemplate" ...>
                            <option value="vehicle" x-text="$t('report.template_vehicle')"></option>
                            <option value="medical" x-text="$t('report.template_medical')"></option>
                            <option value="fire" x-text="$t('report.template_fire')"></option>
                            <option value="injury" x-text="$t('report.template_injury')"></option>
                        </select>
```

Replace the 4 `<option>` lines with 2:

```html
                        <select x-model="selectedTemplate" ...>
                            <option value="auto_claim" x-text="$t('report.template_auto')"></option>
                            <option value="medical_claim" x-text="$t('report.template_medical')"></option>
                        </select>
```

Keep any other attributes that were on the `<select>` (classes, etc.) — only swap the options.

- [ ] **Step 3: Add the processing indicator and disable the record button while processing**

Find the record button at line 1300:

```html
                        <button class="record-btn" id="recordBtn" @click="toggleRecording()"
                            ...
                            x-text="isRecording ? $t('record.recording_info', { sec: recordingSeconds }) : $t('record.start_info')">
                        </button>
```

Modify it to add `:disabled="isProcessing"` and the `isProcessing` branch in the `x-text`:

```html
                        <button class="record-btn" id="recordBtn" @click="toggleRecording()"
                            :disabled="isProcessing"
                            ...
                            x-text="isProcessing
                                ? $t('processing.transcribing')
                                : (isRecording
                                    ? $t('record.recording_info', { sec: recordingSeconds })
                                    : $t('record.start_info'))">
                        </button>
```

Then immediately **after** the `</button>`, add the inline processing indicator:

```html
                        <span x-show="isProcessing" class="processing-spinner"
                              x-text="$t(processingStatus)"
                              style="margin-left:8px;font-size:12px;color:#667eea;"></span>
```

- [ ] **Step 4: Delete the 4 fake sidebar items**

Find the 4 hardcoded `<div class="audio-item">` blocks in the sidebar (lines ~1214–1281). They start right after the `<template x-for="incident in incidents">` block closes with `</template>` on line 1212. Delete all 4 fake `<div class="audio-item">` blocks through line 1281, leaving only:

```html
            <div x-show="incidents.length === 0" class="audio-item">
                <div class="audio-transcript" x-text="$t('sidebar.no_incidents')"></div>
            </div>
```

Verify the `x-show="incidents.length === 0"` empty-state block immediately follows the `<template x-for>` block (with no fake items in between).

- [ ] **Step 5: Remove the quick-access `<template x-for="d in Object.keys(sampleTemplates)">` loop**

Find the quick-access section around lines 1497–1510. The "Current" button stays; the `<template x-for="d in Object.keys(sampleTemplates)">` loop is deleted. Result should look like:

```html
                    <button class="quick-access-btn" :class="{ 'active': activeQuickAccess === 'current' }"
                        @click="selectQuickAccess('current')">
                        <span x-text="$t('report.current')"></span>
                    </button>
                    <!-- template loop over Object.keys(sampleTemplates) removed -->
```

- [ ] **Step 6: Verify the markup renders**

Reload the browser. Check:

- Template dropdown shows exactly 2 options (Auto Claim / Medical Claim).
- Sidebar shows only real incidents (no "Giám định thương tật chị Lan" etc.).
- Empty-state shows when there are no cases.
- Click record → button text changes to "Đang xử lý giọng nói…" while in flight, then back to "Bắt đầu ghi âm" after.
- No console errors, no Alpine warnings about missing properties (`sampleTemplates` removed but no references should remain).

If Alpine warns about `sampleTemplates` being undefined, grep for leftover references:

```bash
rg "sampleTemplates" index.html
```

Should return nothing. If anything remains, delete it.

- [ ] **Step 7: Commit**

```bash
git add index.html
git commit -m "feat(markup): toasts, 2-option template dropdown, processing spinner; remove fake sidebar + sample loop"
```

---

## Task 9: Remove MQTT Script + Methods

**Files:**
- Modify: `index.html` line 1592 (MQTT script tag) and lines 2385–2456 (`initMQTT`, `handleTranscript`, `handleFailed`, `handleAnnotations`)

- [ ] **Step 1: Delete the MQTT `<script>` tag**

Find line 1592:

```html
    <script src="https://cdn.jsdelivr.net/npm/mqtt@5.0.5/dist/mqtt.min.js"></script>
```

Delete the entire line.

- [ ] **Step 2: Delete the four MQTT methods**

Find `initMQTT() {` at line 2385. Delete the four methods `initMQTT`, `handleTranscript`, `handleFailed`, `handleAnnotations` (lines 2385 through the closing of `handleAnnotations` — read the file to find the exact end line; it's around 2456). Keep any code **after** `handleAnnotations` that isn't part of these methods (e.g., the closing `}` of `claimFlow()`'s return object, if present).

- [ ] **Step 3: Delete the `mqttClient: null,` state field**

Find `mqttClient: null,` (added in Task 3 we kept it; now remove it). Delete the line.

- [ ] **Step 4: Verify no MQTT references remain**

Run:

```bash
rg -n "mqtt|MQTT|initMQTT|handleTranscript|handleFailed|handleAnnotations|mqttClient" index.html
```

Expected: no matches. If anything remains, delete it.

- [ ] **Step 5: Verify the page still works**

Reload the browser. The page should load with no console errors. No `mqtt is not defined` errors. The record → process-voice flow from Task 5 still works end-to-end.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "chore(cleanup): remove MQTT script + initMQTT/handleTranscript/handleFailed/handleAnnotations"
```

---

## Task 10: Route PDF/Share Through `api.claim.*`

**Files:**
- Modify: `index.html` `downloadClaimPdf` (lines 2136–2167) and `shareClaimPdf` (lines 2168–2192)

- [ ] **Step 1: Rewrite `downloadClaimPdf()`**

Find `async downloadClaimPdf()` at line 2136. Replace its `fetch` call (line 2142) with the `api.claim.pdf` call. The new body:

```js
                async downloadClaimPdf() {
                    this.claimPdfBusy = true;
                    this.claimGenerationStatus = window.AlpineI18n
                        ? AlpineI18n.t('report.generating') : 'Generating…';
                    try {
                        const payload = this.buildClaimPayload();
                        const blob = await api.claim.pdf(payload);
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = `claim_${this.currentCaseId || 'draft'}.pdf`;
                        document.body.appendChild(a);
                        a.click();
                        document.body.removeChild(a);
                        URL.revokeObjectURL(url);
                        this.claimGenerationStatus = window.AlpineI18n
                            ? AlpineI18n.t('report.pdf_ready') : 'PDF ready';
                    } catch (e) {
                        this.pushToast(e.code || 'UNKNOWN');
                        this.claimGenerationStatus = window.AlpineI18n
                            ? AlpineI18n.t('report.pdf_error') : 'PDF error';
                    } finally {
                        this.claimPdfBusy = false;
                    }
                }
```

*(Note: the exact DOM-creation code for the PDF download should be preserved from the existing implementation — only the `fetch(...)` call is replaced by `await api.claim.pdf(payload)`. Read the existing `downloadClaimPdf` body first and preserve whatever blob-to-download logic is there; only swap the network call.)*

- [ ] **Step 2: Rewrite `shareClaimPdf()`**

Find `async shareClaimPdf()` at line 2168. Replace its `fetch` call with `await api.claim.share(payload)`. The new body preserves the existing UI status updates:

```js
                async shareClaimPdf() {
                    this.claimPdfBusy = true;
                    this.claimGenerationStatus = window.AlpineI18n
                        ? AlpineI18n.t('report.sharing') : 'Sharing…';
                    try {
                        const payload = this.buildClaimPayload();
                        await api.claim.share(payload);
                        this.claimGenerationStatus = window.AlpineI18n
                            ? AlpineI18n.t('report.shared') : 'Shared';
                    } catch (e) {
                        this.pushToast(e.code || 'UNKNOWN');
                        this.claimGenerationStatus = window.AlpineI18n
                            ? AlpineI18n.t('report.share_error') : 'Share error';
                    } finally {
                        this.claimPdfBusy = false;
                    }
                }
```

- [ ] **Step 3: Verify both endpoints work**

In the browser, populate a claim form (record audio or pick a case with transcript data), then click "Download PDF". The Network tab shows `POST /claim/pdf` with `Authorization` + `Accept-Language` headers; on success a PDF downloads. Click "Share PDF" — `POST /claim/share` fires; the status text shows "Đã gửi" / "Shared".

If either endpoint 404s (the spec flags these as undocumented), the toast will say "Đã xảy ra lỗi, vui lòng thử lại." — graceful failure, no crash.

- [ ] **Step 4: Commit**

```bash
git add index.html
git commit -m "refactor(api): downloadClaimPdf/shareClaimPdf route through api.claim.* with toast errors"
```

---

## Task 11: Manual Verification

**Files:** none (verification only)

- [ ] **Step 1: Run all 10 manual checks from spec §5**

Open `index.html` in the browser against the live backend. Run each check; record pass/fail:

1. **Session flow:** clear `localStorage`, reload → sidebar loads (transparent `/activate` + `/cases`).
2. **401 retry:** in DevTools, run `localStorage.setItem('v2c_session_id', 'bogus')`, reload → any call transparently re-activates; no toast.
3. **Session-expired dead-end:** stub `api.activate` to throw (DevTools: `api.activate = async () => { throw new ApiError('SESSION_EXPIRED','',401); }`), trigger any call → "Phiên đã hết hạn…" toast. Restore `api.activate` after.
4. **Record → process-voice:** record 5s → stop → spinner → sidebar updates, recording selected, waveform loads, claim form hydrates with `vehicle_plate`/`damage_items`/`estimated_cost`.
5. **Upload file:** pick `.wav` → same flow. Pick `.txt` → `INVALID_FILE_TYPE` toast, no network call.
6. **Template dropdown:** only 2 options; switch to Medical Claim before recording → Network tab shows `template_type: 'medical_claim'` in the form data.
7. **Locale toggle:** click EN/VI toggle → next API call's `Accept-Language` header matches (check in Network tab).
8. **Sidebar from `GET /cases`:** reload → sidebar populated from backend, no "Giám định thương tật chị Lan" entries.
9. **Removed code grep:** run `rg "sampleTemplates|initMQTT|mqttClient|/api/cases.*upload" index.html` from the project root → no matches.
10. **Lint/typecheck:** none configured — skip (note in the verification log).

- [ ] **Step 2: Fix any failures**

If any check fails, fix the underlying issue in `index.html`, commit the fix with `git commit -m "fix(verify): <what was fixed>"`, and re-run that check. Don't move on until all 10 pass (or #10 is explicitly skipped).

- [ ] **Step 3: Final commit (if any fixes were made in Step 2)**

If Step 2 made fixes, the last fix commit is the final state. Otherwise, no commit needed — the implementation is done.

- [ ] **Step 4: Verify done criteria from spec §5**

Tick each box from the spec's "Done criteria" list. All must be checked:

- [ ] All `fetch('/api/...')` replaced by `api.*` calls
- [ ] `mqtt` script + `initMQTT`/`handleTranscript`/`handleFailed`/`handleAnnotations` removed
- [ ] `sampleTemplates` + 4 fake sidebar items removed
- [ ] `template_type` dropdown has exactly 2 options
- [ ] `BASE_URL` hardcoded to prod
- [ ] Toast container + 10 `errors.*` i18n keys present (VI + EN)
- [ ] 3 `processing.*` i18n keys present (VI + EN)
- [ ] `request()` handles 401 → activate → retry once
- [ ] All async callbacks use arrow functions (preserve `this`)
- [ ] `loadWaveform` streams via authenticated `request()` from `BASE_URL + file_path`
- [ ] 10 manual verification checks pass (or #10 explicitly skipped)

---

## Self-Review

**Spec coverage check:** every section of the spec maps to a task:

- §1 Architecture → Tasks 1, 4, 5, 9 (api client + rewritten methods + MQTT removal)
- §2 API Client → Task 1 (verbatim)
- §3 Component State Changes → Tasks 3 (state), 4 (methods), 5 (upload), 6 (waveform), 7 (mapping + sampleTemplates), 9 (mqttClient removed)
- §4 Markup & i18n → Tasks 2 (i18n), 8 (markup)
- §5 Error/Testing/Migration → Task 11 (manual verification = the migration plan's done criteria)

No spec section is unaddressed.

**Placeholder scan:** no "TBD", no "TODO", no "implement later". Every code step contains the full code to write. Two places reference reading the existing file first (`downloadClaimPdf` body, `handleAnnotations` end line) — both are necessary because the file is 2458 lines and the exact end lines shift as edits land; the instruction is "read first, then delete/replace", not a placeholder.

**Type/name consistency:** `ApiError`, `request`, `api`, `session`, `BASE_URL`, `STORAGE_KEY` are defined in Task 1 and used unchanged through Task 10. `pushToast`, `t`, `formatVND`, `validateAudioFile` defined in Task 3 and used unchanged through Task 10. `isProcessing`, `processingStatus`, `toasts` defined in Task 3 and referenced in Tasks 5, 8. `selectedTemplate: 'auto_claim'` set in Task 3, used in Tasks 5, 8. No name drift.

**Risks flagged for the implementer:**
- Task 6 Step 2 calls out the audio-URL assumption from the spec — verify before proceeding.
- Task 10 notes the PDF/share endpoints are undocumented and may 404 — graceful failure is the expected behavior.
- Task 11 Step 1 #3 requires DevTools console stubbing — the implementer must know how to monkey-patch `api.activate` in the console.