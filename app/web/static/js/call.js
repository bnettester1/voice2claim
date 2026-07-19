/* Trang /call — Outbound Agent Call (E8).
   Monitor WS (/ws/callmon/{sid}) render mọi sự kiện; mode browser mở thêm
   /ws/call/browser/{sid}: mic worklet PCM16 16k đi lên, tts.audio đi xuống. */
function callApp() {
  const cfg = window.CALL_CONFIG || {twilioReady: false, missing: []};
  return {
    twilioReady: cfg.twilioReady,
    isFlows: !!cfg.isFlows,
    mode: 'replay', phone: '', active: false, sid: null,
    state: 'idle', detail: '', elapsed: '',
    msgs: [], logs: [], ticket: null,
    profile: null, intentLabel: '', mails: [], recUrl: '',
    customerEmail: 'hailongluu@gmail.com', handlerEmail: 'long@luuhailong.com',
    missing: cfg.missing.map(f => ({...f, status: 'pending', value: '', confidence: 0})),
    stepText: '', totalSteps: cfg.missing.length,
    monWS: null, callWS: null, micCtx: null, micStream: null, playCtx: null,
    sending: true, _timer: null, _t0: 0,

    // ?sid=… → chế độ THEO DÕI cuộc gọi đang chạy (share link / quay demo):
    // server replay lại toàn bộ history event cho monitor vào trễ.
    init() {
      const sid = new URLSearchParams(location.search).get('sid');
      if (sid) {
        this.sid = sid; this.active = true; this._t0 = Date.now();
        // render snapshot qua fetch trước (headless/virtual-time đợi được),
        // rồi bám WS để xem tiếp live
        fetch('/call/state/' + sid).then(r => r.json())
          .then(d => (d.events || []).forEach(ev => this.onEvent(ev)))
          .catch(() => {});
        this.openMonitor();
      }
    },

    get stateLabel() {
      const m = {idle: 'SẴN SÀNG', starting: 'KHỞI TẠO', dialing: 'ĐANG QUAY SỐ',
        ringing: 'ĐANG ĐỔ CHUÔNG', 'in-progress': 'ĐANG GỌI', connected: 'ĐANG GỌI',
        speaking: 'AI ĐANG NÓI', listening: 'ĐANG NGHE KHÁCH', degraded: 'DEGRADED',
        failed: 'LỖI', ended: 'ĐÃ KẾT THÚC', done: 'HOÀN TẤT'};
      return (m[this.state] || this.state.toUpperCase()) + (this.detail ? ' · ' + this.detail : '');
    },
    get badgeClass() {
      if (['failed'].includes(this.state)) return 'err';
      if (['degraded'].includes(this.state)) return 'warn';
      return this.active ? 'live' : '';
    },
    icon(st) {
      return {pending: '⚪', asking: '🔵', filled: '✅', filled_low: '⚠️', skipped: '⛔'}[st] || '⚪';
    },

    // ---------------- start / end ----------------
    async startCall() {
      this.msgs = []; this.logs = []; this.ticket = null; this.stepText = '';
      this.profile = null; this.intentLabel = ''; this.mails = []; this.recUrl = '';
      this.missing.forEach(f => { f.status = 'pending'; f.value = ''; f.confidence = 0; });
      // mở khoá autoplay ngay trong click gesture
      this.playCtx = this.playCtx || new (window.AudioContext || window.webkitAudioContext)();
      this.playCtx.resume().catch(() => {});
      const r = await fetch('/call/start', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({mode: this.mode, phone: this.phone,
          pack: cfg.packId,
          customer_email: this.customerEmail, handler_email: this.handlerEmail}),
      });
      const j = await r.json();
      if (!r.ok) { alert(j.error + (j.hint ? '\n→ ' + j.hint : '')); return; }
      this.sid = j.sid; this.active = true; this._t0 = Date.now();
      this._timer = setInterval(() => {
        const s = Math.floor((Date.now() - this._t0) / 1000);
        this.elapsed = String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
      }, 500);
      this.openMonitor();
      if (this.mode === 'browser') await this.openBrowserCall();
    },
    async endCall() {
      try { await fetch('/call/end', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({sid: this.sid})}); } catch (e) {}
      if (this.callWS) { try { this.callWS.send(JSON.stringify({type: 'call.end'})); } catch (e) {} }
      this.stopLocal();
    },
    stopLocal() {
      this.active = false;
      clearInterval(this._timer);
      if (this.micStream) { this.micStream.getTracks().forEach(t => t.stop()); this.micStream = null; }
      if (this.micCtx) { this.micCtx.close().catch(() => {}); this.micCtx = null; }
    },

    // ---------------- monitor WS ----------------
    openMonitor() {
      const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/callmon/' + this.sid);
      this.monWS = ws;
      ws.onmessage = ev => this.onEvent(JSON.parse(ev.data));
      ws.onclose = () => { if (this.active) this.log('monitor WS đóng'); };
    },
    onEvent(ev) {
      const t = ev.type;
      if (t === 'call.state') {
        this.state = ev.state; this.detail = ev.detail || '';
        if (['done', 'ended', 'failed'].includes(ev.state)) this.stopLocal();
      } else if (t === 'call.step') {
        const f = this.missing.find(x => x.name === ev.field);
        if (f && !(f.status === 'filled' && ev.status === 'asking')) f.status = ev.status;
        this.stepText = (ev.index + 1) + '/' + this.totalSteps;
      } else if (t === 'agent.say') {
        this.pushMsg({role: 'agent', text: ev.text});
      } else if (t === 'transcript.partial') {
        const last = this.msgs[this.msgs.length - 1];
        if (last && last.partial) last.text = ev.text;
        else this.pushMsg({role: 'customer', text: ev.text, partial: true});
      } else if (t === 'transcript.final') {
        const last = this.msgs[this.msgs.length - 1];
        if (last && last.partial) { last.text = ev.text; last.partial = false; }
        else this.pushMsg({role: 'customer', text: ev.text});
      } else if (t === 'state.patch') {
        for (const [name, st] of Object.entries(ev.fields || {})) {
          const f = this.missing.find(x => x.name === name);
          if (f) {
            f.value = st.value == null ? '' : String(st.value);
            f.confidence = st.confidence || 0;
            if (f.status === 'pending' && f.value) f.status = 'filled';
          }
        }
      } else if (t === 'ticket') {
        this.ticket = {id: ev.id, priority: ev.priority, pdf_url: ev.pdf_url || ev.pdf};
      } else if (t === 'crm.profile') {
        this.profile = ev;
      } else if (t === 'intent') {
        this.intentLabel = ev.label;
      } else if (t === 'mail.status') {
        this.mails = ev.statuses || [];
      } else if (t === 'recording') {
        this.recUrl = ev.url;
      } else if (t === 'tts.audio') {          // replay mode: giọng agent qua monitor
        this.playAudio(ev.b64, ev.mime);
      } else if (t === 'error') {
        this.log('⛔ ' + ev.code + ': ' + ev.message);
      } else if (t === 'status') {
        this.log(ev.state + ' — ' + (ev.detail || ''));
      }
    },
    pushMsg(m) {
      this.msgs.push(m);
      this.$nextTick(() => { const c = this.$refs.conv; if (c) c.scrollTop = c.scrollHeight; });
    },
    log(s) { this.logs.unshift(new Date().toLocaleTimeString() + '  ' + s); this.logs = this.logs.slice(0, 60); },

    // ---------------- browser call (mic ↔ loa) ----------------
    async openBrowserCall() {
      try {
        this.micStream = await navigator.mediaDevices.getUserMedia({
          audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true}});
      } catch (e) { alert('Không truy cập được micro: ' + e.message); return; }
      const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws/call/browser/' + this.sid);
      ws.binaryType = 'arraybuffer';
      this.callWS = ws;
      ws.onmessage = async ev => {
        const m = JSON.parse(ev.data);
        if (m.type === 'tts.audio') {
          this.sending = false;                 // tránh mic nuốt giọng agent (echo)
          await this.playAudio(m.b64, m.mime);
          this.sending = true;
          try { ws.send(JSON.stringify({type: 'tts.done', id: m.id})); } catch (e) {}
        } else if (m.type === 'call.ended') {
          this.stopLocal();
        }
      };
      ws.onopen = async () => {
        this.micCtx = new (window.AudioContext || window.webkitAudioContext)();
        await this.micCtx.audioWorklet.addModule('/static/js/pcm_worklet.js');
        const src = this.micCtx.createMediaStreamSource(this.micStream);
        const node = new AudioWorkletNode(this.micCtx, 'pcm16-downsampler');
        const mute = this.micCtx.createGain(); mute.gain.value = 0;
        src.connect(node); node.connect(mute); mute.connect(this.micCtx.destination);
        node.port.onmessage = e => {
          if (this.sending && ws.readyState === 1) ws.send(e.data);
        };
      };
      ws.onclose = () => { if (this.active) this.stopLocal(); };
    },

    // decodeAudioData chơi được mp3 (ElevenLabs) lẫn wav (VALSEA fallback)
    async playAudio(b64, mime) {
      try {
        const ctx = this.playCtx || (this.playCtx = new (window.AudioContext || window.webkitAudioContext)());
        if (ctx.state === 'suspended') await ctx.resume().catch(() => {});
        const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
        const buf = await ctx.decodeAudioData(bytes.buffer);
        await new Promise(res => {
          const s = ctx.createBufferSource();
          s.buffer = buf; s.connect(ctx.destination); s.onended = res; s.start();
        });
      } catch (e) { /* không phát được thì thôi — transcript vẫn chạy */ }
    },
  };
}
