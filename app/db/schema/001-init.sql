-- E12 Insurance OS — schema khởi tạo (SQLite, WAL, FK ON do database.py set).
-- ID nghiệp vụ TEXT giữ format cũ (KH-/NV-/CL-/TCK-/POL-/GCN-); bảng máy INTEGER PK.
-- FK vòng (claims<->tickets<->workflow_runs) hợp lệ: SQLite chỉ enforce lúc ghi.

-- ============ Hạ tầng ============
CREATE TABLE sequences (
  name  TEXT PRIMARY KEY,          -- 'customer' | 'policy' | 'claim:XE:2607' ...
  value INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE status_history (
  id INTEGER PRIMARY KEY,
  entity_kind TEXT NOT NULL CHECK(entity_kind IN ('claim','policy','task','run','ticket','customer','call')),
  entity_id   TEXT NOT NULL,
  from_status TEXT DEFAULT '',
  to_status   TEXT NOT NULL,
  actor_kind  TEXT NOT NULL DEFAULT 'system'
    CHECK(actor_kind IN ('employee','customer','system','ai')),
  actor_id    TEXT DEFAULT '',
  note        TEXT DEFAULT '',
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX ix_history_entity ON status_history(entity_kind, entity_id, created_at);
CREATE INDEX ix_history_feed ON status_history(created_at DESC);

-- ============ CRM ============
CREATE TABLE customers (
  id TEXT PRIMARY KEY,             -- 'KH-0001'
  name TEXT NOT NULL,
  name_norm TEXT NOT NULL,         -- normalize_vi(name) — phục vụ lookup
  email TEXT NOT NULL DEFAULT '',
  phone TEXT NOT NULL DEFAULT '',
  national_id TEXT NOT NULL DEFAULT '',   -- CCCD; verify_identity khớp đuôi
  dob TEXT, address TEXT,
  source TEXT NOT NULL DEFAULT 'seed'
    CHECK(source IN ('seed','notify_import','call','manual')),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX ix_customers_name_norm ON customers(name_norm);
CREATE INDEX ix_customers_national_id ON customers(national_id);

CREATE TABLE employees (
  id TEXT PRIMARY KEY,             -- 'NV-01'
  name TEXT NOT NULL,
  name_norm TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL CHECK(role IN ('call_agent','assessor','director','admin')),
  claim_groups TEXT NOT NULL DEFAULT '[]',   -- JSON: ["xe","nhan_tho"]
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE policies (
  id TEXT PRIMARY KEY,             -- 'POL-0001'
  policy_no TEXT UNIQUE,           -- 'GCN-2025-104729' (NULL đến khi phát hành)
  customer_id TEXT NOT NULL REFERENCES customers(id),
  product_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK(status IN ('draft','pending_review','pending_sign','active','rejected','cancelled','expired')),
  premium_vnd INTEGER, sum_insured_vnd INTEGER,
  effective_date TEXT, expiry_date TEXT, signed_at TEXT,
  data_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX ix_policies_customer ON policies(customer_id, status);

CREATE TABLE insured_assets (
  id INTEGER PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers(id),
  policy_id TEXT REFERENCES policies(id),
  kind TEXT NOT NULL DEFAULT 'vehicle' CHECK(kind IN ('vehicle','property','person','health')),
  make_model TEXT DEFAULT '',
  plate_no TEXT DEFAULT '',
  data_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX ix_assets_customer ON insured_assets(customer_id);
CREATE INDEX ix_assets_plate ON insured_assets(plate_no);

CREATE TABLE claims (
  id TEXT PRIMARY KEY,             -- 'CL-XE-2607-001'
  customer_id TEXT NOT NULL REFERENCES customers(id),
  policy_id TEXT REFERENCES policies(id),
  asset_id INTEGER REFERENCES insured_assets(id),
  claim_type TEXT NOT NULL DEFAULT '',       -- 'car_accident' | 'health' ...
  claim_group TEXT NOT NULL DEFAULT 'xe' CHECK(claim_group IN ('xe','y_te','nhan_tho')),
  status TEXT NOT NULL DEFAULT 'received'
    CHECK(status IN ('received','pending_assignment','investigating',
                     'pending_approval','approved','paid','rejected')),
  incident_at TEXT DEFAULT '', location TEXT DEFAULT '',
  description TEXT DEFAULT '', injury TEXT DEFAULT '',
  handler_id TEXT REFERENCES employees(id),
  amount_claimed_vnd INTEGER, amount_approved_vnd INTEGER,
  ticket_id TEXT REFERENCES tickets(id),
  run_id INTEGER REFERENCES workflow_runs(id),
  data_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX ix_claims_customer ON claims(customer_id, status);
CREATE INDEX ix_claims_status ON claims(status);
CREATE INDEX ix_claims_handler ON claims(handler_id, status);

CREATE TABLE interactions (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('call_in','call_out','email_out','email_in','web','note')),
  customer_id TEXT REFERENCES customers(id),      -- NULL = chưa định danh
  claim_id TEXT REFERENCES claims(id),
  policy_id TEXT REFERENCES policies(id),
  channel_ref TEXT DEFAULT '',                    -- call sid / Brevo message id
  transcript TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  recording_url TEXT NOT NULL DEFAULT '',
  started_at TEXT, ended_at TEXT,
  data_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX ix_interactions_customer ON interactions(customer_id, created_at);
CREATE INDEX ix_interactions_claim ON interactions(claim_id);

CREATE TABLE documents (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL CHECK(kind IN ('pdf','recording','photo','bien_ban','invoice','contract','other')),
  path TEXT NOT NULL,              -- đường dẫn tương đối repo
  url TEXT NOT NULL DEFAULT '',    -- '/pdf/...' | '/rec/{sid}' | '/uploads/...'
  mime TEXT NOT NULL DEFAULT '',
  size_bytes INTEGER,
  owner_kind TEXT NOT NULL CHECK(owner_kind IN
    ('customer','policy','claim','ticket','interaction','task','run','kb')),
  owner_id TEXT NOT NULL,          -- polymorphic — chỉ ghi qua DAL
  label TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX ix_documents_owner ON documents(owner_kind, owner_id);

-- ============ ERP-lite ============
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  task_type TEXT NOT NULL CHECK(task_type IN
    ('assessor_visit','director_approval','review_contract','call_customer','upload_report','complete_form','other')),
  assignee_id TEXT REFERENCES employees(id),      -- NULL = hàng đợi theo vai
  assignee_role TEXT CHECK(assignee_role IN ('call_agent','assessor','director','admin')),
  status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','in_progress','done','cancelled')),
  outcome TEXT CHECK(outcome IN ('approved','rejected','completed')),
  outcome_note TEXT NOT NULL DEFAULT '',
  priority TEXT NOT NULL DEFAULT 'THƯỜNG' CHECK(priority IN ('CAO','TRUNG BÌNH','THƯỜNG')),
  due_at TEXT,
  customer_id TEXT REFERENCES customers(id),
  claim_id TEXT REFERENCES claims(id),
  policy_id TEXT REFERENCES policies(id),
  run_id INTEGER REFERENCES workflow_runs(id),
  step_run_id INTEGER REFERENCES step_runs(id),
  data_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  completed_at TEXT
);
CREATE INDEX ix_tasks_inbox ON tasks(status, assignee_id, assignee_role);
CREATE INDEX ix_tasks_run ON tasks(run_id);

-- ============ Workflow platform ============
CREATE TABLE workflow_defs (
  id INTEGER PRIMARY KEY,
  key TEXT NOT NULL,               -- 'wf_contract_open' | 'wf_claim'
  version INTEGER NOT NULL DEFAULT 1,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','active','archived')),
  graph_json TEXT NOT NULL,        -- {nodes:[...], edges:[...]} — engine-owned
  trigger_json TEXT NOT NULL DEFAULT '{}',
  source TEXT NOT NULL DEFAULT 'seed' CHECK(source IN ('seed','manual','kb_extraction')),
  source_extraction_id INTEGER REFERENCES kb_extractions(id),
  created_by TEXT REFERENCES employees(id),
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(key, version)
);
CREATE UNIQUE INDEX ux_workflow_defs_active ON workflow_defs(key) WHERE status='active';

CREATE TABLE action_catalog (
  id INTEGER PRIMARY KEY,
  key TEXT NOT NULL,               -- 'SUBMIT_CALLCENTER_CLAIM' | 'send_email' ...
  pack_id TEXT,                    -- NULL = action nền tảng
  kind TEXT NOT NULL CHECK(kind IN
    ('pdf_ticket','send_email','create_claim','create_policy','update_status',
     'create_task','wait_event','auto_call','tts_say','webhook','auto_judge','noop')),
  label TEXT NOT NULL,
  config_json TEXT NOT NULL DEFAULT '{}',
  enabled INTEGER NOT NULL DEFAULT 1,
  overridden INTEGER NOT NULL DEFAULT 0,     -- 1 = sửa tay, import pack không đè
  source TEXT NOT NULL DEFAULT 'pack_import'
    CHECK(source IN ('pack_import','manual','kb_extraction','seed')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(pack_id, key)
);

CREATE TABLE workflow_runs (
  id INTEGER PRIMARY KEY,
  def_id INTEGER NOT NULL REFERENCES workflow_defs(id),  -- pin version lúc start
  status TEXT NOT NULL DEFAULT 'running'
    CHECK(status IN ('running','waiting_event','waiting_task','done','failed','cancelled')),
  current_node TEXT NOT NULL DEFAULT '',
  channel TEXT NOT NULL DEFAULT 'api',       -- 'call'|'web'|'api'
  customer_id TEXT REFERENCES customers(id),
  claim_id TEXT REFERENCES claims(id),
  policy_id TEXT REFERENCES policies(id),
  ticket_id TEXT REFERENCES tickets(id),
  interaction_id INTEGER REFERENCES interactions(id),
  correlation_key TEXT,                      -- token e-sign... → resume không cần run id
  context_json TEXT NOT NULL DEFAULT '{}',
  outcome TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  ended_at TEXT
);
CREATE INDEX ix_runs_status ON workflow_runs(status);
CREATE INDEX ix_runs_def ON workflow_runs(def_id, status);
CREATE INDEX ix_runs_correlation ON workflow_runs(correlation_key) WHERE correlation_key IS NOT NULL;

CREATE TABLE step_runs (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES workflow_runs(id),
  node_id TEXT NOT NULL,
  action_key TEXT NOT NULL DEFAULT '',
  attempt INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'running'
    CHECK(status IN ('running','waiting','completed','failed','skipped','interrupted')),
  waiting_event TEXT NOT NULL DEFAULT '',
  input_json TEXT NOT NULL DEFAULT '{}',
  output_json TEXT NOT NULL DEFAULT '{}',
  error TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  ended_at TEXT
);
CREATE INDEX ix_steps_run ON step_runs(run_id, started_at);
CREATE INDEX ix_steps_waiting ON step_runs(waiting_event, status) WHERE status='waiting';

CREATE TABLE events (
  id INTEGER PRIMARY KEY,
  key TEXT NOT NULL,               -- 'esign.signed'|'report.submitted'|'task.completed'|'call.finished'
  run_id INTEGER REFERENCES workflow_runs(id),
  correlation_key TEXT,            -- token single-use / địa chỉ thay run_id
  payload_json TEXT NOT NULL DEFAULT '{}',
  source TEXT NOT NULL DEFAULT 'system'
    CHECK(source IN ('ui','api','mailer','telephony','system')),
  status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','consumed','ignored','minted')),
  consumed_by_step_run_id INTEGER REFERENCES step_runs(id),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  consumed_at TEXT
);
CREATE INDEX ix_events_new ON events(status, key);
CREATE INDEX ix_events_correlation ON events(correlation_key) WHERE correlation_key IS NOT NULL;

-- ============ Flywheel ============
CREATE TABLE evaluations (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES workflow_runs(id),
  rater_kind TEXT NOT NULL
    CHECK(rater_kind IN ('customer','handler','director','agent','auto','qwen_judge')),
  rater_id TEXT NOT NULL DEFAULT '',
  score INTEGER CHECK(score BETWEEN 1 AND 5),   -- NULL cho phép (auto chỉ metrics)
  comment TEXT NOT NULL DEFAULT '',
  criteria_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  UNIQUE(run_id, rater_kind, rater_id)
);

CREATE VIEW v_workflow_metrics AS
SELECT d.key, d.version, d.status AS def_status,
       COUNT(DISTINCT r.id)                          AS runs,
       SUM(r.status='done')                          AS completed,
       SUM(r.status='failed')                        AS failed,
       ROUND(AVG(CASE WHEN r.ended_at IS NOT NULL THEN
         (julianday(r.ended_at)-julianday(r.started_at))*86400.0 END),1) AS avg_secs,
       ROUND(AVG(CASE WHEN e.score IS NOT NULL THEN e.score END),2) AS avg_score,
       COUNT(e.id)                                   AS ratings
FROM workflow_defs d
LEFT JOIN workflow_runs r ON r.def_id=d.id
LEFT JOIN evaluations  e ON e.run_id=r.id
GROUP BY d.id;

-- ============ Kho tri thức ============
CREATE TABLE kb_documents (
  id INTEGER PRIMARY KEY,
  filename TEXT NOT NULL,
  mime TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL CHECK(kind IN ('pdf','text','audio','image','invoice','other')),
  path TEXT NOT NULL,              -- 'data/kb/<sha1><ext>' hoặc file repo
  size_bytes INTEGER,
  sha1 TEXT UNIQUE,
  status TEXT NOT NULL DEFAULT 'uploaded'
    CHECK(status IN ('uploaded','extracting','extracted','failed')),
  summary TEXT NOT NULL DEFAULT '',
  uploaded_by TEXT REFERENCES employees(id),
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE kb_extractions (
  id INTEGER PRIMARY KEY,
  doc_id INTEGER NOT NULL REFERENCES kb_documents(id),
  engine TEXT NOT NULL DEFAULT 'qwen' CHECK(engine IN ('qwen','manual')),
  extracted_json TEXT NOT NULL,    -- draft: summary + graph + actions đề xuất
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','promoted','discarded')),
  promoted_workflow_def_id INTEGER REFERENCES workflow_defs(id),
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- ============ Tickets (bền hoá ticket_store) ============
CREATE TABLE tickets (
  id TEXT PRIMARY KEY,             -- 'TCK-0012' (giữ format)
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  action TEXT NOT NULL DEFAULT '',
  action_label TEXT NOT NULL DEFAULT '',
  pack TEXT NOT NULL DEFAULT '',
  pack_icon TEXT NOT NULL DEFAULT '',
  priority TEXT NOT NULL DEFAULT 'THƯỜNG',
  status TEXT NOT NULL DEFAULT '',
  pdf_url TEXT NOT NULL DEFAULT '',
  recording_url TEXT NOT NULL DEFAULT '',
  fields_count INTEGER NOT NULL DEFAULT 0,
  customer_id TEXT REFERENCES customers(id),
  claim_id TEXT REFERENCES claims(id),
  run_id INTEGER REFERENCES workflow_runs(id),
  payload_json TEXT NOT NULL DEFAULT '{}'   -- dict gốc nguyên vẹn (hydrate console)
);
CREATE INDEX ix_tickets_created ON tickets(created_at);
