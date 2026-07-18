package shared

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
)

// SetupDLX tạo Dead Letter Exchange & Queue
func SetupDLX(ctx context.Context) error {
	if !RMQ.IsReady() {
		return fmt.Errorf("RabbitMQ not ready")
	}
	ch, _ := RMQ.Channel()
	if err := ch.ExchangeDeclare("dlx", "direct", true, false, false, false, nil); err != nil {
		return err
	}
	if _, err := ch.QueueDeclare("dlq.all", true, false, false, false, nil); err != nil {
		return err
	}
	return ch.QueueBind("dlq.all", "dlq.all", "dlx", false, nil)
}

// PublishToDLQ đẩy message thất bại vào DL Queue
func PublishToDLQ(ctx context.Context, op string, err error, payload any, corrID string, retryCount int) error {
	if !RMQ.IsReady() {
		if Logger != nil {
			Logger.Warn("RabbitMQ not ready, DLQ message dropped (fallback to log)")
		}
		return nil
	}
	msg := DLQMessage{
		Timestamp:  time.Now(),
		Service:    GlobalConfig.Get().ServiceName,
		Operation:  op,
		Error:      err.Error(),
		RetryCount: retryCount,
		Payload:    payload,
		Correlation: corrID,
	}
	data, _ := json.Marshal(msg)

	return RMQ.Publish(ctx, "dlx", "dlq.all", amqp.Publishing{
		ContentType: "application/json",
		Body:        data,
		Timestamp:   time.Now(),
		Headers: amqp.Table{
			"retry_count":    retryCount,
			"original_error": err.Error(),
		},
		DeliveryMode: amqp.Persistent,
	})
}