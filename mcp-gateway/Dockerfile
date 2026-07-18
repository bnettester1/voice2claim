# ============================================
# Stage 1: Build
# ============================================
FROM golang:1.22-bookworm AS builder

WORKDIR /build

# Copy dependency files trước để tận dụng cache
COPY go.mod go.sum ./
RUN go mod download && go mod verify

# Copy source code
COPY . .

# Build binary với CGO disabled để chạy trên Alpine/Debian slim
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /mcp-gateway ./cmd/server/main.go

# ============================================
# Stage 2: Runtime (Debian Bookworm Slim)
# ============================================
FROM debian:bookworm-slim

# Cài đặt các package cần thiết (CA certs để gọi HTTPS, curl để healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Tạo user không phải root để bảo mật
RUN useradd -m -s /bin/bash mcpuser

WORKDIR /app

# Copy binary từ stage builder
COPY --from=builder /mcp-gateway .

# Copy file .env (nếu cần) - thực tế nên mount qua volume
# COPY .env.example .env

# Chuyển quyền sở hữu
RUN chown -R mcpuser:mcpuser /app
USER mcpuser

# Expose port
EXPOSE 8087

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8087/sse || exit 1

# Command mặc định
ENTRYPOINT ["./mcp-gateway"]