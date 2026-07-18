<div align="center">

# 🎙️ Voice2Claim

### **Biến Giọng Nói Hiện Trường Thành Báo Cáo Giám Định Tự Động**

*Speech-to-Meaning, Not Speech-to-Text*

[![VAIC 2026](https://img.shields.io/badge/VAIC-2026-purple?style=for-the-badge)](https://valsea.ai)
[![VALSEA API](https://img.shields.io/badge/VALSEA-API-blue?style=for-the-badge)](https://valsea.ai)
[![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](LICENSE)
[![Status](https://img.shields.io/badge/status-Hackathon-orange?style=for-the-badge)]()

**🏆 Vietnam AI Innovation Challenge 2026 — Innovation Track**

</div>

---

## 📋 Mục Lục

- [Giới Thiệu](#-giới-thiệu)
- [Team Bookworm](#-team-bookworm)
- [Vấn Đề Giải Quyết](#-vấn-đề-giải-quyết)
- [Giải Pháp](#-giải-pháp)
- [Kiến Trúc Hệ Thống](#-kiến-trúc-hệ-thống)
- [Demo GUI](#-demo-gui)
- [Tính Năng Nổi Bật](#-tính-năng-nổi-bật)
- [Công Nghệ Sử Dụng](#-công-nghệ-sử-dụng)
- [Cài Đặt & Chạy Demo](#-cài-đặt--chạy-demo)
- [Roadmap](#-roadmap)
- [Đóng Góp](#-đóng-góp)
- [Liên Hệ](#-liên-hệ)

---

## 🌟 Giới Thiệu

**Voice2Claim** là hệ thống giám định thông minh sử dụng AI để biến **giọng nói hiện trường** (ồn ào, pha trộn tiếng Anh, nhiều giọng địa phương) thành **báo cáo có cấu trúc JSON**, tự động điền vào form và tạo action items — giúp **giảm 70% thời gian nhập liệu** cho giám định viên bảo hiểm.

> 💡 **Elevator Pitch:**  
> *"Thay vì đứng giữa đường ồn ào, vừa nghe khách hàng/garage nói chuyện pha tiếng Anh, vừa gõ vào app — giám định viên chỉ cần nói, hệ thống tự điền form và đề xuất hành động tiếp theo."*

---

## 👥 Team Bookworm

<div align="center">

![Team Bookworm](t.jpg)

**Team Bookworm — VAIC 2026**

*Một nhóm kỹ sư đam mê AI, chuyên xây dựng giải pháp thực tế cho vấn đề thực tế.*

</div>

| Vai trò | Thành viên | Chuyên môn |
|---------|-----------|------------|
| 🧠 AI/ML Engineer | [Tên] | ASR, NLP, LLM |
| 🎨 Frontend Developer | [Tên] | UI/UX, React/Vue |
| ⚙️ Backend Developer | [Tên] | API, Database |
| 📊 Data Engineer | [Tên] | Data Pipeline |

---

## 🎯 Vấn Đề Giải Quyết

### Bối Cảnh

Theo **Problem Brief từ VALSEA**, các hệ thống ASR hiện tại (Whisper, Google STT, Vietnamese cloud STT) gặp nhiều hạn chế khi xử lý tiếng Việt thực tế:

| Thách thức | Mô tả |
|------------|-------|
| 🗣️ **Giọng địa phương** | Bắc/Trung/Nam với accent khác nhau |
| 🔀 **Code-switching** | Pha trộn tiếng Anh trong câu tiếng Việt (VD: *"claim cái policy"*, *"total loss"*) |
| 📢 **Audio nhiễu** | Ghi âm hiện trường, cuộc gọi điện thoại, tiếng ồn nền |
| 📝 **Thuật ngữ chuyên ngành** | Jargon của bảo hiểm, y tế, kỹ thuật |

### Nỗi Đau Của Giám Định Viên
Hiện trường tai nạn → Ồn ào, căng thẳng
↓
Nghe khách hàng/garage nói (pha tiếng Anh)
↓
Vừa nghe vừa gõ vào app → CHẬM, SAI SÓT
↓
Tắc nghẽn quy trình bồi thường


**Kết quả:** 
- ⏱️ Mất 15-20 phút để nhập liệu thủ công cho 1 claim
- ❌ Sai sót dữ liệu → vi phạm compliance
- 😫 Giám định viên mệt mỏi, giảm năng suất

---

## 💡 Giải Pháp

### Chuyển đổi từ "Voice → Manual Typing → Form" sang "Voice → Structured JSON → Auto-fill Form & Trigger Next Step"
                 🎤 Audio hiện trường
      (ồn, giọng vùng miền, code-switching)
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 1: VALSEA ASR (Mandatory)                          │
│ • Chuyển speech → transcript                            │
│ • Giữ nguyên ngữ cảnh, từ địa phương, tiếng Anh         │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 2: Speech Understanding                           │
│ (VALSEA Semantic API + LLM)                             │
│                                                          │
│ • Intent Detection                                      │
│ • Entity Extraction                                     │
│ • Context Understanding                                 │
│ • Confidence Score                                      │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
                 Structured Claim JSON
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 3: AI Workflow Planner                            │
│                                                          │
│ AI Reasoning:                                            │
│ • Thiếu thông tin gì?                                   │
│ • Mức độ ưu tiên?                                       │
│ • Action nào thực hiện trước?                           │
│ • Action nào cần người xác nhận?                        │
│                                                          │
│ Output: Workflow Plan                                   │
└─────────────────────────┬────────────────────────────────┘
                          │
          ┌───────────────┼────────────────┐
          │               │                │
          ▼               ▼                ▼
   Auto-fill Form     Send Email      Dispatch Surveyor
          │               │                │
          └───────────────┼────────────────┘
                          ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 4: MCP Action Executor                            │
│                                                          │
│ • Mail MCP                                               │
│ • Phone MCP                                              │
│ • CRM MCP                                                │
│ • Report MCP                                             │
│ • Notification MCP                                       │
│                                                          │
│ Execute → Update Status → Audit Log                     │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 5: Voice2Claim Dashboard                          │
│                                                          │
│ ✓ Báo cáo đã điền tự động                               │
│ ✓ Timeline các Action                                   │
│ ✓ Pending / Running / Done                              │
│ ✓ Người dùng chỉ cần Review & Approve                   │
└──────────────────────────────────────────────────────────┘

---

## 🏗️ Kiến Trúc Hệ Thống

### 4-Layer Pipeline (Explainable AI)

```mermaid
graph TD
    A[🎤 Audio Input] --> B[Layer 1: VALSEA ASR]
    B --> C[Raw Transcript]
    C --> D[Layer 2: Semantic + LLM]
    D --> E[Entities + Intent]
    E --> F[Layer 3: Workflow Engine]
    F --> G[Structured JSON]
    G --> H[Layer 4: UI + Actions]
    H --> I[✅ Auto-filled Form]
    H --> J[🔔 Action Items]
    
    style B fill:#667eea,stroke:#764ba2,stroke-width:3px
    style D fill:#f093fb,stroke:#f5576c,stroke-width:3px
