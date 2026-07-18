package vad

// VoiceActivityDetection - pre-process audio to cut silence
// Reduces load on VALSEA ASR API
type VADProcessor struct {
    Threshold float64
}

func NewVADProcessor(threshold float64) *VADProcessor {
    return &VADProcessor{Threshold: threshold}
}
