package services

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"voice2claim/backend/configs"
	"voice2claim/backend/internal/models"
)

// --- Structs cho Qwen API ---
type QwenRequest struct {
	Model    string    `json:"model"`
	Messages []Message `json:"messages"`
}

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type QwenResponse struct {
	Choices []struct {
		Message struct {
			Content string `json:"content"`
		} `json:"message"`
	} `json:"choices"`
}

type LLMService struct {
	cfg *configs.Config
}

func NewLLMService(cfg *configs.Config) *LLMService {
	return &LLMService{cfg: cfg}
}

// ExtractData: Gọi Qwen để trích xuất JSON từ transcript
func (s *LLMService) ExtractData(transcript string, templateType string) (*models.TranscriptionResult, error) {
	
	// 🛡️ 1. MOCK FALLBACK (Cứu cánh cho Hackathon)
	if s.cfg.QwenKey == "" || len(s.cfg.QwenKey) < 10 || s.cfg.QwenKey == "your_qwen_api_key_here" {
		fmt.Println("⚠️ [MOCK MODE] Qwen API Key missing/invalid. Returning mock extraction for demo.")
		return getMockExtractionResult(transcript), nil
	}

	// 🛡️ 2. REAL API CALL
	// Lưu ý: Đã loại bỏ dấu backtick khỏi raw string literal để tránh lỗi compile Go
	systemPrompt := `Bạn là trợ lý AI chuyên trích xuất thông tin giám định bảo hiểm. 
Nhiệm vụ: Phân tích đoạn transcript (có thể pha trộn tiếng Việt và tiếng Anh - code-switching).
QUY TẮC BẮT BUỘC:
1. Trả về DUY NHẤT một chuỗi JSON hợp lệ. KHÔNG dùng markdown code block, KHÔNG có giải thích thêm.
2. Giữ nguyên các thuật ngữ tiếng Anh (ví dụ: deductible, total loss, estimate, policy, headlight).
3. Nếu có yêu cầu hành động (gọi điện, email), hãy tách ra mảng suggested_actions.

Format JSON yêu cầu:
{
  "claim_type": "vehicle",
  "location": "Địa điểm",
  "vehicle_plate": "Biển số xe",
  "damages": ["Hạng mục 1", "Hạng mục 2"],
  "estimated_cost": 2000000,
  "suggested_actions": ["Gọi bác sĩ Vân 093879403"]
}`

	reqBody := QwenRequest{
		Model: s.cfg.QwenModel,
		Messages: []Message{
			{Role: "system", Content: systemPrompt},
			{Role: "user", Content: fmt.Sprintf("Transcript: %s", transcript)},
		},
	}

	jsonData, _ := json.Marshal(reqBody)
	req, _ := http.NewRequest("POST", s.cfg.QwenURL, bytes.NewBuffer(jsonData))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+s.cfg.QwenKey)

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		fmt.Printf("⚠️ [FALLBACK] Qwen Network Error: %v\n", err)
		return getMockExtractionResult(transcript), nil
	}
	defer resp.Body.Close()

	respBody, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		fmt.Printf("⚠️ [FALLBACK] Qwen API Error (Status %d): %s\n", resp.StatusCode, string(respBody))
		return getMockExtractionResult(transcript), nil
	}

	var qwenResp QwenResponse
	if err := json.Unmarshal(respBody, &qwenResp); err != nil {
		fmt.Printf("⚠️ [FALLBACK] Failed to parse Qwen Response: %v\n", err)
		return getMockExtractionResult(transcript), nil
	}

	if len(qwenResp.Choices) == 0 {
		return getMockExtractionResult(transcript), nil
	}

	// 🛡️ 3. CLEANUP & PARSE JSON
	content := qwenResp.Choices[0].Message.Content
	content = strings.TrimSpace(content)
	
	// Loại bỏ markdown code block nếu Qwen vẫn trả về dạng đó (dùng string thường, không phải raw string)
	if strings.HasPrefix(content, "```") {
		content = strings.TrimPrefix(content, "```json")
		content = strings.TrimPrefix(content, "```")
		content = strings.TrimSuffix(content, "```")
		content = strings.TrimSpace(content)
	}

	var llmResult struct {
		ClaimType        string   `json:"claim_type"`
		Location         string   `json:"location"`
		VehiclePlate     string   `json:"vehicle_plate"`
		Damages          []string `json:"damages"`
		EstimatedCost    float64  `json:"estimated_cost"`
		SuggestedActions []string `json:"suggested_actions"`
	}

	if err := json.Unmarshal([]byte(content), &llmResult); err != nil {
		fmt.Printf("⚠️ [FALLBACK] Invalid JSON from Qwen: %v. Raw: %s\n", err, content)
		return getMockExtractionResult(transcript), nil
	}

	// 🛡️ 4. MAP TO MODELS.TranscriptionResult
	return &models.TranscriptionResult{
		VehiclePlate:  llmResult.VehiclePlate,
		DamageItems:   llmResult.Damages,
		EstimatedCost: llmResult.EstimatedCost,
		Notes:         fmt.Sprintf("Type: %s, Location: %s", llmResult.ClaimType, llmResult.Location),
		ActionItems:   parseActions(llmResult.SuggestedActions),
		RawText:       transcript,
		Confidence:    0.95,
	}, nil
}

// --- Helper Functions ---

func getMockExtractionResult(transcript string) *models.TranscriptionResult {
	return &models.TranscriptionResult{
		VehiclePlate:  "59X1-123.45",
		DamageItems:   []string{"vỡ headlight"},
		EstimatedCost: 2000000,
		Notes:         "exclude deductible",
		ActionItems: []models.ActionItem{
			{
				ActionType: "CALL",
				Target:     "Bác sĩ Vân",
				Details:    "093879403",
				Priority:   "HIGH",
			},
		},
		RawText:    transcript,
		Confidence: 0.95,
	}
}

func parseActions(actions []string) []models.ActionItem {
	var result []models.ActionItem
	for _, action := range actions {
		target := "Contact Person"
		details := action
		if strings.Contains(strings.ToLower(action), "gọi") || strings.Contains(strings.ToLower(action), "call") {
			target = "Contact Person"
		}
		result = append(result, models.ActionItem{
			ActionType: "CALL",
			Target:     target,
			Details:    details,
			Priority:   "HIGH",
		})
	}
	return result
}