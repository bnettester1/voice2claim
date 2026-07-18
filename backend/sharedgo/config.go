package shared

import (
	"errors"
	"log"
	"os"
	"strings"
	"sync"

	"github.com/go-playground/validator/v10"
	// "github.com/joho/godotenv"
)

type Config struct {
	RedisHost     string `validate:"required"`
	RedisPort     string `validate:"required"`
	RedisPassword string `validate:"required"`

	Keyw string `validate:"required"`

	Messenger string `validate:"required"`
	Streamer  string `validate:"required"`

	DBHost    string `validate:"required"`
	DBPort    string `validate:"required"`
	DBCertDir string `validate:"required"`

	DBUser string // optional
	DBName string // optional

	ServiceName                  string `validate:"required"`
	ServiceSecret                string
	DathocJWTSecret              string `validate:"required"`
	GoogleApplicationCredentials string // optional
	CloudProvider                string
	CORSAllowedOrigins           []string
}

var GlobalConfig = &SafeConfig{}

type SafeConfig struct {
	mu   sync.RWMutex
	data *Config
}

func (sc *SafeConfig) Get() Config {
	sc.mu.RLock()
	defer sc.mu.RUnlock()
	if sc.data == nil {
		return Config{}
	}
	return *sc.data
}

func (sc *SafeConfig) Set(cfg Config) error {
	if err := validateConfig(cfg); err != nil {
		return err
	}
	sc.mu.Lock()
	sc.data = &cfg
	sc.mu.Unlock()
	return nil
}

var validate = validator.New()

func validateConfig(cfg Config) error {
	if err := validate.Struct(cfg); err != nil {
		var errs validator.ValidationErrors
		if errors.As(err, &errs) {
			var errorMessages []string
			for _, e := range errs {
				errorMessages = append(errorMessages, "field '"+e.Field()+"' is "+e.Tag())
			}
			return errors.New("config validation failed: " + strings.Join(errorMessages, ", "))
		}
		return err
	}
	return nil
}

// LoadConfig tải cấu hình từ biến môi trường (không load .env file trong container)
func LoadConfig() {
	// Parse CORS từ env: "localhost,192.168.0.101, dathoc.net"
	corsRaw := getEnv("CORS", "")
	var corsList []string
	if corsRaw != "" {
		for _, origin := range strings.Split(corsRaw, ",") {
			origin = strings.TrimSpace(origin)
			if origin != "" {
				// Chuẩn hóa: thêm scheme nếu thiếu
				if !strings.HasPrefix(origin, "http://") && !strings.HasPrefix(origin, "https://") {
					origin = "http://" + origin
				}
				corsList = append(corsList, origin)
			}
		}
	}
	cfg := Config{
		RedisHost:     getEnv("REDIS_HOST", "localhost"),
		RedisPort:     getEnv("REDIS_PORT", "6379"),
		RedisPassword: getEnv("REDIS_PASSWORD", "123"),

		Keyw: getEnv("KEY_HOST", "192.168.1.20:8080"),

		Messenger: getEnv("MESSENGER", "tcp://messenger:1883"),
		Streamer:  getEnv("STREAMER", "tcp://messenger:8554"),

		DBHost:    getEnv("DB_HOST", "localhost"),
		DBPort:    getEnv("DB_PORT", "26257"),
		DBCertDir: getEnv("DB_CERTS_DIR", "/cockroach/certs"),

		DBUser: getEnv("DB_USER", "root"),
		DBName: getEnv("DB_NAME", "piodb"),

		ServiceName:                  getEnv("SERVICE_NAME", "unknown-service"),
		ServiceSecret:                getEnv("SERVICE_SECRET", ""),
		DathocJWTSecret:              getEnv("DATHOC_JWT_SECRET", ""),
		GoogleApplicationCredentials: getEnv("GOOGLE_APPLICATION_CREDENTIALS", ""),
		CORSAllowedOrigins:           corsList,
	}

	if err := GlobalConfig.Set(cfg); err != nil {
		log.Fatalf("❌ Fatal: %v", err)
	}

	log.Printf("✅ Config loaded for service: %s", cfg.ServiceName)
}

func getEnv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

// Helper để check nhanh trong middleware
func (c *Config) IsOriginAllowed(origin string) bool {
	if origin == "" {
		return false
	}
	// Cho phép tất cả trong dev (tuỳ policy)
	if c.ServiceName != "production" && len(c.CORSAllowedOrigins) == 0 {
		return true
	}
	for _, allowed := range c.CORSAllowedOrigins {
		if origin == allowed {
			return true
		}
	}
	return false
}
