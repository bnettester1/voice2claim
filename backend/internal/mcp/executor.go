package mcp

// ActionExecutor executes workflow actions via MCP tools
type ActionExecutor interface {
    Execute(action ActionStep, context map[string]interface{}) error
}

type ActionStep struct {
    Type      string 
    Status    string  // pending/running/done/failed
    Result    string 
    Timestamp string 
}
