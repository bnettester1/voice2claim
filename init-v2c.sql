-- ============================================================
-- Voice2Claim Database Initialization Script
-- User: admin | Database: voice2claim_db
-- ============================================================
CREATE DATABASE voice2claim_db;

-- 2. Chuyển kết nối sang database vừa tạo (Lệnh meta \c của psql hoạt động tốt trong Docker entrypoint)
-- Kết nối vào database (Docker entrypoint sẽ tự tạo DB này nếu POSTGRES_DB=voice2claim_db)
\c voice2claim_db admin

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- SCHEMA: Users & Authentication
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'adjuster',
    phone VARCHAR(20),
    department VARCHAR(100),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- SCHEMA: Claims & Assessments
-- ============================================================
CREATE TABLE IF NOT EXISTS claim_types (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(50) UNIQUE NOT NULL,
    name_vi VARCHAR(255) NOT NULL,
    name_en VARCHAR(255),
    description TEXT,
    is_active BOOLEAN DEFAULT true
);

INSERT INTO claim_types (code, name_vi, name_en, description) VALUES
('vehicle', 'Giám định tai nạn xe ô tô', 'Vehicle Accident Assessment', 'Giám định thiệt hại xe cơ giới'),
('medical', 'Giám định y tế / thương tật', 'Medical/Disability Assessment', 'Giám định thương tật và y tế'),
('fire', 'Giám định hỏa hoạn', 'Fire Damage Assessment', 'Giám định thiệt hại do cháy nổ'),
('injury', 'Giám định tai nạn con người', 'Personal Injury Assessment', 'Giám định tai nạn cá nhân')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS claims (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_number VARCHAR(100) UNIQUE NOT NULL,
    claim_type_id UUID NOT NULL REFERENCES claim_types(id),
    user_id UUID NOT NULL REFERENCES users(id),
    incident_date TIMESTAMP WITH TIME ZONE,
    incident_location TEXT,
    incident_description TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    priority VARCHAR(20) DEFAULT 'normal',
    estimated_cost DECIMAL(15,2),
    currency VARCHAR(10) DEFAULT 'VND',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS claim_vehicles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    vehicle_model VARCHAR(255),
    license_plate VARCHAR(20),
    damages JSONB,
    estimated_repair_cost DECIMAL(15,2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS claim_medical (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    patient_name VARCHAR(255),
    patient_id_card VARCHAR(20),
    diagnosis TEXT,
    medical_facility VARCHAR(255),
    disability_rate DECIMAL(5,2),
    medications JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- SCHEMA: Audio & Transcription
-- ============================================================
CREATE TABLE IF NOT EXISTS audio_recordings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id UUID REFERENCES claims(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    file_path VARCHAR(500) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    duration_seconds DECIMAL(10,2),
    processing_status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transcripts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    audio_id UUID NOT NULL REFERENCES audio_recordings(id) ON DELETE CASCADE,
    provider VARCHAR(50) DEFAULT 'valsea',
    raw_text TEXT NOT NULL,
    normalized_text TEXT,
    confidence_score DECIMAL(5,4),
    segments JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- SCHEMA: Workflow & Actions
-- ============================================================
CREATE TABLE IF NOT EXISTS action_types (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(50) UNIQUE NOT NULL,
    name_vi VARCHAR(255) NOT NULL,
    icon VARCHAR(50),
    color VARCHAR(20),
    is_active BOOLEAN DEFAULT true
);

INSERT INTO action_types (code, name_vi, icon, color) VALUES
('send_email', 'Gửi mail cho khách', 'fa-envelope', 'primary'),
('make_call', 'Gọi điện', 'fa-phone', 'secondary'),
('dispatch_surveyor', 'Gọi xe xuống hiện trường', 'fa-car', 'warning')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS workflow_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    claim_id UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    action_type_id UUID NOT NULL REFERENCES action_types(id),
    action_params JSONB,
    status VARCHAR(50) DEFAULT 'pending',
    executed_at TIMESTAMP WITH TIME ZONE,
    result JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- GRANT PERMISSIONS (Sửa thành user 'admin')
-- ============================================================
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO admin;

-- ============================================================
-- DEFAULT DATA
-- ============================================================
INSERT INTO users (email, password_hash, full_name, role, phone, department) VALUES
('admin@voice2claim.com', crypt('admin123', gen_salt('bf', 10)), 'Admin User', 'admin', '0909000000', 'IT'),
('minh.nguyen@voice2claim.com', crypt('demo123', gen_salt('bf', 10)), 'Nguyễn Văn Minh', 'adjuster', '0909123456', 'Claims')
ON CONFLICT (email) DO NOTHING;

SELECT '✅ Database voice2claim_db initialized successfully for user admin!' as status;

-- ============================================================
-- 1) CLAIMS
-- ============================================================
INSERT INTO claims (
  claim_number, claim_type_id, user_id,
  incident_date, incident_location, incident_description,
  status, priority, estimated_cost, currency
)
SELECT 'CLM-2026-001', ct.id, u.id,
       '2026-07-18 11:15:00+07',
       'BV Chợ Rẫy, TP.HCM',
       'Giám định thương tật chị Lan - gãy kín xương cẳng chân phải',
       'completed', 'normal', NULL, 'VND'
FROM claim_types ct, users u
WHERE ct.code = 'medical' AND u.email = 'minh.nguyen@voice2claim.com'
ON CONFLICT (claim_number) DO NOTHING;

INSERT INTO claims (
  claim_number, claim_type_id, user_id,
  incident_date, incident_location, incident_description,
  status, priority, estimated_cost, currency
)
SELECT 'CLM-2026-002', ct.id, u.id,
       '2026-07-17 16:48:00+07',
       '15 Nguyễn Kiệm, P.3, Gò Vấp',
       'Hỏa hoạn nhà anh Khoa - bão số 5 tốc mái tôn, chập cháy tivi',
       'completed', 'normal', 45000000.00, 'VND'
FROM claim_types ct, users u
WHERE ct.code = 'fire' AND u.email = 'minh.nguyen@voice2claim.com'
ON CONFLICT (claim_number) DO NOTHING;

INSERT INTO claims (
  claim_number, claim_type_id, user_id,
  incident_date, incident_location, incident_description,
  status, priority, estimated_cost, currency
)
SELECT 'CLM-2026-003', ct.id, u.id,
       '2026-07-17 09:20:00+07',
       'BV Đại học Y Dược, TP.HCM',
       'Khám tiêu hóa anh Nam - viêm loét tá tràng HP dương tính',
       'completed', 'normal', NULL, 'VND'
FROM claim_types ct, users u
WHERE ct.code = 'medical' AND u.email = 'minh.nguyen@voice2claim.com'
ON CONFLICT (claim_number) DO NOTHING;

INSERT INTO claims (
  claim_number, claim_type_id, user_id,
  incident_date, incident_location, incident_description,
  status, priority, estimated_cost, currency
)
SELECT 'CLM-2026-004', ct.id, u.id,
       '2026-07-17 15:40:00+07',
       'Ngã tư Nguyễn Văn Linh - Hoàng Diệu, TP.HCM',
       'Va chạm liên hoàn cầu Sài Gòn - Ford Ranger, SH, xe buýt, Mazda CX-5',
       'completed', 'high', 28500000.00, 'VND'
FROM claim_types ct, users u
WHERE ct.code = 'vehicle' AND u.email = 'minh.nguyen@voice2claim.com'
ON CONFLICT (claim_number) DO NOTHING;

INSERT INTO claims (
  claim_number, claim_type_id, user_id,
  incident_date, incident_location, incident_description,
  status, priority, estimated_cost, currency
)
SELECT 'CLM-2026-005', ct.id, u.id,
       '2026-07-17 10:05:00+07',
       'Đường Cộng Hòa, TP.HCM',
       'Tai nạn xe máy đường Cộng Hòa - Wave Alpha bị Toyota Vios 59A-987.65 đâm từ phía sau',
       'completed', 'normal', NULL, 'VND'
FROM claim_types ct, users u
WHERE ct.code = 'injury' AND u.email = 'minh.nguyen@voice2claim.com'
ON CONFLICT (claim_number) DO NOTHING;

-- ============================================================
-- 2) VEHICLE DETAILS  (claims #4, #5)
-- ============================================================
INSERT INTO claim_vehicles (claim_id, vehicle_model, license_plate, damages, estimated_repair_cost)
SELECT c.id, 'Mazda CX-5', '51H-123.45',
       '["Vỡ đèn pha phải","Móp cản trước 30cm","Rỉ dầu carter","Trầy nắp capô 40cm"]'::jsonb,
       28500000.00
FROM claims c WHERE c.claim_number = 'CLM-2026-004' ON CONFLICT DO NOTHING;

INSERT INTO claim_vehicles (claim_id, vehicle_model, license_plate, damages, estimated_repair_cost)
SELECT c.id, 'Wave Alpha', NULL,
       '["Vỡ yếm xe","Gãy gương chiếu hậu trái"]'::jsonb,
       NULL
FROM claims c WHERE c.claim_number = 'CLM-2026-005' ON CONFLICT DO NOTHING;

-- ============================================================
-- 3) MEDICAL DETAILS  (claims #1, #3)
-- ============================================================
INSERT INTO claim_medical (claim_id, patient_name, patient_id_card, diagnosis, medical_facility, disability_rate, medications)
SELECT c.id, 'Chị Lan', '079-185-xxx-xxx',
        'Gãy kín 1/3 giữa xương cẳng chân phải, đứt dây chằng chéo trước độ 2',
        'BV Chợ Rẫy', 22.00,
        '["Bó bột đùi bàn 6 tuần","Celecoxib 200mg","Alpha Choay"]'::jsonb
FROM claims c WHERE c.claim_number = 'CLM-2026-001' ON CONFLICT DO NOTHING;

INSERT INTO claim_medical (claim_id, patient_name, patient_id_card, diagnosis, medical_facility, disability_rate, medications)
SELECT c.id, 'Anh Nam', NULL,
        'Viêm loét tá tràng HP dương tính',
        'BV Đại học Y Dược', NULL,
        '["Esomeprazole"]'::jsonb
FROM claims c WHERE c.claim_number = 'CLM-2026-003' ON CONFLICT DO NOTHING;

-- ============================================================
-- 4) AUDIO RECORDINGS  (one per sidebar item)
-- ============================================================
INSERT INTO audio_recordings (claim_id, user_id, file_path, file_name, duration_seconds, processing_status)
SELECT c.id, u.id, 'recordings/lan_injury.webm', 'lan_injury.webm', 312.00, 'done'
FROM claims c, users u
WHERE c.claim_number = 'CLM-2026-001' AND u.email = 'minh.nguyen@voice2claim.com'
ON CONFLICT DO NOTHING;

INSERT INTO audio_recordings (claim_id, user_id, file_path, file_name, duration_seconds, processing_status)
SELECT c.id, u.id, 'recordings/khoa_fire.webm', 'khoa_fire.webm', 245.00, 'done'
FROM claims c, users u
WHERE c.claim_number = 'CLM-2026-002' AND u.email = 'minh.nguyen@voice2claim.com'
ON CONFLICT DO NOTHING;

INSERT INTO audio_recordings (claim_id, user_id, file_path, file_name, duration_seconds, processing_status)
SELECT c.id, u.id, 'recordings/nam_gastro.webm', 'nam_gastro.webm', 390.00, 'done'
FROM claims c, users u
WHERE c.claim_number = 'CLM-2026-003' AND u.email = 'minh.nguyen@voice2claim.com'
ON CONFLICT DO NOTHING;

INSERT INTO audio_recordings (claim_id, user_id, file_path, file_name, duration_seconds, processing_status)
SELECT c.id, u.id, 'recordings/saigon_collision.webm', 'saigon_collision.webm', 438.00, 'done'
FROM claims c, users u
WHERE c.claim_number = 'CLM-2026-004' AND u.email = 'minh.nguyen@voice2claim.com'
ON CONFLICT DO NOTHING;

INSERT INTO audio_recordings (claim_id, user_id, file_path, file_name, duration_seconds, processing_status)
SELECT c.id, u.id, 'recordings/conghoa_bike.webm', 'conghoa_bike.webm', 165.00, 'done'
FROM claims c, users u
WHERE c.claim_number = 'CLM-2026-005' AND u.email = 'minh.nguyen@voice2claim.com'
ON CONFLICT DO NOTHING;

-- ============================================================
-- 5) TRANSCRIPTS  (raw_text from sidebar snippets + template details)
-- ============================================================
INSERT INTO transcripts (audio_id, provider, raw_text, normalized_text, confidence_score)
SELECT ar.id, 'valsea',
       'Gãy kín xương cẳng chân phải, tỷ lệ thương tật 22 phần trăm. Bó bột đùi bàn 6 tuần, kê Celecoxib 200mg và Alpha Choay. Đứt dây chằng chéo trước độ 2.',
       'Gãy kín 1/3 giữa xương cẳng chân phải. Đứt dây chằng chéo trước độ 2. Tỷ lệ thương tật 22%.',
       0.92
FROM audio_recordings ar
WHERE ar.file_name = 'lan_injury.webm' ON CONFLICT DO NOTHING;

INSERT INTO transcripts (audio_id, provider, raw_text, normalized_text, confidence_score)
SELECT ar.id, 'valsea',
       'Bão số 5 tốc mái tôn 30 mét vuông, chập cháy tivi Sony 65 inch, hư bộ bàn ghế gỗ do mưa tạt. Ước tính 45.000.000 VNĐ.',
       'Bão số 5 tốc mái tôn 30m². Chập cháy tivi Sony 65 inch. Hư bộ bàn ghế gỗ. Ước tính 45.000.000 VNĐ.',
       0.88
FROM audio_recordings ar
WHERE ar.file_name = 'khoa_fire.webm' ON CONFLICT DO NOTHING;

INSERT INTO transcripts (audio_id, provider, raw_text, normalized_text, confidence_score)
SELECT ar.id, 'valsea',
       'Viêm loét tá tràng HP dương tính, kê Esomeprazole.',
       'Viêm loét tá tràng, HP dương tính. Kê Esomeprazole.',
       0.90
FROM audio_recordings ar
WHERE ar.file_name = 'nam_gastro.webm' ON CONFLICT DO NOTHING;

INSERT INTO transcripts (audio_id, provider, raw_text, normalized_text, confidence_score)
SELECT ar.id, 'valsea',
       'Ford Ranger bị xe SH tông từ phía sau đẩy vào xe buýt. Mazda CX-5 biển 51H-123.45 vỡ đèn pha, móp cản trước 30cm, rỉ dầu carter, trầy nắp capô 40cm. Ước tính 28.500.000 VNĐ.',
       'Va chạm liên hoàn: Ford Ranger, SH, xe buýt. Mazda CX-5 51H-123.45: vỡ đèn pha, móp cản, rỉ dầu, trầy capô. Ước tính 28.500.000 VNĐ.',
       0.86
FROM audio_recordings ar
WHERE ar.file_name = 'saigon_collision.webm' ON CONFLICT DO NOTHING;

INSERT INTO transcripts (audio_id, provider, raw_text, normalized_text, confidence_score)
SELECT ar.id, 'valsea',
       'Wave Alpha bị Toyota Vios 59A-987.65 đâm từ phía sau, vỡ yếm xe, gãy gương chiếu hậu bên trái. Nạn nhân anh Tuấn trầy xước tay, đau nhẹ đầu gối.',
       'Wave Alpha bị Toyota Vios 59A-987.65 đâm từ phía sau. Vỡ yếm, gãy gương trái. Nạn nhân anh Tuấn: trầy tay, đau đầu gối.',
       0.89
FROM audio_recordings ar
WHERE ar.file_name = 'conghoa_bike.webm' ON CONFLICT DO NOTHING;

-- ============================================================
-- 6) WORKFLOW ACTIONS  (a few suggested/completed actions)
-- ============================================================
-- Claim #1 (chị Lan, medical) -> send_email
INSERT INTO workflow_actions (claim_id, action_type_id, action_params, status, executed_at, result)
SELECT c.id, at.id,
       '{"to":"lan.patient@example.com","subject":"Kết quả giám định thương tật"}'::jsonb,
       'completed', '2026-07-18 11:30:00+07',
       '{"sent":true}'::jsonb
FROM claims c, action_types at
WHERE c.claim_number = 'CLM-2026-001' AND at.code = 'send_email'
ON CONFLICT DO NOTHING;

-- Claim #4 (va chạm liên hoàn, vehicle) -> dispatch_surveyor
INSERT INTO workflow_actions (claim_id, action_type_id, action_params, status, executed_at, result)
SELECT c.id, at.id,
       '{"location":"Ngã tư Nguyễn Văn Linh - Hoàng Diệu"}'::jsonb,
       'completed', '2026-07-17 16:10:00+07',
       '{"surveyor":"Trần Đức Long","eta_min":25}'::jsonb
FROM claims c, action_types at
WHERE c.claim_number = 'CLM-2026-004' AND at.code = 'dispatch_surveyor'
ON CONFLICT DO NOTHING;

-- Claim #5 (tai nạn xe máy, injury) -> make_call
INSERT INTO workflow_actions (claim_id, action_type_id, action_params, status, executed_at, result)
SELECT c.id, at.id,
       '{"to":"0909000000","note":"Liên hệ nạn nhân anh Tuấn"}'::jsonb,
       'pending', NULL, NULL
FROM claims c, action_types at
WHERE c.claim_number = 'CLM-2026-005' AND at.code = 'make_call'
ON CONFLICT DO NOTHING;

SELECT '✅ Seed data imported (5 claims, 2 vehicles, 2 medical, 5 audio recordings, 5 transcripts, 3 workflow actions)' AS status;