/* Speech-to-Meaning pilot — Alpine app (batch + live RTT) */
function s2m() {
  return {
    // ---------- state ----------
    packs: [], packId: 'insurance_motor', pack: null,
    tab: 'batch',
    sid: null, processing: false, processingStep: '',
    transcript: '', rawTranscript: '', tags: [], langs: [],
    fields: {}, revealed: {},
    score: null, armed: {}, fired: [], toasts: [],
    timing: null,
    file: null, fileName: '', recording: false, recorder: null, chunks: [],
    swText: '00:00.0', swTimer: null, swStart: 0,
    reviewer: 'GĐV Minh', ack: false, overrideReason: '', submitted: null,
    reviewSecs: 0, reviewTimer: null,
    recordingUrl: '', customerEmail: 'hailongluu@gmail.com',
    handlerEmail: 'long@luuhailong.com', mailStatus: [],
    editing: '', editValue: '',
    tickets: [], logs: [], ticketTimer: null, expanded: '',
    drag: false, demoAudios: [],
    // live mode
    live: false, liveWs: null, liveCtx: null, liveStatus: '', livePartial: '',
    liveFinals: [], liveHint: 0, liveStream: null,

    // ---------- init ----------
    async init() {
      // deep-link tab từ sidebar Voice2Claim: /pilot#console, /pilot#live…
      const h = (location.hash || '').replace('#', '');
      if (['batch', 'live', 'console'].includes(h)) this.tab = h;
      if (this.tab === 'console') this.loadTickets();
      this.packs = await (await fetch('/api/packs')).json();
      this.demoAudios = await (await fetch('/api/demo-audios')).json();
      await this.loadReplays();
      await this.loadPack(this.packId);
      this.ticketTimer = setInterval(() => { if (this.tab === 'console') this.loadTickets(); }, 3000);
    },
    async loadPack(id) {
      if (this.live) this.liveStop();
      this.packId = id;
      this.pack = await (await fetch('/api/pack/' + id)).json();
      this.resetSession();
    },
    resetSession() {
      this.sid = null; this.transcript = ''; this.rawTranscript = '';
      this.tags = []; this.langs = []; this.fields = {}; this.revealed = {};
      this.score = null; this.armed = {}; this.fired = []; this.toasts = [];
      this.timing = null; this.submitted = null;
      this.ack = false; this.overrideReason = ''; this.swText = '00:00.0';
      this.recordingUrl = ''; this.mailStatus = [];
      this.livePartial = ''; this.liveFinals = [];
      if (this.swTimer) clearInterval(this.swTimer);
      if (this.reviewTimer) clearInterval(this.reviewTimer);
      this.reviewSecs = 0;
    },

    // ---------- stopwatch ----------
    swStartNow() {
      this.swStart = performance.now();
      if (this.swTimer) clearInterval(this.swTimer);
      this.swTimer = setInterval(() => {
        const t = (performance.now() - this.swStart) / 1000;
        this.swText = String(Math.floor(t / 60)).padStart(2, '0') + ':' +
          (t % 60).toFixed(1).padStart(4, '0');
      }, 100);
    },
    swStop() { if (this.swTimer) { clearInterval(this.swTimer); this.swTimer = null; } },

    // ---------- audio input ----------
    onFile(ev) {
      const f = ev.target.files?.[0] || ev.dataTransfer?.files?.[0];
      if (f) { this.file = f; this.fileName = f.name; this.process(); }
      this.drag = false;
    },
    async toggleRecord() {
      if (this.recording) { this.recorder.stop(); return; }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.chunks = [];
      this.recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      this.recorder.ondataavailable = e => this.chunks.push(e.data);
      this.recorder.onstop = () => {
        stream.getTracks().forEach(t => t.stop());
        this.recording = false;
        this.file = new File([new Blob(this.chunks, { type: 'audio/webm' })], 'ghi-am.webm');
        this.fileName = 'ghi-am.webm (' + Math.round(this.file.size / 1024) + 'KB)';
        this.process();
      };
      this.recorder.start();
      this.recording = true;
      this.swStartNow();
    },

    // ---------- batch pipeline ----------
    async process() {
      if (!this.file || this.processing) return;
      const fd = new FormData(); fd.append('file', this.file);
      await this._runBatch('/api/batch/' + this.packId, fd);
    },
    async runDemo(id) {
      const d = this.demoAudios.find(x => x.id === id);
      if (d && d.pack_id !== this.packId) await this.loadPack(d.pack_id);
      this.file = null; this.fileName = 'demo ' + id + '.wav (audio mẫu)';
      await this._runBatch('/api/batch/' + this.packId + '?demo=' + id, new FormData());
    },
    async _runBatch(url, fd) {
      if (this.processing) return;
      this.resetSessionKeepFile();
      this.processing = true;
      if (!this.swTimer) this.swStartNow();
      this.processingStep = 'VALSEA đang nghe (ASR)…';
      try {
        const r = await fetch(url, { method: 'POST', body: fd });
        if (!r.ok) throw new Error((await r.json()).detail || r.status);
        const d = await r.json();
        this.sid = d.sid; this.transcript = d.transcript;
        this.recordingUrl = d.recording_url || '';
        this.rawTranscript = d.raw_transcript || '';
        this.tags = d.semantic_tags || []; this.langs = d.detected_languages || [];
        this.armed = d.armed; this.timing = d.timing;
        const names = Object.keys(d.fields).filter(n => d.fields[n].value !== null && d.fields[n].value !== '');
        this.fields = d.fields;
        names.forEach((n, i) => setTimeout(() => { this.revealed[n] = true; }, 150 * i));
        setTimeout(() => {
          this.score = d.score; this.swStop();
          d.fired.forEach(f => this.onFired(f));
        }, 150 * names.length + 250);
      } catch (e) {
        alert('Lỗi xử lý: ' + e.message);
        this.swStop();
      } finally { this.processing = false; this.processingStep = ''; }
    },
    resetSessionKeepFile() {
      const f = this.file, fn = this.fileName;
      this.resetSession(); this.file = f; this.fileName = fn;
    },
    onFired(res) {
      const aid = res.ticket?.action || res.action;
      if (aid && !this.fired.includes(aid)) this.fired.push(aid);
      this.toasts.push(res);
      if (res.tts_b64) new Audio('data:audio/wav;base64,' + res.tts_b64).play().catch(() => {});
    },

    // ---------- live mode (RTT) ----------
    async liveStart() {
      if (this.live) return;
      this.resetSession();
      this.liveStatus = 'đang kết nối VALSEA RTT…';
      try {
        this.liveStream = await navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
      } catch (e) { this.liveStatus = 'mic bị từ chối — cấp quyền micro rồi thử lại'; return; }
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const ws = new WebSocket(`${proto}://${location.host}/ws/live/${this.packId}`);
      ws.binaryType = 'arraybuffer';
      this.liveWs = ws;
      ws.onmessage = ev => this.handleLive(JSON.parse(ev.data));
      ws.onclose = () => { if (this.live) this.liveStatus = 'đã đóng kết nối'; this.live = false; };
      ws.onerror = () => { this.liveStatus = 'lỗi kết nối'; };
      await new Promise(res => { ws.onopen = res; });
      // audio graph
      this.liveCtx = new AudioContext({ sampleRate: 16000 });
      await this.liveCtx.resume();
      await this.liveCtx.audioWorklet.addModule('/static/js/pcm_worklet.js');
      const src = this.liveCtx.createMediaStreamSource(this.liveStream);
      const node = new AudioWorkletNode(this.liveCtx, 'pcm16-downsampler');
      node.port.onmessage = e => { if (ws.readyState === 1) ws.send(e.data); };
      const mute = this.liveCtx.createGain(); mute.gain.value = 0;
      src.connect(node); node.connect(mute); mute.connect(this.liveCtx.destination);
      this.live = true;
      this.swStartNow();
      ws.send(JSON.stringify({ type: 'mic.start' }));
    },
    liveStop() {
      if (this.liveWs && this.liveWs.readyState === 1) {
        this.liveWs.send(JSON.stringify({ type: 'mic.stop' }));
        setTimeout(() => { try { this.liveWs.close(); } catch (e) {} }, 1600);
      }
      if (this.liveStream) this.liveStream.getTracks().forEach(t => t.stop());
      if (this.liveCtx) { try { this.liveCtx.close(); } catch (e) {} }
      this.live = false; this.swStop();
      this.liveStatus = 'đã dừng — form giữ nguyên để duyệt';
    },
    handleLive(m) {
      switch (m.type) {
        case 'session.ready':
          this.liveStatus = 'LIVE — hint_text ' + m.hint_chars + ' ký tự từ điển nghiệp vụ';
          this.liveHint = m.hint_chars; break;
        case 'transcript.partial': this.livePartial = m.text; break;
        case 'transcript.final':
          this.liveFinals.push(m.text); this.livePartial = '';
          this.transcript = this.liveFinals.join(' ');
          break;
        case 'state.patch':
          for (const [n, f] of Object.entries(m.fields)) { this.fields[n] = f; this.revealed[n] = true; }
          break;
        case 'score.update': this.score = m; break;
        case 'action.armed':
          this.armed[m.action] = { score: m.score, latency_ms: m.arm_latency_ms }; break;
        case 'action.fired':
          if (!this.fired.includes(m.action)) this.fired.push(m.action); break;
        case 'action.result': this.onFired(m); break;
        case 'session.saved':
          this.sid = m.sid;
          if (m.recording_url) this.recordingUrl = m.recording_url;
          break;
        case 'status': this.liveStatus = m.state + (m.detail ? ' — ' + m.detail : ''); break;
        case 'error': this.liveStatus = '⚠ ' + (m.message || m.code); break;
      }
    },
    liveConfirm(id) {
      if (this.liveWs?.readyState === 1) this.liveWs.send(JSON.stringify({ type: 'action.confirm', action: id }));
    },

    // ---------- replay mode (không tốn API — cứu nguy demo) ----------
    replayList: [], replaying: false, replayAbort: false,
    async loadReplays() {
      try { this.replayList = await (await fetch('/api/replay-list')).json(); } catch (e) {}
    },
    async replayStart(id) {
      if (this.replaying) { this.replayAbort = true; return; }
      const d = await (await fetch('/api/replay/' + id)).json();
      const pk = d.pack === 'insurance_motor' || d.pack === 'healthcare_exam' ? d.pack : this.packId;
      if (pk !== this.packId) await this.loadPack(pk);
      this.resetSession();
      this.replaying = true; this.replayAbort = false;
      this.liveStatus = 'REPLAY ' + id + ' — bản ghi thật, không gọi API';
      this.swStartNow();
      let prev = 0;
      for (const item of d.events) {
        if (this.replayAbort) break;
        await new Promise(r => setTimeout(r, Math.min(2000, (item.dt - prev) * 1000)));
        prev = item.dt;
        this.handleLive(item.ev);
      }
      this.swStop(); this.replaying = false;
      this.liveStatus = 'REPLAY kết thúc — form giữ nguyên để duyệt';
    },

    // (đối chứng whisper generic đã gỡ 18/07 — pilot 100% VALSEA)
    demoId() {
      return this.fileName.startsWith('demo ') ? this.fileName.split(' ')[1].replace('.wav', '') : '';
    },

    // ---------- field edit ----------
    startEdit(name) {
      this.editing = name;
      const v = this.fields[name]?.value;
      this.editValue = Array.isArray(v) ? v.join('\n') : (v ?? '');
    },
    async saveEdit() {
      const name = this.editing; if (!name) return;
      const spec = this.pack.form.sections.flatMap(s => s.fields).find(f => f.name === name);
      let value = this.editValue;
      if (spec?.type === 'list') value = this.editValue.split('\n').map(x => x.trim()).filter(Boolean);
      if (spec?.type === 'number') value = parseFloat(this.editValue) || this.editValue;
      if (this.live && this.liveWs?.readyState === 1) {
        this.liveWs.send(JSON.stringify({ type: 'field.edit', field: name, value }));
        this.editing = ''; return;
      }
      if (!this.sid) { this.editing = ''; return; }
      const r = await fetch(`/api/session/${this.sid}/field`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, value }),
      });
      const d = await r.json();
      this.fields = d.fields; this.score = d.score;
      Object.keys(this.fields).forEach(n => { if (this.fields[n].value) this.revealed[n] = true; });
      this.editing = '';
    },

    // ---------- review ----------
    async goReview() {
      this.tab = 'review';
      if (this.sid) {
        fetch(`/api/session/${this.sid}/review-start`, { method: 'POST' });
        if (!this.reviewTimer) {
          const t0 = performance.now();
          this.reviewTimer = setInterval(() => { this.reviewSecs = Math.floor((performance.now() - t0) / 1000); }, 500);
        }
      }
    },
    _submitBody(extra = {}) {
      return JSON.stringify({
        reviewer: this.reviewer, ack: this.ack, override_reason: this.overrideReason,
        customer_email: this.customerEmail.trim(), handler_email: this.handlerEmail.trim(),
        base_url: location.origin, ...extra,
      });
    },
    async submitForm() {
      if (!this.sid || !this.score) return;
      const r = await fetch(`/api/session/${this.sid}/submit`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: this._submitBody(),
      });
      if (!r.ok) { alert((await r.json()).detail); return; }
      const d = await r.json();
      this.submitted = d;
      this.mailStatus = d.mail || [];
      if (this.reviewTimer) { clearInterval(this.reviewTimer); this.reviewTimer = null; }
      this.onFired(d);
    },
    async fireAction(id) {
      if (this.live) { this.liveConfirm(id); return; }
      if (!this.sid) return;
      const r = await fetch(`/api/session/${this.sid}/action/${id}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: this._submitBody(),
      });
      if (!r.ok) { alert((await r.json()).detail); return; }
      const d = await r.json();
      if (d.mail?.length) this.mailStatus = d.mail;
      this.onFired(d);
    },

    // ---------- console ----------
    async loadTickets() {
      const d = await (await fetch('/api/tickets')).json();
      this.tickets = d.tickets; this.logs = d.logs;
    },

    // ---------- helpers ----------
    confClass(f) {
      if (!f || f.value === null || f.value === '') return 'lo';
      if (f.source === 'user' || f.confidence >= 0.8) return 'hi';
      if (f.confidence >= 0.5) return 'mid';
      return 'lo';
    },
    fmtVal(v) {
      const s = x => (x && typeof x === 'object')
        ? Object.values(x).filter(y => y !== null && y !== '').map(s).join(' — ')
        : String(x);
      if (v === null || v === undefined || v === '') return 'chưa nhắc tới';
      if (Array.isArray(v)) return v.map(x => '• ' + s(x)).join('\n');
      return s(v);
    },
    gradeLabel(g) {
      return { SAN_SANG: 'SẴN SÀNG GỬI', CAN_DOC_KY: 'CẦN ĐỌC KỸ', NEN_SUA: 'NÊN SỬA' }[g] || g;
    },
    gradeClass(g) { return { SAN_SANG: 'ok', CAN_DOC_KY: 'warn', NEN_SUA: 'bad' }[g] || 'ok'; },
    ringStyle() {
      const t = this.score?.total ?? 0;
      const col = t >= 85 ? 'var(--ok)' : (t >= 60 ? 'var(--warn)' : 'var(--danger)');
      return `background:conic-gradient(${col} ${t}%, #e8eaf5 0)`;
    },
    prClass(p) { return p === 'CAO' ? 'CAO' : (p === 'TRUNG BÌNH' ? 'TB' : 'THUONG'); },
    filledCount() {
      return Object.values(this.fields).filter(f => f.value !== null && f.value !== '' && !(Array.isArray(f.value) && !f.value.length)).length;
    },
  };
}
