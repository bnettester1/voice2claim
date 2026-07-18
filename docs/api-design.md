# Voice2Claim — Backend API Design

This document describes the REST API the `index.html` frontend expects from the backend. It is derived from the actual `fetch()` calls and data shapes already used in the frontend code. MQTT is **out of scope** per team lead decision; all async results (transcript, annotations) are delivered through polling or the detail endpoint.

The frontend is a single-page Alpine.js app. State lives in one `claimFlow()` component. There is one "case" (vụ/tình huống) per claim, which contains audio recordings, images, transcripts, structured claim data, and generated PDFs.

---

## 1. Base conventions

| Topic | Convention |
|---|---|
| Base URL | `/api` |
| Content type | `application/json` for all bodies except upload (see below) |
| Auth | TBD by backend — assume a bearer token header on every request |
| IDs | Server-generated, opaque strings (UUID recommended). Frontend treats them as opaque. |
| Errors | HTTP non-2xx + `{ "error": { "code": "...", "message": "..." } }` |
| Datetimes | ISO 8601 UTC strings (`created_at`, `accident_time`, etc.) |
| Language | Frontend sends current locale via header `Accept-Language: vi` or `en`. Backend should localize PDF labels accordingly. |
| Encoding | All endpoints accept/return UTF-8. |

Frontend references backend fields by these names (do not rename):

```
case.id, case.title, case.created_at, case.recordings[], case.images[]
recording.id, recording.file_path, recording.duration_sec, recording.status,
recording.template_type, recording.error, recording.transcript
transcript.raw_text, transcript.structured, transcript.suggested_actions,
transcript.confidence, transcript.quality_score
image.id, image.file_path, image.status, image.annotations[]
```

---

## 2. Endpoint overview

| # | Method | Path | Purpose | Used by frontend |
|---|---|---|---|---|
| 1 | `GET`  | `/api/cases` | List history (sidebar) | `loadIncidents()` index.html:1903 |
| 2 | `GET`  | `/api/cases/{caseId}` | Detailed data for one case (recordings + images + claim) | `loadCaseDetail()` index.html:1929 |
| 3 | `POST` | `/api/cases` | Create a new empty case | `startRecording()` / `uploadImages()` index.html:2245, 2307, 2355 |
| 4 | `POST` | `/api/cases/{caseId}/upload` | Upload audio recording **or** image (multipart) | `uploadAudio()` index.html:2283, `uploadImages()` index.html:2313 |
| 5 | `GET`  | `/api/audio/{assetId}` | Download the raw audio/image binary (for playback & image display) | `loadWaveform()` index.html:1981, image `:src` index.html:1537 |
| 6 | `PUT`  | `/api/cases/{caseId}/claim` | Save (persist) the structured claim form data | new — see §3.6 |
| 7 | `POST` | `/api/cases/{caseId}/claim/pdf` | Generate a PDF from the claim data, return as binary | `downloadClaimPdf()` index.html:2142 (URL adjusted) |
| 8 | `POST` | `/api/cases/{caseId}/claim/share` | Generate + send/share the PDF (email, link, etc.) | `shareClaimPdf()` index.html:2174 (URL adjusted) |

> **Note on current frontend URLs.** The frontend currently calls `/api/claim/pdf` and `/api/claim/share` without a `caseId` and passes `{ template, reference, recording_id, fields, missing }` in the body. Recommendation: scope these under `/api/cases/{caseId}/claim/...` so a saved claim is the source of truth. The frontend can be trivially updated; see §5.

---

## 3. Endpoint specifications

### 3.1 `GET /api/cases` — history list

Returns the list of all cases for the current user, newest first. Used to populate the sidebar.

Response `200 OK`:

```json
[
  {
    "id": "case_01HM...",
    "title": "Tai nạn xe ô tô — 18/07/2026",
    "created_at": "2026-07-18T07:32:00Z",
    "recordings": [
      { "transcript": { "raw_text": "Gãy kín xương cẳng chân phải..." } }
    ]
  }
]
```

Frontend only reads: `id`, `title`, `created_at`, and `recordings[0].transcript.raw_text` (for the snippet, truncated client-side). The endpoint **may** return full recordings, but to keep the list light, recommend returning only what is shown:

```json
[
  {
    "id": "case_01HM...",
    "title": "Tai nạn xe ô tô — 18/07/2026",
    "created_at": "2026-07-18T07:32:00Z",
    "recording_count": 3,
    "snippet": "Gãy kín xương cẳng chân phải tỷ lệ thương tật 22 phần trăm..."
  }
]
```

Notes:
- `title` — backend should derive a default title from the first transcript or the accident location/time; user cannot edit it today.
- No query params needed for v1. Pagination/filtering can be added later (`?limit=`, `?q=`).

---

### 3.2 `GET /api/cases/{caseId}` — detailed data for one case

Returned when the user selects a case in the sidebar. **This is the single source of truth for the detail view**, including the structured claim data that should now be persisted server-side (see §3.6).

Response `200 OK`:

```json
{
  "id": "case_01HM...",
  "title": "Tai nạn xe ô tô — 18/07/2026",
  "created_at": "2026-07-18T07:32:00Z",
  "recordings": [
    {
      "id": "rec_01HM...",
      "file_path": "recordings/rec_01HM.webm",
      "duration_sec": 312,
      "status": "done",
      "template_type": "vehicle",
      "error": null,
      "transcript": {
        "raw_text": "Gãy kín xương cẳng chân phải tỷ lệ thương tật 22 phần trăm...",
        "structured": {
          "vehicle_plate": "51H-123.45",
          "location": "Ngã tư Nguyễn Văn Linh - Hoàng Diệu, TP.HCM",
          "damage_description": "Vỡ đèn pha phải, móp cản trước 30cm...",
          "estimate_amount": "28.500.000 VNĐ",
          "diagnosis": null,
          "patient_name": null
        },
        "suggested_actions": [
          { "text": "Gửi email xác nhận cho chủ xe", "action_type": "email", "target": "chuxe@example.com" },
          { "text": "Gọi garage đến kéo xe",        "action_type": "call",  "target": "0901234567" }
        ],
        "confidence": 0.92,
        "quality_score": 8
      }
    }
  ],
  "images": [
    {
      "id": "img_01HM...",
      "file_path": "images/img_01HM.jpg",
      "status": "done",
      "annotations": [
        { "label": "Vỡ đèn pha phải", "x": 0.62, "y": 0.41 }
      ]
    }
  ],
  "claim": {
    "template": "vehicle",
    "fields": {
      "claimReference": "CL-2026-0717-001",
      "adjusterName": "Nguyễn Văn A",
      "insuredName": "Anh Hùng",
      "vehiclePlate": "51H-123.45",
      "accidentTime": "14:32 ngày 18/07/2026",
      "accidentLocation": "Ngã tư Nguyễn Văn Linh - Hoàng Diệu, TP.HCM",
      "accidentDescription": "Xe ô tô Mazda CX-5...",
      "vehicleDamage": "Vỡ đèn pha bên phải\nMóp cản trước 30cm\n...",
      "estimatedAmount": "28.500.000 VNĐ"
    }
  }
}
```

Notes:
- `recording.status` ∈ `uploading` | `transcribing` | `done` | `needs_review` | `failed`.
- `transcript` may be `null` while `status` is `transcribing`.
- `claim` may be `null` if no claim data has been saved yet. Frontend will fall back to deriving from the first transcript.
- `claim.fields` uses the **exact field IDs** defined in the frontend `claimFormSchema` (`claimReference`, `adjusterName`, `insuredName`, `insuredPhone`, `insuredEmail`, `policyNumber`, `insuredAddress`, `vehicleMakeModel`, `vehiclePlate`, `vehicleVin`, `driverName`, `driverPhone`, `driverLicense`, `accidentTime`, `accidentLocation`, `accidentDescription`, `accidentCause`, `policeAgency`, `estimatedAmount`, `vehicleDamage`, `thirdPartyDamage`, `injuries`, `repairRecommendation`, `immediateActions`).
- Polling recommendation: while any recording has `status: "transcribing"` or any image has `status: "processing"`, the frontend should re-call this endpoint every ~3–5s until all are `done`/`failed`/`needs_review`. This replaces the previous MQTT push channel.

---

### 3.3 `POST /api/cases` — create a new case

Creates an empty case and returns its id. Called before recording or uploading when no `currentCaseId` exists yet.

Request body: empty, or optionally:

```json
{ "title": "Tai nạn xe máy đường Cộng Hòa" }
```

Response `201 Created`:

```json
{ "id": "case_01HM...", "created_at": "2026-07-18T07:32:00Z" }
```

The frontend only reads `id` from this response.

---

### 3.4 `POST /api/cases/{caseId}/upload` — upload audio or image

Multipart form-data. Used for both recorded audio (Blob) and uploaded image files. The backend distinguishes them by MIME type.

Request:
- `Content-Type: multipart/form-data`
- field `file` — the binary file. Filename hint provided (`recording_{ts}.webm` for audio, original filename for images).

Response `201 Created`:

```json
{
  "recording_id": "rec_01HM...",
  "status": "transcribing"
}
```

For images the response field is the same shape but the id is an image id:

```json
{
  "recording_id": "img_01HM...",
  "status": "processing"
}
```

> **Naming nit.** The frontend reads `data.recording_id` even for images (see `uploadImages()` index.html:2319). Recommend renaming to `asset_id` in a future refactor — for now keep `recording_id` so the frontend doesn't change.

Behavior:
- Backend saves the binary, creates a recording/image record with `status: "transcribing"` (audio) or `"processing"` (image), and enqueues the transcription/annotation job.
- Frontend immediately adds the asset to its list with `status: "transcribing"` and polls the case detail endpoint to pick up the transcript/annotations when ready.

---

### 3.5 `GET /api/audio/{assetId}` — fetch raw binary

Returns the raw audio/image bytes. Used for:
- WaveSurfer playback (`loadWaveform()` index.html:1981)
- `<img :src="/api/audio/{imageId}">` for field photos (index.html:1537)

Response: the binary with the correct `Content-Type` (`audio/webm`, `image/jpeg`, …). Frontend reads it as a `blob()`.

> **Path naming.** `/api/audio/` is currently used for both audio and images. Acceptable for v1. A future refactor should rename to `/api/assets/{assetId}`.

---

### 3.6 `PUT /api/cases/{caseId}/claim` — save structured claim data **(new)**

The frontend's `saveClaimForm()` currently only updates local state. To persist, it should `PUT` the form to this endpoint. This is the new endpoint the backend needs to add.

Request body:

```json
{
  "template": "vehicle",
  "fields": {
    "claimReference": "CL-2026-0717-001",
    "adjusterName": "Nguyễn Văn A",
    "insuredName": "Anh Hùng",
    "insuredPhone": "0901234567",
    "insuredEmail": "",
    "policyNumber": "BA-123456",
    "insuredAddress": "",
    "vehicleMakeModel": "Mazda CX-5",
    "vehiclePlate": "51H-123.45",
    "vehicleVin": "",
    "driverName": "",
    "driverPhone": "",
    "driverLicense": "",
    "accidentTime": "14:32 ngày 18/07/2026",
    "accidentLocation": "Ngã tư Nguyễn Văn Linh - Hoàng Diệu, TP.HCM",
    "accidentDescription": "Xe ô tô Mazda CX-5 đi hướng Bắc - Nam...",
    "accidentCause": "",
    "policeAgency": "",
    "estimatedAmount": "28.500.000 VNĐ",
    "vehicleDamage": "Vỡ đèn pha bên phải\nMóp cản trước 30cm",
    "thirdPartyDamage": "",
    "injuries": "",
    "repairRecommendation": "Thay đèn pha phải, nắn cản trước.",
    "immediateActions": "Chụp ảnh hiện trường\nLiên hệ garage"
  }
}
```

Response `200 OK`:

```json
{
  "case_id": "case_01HM...",
  "template": "vehicle",
  "fields": { "...same shape, server-normalized..." },
  "missing": ["Số đơn / GCN bảo hiểm", "Địa chỉ liên hệ"],
  "updated_at": "2026-07-18T08:01:00Z"
}
```

Notes:
- Backend should validate the required fields (see §4) and return `missing` so the frontend can show the same list without recomputing.
- Backend should merge with any transcript-derived `structured` data: empty fields in the payload should not overwrite previously-extracted values unless explicitly sent. (Or: always store the user-edited form separately and let the frontend merge — backend's choice. Document it.)
- The PDF and share endpoints (§3.7, §3.8) should read from this saved claim, not from the POST body, so a generated PDF always reflects what was saved.

---

### 3.7 `POST /api/cases/{caseId}/claim/pdf` — generate & download PDF

Generates a PDF from the saved claim (and the related case recordings/images as evidence). Returns the PDF binary so the frontend can trigger a download.

Request body (optional — overrides saved values for this generation only):

```json
{
  "language": "vi",
  "include_photos": true,
  "include_transcript": true
}
```

Response `200 OK`:
- `Content-Type: application/pdf`
- `Content-Disposition: attachment; filename="claim-CL-2026-0717-001.pdf"`
- Body: PDF bytes (frontend reads as `blob()` and triggers `<a download>`).

Response `422 Unprocessable Entity` (required fields missing):

```json
{
  "error": {
    "code": "missing_fields",
    "message": "Cannot generate PDF: required fields are missing.",
    "missing": ["Số đơn / GCN bảo hiểm", "Địa chỉ liên hệ"]
  }
}
```

Frontend behavior today: it sends the full form in the body and reads the response as a blob. Recommendation: change frontend to `PUT` the claim first (§3.6), then `POST` to this endpoint with only options. Backend reads the saved claim.

---

### 3.8 `POST /api/cases/{caseId}/claim/share` — generate & share PDF

Same as §3.7 but instead of returning the binary, the backend generates the PDF and sends it via the configured channel (email, signed link, storage upload, etc.).

Request body:

```json
{
  "language": "vi",
  "channel": "email",
  "recipient": "claims@insurance.example.com"
}
```

Response `200 OK`:

```json
{
  "recipient": "claims@insurance.example.com",
  "sent_at": "2026-07-18T08:05:00Z",
  "pdf_url": "https://storage.../claim-CL-2026-0717-001.pdf"
}
```

Frontend reads `data.recipient` and appends it to the status line ("Đã gửi → claims@...").

---

## 4. Required fields (validation contract)

The frontend marks these as required (see `requiredClaimFieldIds` in `index.html`). Backend should enforce the same list so PDF generation and persistence are consistent.

| Field ID | VI label | EN label |
|---|---|---|
| `claimReference` | Mã hồ sơ | Reference |
| `adjusterName` | Giám định viên | Adjuster |
| `insuredName` | Chủ xe / Người được bảo hiểm | Insured |
| `policyNumber` | Số đơn / GCN bảo hiểm | Policy / Certificate No. |
| `vehicleMakeModel` | Nhãn hiệu / Model | Make / Model |
| `vehiclePlate` | Biển số xe | Plate |
| `accidentTime` | Thời gian xảy ra | Time of accident |
| `accidentLocation` | Địa điểm | Location |
| `accidentDescription` | Diễn biến tai nạn | Accident description |
| `estimatedAmount` | Ước tính thiệt hại | Estimated damage |

The full claim field schema (all 24 fields, their labels, and which are multi-line `textarea` vs single-line `input`) is defined in `claimFormSchema` in `index.html`. Backend should mirror it.

---

## 5. Frontend changes that accompany this API

These are small frontend updates to align with the API above. They can be done in a follow-up PR.

1. **Persist claim on Save.** In `saveClaimForm()`, after updating local state, `PUT` to `/api/cases/{currentCaseId}/claim` with `{ template, fields }`. On success, keep local state; on error, show status.
2. **Scope PDF/share under the case.** Change `fetch('/api/claim/pdf', …)` → `fetch('/api/cases/{currentCaseId}/claim/pdf', …)` and likewise for `/share`. Send only options in the body, not the whole form (backend reads the saved claim).
3. **Remove MQTT.** Delete `initMQTT()`, `mqttClient`, and the `mqtt` script include. Replace the `handleTranscript` / `handleAnnotations` / `handleFailed` callbacks with a polling loop on `GET /api/cases/{caseId}` (every 3–5 s while any asset is `transcribing`/`processing`).
4. **Hydrate claim from `case.claim`.** In `loadCaseDetail()`, after mapping recordings/images, if `data.claim` exists, populate `claimForm` from `data.claim.fields` instead of deriving from the first transcript.

---

## 6. Open questions for the backend developer

1. **Auth & multi-tenancy.** Who owns a case? Do we need `user_id` scoping on every query?
2. **Transcription pipeline.** Is transcription synchronous on upload (return transcript in the upload response) or async (status polling)? Async + polling is assumed here.
3. **PDF template.** Will the backend use the same `docs/draft-claim-form.html` as the PDF template, or a separate server-side template (e.g. WeasyPrint / wkhtmltopdf)? Recommend sharing one template to keep the on-screen and PDF layouts identical.
4. **Storage.** Where do binaries live? Local FS, S3, object storage? Affects `/api/audio/{id}` implementation.
5. **Sharing channel.** For §3.8, is email the only channel, or do we also need signed-link / webhook / internal-portal handoff?
6. **Localization.** Should the PDF labels come from the backend (per `Accept-Language`) or from a shared i18n resource? Frontend already has vi/en strings.