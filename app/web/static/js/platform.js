/* E12 Voice2Claim — Alpine factories cho shell + dashboard + CRM.
   Không build step; mọi fetch đều degrade im lặng (UI hiện trạng thái rỗng). */

const VI_STATUS = {
  received: "Đã tiếp nhận", pending_assignment: "Chờ phân công",
  investigating: "Đang giám định", pending_approval: "Chờ duyệt",
  approved: "Đã duyệt", paid: "Đã chi trả", rejected: "Từ chối",
  draft: "Nháp", pending_review: "Chờ thẩm định", pending_sign: "Chờ ký",
  active: "Hiệu lực", cancelled: "Đã huỷ", expired: "Hết hạn",
  open: "Mở", in_progress: "Đang làm", done: "Xong",
  running: "Đang chạy", waiting_event: "Chờ sự kiện", waiting_task: "Chờ xử lý",
  failed: "Lỗi",
};
const VI_GROUP = { xe: "Xe cộ", y_te: "Y tế", nhan_tho: "Nhân thọ" };

function fmtTimeIso(ts) {
  if (!ts) return "—";
  try {
    const d = new Date(ts.endsWith("Z") || ts.includes("+") ? ts : ts + "Z");
    const today = new Date();
    const hm = d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
    if (d.toDateString() === today.toDateString()) return hm;
    return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" }) + " " + hm;
  } catch { return ts; }
}

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

/* ---------------- popup video hướng dẫn (lần đầu vào) ---------------- */
function introVideo() {
  return {
    open: false, dontShow: true, autoplayMuted: true,
    phase: "pick", lang: localStorage.getItem("v2c_lang") || "vi",
    init() {
      if (!localStorage.getItem("v2c_intro_seen")) {
        setTimeout(() => this.show(false), 450);
      }
    },
    show(manual) {
      this.open = true;
      this.phase = "pick";                     // luôn cho chọn VI / EN trước
      this.autoplayMuted = !manual;            // tự hiện → muted (autoplay policy)
    },
    play(lang) {
      this.lang = lang;
      localStorage.setItem("v2c_lang", lang);
      this.phase = "play";
      this.$nextTick(() => {
        const v = this.$refs.vid;
        if (!v) return;
        v.src = "/demo-video?lang=" + lang;
        v.currentTime = 0;
        v.play().catch(() => {});
      });
    },
    pause() {
      const v = this.$refs.vid;
      if (v) v.pause();
    },
    close() {
      this.open = false;
      this.pause();
      if (this.dontShow) localStorage.setItem("v2c_intro_seen", "1");
    },
  };
}

/* ---------------- role switcher (sidebar) ---------------- */
function roleBox() {
  return {
    open: false,
    role: localStorage.getItem("e12_role") || "call_agent",
    roles: [
      { id: "call_agent", label: "Tổng đài viên", name: "Mai Thị Thanh · NV-03", icon: "🎧" },
      { id: "assessor", label: "Thẩm định viên", name: "Lưu Hải Long · NV-01", icon: "🕵️" },
      { id: "director", label: "Giám đốc", name: "Phạm Quang Dũng · NV-04", icon: "👔" },
      { id: "admin", label: "Admin nền tảng", name: "toàn quyền cấu hình", icon: "🛠️" },
      { id: "customer", label: "Khách hàng", name: "góc nhìn người mua", icon: "🙋" },
    ],
    current() { return this.roles.find(r => r.id === this.role) || this.roles[0]; },
    pick(id) {
      this.role = id;
      localStorage.setItem("e12_role", id);
      this.open = false;
      window.dispatchEvent(new CustomEvent("e12-role", { detail: id }));
    },
  };
}

/* ---------------- dashboard ---------------- */
function dashboardApp() {
  return {
    counts: {}, feed: [], timer: null,
    fmtTime: fmtTimeIso,
    async load() {
      try {
        const d = await getJSON("/api/wf/dashboard");
        this.counts = d.counts || {};
        this.feed = d.feed || [];
      } catch { this.counts = { db_ok: false }; }
      clearInterval(this.timer);
      this.timer = setInterval(() => this.refreshFeed(), 5000);
    },
    async refreshFeed() {
      try {
        const d = await getJSON("/api/wf/dashboard");
        this.counts = d.counts || this.counts;
        this.feed = d.feed || this.feed;
      } catch { /* giữ dữ liệu cũ */ }
    },
    feedTag(f) {
      if (f.actor_kind === "ai") return "AI Điều hành";
      if (f.actor_kind === "employee") return "Nhân sự " + (f.actor_id || "");
      if (f.actor_kind === "customer") return "Khách hàng";
      return "Hệ thống";
    },
  };
}

/* ---------------- workflows: danh sách ---------------- */
function workflowsApp() {
  return {
    defs: [],
    async load() {
      try {
        const d = await getJSON("/api/wf/defs");
        // gộp theo key: ưu tiên bản active
        const byKey = {};
        (d.defs || []).forEach(x => {
          if (!byKey[x.key] || x.status === "active") byKey[x.key] = x;
        });
        this.defs = Object.values(byKey);
      } catch { this.defs = []; }
    },
  };
}

/* ---------------- workflows: chi tiết + intake ---------------- */
function wfDetailApp(key) {
  return {
    key, def: null, versions: [], runs: [], selNode: null, icons: {},
    metrics: [],
    editorOpen: false, editorText: "", editorMsg: "", editorMsgOk: true,
    editorBusy: false,
    prefilling: false, starting: false, startError: "", photos: [],
    form: { ho_ten: "", so_cccd: "", email: "hailongluu@gmail.com",
            so_dien_thoai: "", xe_khach: "", bien_so_xe: "",
            san_pham: "Bảo hiểm vật chất ô tô" },
    fmtTime: fmtTimeIso,
    stVi: s => VI_STATUS[s] || s,
    async load() {
      try {
        const d = await getJSON("/api/wf/defs/" + this.key);
        this.def = { ...d.def, trigger: d.def.trigger || {} };
        this.versions = d.versions || [];
        this.icons = d.node_types || {};
        this.metrics = d.metrics || [];
        this.$nextTick(() => renderGraph(
          this.$refs.viz, this.def.graph, {}, n => { this.selNode = n; }));
      } catch { /* trang trống */ }
      try {
        this.runs = (await getJSON("/api/wf/runs?def_key=" + this.key)).runs || [];
      } catch { this.runs = []; }
    },
    selIcon() { return this.icons[this.selNode?.type] || "▫️"; },
    async activate(version) {
      await fetch(`/api/wf/defs/${this.key}/activate`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version }) });
      this.load();
    },
    editorInit() {
      if (this.editorOpen && !this.editorText && this.def) {
        this.editorText = JSON.stringify(this.def.graph, null, 2);
      }
    },
    _editorGraph() {
      try { return JSON.parse(this.editorText); }
      catch (e) { this.editorMsg = "JSON lỗi: " + e.message; this.editorMsgOk = false; return null; }
    },
    async editorValidate() {
      const g = this._editorGraph();
      if (!g) return;
      const r = await fetch("/api/wf/defs/validate", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ graph: g }) });
      const d = await r.json();
      this.editorMsgOk = d.ok;
      this.editorMsg = d.ok ? "✔ Graph hợp lệ" : d.errors.join("; ");
    },
    editorPreview() {
      const g = this._editorGraph();
      if (!g) return;
      renderGraph(this.$refs.viz, g, {}, n => { this.selNode = n; });
      this.editorMsgOk = true;
      this.editorMsg = "Đang xem trước bản nháp (chưa lưu)";
    },
    async editorSave() {
      const g = this._editorGraph();
      if (!g) return;
      this.editorBusy = true;
      const note = prompt("Ghi chú cho version mới:", "chỉnh cấu hình từ editor") || "";
      const r = await fetch(`/api/wf/defs/${this.key}/versions`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ graph: g, note }) });
      const d = await r.json();
      this.editorBusy = false;
      this.editorMsgOk = !!d.ok;
      this.editorMsg = d.ok ? `💾 Đã lưu v${d.version} (bấm “bật” để kích hoạt)`
                            : (d.errors || [d.error]).join("; ");
      if (d.ok) this.load();
    },
    async voicePrefill(ev) {
      const f = ev.target.files[0];
      if (!f) return;
      this.prefilling = true;
      try {
        const fd = new FormData();
        fd.append("file", f);
        const r = await fetch("/api/batch/insurance_contract", { method: "POST", body: fd });
        const d = await r.json();
        Object.entries(d.fields || {}).forEach(([name, st]) => {
          const v = st && st.value;
          if (v && this.form[name] !== undefined && !this.form[name]) {
            this.form[name] = Array.isArray(v) ? v.join("; ") : String(v);
          }
        });
      } catch { /* để user điền tay */ }
      this.prefilling = false;
      ev.target.value = "";
    },
    async uploadPhotos(ev) {
      for (const f of ev.target.files) {
        const fd = new FormData();
        fd.append("file", f);
        try {
          const r = await fetch("/api/wf/uploads", { method: "POST", body: fd });
          const d = await r.json();
          if (d.ok) this.photos.push(d);
        } catch { /* bỏ qua ảnh lỗi */ }
      }
      ev.target.value = "";
    },
    async startRun() {
      this.startError = "";
      const need = ["ho_ten", "so_cccd", "email", "xe_khach", "bien_so_xe"];
      const miss = need.filter(k => !this.form[k].trim());
      if (miss.length) {
        this.startError = "Thiếu: " + miss.join(", ");
        return;
      }
      this.starting = true;
      try {
        const r = await fetch("/api/wf/runs", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            def_key: this.key, channel: "web",
            context: { fields: { ...this.form }, photos: this.photos },
          }),
        });
        const d = await r.json();
        if (d.ok) window.location = "/runs/" + d.run_id;
        else this.startError = d.error || "Không khởi động được";
      } catch { this.startError = "Lỗi mạng"; }
      this.starting = false;
    },
  };
}

/* ---------------- run detail ---------------- */
function runApp(runId) {
  return {
    runId, run: null, statusMap: {}, timer: null,
    fmtTime: fmtTimeIso,
    stVi: s => VI_STATUS[s] || s || "…",
    ctx() { return this.run?.context || {}; },
    ctxPublic() {
      const c = { ...(this.run?.context || {}) };
      Object.keys(c).filter(k => k.startsWith("_")).forEach(k => delete c[k]);
      return c;
    },
    waitInfo() {
      if (!this.run) return "";
      const c = this.ctx();
      if (this.run.status === "waiting_event" && c._sign_token) {
        const url = "/sign/" + c._sign_token;
        return `Khách cần <b>ký điện tử</b> — link đã gửi email` +
          ` <span class="mono">${(c.fields || {}).email || ""}</span>.` +
          ` <a href="${url}" target="_blank" style="color:var(--acc2)">Mở trang ký (demo) →</a>`;
      }
      if (this.run.status === "waiting_task") {
        return `Đang chờ nhân sự xử lý trong <a href="/tasks" style="color:var(--acc2)">Hộp công việc</a>` +
          ` — node <span class="mono">${this.run.current_node}</span>.`;
      }
      return "";
    },
    async load() {
      await this.refresh();
      clearInterval(this.timer);
      this.timer = setInterval(() => this.refresh(), 3000);
    },
    async refresh() {
      try {
        const d = await getJSON("/api/wf/runs/" + this.runId);
        this.run = d.run;
        this.statusMap = d.status_map || {};
        this.$nextTick(() => renderGraph(
          this.$refs.viz, this.run.graph, this.statusMap, null));
        if (["done", "failed", "cancelled"].includes(this.run.status)) {
          clearInterval(this.timer);
        }
      } catch { /* giữ trạng thái cũ */ }
    },
    async retry() {
      await fetch(`/api/wf/runs/${this.runId}/retry`, { method: "POST" });
      this.load();
    },
  };
}

/* ---------------- tasks inbox ---------------- */
const ROLE_ACTOR = { call_agent: "NV-03", assessor: "NV-01",
                     director: "NV-04", admin: "NV-04" };

function tasksApp() {
  return {
    tasks: [], sel: null, values: {}, files: [], note: "", stars: 0,
    busy: false, uploading: false, loading: false, error: "", showAll: false,
    fmtTime: fmtTimeIso,
    roleId() {                                   // ?role=… thắng (share/demo)
      return new URLSearchParams(location.search).get("role")
        || localStorage.getItem("e12_role") || "call_agent";
    },
    roleLabel() {
      return { call_agent: "Tổng đài viên", assessor: "Thẩm định viên",
               director: "Giám đốc", admin: "Admin", customer: "Khách hàng" }[this.roleId()] || this.roleId();
    },
    roleVi(r) { return { call_agent: "CSR", assessor: "thẩm định",
                         director: "giám đốc", admin: "admin" }[r] || r; },
    ticon(t) { return { assessor_visit: "🕵️", director_approval: "👔",
                        review_contract: "🧐", complete_form: "📝",
                        call_customer: "📞" }[t.task_type] || "🗂️"; },
    prClass(p) { return p === "CAO" ? "CAO" : (p === "TRUNG BÌNH" ? "TB" : "THUONG"); },
    async load() {
      const role = this.showAll || this.roleId() === "admin" ? "" : this.roleId();
      try {
        this.tasks = (await getJSON("/api/wf/tasks?role=" + role)).tasks || [];
      } catch { this.tasks = []; }
      if (this.sel && !this.tasks.find(t => t.id === this.sel.id)) this.sel = null;
      const sel = new URLSearchParams(location.search).get("sel");
      if (sel && !this.sel) {                    // deep-link ?sel=<task_id>
        const t = this.tasks.find(x => String(x.id) === sel);
        if (t) this.pick(t);
      }
      window.addEventListener("e12-role", () => this.load(), { once: true });
    },
    pick(t) {
      this.sel = t; this.values = {}; this.files = [];
      this.note = ""; this.error = ""; this.stars = 0;
    },
    data() { try { return JSON.parse(this.sel?.data_json || "{}"); } catch { return {}; } },
    formFields() { return this.data().form || []; },
    hasDecision() { return !!(this.data().decision || []).length; },
    wantsUploads() { return !!this.data().uploads; },
    excerpt() {
      const e = this.data().context_excerpt;
      if (!e) return null;
      const out = {};
      if (e.khach) out["Khách"] = e.khach;
      Object.entries(e.fields || {}).forEach(([k, v]) => { out[k] = String(v); });
      return Object.keys(out).length ? out : null;
    },
    async upload(ev) {
      this.uploading = true;
      for (const f of ev.target.files) {
        const fd = new FormData();
        fd.append("file", f);
        try {
          const r = await fetch("/api/wf/uploads", { method: "POST", body: fd });
          const d = await r.json();
          if (d.ok) this.files.push(d);
          else this.error = d.error || "upload lỗi";
        } catch { this.error = "upload lỗi mạng"; }
      }
      this.uploading = false;
      ev.target.value = "";
    },
    async complete(outcome) {
      if (!this.sel) return;
      this.busy = true; this.error = "";
      const result = { ...this.values, files: this.files };
      const rec = this.files.find(f => /\.(wav|m4a|mp3|ogg|webm)$/i.test(f.name));
      if (rec) result.recording = rec.path;
      try {
        const r = await fetch(`/api/wf/tasks/${this.sel.id}/complete`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ outcome, note: this.note, result,
                                 stars: this.stars,
                                 actor_id: ROLE_ACTOR[this.roleId()] || "" }),
        });
        const d = await r.json();
        if (d.ok) {
          const runId = d.run_id;
          this.sel = null;
          await this.load();
          if (runId) window.location = "/runs/" + runId;
        } else this.error = d.error || "không hoàn tất được";
      } catch { this.error = "lỗi mạng"; }
      this.busy = false;
    },
  };
}

/* ---------------- kho tri thức ---------------- */
function kbApp() {
  return {
    docs: [], extractions: [], qwenReady: false, drag: false,
    uploading: false, busyDoc: 0, busyExt: 0, errors: {},
    kindIcon: k => ({ text: "📄", pdf: "📕", audio: "🎙️", image: "🖼️",
                      invoice: "🧾" }[k] || "📄"),
    stLabel: s => ({ uploaded: "đã lưu", extracting: "đang bóc…",
                     extracted: "đã bóc tách", failed: "lỗi" }[s] || s),
    async load() {
      try {
        const d = await getJSON("/api/wf/kb");
        this.docs = d.docs || [];
        this.extractions = d.extractions || [];
        this.qwenReady = !!d.qwen_ready;
      } catch { /* trống */ }
    },
    onDrop(ev) { this.drag = false; this.upload(ev.dataTransfer.files); },
    async upload(files) {
      this.uploading = true;
      for (const f of files) {
        const fd = new FormData();
        fd.append("file", f);
        try { await fetch("/api/wf/kb/upload", { method: "POST", body: fd }); }
        catch { /* bỏ qua */ }
      }
      this.uploading = false;
      this.load();
    },
    async extract(d) {
      this.busyDoc = d.id;
      try {
        const r = await fetch(`/api/wf/kb/${d.id}/extract`, { method: "POST" });
        await r.json();
      } catch { /* hiện qua status */ }
      this.busyDoc = 0;
      this.load();
    },
    async promote(e) {
      this.busyExt = e.id;
      try {
        const r = await fetch(`/api/wf/kb/extractions/${e.id}/promote`,
          { method: "POST", headers: { "Content-Type": "application/json" },
            body: "{}" });
        const d = await r.json();
        if (!d.ok) this.errors[e.id] = (d.errors || [d.error]).join("; ");
      } catch { this.errors[e.id] = "lỗi mạng"; }
      this.busyExt = 0;
      this.load();
    },
  };
}

/* ---------------- CRM ---------------- */
function crmApp() {
  return {
    tab: "customers", customers: [], policies: [], claims: [], employees: [],
    sel: "", d: null, loading: false,
    editCust: null, savingCust: false, custMsg: "", custMsgOk: true,
    editEmp: null, savingEmp: false, empMsg: "", empMsgOk: true,
    fmtTime: fmtTimeIso,
    stVi: s => VI_STATUS[s] || s,
    groupVi: g => VI_GROUP[g] || g,
    roleVi: r => ({ call_agent: "Tổng đài viên", assessor: "Thẩm định viên",
                    director: "Giám đốc", admin: "Admin" }[r] || r),
    empIcon: r => ({ call_agent: "🎧", assessor: "🕵️", director: "👔",
                     admin: "🛠️" }[r] || "🧑‍💼"),
    async load() {
      try {
        const [c, p, cl, em] = await Promise.all([
          getJSON("/api/wf/crm/customers"),
          getJSON("/api/wf/crm/policies"),
          getJSON("/api/wf/crm/claims"),
          getJSON("/api/wf/crm/employees"),
        ]);
        this.customers = c.customers || [];
        this.policies = p.policies || [];
        this.claims = cl.claims || [];
        this.employees = em.employees || [];
        if (this.sel) this.pick(this.sel);
        const sel = new URLSearchParams(location.search).get("sel");
        if (sel && !this.sel) this.pick(sel);   // deep-link ?sel=KH-0001
      } catch { /* bảng rỗng */ }
    },
    async pick(cid) {
      this.sel = cid;
      this.loading = true;
      this.editCust = null; this.custMsg = "";
      try { this.d = (await getJSON("/api/wf/crm/customers/" + cid)).detail; }
      catch { this.d = null; }
      this.loading = false;
    },
    startEditCust() {
      const c = this.d?.customer;
      if (!c) return;
      this.custMsg = "";
      this.editCust = { id: c.id, name: c.name, email: c.email || "",
                        phone: c.phone || "", national_id: c.national_id || "" };
    },
    async saveCust() {
      this.savingCust = true; this.custMsg = "";
      try {
        const r = await fetch("/api/wf/crm/customers/" + this.editCust.id, {
          method: "PATCH", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.editCust) });
        const j = await r.json();
        this.custMsgOk = r.ok;
        this.custMsg = r.ok ? "✔ Đã lưu — email/SĐT mới dùng cho run kế tiếp"
                            : (j.error || "không lưu được");
        if (r.ok) { this.editCust = null; await this.load(); }
      } catch { this.custMsgOk = false; this.custMsg = "lỗi mạng"; }
      this.savingCust = false;
    },
    pickEmp(e) {
      this.empMsg = "";
      this.editEmp = { id: e.id, role: e.role, claim_groups: e.claim_groups,
                       name: e.name, email: e.email || "", phone: e.phone || "" };
    },
    async saveEmp() {
      this.savingEmp = true; this.empMsg = "";
      try {
        const r = await fetch("/api/wf/crm/employees/" + this.editEmp.id, {
          method: "PATCH", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(this.editEmp) });
        const j = await r.json();
        this.empMsgOk = r.ok;
        this.empMsg = r.ok ? "✔ Đã lưu — người này nhận việc từ giờ"
                           : (j.error || "không lưu được");
        if (r.ok) await this.load();
      } catch { this.empMsgOk = false; this.empMsg = "lỗi mạng"; }
      this.savingEmp = false;
    },
  };
}
