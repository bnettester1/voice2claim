package llm

// LLMClient uses OpenAI/Claude for post-processing
// Handles code-switching normalization and context correction
type LLMClient struct {
    Provider string
    APIKey   string
}
