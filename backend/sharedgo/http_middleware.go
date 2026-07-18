// http_middleware.go
// shared/http_middleware.go
package shared

import (
	"fmt"
	"net/http"
)

// ValidateRequestOrigin middleware kiểm tra origin/referer của request
func ValidateRequestOrigin(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		origin := GetEffectiveOrigin(r)
		referer := GetEffectiveReferer(r)
		ctx := r.Context()

		// 1. Ưu tiên validate Origin (cho CORS requests)
		if origin != "" {
			if !IsValidOrigin(origin) {
				HandleInvalidOrigin(w, r, origin)
				return
			}
			InfoCtx(ctx, "Validated via Origin", "origin", origin)
			next(w, r)
			return
		}

		// 2. Fallback sang Referer (cho non-CORS)
		if referer != "" {
			if !IsValidReferer(referer) {
				HandleInvalidReferer(w, r, referer)
				return
			}
			InfoCtx(ctx, "Validated via Referer", "referer", referer)
			next(w, r)
			return
		}

		// 3. Trường hợp không có Origin/Referer (có thể là bot)
		ip := GetRealIP(r)
		if !IsTrustedIP(ip) {
			InfoCtx(ctx, "Blocked missing origin/referer", "ip", ip)
			http.Error(w, "Missing security headers", http.StatusForbidden)
			return
		}

		next(w, r)
	}
}

// HandleInvalidOrigin xử lý khi phát hiện origin không hợp lệ
func HandleInvalidOrigin(w http.ResponseWriter, r *http.Request, origin string) {
	ip := GetRealIP(r)
	ctx := r.Context()

	// Gửi cảnh báo đến hệ thống monitoring
	ReportError(ctx, "invalid_origin",
		fmt.Errorf("blocked origin: %s from %s", origin, ip))

	// Trả về lỗi generic để tránh lộ thông tin
	http.Error(w, "Invalid request origin", http.StatusForbidden)

	// Tăng counter cho circuit breaker
	IncError("invalid_origin", GlobalConfig.Get().ServiceName)
}

// HandleInvalidReferer xử lý khi phát hiện referer không hợp lệ
func HandleInvalidReferer(w http.ResponseWriter, r *http.Request, referer string) {
	ip := GetRealIP(r)
	ctx := r.Context()

	// Gửi cảnh báo đến hệ thống monitoring
	ReportError(ctx, "invalid_referer",
		fmt.Errorf("blocked referer: %s from %s", referer, ip))

	// Trả về lỗi generic để tránh lộ thông tin
	http.Error(w, "Invalid request referer", http.StatusForbidden)

	// Tăng counter cho circuit breaker
	IncError("invalid_referer", GlobalConfig.Get().ServiceName)
}
