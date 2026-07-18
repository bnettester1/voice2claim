package shared

import (
	"context"
	"net/http"
)

// CorrelationMiddleware tự động sinh hoặc lấy Correlation ID từ request
func CorrelationMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		corrID := r.Header.Get("X-Correlation-ID")
		if corrID == "" {
			corrID = r.Header.Get("X-Request-ID")
		}
		if corrID == "" {
			corrID = GenerateID() // Dùng hàm sẵn có trong logger.go
		}

		// Đưa vào context để các hàm bên dưới tự lấy được
		ctx := WithCorrelationID(r.Context(), corrID)
		w.Header().Set("X-Correlation-ID", corrID) // Echo lại cho client
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// GetCorrelationIDOrGen lấy từ context, nếu không có thì sinh mới (dành cho background worker)
func GetCorrelationIDOrGen(ctx context.Context) string {
	if id := GetCorrelationIDFromContext(ctx); id != "" {
		return id
	}
	return GenerateID()
}
