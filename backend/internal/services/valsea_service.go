package services

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"voice2claim/backend/configs"
)

type ValseaResponse struct {
	Text       string  `json:"text"`
	Confidence float64 `json:"confidence"`
}

type ValseaService struct {
	cfg *configs.Config
}

func NewValseaService(cfg *configs.Config) *ValseaService {
	return &ValseaService{cfg: cfg}
}

func (s *ValseaService) TranscribeAudio(cfg *configs.Config, fileName string, fileBytes []byte) (*ValseaResponse, error) {
	// 🛡️ MOCK FALLBACK: Nếu không có key hoặc key sai
	if s.cfg.ValseaKey == "" || len(s.cfg.ValseaKey) < 10 {
		fmt.Println("⚠️ [MOCK] VALSEA API Key missing/invalid. Using mock data.")
		return &ValseaResponse{
			Text:       "Khách hàng claim xe máy biển số 59X1-123.45, vỡ headlight, estimate 2 triệu, exclude deductible. Gọi bác sĩ Vân 093879403.",
			Confidence: 0.95,
		}, nil
	}

	body := &bytes.Buffer{}
	writer := multipart.NewWriter(body)

	// 1. SỬA: Đổi tên field từ "audio" thành "file" (theo chuẩn Valsea/OpenAI)
	part, err := writer.CreateFormFile("file", fileName)
	if err != nil {
		return nil, fmt.Errorf("failed to create form file: %w", err)
	}
	
	_, err = part.Write(fileBytes)
	if err != nil {
		return nil, fmt.Errorf("failed to write file bytes: %w", err)
	}

	// 2. SỬA: Thêm 2 field BẮT BUỘC theo tài liệu Valsea API
	writer.WriteField("model", "valsea-transcribe")
	writer.WriteField("language", "vietnamese") // Có thể thay đổi nếu cần hỗ trợ đa ngôn ngữ

	// Đóng writer để hoàn tất việc ghi multipart boundary
	if err := writer.Close(); err != nil {
		return nil, fmt.Errorf("failed to close multipart writer: %w", err)
	}

	req, err := http.NewRequest("POST", s.cfg.ValseaURL, body)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", writer.FormDataContentType())
	req.Header.Set("Authorization", "Bearer "+s.cfg.ValseaKey)

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("http request failed: %w", err)
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}

	// 3. CẢI THIỆN: In ra lỗi thực tế thay vì chỉ fallback, giúp debug dễ hơn
	if resp.StatusCode != http.StatusOK {
		fmt.Printf("⚠️ [ERROR] VALSEA API failed with status %d: %s\n", resp.StatusCode, string(respBody))
		return nil, fmt.Errorf("valsea api error (status %d): %s", resp.StatusCode, string(respBody))
	}

	var result ValseaResponse
	if err := json.Unmarshal(respBody, &result); err != nil {
		return nil, fmt.Errorf("failed to unmarshal response: %w, body: %s", err, string(respBody))
	}

	return &result, nil
}