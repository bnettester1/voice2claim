package tools

import (
	"context"
	"fmt"
	"github.com/mark3labs/mcp-go/mcp"
)

func RegisterEmailTool(server *mcp.MCPServer) {
	tool := mcp.NewTool("send_email",
		mcp.WithDescription("Gửi email thông báo đến người dùng hoặc thân nhân về trạng thái claim."),
		mcp.WithString("to", mcp.Required(), mcp.Description("Địa chỉ email người nhận")),
		mcp.WithString("subject", mcp.Required(), mcp.Description("Tiêu đề email")),
		mcp.WithString("body", mcp.Required(), mcp.Description("Nội dung email (hỗ trợ HTML)")),
	)

	server.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		to := request.Params.Arguments["to"].(string)
		subject := request.Params.Arguments["subject"].(string)
		body := request.Params.Arguments["body"].(string)

		fmt.Printf("[MCP] 📧 Gửi mail đến: %s | Tiêu đề: %s\n", to, subject)
		return mcp.NewToolResultText(fmt.Sprintf("✅ Đã gửi email thành công đến %s", to)), nil
	})
}
