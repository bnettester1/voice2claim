// sharedgo/metrics.go
package shared

import (
	"context"
	"encoding/json"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
	"github.com/shirou/gopsutil/v3/cpu"
	"github.com/shirou/gopsutil/v3/disk"
	"github.com/shirou/gopsutil/v3/mem"
)

var (
	metricsOnce         sync.Once
	RetryCount          *prometheus.CounterVec
	CircuitBreakerState *prometheus.GaugeVec
	ErrorCount          *prometheus.CounterVec
	Latency             *prometheus.HistogramVec
)

// initMetrics đảm bảo metrics chỉ được khởi tạo 1 lần
func initMetrics() {
	metricsOnce.Do(func() {
		RetryCount = promauto.NewCounterVec(prometheus.CounterOpts{
			Name: "dathoc_all_svc_retry_total",
			Help: "Total number of retries by operation",
		}, []string{"operation", "service"})

		CircuitBreakerState = promauto.NewGaugeVec(prometheus.GaugeOpts{
			Name: "dathoc_all_svc_circuit_breaker_state",
			Help: "1 = closed, 0 = open",
		}, []string{"service", "dependency"})

		ErrorCount = promauto.NewCounterVec(prometheus.CounterOpts{
			Name: "dathoc_all_svc_errors_total",
			Help: "Total errors by type",
		}, []string{"error_type", "service"})

		Latency = promauto.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "dathoc_all_svc_operation_duration_seconds",
			Help:    "Operation latency",
			Buckets: prometheus.DefBuckets,
		}, []string{"operation"})
	})
}

// Gọi initMetrics() ngay khi package được import (tùy chọn)
// Hoặc gọi thủ công trong main() trước khi dùng metrics
func init() {
	initMetrics()
}

func IncRetry(operation, service string) {
	RetryCount.WithLabelValues(operation, service).Inc()
}

func SetCircuitBreaker(service, dep string, isOpen bool) {
	val := 1.0
	if isOpen {
		val = 0.0
	}
	CircuitBreakerState.WithLabelValues(service, dep).Set(val)
}

func IncError(errType, service string) {
	ErrorCount.WithLabelValues(errType, service).Inc()
}

func ObserveLatency(operation string, duration float64) {
	Latency.WithLabelValues(operation).Observe(duration)
}

// SystemMetricsAlert gửi cảnh báo hệ thống mỗi 5 giây qua MQTT
func SystemMetricsAlert(ctx context.Context, serviceName string) {
	ticker := time.NewTicker(5 * time.Second)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			Info("Stopping system metrics alert")
			return
		case <-ticker.C:
			sendSystemMetrics(serviceName)
		}
	}
}

func sendSystemMetrics(serviceName string) {
	// CPU (%)
	cpuPerc, err := cpu.Percent(0, false)
	if err != nil {
		Warn("Failed to get CPU usage", "error", err)
		return
	}
	cpuUsage := 0.0
	if len(cpuPerc) > 0 {
		cpuUsage = cpuPerc[0]
	}
	// RAM (%)
	vmStat, err := mem.VirtualMemory()
	if err != nil {
		Warn("Failed to get memory usage", "error", err)
		return
	}
	ramUsage := vmStat.UsedPercent
	// Disk (%)
	diskStat, err := disk.Usage("/")
	if err != nil {
		Warn("Failed to get disk usage", "error", err)
		return
	}
	diskUsage := diskStat.UsedPercent

	// Tạo payload
	payload := map[string]interface{}{
		"service":      serviceName,
		"timestamp":    time.Now().UTC().Format(time.RFC3339),
		"cpu_percent":  cpuUsage,
		"ram_percent":  ramUsage,
		"disk_percent": diskUsage,
	}
	data, err := json.Marshal(payload)
	if err != nil {
		Warn("Failed to marshal system metrics", "error", err)
		return
	}
	if MQTT == nil {
		Warn("MQTT client not initialized, skipping system metrics")
		return
	}
	token := MQTT.Publish("codedebug/all", 0, false, data)
	if !token.WaitTimeout(2 * time.Second) {
		Warn("MQTT publish timeout for system metrics")
	} else if token.Error() != nil {
		Warn("Failed to publish system metrics to MQTT", "error", token.Error())
	}
}