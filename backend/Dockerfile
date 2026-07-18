# ==========================================
# Stage 1: Builder
# ==========================================
FROM golang:1.25-alpine AS builder
WORKDIR /app

# Cài đặt git và các tool cần thiết
RUN apk add --no-cache git

# Copy go mod và download dependencies
COPY go.mod go.sum ./
RUN go mod tidy
RUN go mod download

# Copy toàn bộ source code
COPY . .

# 🛡️ BUILD PRODUCTION-READY:
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o voice2claim-backend ./cmd/server/main.go

# ==========================================
# Stage 2: Runner (Production Image)
# ==========================================
FROM alpine:latest

# Cài đặt CA certificates để gọi HTTPS API (VALSEA/Qwen) và timezone
RUN apk --no-cache add ca-certificates tzdata

WORKDIR /root/

# Copy binary đã được tối ưu từ stage builder
COPY --from=builder /app/voice2claim-backend .

EXPOSE 8086

# Chạy ứng dụng
CMD ["./voice2claim-backend"]
