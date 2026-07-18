package tools

import (
	"context"
	"fmt"
	"github.com/mark3labs/mcp-go/mcp"
)

func RegisterVectorSearchTool(server *mcp.MCPServer) {
	tool := mcp.NewTool("search_relatives_vector",
		mcp.WithDescription("Tìm kiếm thân nhân hoặc hồ sơ liên quan dựa trên mô tả tự nhiên bằng Vector Search."),
		mcp.WithString("query", mcp.Required(), mcp.Description("Mô tả tìm kiếm (vd: 'người thân tên Nguyễn Văn A, xe biển số 59X1...')")),
		mcp.WithNumber("top_k", mcp.Description("Số lượng kết quả trả về tối đa"), mcp.DefaultNumber(3)),
	)

	server.AddTool(tool, func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
		query := request.Params.Arguments["query"].(string)
		topK := int(request.Params.Arguments["top_k"].(float64))

		fmt.Printf("[MCP] 🔍 Vector Search query: '%s' (top_k: %d)\n", query, topK)
		
		mockResults := fmt.Sprintf(`[
  {"name": "Nguyễn Văn B", "relation": "Anh trai", "phone": "0901112223", "similarity": 0.92},
  {"name": "Trần Thị C", "relation": "Vợ", "phone": "0912223334", "similarity": 0.85}
]`)
		return mcp.NewToolResultText(fmt.Sprintf("🔍 Tìm thấy %d kết quả phù hợp:\n%s", topK, mockResults)), nil
	})
}
