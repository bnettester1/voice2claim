// shared/circuit_breaker.go
package shared

import (
	"context"
	"time"

	"github.com/sony/gobreaker"
)

// NewCircuitBreaker tạo circuit breaker theo tên
func NewCircuitBreaker(name string) *gobreaker.CircuitBreaker {
	return gobreaker.NewCircuitBreaker(gobreaker.Settings{
		Name:        name,
		MaxRequests: 3,                // số request cho phép khi half-open
		Interval:    5 * time.Second,  // rolling window
		Timeout:     10 * time.Second, // thời gian chuyển từ open → half-open
		ReadyToTrip: func(counts gobreaker.Counts) bool {
			failureRatio := float64(counts.TotalFailures) / float64(counts.Requests)
			return counts.Requests >= 5 && failureRatio >= 0.6
		},
		OnStateChange: func(name string, from, to gobreaker.State) {
			// Dùng log.Printf thay vì Logger để tránh panic
			// hoặc kiểm tra Logger có sẵn không
			if Logger != nil {
				Logger.Warn("Circuit breaker state changed",
					"name", name,
					"from", from.String(),
					"to", to.String(),
				)
			}
		},
	})
}

// ExecuteWithCB thực thi hàm với circuit breaker + context
func ExecuteWithCB[T any](ctx context.Context, cb *gobreaker.CircuitBreaker, fn func() (T, error)) (T, error) {
	result, err := cb.Execute(func() (interface{}, error) {
		return fn()
	})
	if err != nil {
		var zero T
		return zero, err
	}

	// ✅ KIỂM TRA NẾU result LÀ nil TRƯỚC KHI ÉP TYPE
	if result == nil {
		var zero T
		return zero, nil
	}

	// ✅ ÉP TYPE AN TOÀN VỚI TYPE ASSERTION KÈM OK
	if typedResult, ok := result.(T); ok {
		return typedResult, nil
	}

	// ✅ Fallback: nếu type không khớp, trả về zero value
	var zero T
	return zero, nil
}
