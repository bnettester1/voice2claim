package shared

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
)

// SetupRetryQueue tạo queue retry với TTL & DLX routing
func SetupRetryQueue(ctx context.Context, queueName string, retryDelay time.Duration) error {
	if !RMQ.IsReady() {
		return fmt.Errorf("RabbitMQ not ready")
	}
	ch, _ := RMQ.Channel()
	args := amqp.Table{
		"x-message-ttl":             int32(retryDelay.Milliseconds()),
		"x-dead-letter-exchange":    "dlx",
		"x-dead-letter-routing-key": "dlq.all",
	}
	_, err := ch.QueueDeclare(queueName, true, false, false, false, args)
	return err
}

// PublishRetry đẩy task cần retry lại sau delay
func PublishRetry(ctx context.Context, queueName string, payload any, retryCount int) error {
	if !RMQ.IsReady() {
		return fmt.Errorf("RabbitMQ not ready")
	}
	data, _ := json.Marshal(payload)
	return RMQ.Publish(ctx, "", queueName, amqp.Publishing{
		ContentType:  "application/json",
		Body:         data,
		DeliveryMode: amqp.Persistent,
		Headers: amqp.Table{
			"retry_count": retryCount,
		},
	})
}