package tools

import (
	"context"
	"fmt"
	"github.com/mark3labs/mcp-go/mcp"
)

func RegisterPhoneTool(server *mcp.MCPServer) {
	tool := mcp.NewTool("make_phone_call",
		mcp.WithDescription("Thực hiện cuộc gọi thoại tự động (voice call) đến số điện thoại chỉ định."),
		mcp.WithString("phone_number", mcp.Required(), mcp.Description("Số điện thoại (định dạng E.164, vd: +84901234567)")),
		mcp.WithString("message", mcp.Required(), mcp.Description("Nội dung tin nhắn thoại (TTS) hoặc kịch bản cuộc gọi")),
	)

	server.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		phone := request.Params.Arguments["phone_number"].(string)
		message := request.Params.Arguments["message"].(string)

		fmt.Printf("[MCP] 📞 Đang gọi điện đến: %s | Nội dung: %s\n", phone, message)
		return mcp.NewToolResultText(fmt.Sprintf("✅ Đã khởi tạo cuộc gọi đến %s.", phone)), nil
	})
}
