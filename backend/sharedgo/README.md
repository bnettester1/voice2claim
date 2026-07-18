## 📬 Message Routing Rules (Production)

### ✅ Dùng MQTT khi:
- [x] Log streaming (lossy-ok, low overhead)
- [x] Alert/Notification real-time (push mobile)
- [x] Online Presence (retain flag, lightweight)
- [x] Low-bandwidth telemetry (metrics, heartbeat)
- [x] Broadcast to many clients (pub/sub)

### ✅ Dùng RabbitMQ khi:
- [x] Job Queue (ack/nack, retry, durable)
- [x] Dead Letter Queue (must not lose failed tasks)
- [x] Retry with delay (TTL + DLX pattern)
- [x] Workflow/Orchestration (stateful, ordered)
- [x] AI/ETL Pipeline (large payload, batch)
- [x] Batch Processing (exactly-once semantics)
- [x] Any operation that cannot afford message loss

### 🔄 Dùng queue_router.go khi:
- Muốn code gọi chung 1 hàm `PublishMessage(ctx, MsgType, payload, topic)`
- Hệ thống tự động chọn protocol dựa trên `MessageType`

# 1. Xóa hoặc deprecate dlq.go (MQTT version)
mv shared/dlq.go shared/dlq_mqtt_deprecated.go

# 2. Thêm queue_router.go vào project
# 3. Update retry.go với hàm RetryWithDurability
# 4. Trong main.go, khởi tạo RMQ trước khi dùng:
ctx := context.Background()
LoadConfig()
InitRabbitMQ(ctx, "amqp://guest:guest@rabbitmq:5672/")
SetupDLX(ctx)
SetupRetryQueue(ctx, "auth.retry", 5*time.Second)

# 5. Dùng router cho các publish mới:
_ = PublishMessage(ctx, MsgAlert, alertPayload, "alert/auth")      // → MQTT
_ = PublishMessage(ctx, MsgJob, jobPayload, "job_queue")           // → RabbitMQ
_ = PublishMessage(ctx, MsgDLQ, dlqPayload, "dlq.all")             // → RabbitMQ


# 6. Test preflight CORS + correlation ID:
curl -X OPTIONS http://localhost:5000/api/test \
  -H "Origin: http://localhost:3000" \
  -H "X-Correlation-ID: test-123" \
  -v

----------------------------------
LƯU Ý

RealIP phải đầu tiên để lấy IP thật, RateLimit cuối cùng để không block middleware khác
WebSocket
Không áp dụng CORS/Idempotency middleware (chỉ dùng cho HTTP)

Idempotency-Key là bắt buộc khi dùng RabbitMQ retry/DLQ → luôn check Idempotency-Key hoặc correlation_id trước khi xử lý. Chỉ check cho method POST/PUT/DELETE, bỏ qua GET

RabbitMQ URL
Sửa rmqURL thành amqp://user:pass@rabbitmq:5672/ theo docker network của bạn

RabbitMQ DLX
Không cần plugin. Dùng x-dead-letter-exchange + x-dead-letter-routing-key là chuẩn công nghiệp.

Retry Queue
x-message-ttl chỉ delay message. Nếu muốn delay chính xác đến phút/giờ, cần plugin rabbitmq-delayed-message-exchange.

Graceful shutdown
Đóng RMQ.conn.Close() trước MQTT.Disconnect() để ưu tiên durable messages. Đóng RMQ.conn.Close() và MQTT.Disconnect() trong shutdown.go để flush buffer.

Monitor queue depth: Thêm metric rabbitmq_queue_messages_ready để alert khi queue bị tắc.
DLQ consumer: Nên có service riêng để xử lý dlq.all queue, tránh block main pipeline.