package shared

import (
	"context"
	"time"
)

type DLQMessage struct {
	Timestamp   time.Time `json:"ts"`
	Service     string    `json:"service"`
	Operation   string    `json:"op"`
	Error       string    `json:"error"`
	RetryCount  int       `json:"retry_count"`
	Payload     any       `json:"payload,omitempty"`
	Correlation string    `json:"correlation_id,omitempty"`
}

type DLQ struct {
	service string
}

func NewDLQ(mqttClient interface{}, service string) *DLQ {
	if Logger != nil {
		Logger.Warn("shared.NewDLQ is deprecated, use PublishToDLQ from dlq_rmq.go")
	}
	return &DLQ{service: service}
}

func (d *DLQ) Publish(ctx context.Context, op string, err error, payload any, corrID string, retryCount int) {
	if Logger != nil {
		Logger.Warn("dlq.go (MQTT) is deprecated, redirecting to dlq_rmq.go",
			"operation", op, "correlation", corrID)
	}
	if RMQ != nil && RMQ.IsReady() {
		_ = PublishToDLQ(ctx, op, err, payload, corrID, retryCount)
		return
	}
	if Logger != nil {
		Logger.Error("DLQ fallback: RabbitMQ not ready, message logged locally",
			"operation", op, "error", err, "correlation", corrID)
	}
}
