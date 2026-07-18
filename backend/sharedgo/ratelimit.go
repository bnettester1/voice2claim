// sharedgo/ratelimit.go
package shared

import (
	"context"
	"net/http"

	"golang.org/x/time/rate"
)

// RateLimiter bao bọc rate.Limiter với context
type RateLimiter struct {
	limiter *rate.Limiter
}

// NewRateLimiter tạo rate limiter (r requests/sec, burst)
func NewRateLimiter(r rate.Limit, burst int) *RateLimiter {
	return &RateLimiter{
		limiter: rate.NewLimiter(r, burst),
	}
}

// WaitWithContext chờ đến khi được phép thực hiện
func (rl *RateLimiter) WaitWithContext(ctx context.Context) error {
	return rl.limiter.Wait(ctx)
}

// Allow kiểm tra nhanh (không chờ)
func (rl *RateLimiter) Allow() bool {
	return rl.limiter.Allow()
}

// Middleware trả về http.Handler wrapper để dùng trong chain
func (rl *RateLimiter) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := rl.limiter.Wait(r.Context()); err != nil {
			http.Error(w, "Rate limit exceeded", http.StatusTooManyRequests)
			IncError("rate_limit", GlobalConfig.Get().ServiceName)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// RateLimitMiddleware helper để tạo nhanh middleware
func RateLimitMiddleware(r rate.Limit, burst int) func(http.Handler) http.Handler {
	rl := NewRateLimiter(r, burst)
	return rl.Middleware
}
