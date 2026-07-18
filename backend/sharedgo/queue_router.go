// shared/queue_router.go
package shared

import (
	"context"
	"encoding/json" // ✅ Thêm
	"fmt"
	amqp "github.com/rabbitmq/amqp091-go" // ✅ Thêm
	"time"                                // ✅ Thêm
)

// MessageType định nghĩa loại message để routing
type MessageType string

const (
	MsgLog          MessageType = "log"          // → MQTT
	MsgAlert        MessageType = "alert"        // → MQTT
	MsgPresence     MessageType = "presence"     // → MQTT
	MsgNotification MessageType = "notification" // → MQTT
	MsgJob          MessageType = "job"          // → RabbitMQ
	MsgRetry        MessageType = "retry"        // → RabbitMQ
	MsgDLQ          MessageType = "dlq"          // → RabbitMQ
	MsgWorkflow     MessageType = "workflow"     // → RabbitMQ
	MsgAIPipeline   MessageType = "ai_pipeline"  // → RabbitMQ
	MsgETLPipeline  MessageType = "etl_pipeline" // → RabbitMQ
	MsgBatch        MessageType = "batch"        // → RabbitMQ
)

// PublishMessage: router tự động chọn protocol dựa trên message type
func PublishMessage(ctx context.Context, msgType MessageType, payload any, topicOrQueue string) error {
	switch msgType {
	// === MQTT: low-bandwidth, realtime, lossy-ok ===
	case MsgLog, MsgAlert, MsgPresence, MsgNotification:
		return publishToMQTT(ctx, msgType, payload, topicOrQueue)

	// === RabbitMQ: durable, ack, retry, workflow ===
	case MsgJob, MsgRetry, MsgDLQ, MsgWorkflow, MsgAIPipeline, MsgETLPipeline, MsgBatch:
		return publishToRabbitMQ(ctx, msgType, payload, topicOrQueue)

	default:
		return fmt.Errorf("unknown message type: %s", msgType)
	}
}

func publishToMQTT(ctx context.Context, msgType MessageType, payload any, topic string) error {
	if MQTT == nil || !MQTT.IsConnected() {
		if Logger != nil {
			Logger.Warn("MQTT not ready, message dropped", "type", msgType, "topic", topic)
		}
		return nil // MQTT là best-effort, không block app
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	qos := byte(1) // At-least-once cho alert/notification
	if msgType == MsgLog {
		qos = 0 // Fire-and-forget cho log
	}

	token := MQTT.Publish(topic, qos, false, data)
	if !token.WaitTimeout(2 * time.Second) {
		return fmt.Errorf("MQTT publish timeout")
	}
	return token.Error()
}

func publishToRabbitMQ(ctx context.Context, msgType MessageType, payload any, queueOrRoutingKey string) error {
	if !RMQ.IsReady() {
		return fmt.Errorf("RabbitMQ not ready, durable message cannot be sent")
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	// Default exchange + routing key = queue name (simple mode)
	return RMQ.Publish(ctx, "", queueOrRoutingKey, amqp.Publishing{
		ContentType:  "application/json",
		Body:         data,
		DeliveryMode: amqp.Persistent, // 💾 Durable
		Timestamp:    time.Now(),
		Headers: amqp.Table{
			"message_type": string(msgType),
			"service":      GlobalConfig.Get().ServiceName,
		},
	})
}
