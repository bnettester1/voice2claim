package shared

import "context"

type FallbackOption struct {
	Primary    func() error
	Fallback   func() error
	IsCritical bool
}

func RunWithFallback(ctx context.Context, opt FallbackOption) error {
	err := opt.Primary()
	if err == nil {
		return nil
	}

	// ✅ KIỂM TRA Logger có sẵn không để tránh panic
	if Logger != nil {
		Logger.Warn("Primary failed, using fallback: %v", err)
	}

	fbErr := opt.Fallback()
	if fbErr != nil {
		if Logger != nil {
			Logger.Error("Fallback also failed: %v", fbErr)
		}
		return err
	}

	if opt.IsCritical {
		ReportError(ctx, "degraded_mode", err)
	}

	return nil
}
