package shared

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"log" // Thêm import log để fallback
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
)

var MQTT mqtt.Client

type DebugLog struct {
	Timestamp   time.Time `json:"ts"`
	Service     string    `json:"service"`
	ClientID    string    `json:"client_id,omitempty"`
	User        string    `json:"user,omitempty"`
	Message     string    `json:"msg"`
	Error       string    `json:"error,omitempty"`
	Level       string    `json:"level"`
	Correlation string    `json:"trace_id,omitempty"`
}

func randomSuffix() string {
	b := make([]byte, 4)
	rand.Read(b)
	return fmt.Sprintf("%x", b)
}

func InitMQTTErrClient() {
	if MQTT != nil {
		return
	}
	cfg := GlobalConfig.Get()
	clientID := cfg.ServiceName + "-" + randomSuffix()

	opts := mqtt.NewClientOptions()
	opts.AddBroker(cfg.Messenger)
	opts.SetClientID(clientID)
	opts.SetConnectTimeout(5 * time.Second)
	opts.SetKeepAlive(10 * time.Second)
	opts.SetAutoReconnect(true)

	opts.SetOnConnectHandler(func(c mqtt.Client) {
		// Dùng log.Printf thay vì Logger.Info để tránh panic
		log.Printf("✅ MQTT client connected: %s", cfg.Messenger)
	})
	opts.SetConnectionLostHandler(func(c mqtt.Client, err error) {
		// Dùng log.Printf thay vì Logger.Warn để tránh panic
		log.Printf("⚠️ MQTT connection lost: %v", err)
	})

	MQTT = mqtt.NewClient(opts)

	// Gọi Connect nhưng không log lỗi bằng Logger để tránh panic
	token := MQTT.Connect()
	go func() {
		// Đợi kết nối trong goroutine để không block
		token.Wait()
		if token.Error() != nil {
			// Chỉ log đơn giản, không dùng Logger
			log.Printf("❌ MQTT initial connect failed: %v", token.Error())
		}
	}()
}

// ReportError gửi lỗi lên MQTT (dùng context để lấy correlation ID)
func ReportError(ctx context.Context, msg string, err error) {
	if MQTT == nil || !MQTT.IsConnected() {
		// Fallback log bằng log.Printf
		log.Printf("MQTT not ready, log locally: msg=%s, error=%v", msg, err)
		return
	}

	serviceName := "unknown-service"
	if cfg := GlobalConfig.Get(); cfg.ServiceName != "" {
		serviceName = cfg.ServiceName
	}

	logEntry := DebugLog{
		Timestamp:   time.Now(),
		Service:     serviceName,
		Message:     msg,
		Error:       err.Error(),
		Level:       "error",
		Correlation: GetCorrelationIDFromContext(ctx),
	}

	payload, _ := json.Marshal(logEntry)
	token := MQTT.Publish("dathocdebug/all", 0, false, payload)
	token.Wait()
}

// PublishLog gửi log có cấu trúc lên MQTT
func PublishLog(ctx context.Context, level, msg string, extra map[string]string) {
	// Luôn log local
	log.Printf("[%s] %s: %v", level, msg, extra)

	if MQTT == nil || !MQTT.IsConnected() {
		return
	}

	serviceName := "unknown-service"
	if cfg := GlobalConfig.Get(); cfg.ServiceName != "" {
		serviceName = cfg.ServiceName
	}

	entry := DebugLog{
		Timestamp:   time.Now(),
		Service:     serviceName,
		Message:     msg,
		Level:       level,
		Correlation: GetCorrelationIDFromContext(ctx),
	}

	if v, ok := extra["error"]; ok {
		entry.Error = v
	}
	if v, ok := extra["user"]; ok {
		entry.User = v
	}
	if v, ok := extra["client_id"]; ok {
		entry.ClientID = v
	}

	payload, err := json.Marshal(entry)
	if err != nil {
		log.Printf("Failed to marshal log: %v", err)
		return
	}

	MQTT.Publish("dathocdebug/all", 0, false, payload)
}
