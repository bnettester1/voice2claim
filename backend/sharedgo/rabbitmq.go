package shared

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"

	amqp "github.com/rabbitmq/amqp091-go"
)

var RMQ *RabbitMQManager

type RabbitMQManager struct {
	mu      sync.RWMutex
	conn    *amqp.Connection
	channel *amqp.Channel
	url     string
	isReady bool
}

// InitRabbitMQ khởi tạo connection & channel, tự động reconnect nếu mất kết nối
func InitRabbitMQ(ctx context.Context, url string) error {
	if RMQ != nil && RMQ.isReady {
		return nil
	}
	rmq := &RabbitMQManager{url: url}
	if err := rmq.connect(ctx); err != nil {
		return fmt.Errorf("failed to init RabbitMQ: %w", err)
	}
	RMQ = rmq
	go rmq.watchReconnect(ctx)
	return nil
}

func (r *RabbitMQManager) connect(ctx context.Context) error {
	conn, err := amqp.Dial(r.url)
	if err != nil {
		return err
	}
	ch, err := conn.Channel()
	if err != nil {
		conn.Close()
		return err
	}
	r.mu.Lock()
	r.conn = conn
	r.channel = ch
	r.isReady = true
	r.mu.Unlock()
	log.Println("✅ RabbitMQ connected & channel opened")
	return nil
}

// rabbitmq.go - Sửa hàm watchReconnect
func (r *RabbitMQManager) watchReconnect(ctx context.Context) {
	defer func() {
		// Đảm bảo đóng connection khi context hủy
		r.mu.Lock()
		if r.conn != nil {
			r.conn.Close()
		}
		r.mu.Unlock()
	}()

	for {
		r.mu.RLock()
		conn := r.conn
		r.mu.RUnlock()
		
		if conn == nil {
			time.Sleep(1 * time.Second) // Đợi khởi tạo xong
			continue
		}

		notifyClose := make(chan *amqp.Error, 1)
		conn.NotifyClose(notifyClose)

		select {
		case <-ctx.Done():
			return
		case err := <-notifyClose:
			if Logger != nil {
				Logger.Warn("RabbitMQ connection lost, reconnecting...", "error", err)
			}
			
			// Reset trạng thái
			r.mu.Lock()
			r.isReady = false
			r.channel = nil // Đóng channel cũ implicitly khi conn mất
			r.mu.Unlock()
			
			// Reconnect loop
			for {
				select {
				case <-ctx.Done(): return
				default:
					time.Sleep(5 * time.Second)
					if r.connect(ctx) == nil {
						break // Kết nối thành công, quay lại vòng ngoài đợi notifyClose mới
					}
				}
			}
		}
	}
}
func (r *RabbitMQManager) IsReady() bool {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.isReady
}

func (r *RabbitMQManager) Channel() (*amqp.Channel, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	if !r.isReady {
		return nil, fmt.Errorf("RabbitMQ not ready")
	}
	return r.channel, nil
}

// Publish helper an toàn theo context
func (r *RabbitMQManager) Publish(ctx context.Context, exchange, routingKey string, msg amqp.Publishing) error {
	ch, err := r.Channel()
	if err != nil {
		return err
	}
	return ch.PublishWithContext(ctx, exchange, routingKey, false, false, msg)
}
func (r *RabbitMQManager) Close() error {
	r.mu.Lock()
	defer r.mu.Unlock()
	
	if r.channel != nil {
		r.channel.Close()
		r.channel = nil
	}
	if r.conn != nil {
		err := r.conn.Close()
		r.conn = nil
		r.isReady = false
		return err
	}
	return nil
}