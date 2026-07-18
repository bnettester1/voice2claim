package valsea

// VALSEAClient implements ASRService using VALSEA ASR API
// Endpoint: POST /v1/asr/transcribe (MANDATORY per hackathon rules)
type VALSEAClient struct {
    APIKey  string
    BaseURL string
}

func NewVALSEAClient(apiKey, baseURL string) *VALSEAClient {
    return &VALSEAClient{APIKey: apiKey, BaseURL: baseURL}
}

func (c *VALSEAClient) Transcribe(audio []byte) (*Transcript, error) {
    // TODO: Implement VALSEA ASR API call
    return nil, nil
}
