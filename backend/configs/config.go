package configs

import (
	"log"
	"os"
	"path/filepath"

	"github.com/joho/godotenv"
)

type Config struct {
	Port string

	// Database
	DBHost string
	DBUser string
	DBPass string
	DBName string
	DBPort string

	// VALSEA ASR
	ValseaURL string
	ValseaKey string

	RedisHost     string
	RedisPort     string
	RedisPassword string
	Environment   string

	// Qwen LLM
	QwenURL   string
	QwenKey   string
	QwenModel string
}

func LoadConfig() *Config {
	// 1. DEBUG: In ra thư mục hiện tại để biết Go đang tìm file .env ở đâu
	cwd, _ := os.Getwd()
	log.Printf("📂 [DEBUG] Đang chạy từ thư mục: %s", cwd)
	log.Printf("📂 [DEBUG] Đường dẫn dự kiến của file .env: %s", filepath.Join(cwd, ".env"))

	// 2. Tải file .env và BẮT LỖI rõ ràng (KHÔNG dùng _ nữa)
	err := godotenv.Load()
	if err != nil {
		log.Printf("⚠️ [LỖI] Không thể load file .env: %v", err)
		log.Println("💡 Kiểm tra lại: File .env có nằm ĐÚNG thư mục bạn chạy lệnh 'go run' không?")
	} else {
		log.Println("✅ [SUCCESS] Đã load file .env thành công!")
	}

	return &Config{
		Port:      getEnv("PORT", "8086"),
		DBHost:    getEnv("DB_POSTGRES_HOST", "localhost"),
		DBUser:    getEnv("DB_POSTGRES_USER", "postgres"),
		DBPass:    getEnv("DB_POSTGRES_PASS", ""),
		DBName:    getEnv("DB_POSTGRES_NAME", "voice2claim"),
		DBPort:    getEnv("DB_POSTGRES_PORT", "5432"),
		ValseaURL: getEnv("VALSEA_API_URL", "https://api.valsea.ai/v1/audio/transcriptions"),
		ValseaKey: getEnv("VALSEA_API_KEY", ""),
		QwenURL:   getEnv("QWEN_API_URL", "https://ws-e6tggsg2mpb6wdxx.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/chat/completions"),
		QwenKey:   getEnv("QWEN_API_KEY", ""),
		QwenModel: getEnv("QWEN_MODEL", "qwen-plus"),
		RedisHost:     getEnv("REDIS_HOST", "127.0.0.1"),
		RedisPort:     getEnv("REDIS_PORT", "6379"),
		RedisPassword: getEnv("REDIS_PASSWORD", ""),
		Environment:   getEnv("ENVIRONMENT", "development"),
	}
}

func getEnv(key, fallback string) string {
	if value, ok := os.LookupEnv(key); ok {
		// DEBUG: In ra xác nhận các key quan trọng đã được load (chỉ hiện 10 ký tự đầu để bảo mật)
		if key == "VALSEA_API_KEY" || key == "QWEN_API_KEY" {
			if len(value) > 10 {
				log.Printf("🔑 [DEBUG] %s đã được load: %s...", key, value[:10])
			} else {
				log.Printf("⚠️ [DEBUG] %s quá ngắn: '%s'", key, value)
			}
		}
		return value
	}
	return fallback
}

func Init() {
	cfg := LoadConfig()
	if cfg.ValseaKey == "" {
		log.Println("⚠️ WARNING: VALSEA_API_KEY is not set in .env")
	}
	if cfg.QwenKey == "" {
		log.Println("⚠️ WARNING: QWEN_API_KEY is not set in .env")
	}
}