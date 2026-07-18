// shared/retry.go
package shared

import (
	"context"
	"errors"
	"math/rand"
	"time"
)

// RetryOption định nghĩa cấu hình retry
type RetryOption struct {
	MaxRetries int
	BaseDelay  time.Duration
	MaxDelay   time.Duration
	Jitter     bool
}

// DefaultRetryOption — cấu hình mặc định
var DefaultRetryOption = RetryOption{
	MaxRetries: 3,
	BaseDelay:  100 * time.Millisecond,
	MaxDelay:   5 * time.Second,
	Jitter:     true,
}

// Retry thực thi hàm với retry exponential backoff
func Retry(ctx context.Context, fn func() error, opts RetryOption) error {
	var lastErr error
	for attempt := 0; attempt <= opts.MaxRetries; attempt++ {
		err := fn()
		if err == nil {
			return nil // thành công
		}

		lastErr = err

		// Không retry nếu context đã cancel
		if ctx.Err() != nil {
			return errors.Join(lastErr, ctx.Err())
		}

		// Lần cuối → không retry nữa
		if attempt == opts.MaxRetries {
			break
		}

		// Tính delay (exponential backoff)
		delay := opts.BaseDelay * time.Duration(1<<attempt)
		if delay > opts.MaxDelay {
			delay = opts.MaxDelay
		}

		// Thêm jitter (±10%)
		if opts.Jitter {
			jitter := time.Duration(rand.Float64() * 0.1 * float64(delay))
			delay += jitter
		}

		// Chờ trước khi retry
		select {
		case <-time.After(delay):
		case <-ctx.Done():
			return errors.Join(lastErr, ctx.Err())
		}
	}
	return lastErr
}

// RetryWithDurability: retry in-memory trước, nếu fail hoặc cần durable thì đẩy sang RabbitMQ
func RetryWithDurability(ctx context.Context, fn func() error, opts RetryOption, durable bool, queueName string) error {
	var lastErr error

	for attempt := 0; attempt <= opts.MaxRetries; attempt++ {
		err := fn()
		if err == nil {
			return nil
		}
		lastErr = err

		if ctx.Err() != nil {
			return errors.Join(lastErr, ctx.Err())
		}

		// Lần cuối + durable → push sang RabbitMQ để retry sau
		if attempt == opts.MaxRetries && durable && RMQ != nil && RMQ.IsReady() {
			return PublishRetry(ctx, queueName, map[string]any{
				"error":   err.Error(),
				"attempt": attempt,
				"payload": nil, // TODO: truyền payload từ caller nếu cần
			}, attempt)
		}

		// Không retry nữa nếu là lần cuối
		if attempt == opts.MaxRetries {
			break
		}

		// Exponential backoff + jitter (giữ nguyên logic cũ)
		delay := opts.BaseDelay * time.Duration(1<<attempt)
		if delay > opts.MaxDelay {
			delay = opts.MaxDelay
		}
		if opts.Jitter {
			jitter := time.Duration(rand.Float64() * 0.1 * float64(delay))
			delay += jitter
		}

		select {
		case <-time.After(delay):
		case <-ctx.Done():
			return errors.Join(lastErr, ctx.Err())
		}
	}
	return lastErr
}
