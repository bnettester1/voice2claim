// shared/health.go
package shared

import (
	"net/http"
	"sync/atomic"
)

type HealthStatus int32

const (
	Healthy HealthStatus = iota
	Unhealthy
)

var globalHealth = Healthy

func SetHealth(status HealthStatus) {
	atomic.StoreInt32((*int32)(&globalHealth), int32(status))
}

func IsHealthy() bool {
	return atomic.LoadInt32((*int32)(&globalHealth)) == int32(Healthy)
}

// HTTP handler
func LivenessHandler(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("ok"))
}

func ReadinessHandler(w http.ResponseWriter, r *http.Request) {
	if IsHealthy() {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ready"))
	} else {
		w.WriteHeader(http.StatusServiceUnavailable)
		w.Write([]byte("not ready"))
	}
}
