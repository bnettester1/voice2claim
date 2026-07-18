package shared

import (
	"context"
	"fmt"
	"log"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
)

// MessageHandler định nghĩa hàm xử lý message
type MessageHandler func(ctx context.Context, msg amqp.Delivery) error

// Consume khởi tạo consumer, tự động xử lý Ack/Nack/Retry/DLQ
func Consume(ctx context.Context, queueName string, handler MessageHandler, maxRetries int) error {
	if !RMQ.IsReady() {
		return fmt.Errorf("RabbitMQ not ready")
	}
	ch, err := RMQ.Channel()
	if err != nil {
		return err
	}

	// QoS: 1 message/unack per worker (fair dispatch)
	if err := ch.Qos(1, 0, false); err != nil {
		return err
	}

	msgs, err := ch.Consume(queueName, "", false, false, false, false, nil)
	if err != nil {
		return fmt.Errorf("failed to register consumer: %w", err)
	}

	log.Printf("✅ Start consuming queue: %s", queueName)

	for {
		select {
		case <-ctx.Done():
			log.Printf("🛑 Consumer stopped for queue: %s", queueName)
			return ctx.Err()
		case msg := <-msgs:
			go processMessage(ctx, queueName, msg, handler, maxRetries)
		}
	}
}

// processMessage xử lý ack/nack/retry/dlq tự động
func processMessage(ctx context.Context, queueName string, msg amqp.Delivery, handler MessageHandler, maxRetries int) {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("💥 Panic in consumer %s: %v", queueName, r)
			msg.Nack(false, false) // Không requeue, sẽ vào DLQ ở bước dưới nếu retry hết
		}
	}()

	// Lấy retry count từ headers
	retryCount := int32(0)
	if rc, ok := msg.Headers["retry_count"].(int32); ok {
		retryCount = rc
	}

	// Inject correlation ID vào context
	corrID := msg.CorrelationId
	if corrID == "" {
		corrID = msg.MessageId
	}
	ctx = WithCorrelationID(ctx, corrID)

	// Gọi handler nghiệp vụ
	if err := handler(ctx, msg); err != nil {
		log.Printf("❌ Handler failed %s (attempt %d): %v", msg.MessageId, retryCount, err)

		// 🔁 Retry nếu chưa đạt max
		if retryCount < int32(maxRetries) {
			nextRetry := retryCount + 1
			retryQueue := queueName + ".retry"
			if err := PublishRetry(ctx, retryQueue, msg.Body, int(nextRetry)); err != nil {
				log.Printf("⚠️ Failed to publish retry: %v", err)
			}
			msg.Nack(false, false) // Không requeue original, dùng delayed message mới
		} else {
			// 📥 Hết retry → Đẩy sang DLQ
			PublishToDLQ(ctx, "consume:"+queueName, err, msg.Body, corrID, int(retryCount))
			msg.Nack(false, false)
		}
		return
	}

	// ✅ Success → Acknowledge
	if ackErr := msg.Ack(false); ackErr != nil {
		log.Printf("⚠️ Failed to ack message %s: %v", msg.MessageId, ackErr)
	}
}

// RetryMiddleware wraps handler để check idempotency & retry logic
func RetryMiddleware(maxRetries int) func(MessageHandler) MessageHandler {
	return func(next MessageHandler) MessageHandler {
		return func(ctx context.Context, msg amqp.Delivery) error {
			// 1. Check Idempotency
			if key, ok := msg.Headers["idempotency_key"]; ok {
				if IdemStore != nil {
					isNew, err := IdemStore.SetIfAbsent(ctx, fmt.Sprintf("%v", key), 48*time.Hour)
					if err != nil {
						return fmt.Errorf("idempotency check failed: %w", err)
					}
					if !isNew {
						log.Printf("⏭️ Duplicate skipped: %v", key)
						return nil // Trả nil để Ack message cũ
					}
				}
			}
			// 2. Thực thi handler gốc
			return next(ctx, msg)
		}
	}
}