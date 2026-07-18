package semantic

// SpeechUnderstandingService extracts meaning from transcripts
type SpeechUnderstandingService interface {
    ExtractEntities(transcript string) (*ClaimEntities, error)
    DetectIntent(transcript string) (*Intent, error)
    Understand(transcript string) (*UnderstandingResult, error)
}

type ClaimEntities struct {
    VehicleModel   string   
    LicensePlate   string   
    Damages        []string 
    Location       string   
    EstimatedCost  float64  
    DisabilityRate float64  
}

type Intent struct {
    Name       string  
    Confidence float64 
}

type UnderstandingResult struct {
    Entities   ClaimEntities 
    Intent     Intent        
    Confidence float64       
}
