package handlers

import (
	"fmt"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"
	"voice2claim/backend/internal/models"
)

type ClaimDBHandler struct {
	DB *gorm.DB
}

func NewClaimDBHandler(db *gorm.DB) *ClaimDBHandler {
	return &ClaimDBHandler{DB: db}
}

// respondError: Helper trả về lỗi chuẩn theo yêu cầu Frontend
func respondError(c *gin.Context, statusCode int, code, message string) {
	c.JSON(statusCode, gin.H{
		"error": map[string]string{
			"code":    code,
			"message": message,
		},
	})
}

// mapClaimToCaseResponse: Chuyển đổi từ DB Model sang Frontend DTO
func mapClaimToCaseResponse(claim models.Claim) models.CaseResponse {
	// Tạo tiêu đề case từ biển số xe hoặc mã claim
	title := fmt.Sprintf("Hồ sơ %s", claim.ClaimNumber)
	if len(claim.Vehicles) > 0 && claim.Vehicles[0].LicensePlate != "" {
		title = fmt.Sprintf("Claim xe %s", claim.Vehicles[0].LicensePlate)
	}

	// Tổng hợp suggested_actions từ Entities (nếu có)
	actions := []string{}
	for _, entity := range claim.Entities {
		if entity.EntityType == "action_item" {
			// Giả sử data lưu dạng JSON đơn giản, ở đây ta mock hoặc parse nếu cần
			actions = append(actions, fmt.Sprintf("Action từ AI: %s", entity.SourceText))
		}
	}

	return models.CaseResponse{
		ID:        claim.ID.String(), // Opaque UUID string
		Title:     title,
		CreatedAt: claim.CreatedAt.UTC().Format(time.RFC3339), // ISO 8601 UTC
		Recordings: []models.Recording{
			{
				ID:           uuid.New().String(),
				FilePath:     "/uploads/synthesized_audio.wav", // Placeholder nếu DB chưa lưu path
				DurationSec:  0,
				Status:       "completed",
				TemplateType: "auto_claim",
				Transcript: &models.TranscriptDTO{
					RawText:          claim.IncidentDescription,
					Structured:       claim, // Trả về toàn bộ object claim đã structured
					SuggestedActions: actions,
					Confidence:       0.95,
					QualityScore:     0.90,
				},
			},
		},
		Images: []models.ImageDTO{}, // Chưa có tính năng ảnh, trả về mảng rỗng
	}
}

// POST /api/cases - Tạo hồ sơ giám định mới (Đổi route thành /cases cho khớp frontend nếu cần)
func (h *ClaimDBHandler) CreateClaim(c *gin.Context) {
	var req models.Claim
	if err := c.ShouldBindJSON(&req); err != nil {
		respondError(c, http.StatusBadRequest, "INVALID_INPUT", "Invalid request body format")
		return
	}

	req.ID = uuid.New()
	req.ClaimNumber = fmt.Sprintf("CLM-%d-%05d", time.Now().Year(), time.Now().UnixNano()%100000)
	req.CreatedAt = time.Now().UTC()

	if err := h.DB.Create(&req).Error; err != nil {
		respondError(c, http.StatusInternalServerError, "DB_ERROR", "Failed to create claim in database")
		return
	}

	// Trả về đúng định dạng Frontend cần
	response := mapClaimToCaseResponse(req)
	c.JSON(http.StatusCreated, response)
}

// GET /api/cases/:id - Lấy chi tiết 1 hồ sơ theo ID
func (h *ClaimDBHandler) GetClaim(c *gin.Context) {
	idStr := c.Param("id")
	id, err := uuid.Parse(idStr)
	if err != nil {
		respondError(c, http.StatusBadRequest, "INVALID_ID", "Invalid UUID format for case ID")
		return
	}

	var claim models.Claim
	err = h.DB.Preload("Vehicles").Preload("Medical").Preload("Entities").
		Where("id = ?", id).First(&claim).Error

	if err != nil {
		if err == gorm.ErrRecordNotFound {
			respondError(c, http.StatusNotFound, "NOT_FOUND", "Case not found")
		} else {
			respondError(c, http.StatusInternalServerError, "DB_ERROR", "Failed to fetch case from database")
		}
		return
	}

	response := mapClaimToCaseResponse(claim)
	c.JSON(http.StatusOK, response)
}

// GET /api/cases - Lấy danh sách claims (10 cái mới nhất)
func (h *ClaimDBHandler) GetClaims(c *gin.Context) {
	var claims []models.Claim

	err := h.DB.Preload("Vehicles").Preload("Medical").
		Order("created_at DESC").Limit(10).Find(&claims).Error

	if err != nil {
		respondError(c, http.StatusInternalServerError, "DB_ERROR", "Failed to fetch claims list")
		return
	}

	// Map toàn bộ danh sách sang DTO
	var responses []models.CaseResponse
	for _, claim := range claims {
		responses = append(responses, mapClaimToCaseResponse(claim))
	}

	c.JSON(http.StatusOK, gin.H{"data": responses})
}