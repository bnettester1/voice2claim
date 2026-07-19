"""Seed workflow_defs — WF1 mở hợp đồng (S3). WF2 claim nối E10 vào ở S4."""
from __future__ import annotations

from app.db.dal import workflow as dal_wf
from app.workflow.defs import validate_graph

WF_CONTRACT_OPEN = {
    "nodes": [
        {"id": "start", "type": "start", "label": "Tiếp nhận yêu cầu",
         "config": {"expects": ["ho_ten", "so_cccd", "email", "xe_khach",
                                "bien_so_xe"]}},
        {"id": "intake", "type": "collect_form", "label": "Hồ sơ khách + ảnh xe",
         "config": {"pack_id": "insurance_contract",
                    "fields": ["ho_ten", "so_cccd", "email", "xe_khach",
                               "bien_so_xe"]}},
        {"id": "lookup", "type": "crm_lookup", "label": "Đối chiếu CRM",
         "config": {"query_from": "fields.ho_ten",
                    "verify_from": "fields.so_cccd", "out": "customer"}},
        {"id": "assess", "type": "ai_assess", "label": "AI thẩm định rủi ro",
         "config": {"base": 20, "out": "assessment", "second_opinion": True,
                    "rules": [
                        {"when": {"path": "photos", "op": "not_exists"},
                         "score": 35, "reason": "Thiếu ảnh xe"},
                        {"when": {"path": "customer.claim.status",
                                  "op": "==", "value": "rejected"},
                         "score": 20, "reason": "Từng bị từ chối claim"},
                        {"when": {"path": "fields.xe_khach", "op": "contains",
                                  "value": "202"},
                         "score": -10, "reason": "Xe đời mới"},
                        {"when": {"path": "verified", "op": "==",
                                  "value": True},
                         "score": -10, "reason": "Danh tính khớp CCCD"}]}},
        {"id": "gate", "type": "branch", "label": "Ngưỡng rủi ro",
         "config": {"on": "assessment.risk_score"}},
        {"id": "manual", "type": "human_task", "label": "Thẩm định thủ công",
         "config": {"role": "tham_dinh_vien",
                    "title": "Thẩm định hồ sơ mở hợp đồng",
                    "decision": ["approve", "reject"],
                    "form": [{"name": "ghi_chu", "label": "Ghi chú thẩm định",
                              "type": "textarea"}],
                    "out": "underwriter"}},
        {"id": "gate2", "type": "branch", "label": "Kết quả thẩm định",
         "config": {"on": "underwriter.decision"}},
        {"id": "make_policy", "type": "update_record",
         "label": "Lập hợp đồng (chờ ký)",
         "config": {"entity": "policies", "insert_if_missing": True,
                    "set": {"status": "pending_sign"}}},
        {"id": "gen_contract", "type": "gen_pdf", "label": "Soạn hợp đồng PDF",
         "config": {"template": "contract_issue",
                    "pack_id": "insurance_contract", "doc_kind": "contract",
                    "out": "contract_doc"}},
        {"id": "mail_sign", "type": "send_email", "label": "Gửi link ký điện tử",
         "config": {"template_id": "esign_request", "to": "fields.email",
                    "attach": ["contract_doc"],
                    "links": [{"kind": "sign", "wait_node": "wait_sign"}]}},
        {"id": "wait_sign", "type": "wait_event", "label": "Chờ khách ký",
         "config": {"event": "esign.signed"}},
        {"id": "activate", "type": "update_record", "label": "Kích hoạt hợp đồng",
         "config": {"entity": "policies", "set": {"status": "active"}}},
        {"id": "call_confirm", "type": "auto_call",
         "label": "Autocall chúc mừng khách",
         "config": {"mode": "replay", "listen_secs": 6, "say": [
             "Chào {name}, em gọi từ công ty bảo hiểm ạ. Hợp đồng {policy_no}"
             " của mình vừa được kích hoạt thành công sau khi anh chị ký điện"
             " tử. Email xác nhận kèm bản hợp đồng đã gửi tới hộp thư."
             " Em cảm ơn anh chị đã tin tưởng công ty ạ!"]}},
        {"id": "mail_ok", "type": "send_email",
         "label": "Email xác nhận + mời đánh giá",
         "config": {"template_id": "esign_confirmed", "to": "fields.email",
                    "attach": ["contract_doc"],
                    "links": [{"kind": "rate"}]}},
        {"id": "end_ok", "type": "end", "label": "Đã phát hành",
         "config": {"outcome": "issued"}},
        {"id": "mail_rej", "type": "send_email", "label": "Email từ chối",
         "config": {"template_id": "decision_result", "to": "fields.email"}},
        {"id": "end_rej", "type": "end", "label": "Từ chối",
         "config": {"outcome": "rejected"}},
    ],
    "edges": [
        {"from": "start", "to": "intake"},
        {"from": "intake", "to": "lookup"},
        {"from": "lookup", "to": "assess"},
        {"from": "assess", "to": "gate"},
        {"from": "gate", "to": "make_policy",
         "when": "assessment.risk_score < 50", "label": "Rủi ro thấp — tự duyệt"},
        {"from": "gate", "to": "manual", "else": True,
         "label": "Rủi ro cao — thẩm định"},
        {"from": "manual", "to": "gate2"},
        {"from": "gate2", "to": "make_policy",
         "when": "underwriter.decision == 'approve'", "label": "Duyệt"},
        {"from": "gate2", "to": "mail_rej", "else": True, "label": "Từ chối"},
        {"from": "make_policy", "to": "gen_contract"},
        {"from": "gen_contract", "to": "mail_sign"},
        {"from": "mail_sign", "to": "wait_sign"},
        {"from": "wait_sign", "to": "activate"},
        {"from": "activate", "to": "call_confirm"},
        {"from": "call_confirm", "to": "mail_ok"},
        {"from": "mail_ok", "to": "end_ok"},
        {"from": "mail_rej", "to": "end_rej"},
    ],
}

WF_CLAIM = {
    "nodes": [
        {"id": "start", "type": "start", "label": "Claim từ tổng đài",
         "config": {"expects": ["ho_ten", "vi_tri", "thoi_diem",
                                "mo_ta_thiet_hai"]}},
        {"id": "formcheck", "type": "collect_form",
         "label": "Kiểm tra phiếu tiếp nhận",
         "config": {"pack_id": "insurance_callcenter",
                    "fields": ["vi_tri", "thoi_diem", "mo_ta_thiet_hai"],
                    "mode": "task_if_missing", "role": "csr",
                    "title": "Gọi lại khách bổ sung thông tin claim"}},
        {"id": "create_claim", "type": "update_record", "label": "Mở hồ sơ claim",
         "config": {"entity": "claims", "insert_if_missing": True,
                    "claim_type": "car_accident",
                    "set": {"status": "investigating"}}},
        {"id": "severity", "type": "ai_assess", "label": "AI đánh giá mức độ",
         "config": {"base": 30, "out": "assessment", "second_opinion": True,
                    "rules": [
                        {"when": {"path": "fields.thuong_tich", "op": "exists"},
                         "score": 30, "reason": "Có thương tích"},
                        {"when": {"path": "fields.mo_ta_thiet_hai",
                                  "op": "contains", "value": "cháy"},
                         "score": 25, "reason": "Cháy / hư hỏng nặng"},
                        {"when": {"path": "fields.mo_ta_thiet_hai",
                                  "op": "contains", "value": "trầy"},
                         "score": -15, "reason": "Thiệt hại nhẹ (trầy xước)"}]}},
        {"id": "dispatch", "type": "human_task", "label": "Giám định hiện trường",
         "config": {"role": "tham_dinh_vien",
                    "title": "Đi hiện trường: chụp ảnh + ghi âm + ước tính",
                    "uploads": True,
                    "form": [{"name": "thiet_hai_uoc_tinh",
                              "label": "Thiệt hại ước tính (VNĐ)",
                              "type": "number"},
                             {"name": "ghi_chu", "label": "Ghi chú hiện trường",
                              "type": "textarea"}],
                    "out": "report"}},
        {"id": "transcribe", "type": "transcribe_media",
         "label": "AI bóc băng ghi âm",
         "config": {"media_from": "report.recording",
                    "pack_id": "insurance_callcenter",
                    "out": "report_transcript", "narrative": True}},
        {"id": "bienban", "type": "gen_pdf", "label": "Soạn biên bản giám định",
         "config": {"template": "claim_report",
                    "pack_id": "insurance_callcenter", "doc_kind": "bien_ban",
                    "extra_narrative_from": "report_transcript.narrative",
                    "out": "bien_ban_doc"}},
        {"id": "mail_cust", "type": "send_email", "label": "Báo khách: đã giám định",
         "config": {"template_id": "claim_update", "to": "customer.email",
                    "attach": ["bien_ban_doc"]}},
        {"id": "director", "type": "human_task", "label": "Giám đốc phê duyệt",
         "config": {"role": "giam_doc", "title": "Duyệt chi trả claim",
                    "decision": ["approve", "reject"],
                    "form": [{"name": "so_tien",
                              "label": "Số tiền chi trả (VNĐ)",
                              "type": "number"},
                             {"name": "ly_do", "label": "Lý do",
                              "type": "textarea"}],
                    "out": "director"}},
        {"id": "gate", "type": "branch", "label": "Quyết định",
         "config": {"on": "director.decision"}},
        {"id": "payout", "type": "update_record", "label": "Ghi nhận chi trả",
         "config": {"entity": "claims", "set": {"status": "paid"}}},
        {"id": "call_notify", "type": "auto_call",
         "label": "Autocall báo kết quả",
         "config": {"mode": "replay", "listen_secs": 6, "say": [
             "Chào {name}, em gọi từ công ty bảo hiểm ạ. Hồ sơ {ref} của mình"
             " đã được giám đốc phê duyệt chi trả {amount} đồng. Khoản tiền sẽ"
             " về tài khoản trong vòng 5 ngày làm việc. Biên bản giám định và"
             " email xác nhận đã gửi tới hộp thư của anh chị ạ."]}},
        {"id": "mail_paid", "type": "send_email",
         "label": "Email chi trả + mời đánh giá",
         "config": {"template_id": "decision_result", "to": "customer.email",
                    "links": [{"kind": "rate"}]}},
        {"id": "end_paid", "type": "end", "label": "Đã chi trả",
         "config": {"outcome": "paid"}},
        {"id": "reject_upd", "type": "update_record", "label": "Ghi nhận từ chối",
         "config": {"entity": "claims", "set": {"status": "rejected"}}},
        {"id": "mail_rej", "type": "send_email", "label": "Email từ chối + lý do",
         "config": {"template_id": "decision_result", "to": "customer.email",
                    "links": [{"kind": "rate"}]}},
        {"id": "end_rej", "type": "end", "label": "Từ chối",
         "config": {"outcome": "rejected"}},
    ],
    "edges": [
        {"from": "start", "to": "formcheck"},
        {"from": "formcheck", "to": "create_claim"},
        {"from": "create_claim", "to": "severity"},
        {"from": "severity", "to": "dispatch"},
        {"from": "dispatch", "to": "transcribe"},
        {"from": "transcribe", "to": "bienban"},
        {"from": "bienban", "to": "mail_cust"},
        {"from": "mail_cust", "to": "director"},
        {"from": "director", "to": "gate"},
        {"from": "gate", "to": "payout",
         "when": "director.decision == 'approve'", "label": "Duyệt chi trả"},
        {"from": "gate", "to": "reject_upd", "else": True, "label": "Từ chối"},
        {"from": "payout", "to": "call_notify"},
        {"from": "call_notify", "to": "mail_paid"},
        {"from": "mail_paid", "to": "end_paid"},
        {"from": "reject_upd", "to": "mail_rej"},
        {"from": "mail_rej", "to": "end_rej"},
    ],
}

_SEEDS = [
    ("wf_contract_open", "Mở hợp đồng bảo hiểm xe",
     "Intake khách (voice/text + ảnh xe) → AI thẩm định → hợp đồng PDF →"
     " ký điện tử qua email → kích hoạt + xác nhận.",
     WF_CONTRACT_OPEN,
     {"channel": "web", "form_type": "contract_intake", "icon": "📄",
      "keywords": ["mua bảo hiểm", "mở hợp đồng", "hợp đồng mới",
                   "đăng ký bảo hiểm"]}),
    ("wf_claim", "Xử lý claim tai nạn xe",
     "Cuộc gọi báo tai nạn (E10 tự điền form) → mở claim → thẩm định viên đi"
     " hiện trường (ảnh + ghi âm) → AI bóc băng, dựng biên bản → giám đốc"
     " duyệt → chi trả/từ chối + email.",
     WF_CLAIM,
     {"channel": "call", "intent": "new_claim", "icon": "🚗",
      "keywords": ["bị đâm xe", "tai nạn", "va chạm", "bồi thường",
                   "báo tai nạn"]}),
]


def seed_defs() -> None:
    """Idempotent: chưa có → insert v1 active; bản active vẫn là seed nhưng
    graph trong code đã đổi → tự nâng version mới + activate (không đụng
    bản do người dùng sửa tay — source='manual' giữ nguyên)."""
    import json as _json
    for key, name, desc, graph, trigger in _SEEDS:
        errors = validate_graph(graph)
        if errors:
            raise ValueError(f"seed {key} không hợp lệ: {errors}")
        cur = dal_wf.get_def_by_key(key)
        if cur is None:
            dal_wf.insert_def(key, name, graph, trigger, description=desc)
            continue
        same = _json.dumps(cur["graph"], sort_keys=True) == \
            _json.dumps(graph, sort_keys=True)
        if not same and cur.get("source") == "seed" \
                and cur.get("status") == "active":
            ver = dal_wf.next_version(key)
            dal_wf.insert_def(key, name, graph, trigger, description=desc,
                              version=ver, status="draft", source="seed",
                              note="seed nâng cấp (auto)")
            dal_wf.activate(key, ver)
