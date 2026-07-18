package handlers

import (
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"gorm.io/gorm"
	"voice2claim/backend/configs"
	"voice2claim/backend/internal/models"
	"voice2claim/backend/internal/services"
)

type Handler struct {
	cfg       *configs.Config
	valseaSvc *services.ValseaService
	llmSvc    *services.LLMService
	db        *gorm.DB
}

func NewHandler(cfg *configs.Config) *Handler {
	return &Handler{
		cfg:       cfg,
		valseaSvc: services.NewValseaService(cfg),
		llmSvc:    services.NewLLMService(cfg),
	}
}

func (h *Handler) InjectDB(db *gorm.DB) {
	h.db = db
}

func isValidAudioFile(filename string) bool {
	ext := strings.ToLower(filepath.Ext(filename))
	validExts := map[string]bool{".wav": true, ".mp3": true, ".m4a": true, ".ogg": true, ".flac": true, ".webm": true}
	return validExts[ext]
}

// TranscribeAudio
func (h *Handler) TranscribeAudio(c *gin.Context) {
	file, err := c.FormFile("audio")
	if err != nil {
		respondError(c, http.StatusBadRequest, "MISSING_AUDIO", "Audio file is required in 'audio' form field")
		return
	}

	if !isValidAudioFile(file.Filename) {
		respondError(c, http.StatusBadRequest, "INVALID_FILE_TYPE", "Uploaded file is not a valid audio format. Supported: .wav, .mp3, .m4a, .ogg, .flac, .webm")
		return
	}

	uploadDir := "./uploads"
	os.MkdirAll(uploadDir, os.ModePerm)
	fileName := fmt.Sprintf("%d_%s", time.Now().Unix(), file.Filename)
	filePath := filepath.Join(uploadDir, fileName)
	
	if err := c.SaveUploadedFile(file, filePath); err != nil {
		respondError(c, http.StatusInternalServerError, "SAVE_FAILED", "Failed to save uploaded file")
		return
	}

	fileBytes, _ := os.ReadFile(filePath)
	res, err := h.valseaSvc.TranscribeAudio(h.cfg, fileName, fileBytes)
	if err != nil {
		respondError(c, http.StatusInternalServerError, "ASR_FAILED", err.Error())
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"transcript": res.Text,
		"confidence": res.Confidence,
		"file_path":  filePath,
	})
}

// ExtractData
func (h *Handler) ExtractData(c *gin.Context) {
	var req struct {
		Transcript   string `json:"transcript" binding:"required"`
		TemplateType string `json:"template_type"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		respondError(c, http.StatusBadRequest, "INVALID_INPUT", "Transcript is required")
		return
	}
	res, err := h.llmSvc.ExtractData(req.Transcript, req.TemplateType)
	if err != nil {
		respondError(c, http.StatusInternalServerError, "LLM_FAILED", err.Error())
		return
	}
	c.JSON(http.StatusOK, res)
}

// ProcessVoiceClaim (All-in-One)
func (h *Handler) ProcessVoiceClaim(c *gin.Context) {
	if h.db == nil {
		respondError(c, http.StatusInternalServerError, "INTERNAL_ERROR", "Database not initialized")
		return
	}

	file, err := c.FormFile("audio")
	if err != nil {
		respondError(c, http.StatusBadRequest, "MISSING_AUDIO", "Audio file is required")
		return
	}

	if !isValidAudioFile(file.Filename) {
		respondError(c, http.StatusBadRequest, "INVALID_FILE_TYPE", "Uploaded file is not a valid audio format.")
		return
	}

	uploadDir := "./uploads"
	os.MkdirAll(uploadDir, os.ModePerm)
	fileName := fmt.Sprintf("%d_%s", time.Now().Unix(), file.Filename)
	filePath := filepath.Join(uploadDir, fileName)
	c.SaveUploadedFile(file, filePath)

	fileBytes, _ := os.ReadFile(filePath)
	templateType := c.PostForm("template_type")
	if templateType == "" { templateType = "auto_claim" }

	// 1. Transcribe
	valseaRes, err := h.valseaSvc.TranscribeAudio(h.cfg, fileName, fileBytes)
	if err != nil {
		respondError(c, http.StatusInternalServerError, "ASR_FAILED", err.Error())
		return
	}
	
	// 2. Extract
	llmRes, err := h.llmSvc.ExtractData(valseaRes.Text, templateType)
	if err != nil {
		respondError(c, http.StatusInternalServerError, "LLM_FAILED", err.Error())
		return
	}

	newClaim := models.Claim{
		ID:                  uuid.New(),
		ClaimNumber:         fmt.Sprintf("CLM-%d-%05d", time.Now().Year(), time.Now().UnixNano()%100000),
		IncidentDescription: llmRes.RawText,
		Status:              "pending",
		EstimatedCost:       llmRes.EstimatedCost,
		CreatedAt:           time.Now().UTC(),
	}

	if llmRes.VehiclePlate != "" {
		newClaim.Vehicles = []models.ClaimVehicle{{
			ID:                  uuid.New(),
			ClaimID:             newClaim.ID,
			LicensePlate:        llmRes.VehiclePlate,
			DamageDescription:   fmt.Sprintf("%v", llmRes.DamageItems),
			EstimatedRepairCost: llmRes.EstimatedCost,
		}}
	}

	if err := h.db.Create(&newClaim).Error; err != nil {
		respondError(c, http.StatusInternalServerError, "DB_ERROR", "Failed to save to DB")
		return
	}

	actions := []string{}
	for _, a := range llmRes.ActionItems {
		actions = append(actions, fmt.Sprintf("%s: %s (%s)", a.ActionType, a.Target, a.Details))
	}

	// 🌟 Map sang Frontend DTO (Sử dụng các struct đã định nghĩa trong api_response.go)
	response := models.CaseResponse{
		ID:        newClaim.ID.String(),
		Title:     fmt.Sprintf("Claim xe %s", llmRes.VehiclePlate),
		CreatedAt: newClaim.CreatedAt.Format(time.RFC3339),
		Recordings: []models.Recording{
			{
				ID:           uuid.New().String(),
				FilePath:     filePath,
				DurationSec:  0,
				Status:       "completed",
				TemplateType: templateType,
				Transcript: &models.TranscriptDTO{
					RawText:          llmRes.RawText,
					Structured:       llmRes,
					SuggestedActions: actions,
					Confidence:       llmRes.Confidence,
					QualityScore:     0.95,
				},
			},
		},
		Images: []models.ImageDTO{},
	}

	c.JSON(http.StatusOK, response)
}