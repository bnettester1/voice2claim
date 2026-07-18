package asr

// ASRService defines the interface for speech-to-text services
type ASRService interface {
    Transcribe(audio []byte) (*Transcript, error)
    TranscribeWithConfidence(audio []byte) (*TranscriptWithConfidence, error)
}

type Transcript struct {
    Text      string  
    Language  string  
    Duration  float64 
}

type TranscriptWithConfidence struct {
    Transcript
    Confidence float64 
    Segments   []Segment 
}

type Segment struct {
    Text       string  
    Start      float64 
    End        float64 
    Confidence float64 
}
