package shared

import (
	"context"
	"github.com/redis/go-redis/v9"
	"net/http"
	"time"
)

type IdempotencyStore interface {
	SetIfAbsent(ctx context.Context, key string, ttl time.Duration) (bool, error)
	Get(ctx context.Context, key string) (string, error)
}

type RedisIdempotencyStore struct {
	Client *redis.Client
}

func (s *RedisIdempotencyStore) SetIfAbsent(ctx context.Context, key string, ttl time.Duration) (bool, error) {
	return s.Client.SetNX(ctx, "idem:"+key, "processing", ttl).Result()
}

func (s *RedisIdempotencyStore) Get(ctx context.Context, key string) (string, error) {
	return s.Client.Get(ctx, "idem:"+key).Result()
}

var IdemStore IdempotencyStore

func IdempotencyMiddleware(store IdempotencyStore) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			key := r.Header.Get("Idempotency-Key")
			if key == "" {
				http.Error(w, "Idempotency-Key header required", http.StatusBadRequest)
				return
			}
			ok, err := store.SetIfAbsent(r.Context(), key, 24*time.Hour)
			if err != nil {
				http.Error(w, "Idempotency check failed", http.StatusBadGateway)
				return
			}
			if !ok {
				w.Header().Set("Idempotency-Key", key)
				w.WriteHeader(http.StatusOK)
				w.Write([]byte(`{"status":"already_processed"}`))
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

func CheckQueueIdempotency(ctx context.Context, key string) (bool, error) {
	if IdemStore == nil {
		return true, nil
	}
	return IdemStore.SetIfAbsent(ctx, key, 48*time.Hour)
}
