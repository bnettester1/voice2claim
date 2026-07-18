package main

import (
	"log"
	"net/http"

	"github.com/joho/godotenv"
	"github.com/mark3labs/mcp-go/server"
	"github.com/your-org/voice2claim-mcp/internal/tools"
)

func main() {
	if err := godotenv.Load(); err != nil {
		log.Println("⚠️ Không tìm thấy file .env, sử dụng cấu hình mặc định")
	}

	mcpServer := server.NewMCPServer(
		"Voice2Claim MCP Gateway",
		"1.0.0",
		server.WithResourceCapabilities(true, true),
		server.WithLogging(),
	)

	// Đăng ký các Tool
	tools.RegisterEmailTool(mcpServer)
	tools.RegisterPhoneTool(mcpServer)
	tools.RegisterVectorSearchTool(mcpServer)
	tools.RegisterReportTool(mcpServer)

	log.Println("✅ Đã đăng ký 4 tools thành công.")

	// Khởi chạy SSE Server
	sseServer := server.NewSSEServer(mcpServer, server.WithBaseURL("http://localhost:8087"))

	log.Println("🚀 MCP Gateway đang chạy trên port 8087...")
	log.Println("🔗 Endpoint SSE: http://localhost:8087/sse")
	log.Println("🔗 Endpoint Message: http://localhost:8087/message")

	if err := http.ListenAndServe(":8087", sseServer); err != nil {
		log.Fatalf("❌ Lỗi khởi động MCP Server: %v", err)
	}
}
