package shared

import (
	"context"
	"os"
	"os/signal"
	"syscall"
	"time"
)

type ShutdownManager struct {
	handlers []func(context.Context) error
}

func NewShutdownManager() *ShutdownManager {
	return &ShutdownManager{}
}

func (sm *ShutdownManager) AddHandler(fn func(context.Context) error) {
	sm.handlers = append(sm.handlers, fn)
}

func (sm *ShutdownManager) Listen() {
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	<-sigCh
	// ✅ KIỂM TRA Logger có sẵn không để tránh panic
	if Logger != nil {
		Logger.Info("Shutdown signal received")
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	for _, fn := range sm.handlers {
		if err := fn(ctx); err != nil && Logger != nil {
			Logger.Error("Shutdown handler error", "error", err)
		}
	}

	if Logger != nil {
		Logger.Info("Shutdown complete")
	}
}
