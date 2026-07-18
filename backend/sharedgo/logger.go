package shared

import (
	"context"
	"crypto/rand"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os" // Thêm import này
	"regexp"
	"strings"

	"golang.org/x/text/unicode/norm"
)

type contextKey string

const CorrelationIDKey contextKey = "correlation_id"

// Logger là global logger
var Logger *slog.Logger

func JoinStrings(ss []string, sep string) string {
	return strings.Join(ss, sep)
}

func init() {
	// SỬA: dùng os.Stdout thay vì nil
	Logger = slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))
}

// WithCorrelationID thêm correlation ID vào context
func WithCorrelationID(ctx context.Context, id string) context.Context {
	return context.WithValue(ctx, CorrelationIDKey, id)
}

// GetCorrelationID lấy ID từ context (hoặc rỗng)
func GetCorrelationIDFromContext(ctx context.Context) string {
	if id, ok := ctx.Value(CorrelationIDKey).(string); ok {
		return id
	}
	return ""
}

// Info, Error, ... hỗ trợ correlation ID tự động
func Info(msg string, args ...any) {
	Logger.Info(msg, args...)
}
func Warn(msg string, args ...any) {
	Logger.Warn(msg, args...)
}
func Debug(msg string, args ...any) {
	Logger.Debug(msg, args...)
}
func Error(msg string, args ...any) {
	Logger.Error(msg, args...)
}

// InfoCtx ghi log kèm correlation ID nếu có
func InfoCtx(ctx context.Context, msg string, args ...any) {
	corrID := GetCorrelationIDFromContext(ctx)
	if corrID != "" {
		args = append(args, "trace_id", corrID)
	}
	Logger.Info(msg, args...)
}

func ErrorCtx(ctx context.Context, msg string, args ...any) {
	corrID := GetCorrelationIDFromContext(ctx)
	if corrID != "" {
		args = append(args, "trace_id", corrID)
	}
	Logger.Error(msg, args...)
}

func GenerateID() string {
	b := make([]byte, 16)
	rand.Read(b)
	return fmt.Sprintf("%x", b)
}
func GetRealIP(r *http.Request) string {
	ip := r.Header.Get("X-Forwarded-For")
	if ip == "" {
		ip = r.Header.Get("X-Real-IP")
	}
	if ip == "" {
		ip, _, _ = net.SplitHostPort(r.RemoteAddr)
	}
	return ip
}
func GetCorrelationIDFromRequest(r *http.Request) string {
	if id := r.Header.Get("X-Correlation-ID"); id != "" {
		return id
	}
	return ""
}
func NormalizeTextVi(text string) string {
	// Bước 1: Chuẩn hóa Unicode
	text = norm.NFC.String(text)

	// Bước 2: Thay thế tất cả ký tự không phải chữ/số/khoảng trắng bằng khoảng trắng
	// \p{L} = any letter, \p{N} = any number
	text = regexp.MustCompile(`[^\p{L}\p{N}\s]`).ReplaceAllString(text, " ")

	// Bước 3: Loại bỏ khoảng trắng thừa
	text = strings.Join(strings.Fields(text), " ")

	// Bước 4: Lowercase
	return strings.ToLower(text)
}
func NormalizeText(text string) string {
	// Thay dấu câu bằng space
	reg := regexp.MustCompile(`[^\w\s]`)
	text = reg.ReplaceAllString(text, " ")

	// Rút gọn space thừa
	text = regexp.MustCompile(`\s+`).ReplaceAllString(text, " ")

	// Trim và lowercase
	return strings.ToLower(strings.TrimSpace(text))
}
func AllowMethods(methods ...string) func(http.HandlerFunc) http.HandlerFunc {
	allowed := make(map[string]bool)
	for _, m := range methods {
		allowed[strings.ToUpper(m)] = true
	}

	return func(handler http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			if !allowed[r.Method] {
				w.WriteHeader(http.StatusMethodNotAllowed)
				w.Write([]byte("405 Method Not Allowed"))
				return
			}
			handler(w, r)
		}
	}
}
func HandleDBError(ctx context.Context, operation string, err error, details ...interface{}) error {
	// Gộp các bước log + report + return
	fields := append(details, "operation", operation, "error", err)
	Logger.Error("DB operation failed", fields...)
	ReportError(ctx, operation+"_failed", err)
	return fmt.Errorf("%s failed: %w", operation, err)
}
