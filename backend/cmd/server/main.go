package main

import (
	"context"
	"encoding/json" // ĐÃ THÊM
	"fmt"
	"log"
	"os"            // ĐÃ THÊM
	"time"

	"voice2claim/backend/api/v1/handlers"
	"voice2claim/backend/configs"
	"voice2claim/backend/pkg/database"
	"voice2claim/backend/pkg/middleware"

	"github.com/gin-gonic/gin"
	"github.com/redis/go-redis/v9"
)

var rdb *redis.Client

// Khởi tạo Redis
func initRedis(cfg *configs.Config) {
	rdb = redis.NewClient(&redis.Options{
		Addr:         fmt.Sprintf("%s:%s", cfg.RedisHost, cfg.RedisPort),
		Password:     cfg.RedisPassword,
		DB:           0,
		DialTimeout:  5 * time.Second,
		ReadTimeout:  3 * time.Second,
		WriteTimeout: 3 * time.Second,
		PoolSize:     10,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := rdb.Ping(ctx).Err(); err != nil {
		log.Fatalf("❌ Redis connection failed: %v", err)
	}
	log.Println("✅ Redis connected successfully")
}

// Endpoint để Frontend kích hoạt session
func activateSessionHandler(c *gin.Context) {
	var req struct {
		Fingerprint string `json:"fingerprint"`
	}
	if err := c.ShouldBindJSON(&req); err != nil || req.Fingerprint == "" {
		c.JSON(400, gin.H{"error": map[string]string{"code": "INVALID_INPUT", "message": "Fingerprint is required"}})
		return
	}

	sessionID, err := middleware.GenerateSessionToken()
	if err != nil {
		c.JSON(500, gin.H{"error": map[string]string{"code": "INTERNAL_ERROR", "message": "Failed to generate session"}})
		return
	}

	session := middleware.SessionData{
		SessionID:    sessionID,
		Fingerprint:  req.Fingerprint,
		IP:           c.ClientIP(),
		UserAgent:    c.GetHeader("User-Agent"),
		CreatedAt:    time.Now(),
		LastActivity: time.Now(),
		RequestCount: 0,
		MaxRequests:  100,
	}

	// json.Marshal giờ đã hoạt động vì đã import "encoding/json"
	sessionJSON, _ := json.Marshal(session)
	ctx := c.Request.Context()
	
	if err := rdb.Set(ctx, "session:"+sessionID, sessionJSON, 30*time.Minute).Err(); err != nil {
		c.JSON(500, gin.H{"error": map[string]string{"code": "REDIS_ERROR", "message": "Failed to save session"}})
		return
	}

	// ĐÃ SỬA: Dùng os.Getenv thay vì biến cfg local để tránh lỗi "undefined: cfg"
	isProd := os.Getenv("ENVIRONMENT") == "production"
	c.SetCookie("session_id", sessionID, 1800, "/", "", isProd, true)

	c.JSON(200, gin.H{
		"status":     "success",
		"session_id": sessionID,
	})
}

func main() {
	cfg := configs.LoadConfig()
	db := database.Connect(cfg)
	initRedis(cfg)

	gin.SetMode(gin.ReleaseMode)
	r := gin.Default()

	// 1. Global CORS
	r.Use(func(c *gin.Context) {
		c.Writer.Header().Set("Access-Control-Allow-Origin", "https://dathoc.net")
		c.Writer.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		c.Writer.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization, Accept-Language, X-Device-Fingerprint")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(204)
			return
		}
		c.Next()
	})

	// 2. ÁP DỤNG CÁC MIDDLEWARE BẢO MẬT
	r.Use(middleware.EnforceHTTPSMiddleware())
	r.Use(middleware.BrowserProtectionMiddleware())

	aiHandler := handlers.NewHandler(cfg)
	aiHandler.InjectDB(db)
	dbHandler := handlers.NewClaimDBHandler(db)

	api := r.Group("/api")
	{
		// --- PUBLIC ENDPOINTS ---
		api.GET("/health", func(c *gin.Context) {
			c.JSON(200, gin.H{"status": "ok", "message": "Voice2Claim Backend is running"})
		})
		api.POST("/activate", activateSessionHandler)
		api.POST("/claims/transcribe", aiHandler.TranscribeAudio)

		// --- PROTECTED ENDPOINTS ---
		protected := api.Group("")
		protected.Use(middleware.SessionValidationMiddleware(rdb))
		{
			protected.POST("/claims/extract", aiHandler.ExtractData)
			protected.POST("/claims/process-voice", aiHandler.ProcessVoiceClaim)
			protected.POST("/claims", dbHandler.CreateClaim)
			protected.GET("/claims/:id", dbHandler.GetClaim)
			protected.GET("/claims", dbHandler.GetClaims)
		}
	}
	// Phục vụ file index.html khi truy cập vào đường dẫn gốc "/"
	r.Static("/", "./webclient")

	log.Printf("🚀 Server is running on port %s", cfg.Port)
	if err := r.Run(":" + cfg.Port); err != nil {
		log.Fatalf("❌ Failed to start server: %v", err)
	}
}
