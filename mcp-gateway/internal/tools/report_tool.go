package tools

import (
	"context"
	"fmt"
	"github.com/mark3labs/mcp-go/mcp"
)

func RegisterReportTool(server *mcp.MCPServer) {
	tool := mcp.NewTool("print_report",
		mcp.WithDescription("Tạo và in báo cáo chi tiết (PDF) cho một vụ việc/claim cụ thể."),
		mcp.WithString("claim_id", mcp.Required(), mcp.Description("ID của claim (UUID) cần in báo cáo")),
		mcp.WithString("format", mcp.Description("Định dạng báo cáo"), mcp.DefaultString("pdf")),
	)

	server.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		claimID := request.Params.Arguments["claim_id"].(string)
		format := request.Params.Arguments["format"].(string)

		fmt.Printf("[MCP] 🖨️ Đang tạo báo cáo cho Claim ID: %s (Định dạng: %s)\n", claimID, format)
		
		reportURL := fmt.Sprintf("https://storage.dathoc.net/reports/%s.%s", claimID, format)
		return mcp.NewToolResultText(fmt.Sprintf("🖨️ Báo cáo đã được tạo thành công!\n🔗 Tải xuống: %s", reportURL)), nil
	})
}
