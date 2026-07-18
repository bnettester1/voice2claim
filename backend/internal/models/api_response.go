package models

// APIError và ErrorResponse: Chuẩn hóa format lỗi theo yêu cầu Frontend
type APIError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type ErrorResponse struct {
	Error APIError `json:"error"`
}

// CaseResponse: Cấu trúc trả về cho Frontend
type CaseResponse struct {
	ID         string       `json:"id"`
	Title      string       `json:"title"`
	CreatedAt  string       `json:"created_at"` // ISO 8601 UTC
	Recordings []Recording  `json:"recordings"`
	Images     []ImageDTO   `json:"images"`
}

type Recording struct {
	ID           string          `json:"id"`
	FilePath     string          `json:"file_path"`
	DurationSec  int             `json:"duration_sec"`
	Status       string          `json:"status"`
	TemplateType string          `json:"template_type"`
	Error        string          `json:"error,omitempty"`
	Transcript   *TranscriptDTO  `json:"transcript,omitempty"`
}

type TranscriptDTO struct {
	RawText          string        `json:"raw_text"`
	Structured       interface{}   `json:"structured"`
	SuggestedActions []string      `json:"suggested_actions"`
	Confidence       float64       `json:"confidence"`
	QualityScore     float64       `json:"quality_score"`
}

type ImageDTO struct {
	ID          string        `json:"id"`
	FilePath    string        `json:"file_path"`
	Status      string        `json:"status"`
	Annotations []interface{} `json:"annotations"`
}

// ActionItem: Dùng cho SuggestedActions
type ActionItem struct {
	ActionType string `json:"action_type"`
	Target     string `json:"target"`
	Details    string `json:"details"`
	Priority   string `json:"priority"`
}

// TranscriptionResult: Kết quả trung gian từ LLM
type TranscriptionResult struct {
	VehiclePlate  string       `json:"vehicle_plate"`
	DamageItems   []string     `json:"damage_items"`
	EstimatedCost float64      `json:"estimated_cost"`
	Notes         string       `json:"notes"`
	ActionItems   []ActionItem `json:"action_items"`
	RawText       string       `json:"raw_text"`
	Confidence    float64      `json:"confidence"`
}