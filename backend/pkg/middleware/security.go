package middleware

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/redis/go-redis/v9"
)

// --- CẤU HÌNH ---
var (
	AllowedDomains   = []string{"dathoc.net", "localhost", "127.0.0.1"}
	BlockedUserAgents = []string{
		"python-requests", "curl", "wget", "httpclient", "java/", 
		"scrapy", "bot", "spider", "crawl", "go-http-client", 
		"node-fetch", "axios", "headlesschrome", "webdriver", "playwright",
	}
	AllowedBrowsers = []string{"chrome", "firefox", "safari", "edg", "opera"}
)

// SessionData lưu trữ thông tin session trong Redis
type SessionData struct {
	SessionID    string    `json:"session_id"`
	Fingerprint  string    `json:"fingerprint"`
	IP           string    `json:"ip"`
	UserAgent    string    `json:"user_agent"`
	CreatedAt    time.Time `json:"created_at"`
	LastActivity time.Time `json:"last_activity"`
	RequestCount int       `json:"request_count"`
	MaxRequests  int       `json:"max_requests"`
}

// ==========================================
// 1. MIDDLEWARE: BẮT BUỘC HTTPS (Ngoại trừ Localhost)
// ==========================================
func EnforceHTTPSMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Kiểm tra nếu không phải HTTPS và không phải localhost
		isHTTPS := c.Request.TLS != nil || c.GetHeader("X-Forwarded-Proto") == "https"
		host := strings.Split(c.Request.Host, ":")[0]
		
		if !isHTTPS && host != "localhost" && host != "127.0.0.1" {
			// Redirect sang HTTPS
			c.Redirect(http.StatusMovedPermanently, "https://"+c.Request.Host+c.Request.URL.Path)
			c.Abort()
			return
		}
		c.Next()
	}
}

// ==========================================
// 2. MIDDLEWARE: CHẶN BOT, CURL, PLAYWRIGHT & KIỂM TRA ORIGIN
// ==========================================
func BrowserProtectionMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Chỉ áp dụng cho các route /api/
		if !strings.HasPrefix(c.Request.URL.Path, "/api/") {
			c.Next()
			return
		}

		ua := strings.ToLower(c.GetHeader("User-Agent"))
		
		// A. Chặn cứng các User-Agent của Bot/Tool
		for _, bot := range BlockedUserAgents {
			if strings.Contains(ua, bot) {
				c.AbortWithStatusJSON(http.StatusForbidden, gin.H{
					"error": map[string]string{
						"code":    "BOT_DETECTED",
						"message": "Access denied: Automated tool or bot detected",
					},
				})
				return
			}
		}

		// B. Kiểm tra Origin / Referer
		origin := c.GetHeader("Origin")
		referer := c.GetHeader("Referer")
		checkStr := strings.ToLower(origin + " " + referer)
		
		isValidRequest := false
		for _, domain := range AllowedDomains {
			if strings.Contains(checkStr, domain) {
				isValidRequest = true
				break
			}
		}

		// C. Ngoại lệ: Cho phép Dev mở trực tiếp URL trên trình duyệt thật để test (Origin/Referer rỗng)
		if !isValidRequest && origin == "" && referer == "" {
			for _, b := range AllowedBrowsers {
				if strings.Contains(ua, b) {
					isValidRequest = true
					break
				}
			}
		}

		if !isValidRequest {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{
				"error": map[string]string{
					"code":    "INVALID_ORIGIN",
					"message": "Forbidden: Request must originate from dathoc.net or localhost",
				},
			})
			return
		}

		c.Next()
	}
}

// ==========================================
// 3. MIDDLEWARE: VALIDATE SESSION TỪ REDIS
// ==========================================
func SessionValidationMiddleware(rdb *redis.Client) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Whitelist các endpoint không cần session (Public)
		publicPaths := []string{"/api/health", "/api/activate", "/api/claims/transcribe"} // Thêm transcribe nếu muốn public
		for _, path := range publicPaths {
			if c.Request.URL.Path == path || strings.HasPrefix(c.Request.URL.Path, path+"?") {
				c.Next()
				return
			}
		}

		// 1. Lấy session_id từ Cookie
		sessionID, err := c.Cookie("session_id")
		if err != nil || sessionID == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"error": map[string]string{
					"code":    "UNAUTHORIZED",
					"message": "Session required. Please activate session first.",
				},
			})
			return
		}

		// 2. Kiểm tra session trong Redis
		ctx := c.Request.Context()
		sessionJSON, err := rdb.Get(ctx, "session:"+sessionID).Result()
		if err == redis.Nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"error": map[string]string{
					"code":    "SESSION_EXPIRED",
					"message": "Session has expired. Please reactivate.",
				},
			})
			return
		} else if err != nil {
			c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{
				"error": map[string]string{
					"code":    "REDIS_ERROR",
					"message": "Internal server error",
				},
			})
			return
		}

		// 3. Parse và Validate dữ liệu session
		var session SessionData
		if err := json.Unmarshal([]byte(sessionJSON), &session); err != nil {
			rdb.Del(ctx, "session:"+sessionID)
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"error": map[string]string{
					"code":    "INVALID_SESSION",
					"message": "Corrupted session data",
				},
			})
			return
		}

		// 4. Kiểm tra Fingerprint & User-Agent (Chống session hijacking)
		clientFingerprint := c.GetHeader("X-Device-Fingerprint")
		if clientFingerprint != "" && clientFingerprint != session.Fingerprint {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{
				"error": map[string]string{
					"code":    "DEVICE_MISMATCH",
					"message": "Security violation: Device fingerprint mismatch",
				},
			})
			return
		}

		clientUA := c.GetHeader("User-Agent")
		if clientUA != session.UserAgent {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{
				"error": map[string]string{
					"code":    "UA_MISMATCH",
					"message": "Security violation: Browser mismatch",
				},
			})
			return
		}

		// 5. Rate limit per session
		if session.RequestCount >= session.MaxRequests {
			c.AbortWithStatusJSON(http.StatusTooManyRequests, gin.H{
				"error": map[string]string{
					"code":    "RATE_LIMITED",
					"message": "Too many requests from this session",
				},
			})
			return
		}

		// 6. Cập nhật session (tăng count, gia hạn TTL)
		session.RequestCount++
		session.LastActivity = time.Now()
		updatedJSON, _ := json.Marshal(session)
		rdb.Set(ctx, "session:"+sessionID, updatedJSON, 30*time.Minute) // Gia hạn 30 phút

		// Lưu session vào context để các handler phía sau có thể dùng
		c.Set("session", session)
		c.Next()
	}
}

// ==========================================
// HELPER: TẠO SESSION MỚI (Dùng cho endpoint /api/activate)
// ==========================================
func GenerateSessionToken() (string, error) {
	token := make([]byte, 32)
	_, err := rand.Read(token)
	if err != nil {
		return "", err
	}
	return hex.EncodeToString(token), nil
}