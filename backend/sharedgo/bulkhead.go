// shared/bulkhead.go
package shared

import (
	"context"
)

// Bulkhead limits goroutine
type Bulkhead struct {
	sem chan struct{}
}

// NewBulkhead with maxWorkers
func NewBulkhead(maxWorkers int) *Bulkhead {
	return &Bulkhead{
		sem: make(chan struct{}, maxWorkers),
	}
}

// Do executes a task within the concurrency limit
func (b *Bulkhead) Do(ctx context.Context, task func()) error {
	select {
	case b.sem <- struct{}{}:
		defer func() { <-b.sem }()
		task()
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

// DoWithResult executes a task with return value within the concurrency limit
// This is a standalone function (not a method) because Go doesn't allow generic methods
func DoWithResult[T any](b *Bulkhead, ctx context.Context, task func() (T, error)) (T, error) {
	var result T
	err := b.Do(ctx, func() {
		var innerErr error
		result, innerErr = task()
		if innerErr != nil {
			// Handle or log the error if needed
			if Logger != nil {
				Logger.Warn("Bulkhead task failed", "error", innerErr)
			}
		}
	})
	return result, err
}

// WaitAll no block, or WaitGroup
