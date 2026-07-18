package normalizer

// Normalizer handles ITN (Inverse Text Normalization)
// - License plate: "năm một hát" → "51H"
// - Phone numbers, currency, percentages
// - Code-switching: "deductible" → "mức_khấu_trừ"
type Normalizer struct {
    DomainDict map[string]string
}
