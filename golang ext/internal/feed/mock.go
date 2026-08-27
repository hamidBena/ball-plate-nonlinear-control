package feed

import (
	"context"
	"math"
	"time"

	"golangext/internal/model"
	"golangext/internal/store"
)

func RunMock(ctx context.Context, s *store.Store) {
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()

	start := time.Now()
	for {
		select {
		case now := <-ticker.C:
			elapsed := now.Sub(start).Seconds()
			setpointX := 130 + 25*math.Sin(elapsed*0.7)
			setpointY := 100 + 20*math.Cos(elapsed*0.5)
			measurementX := setpointX - 8*math.Sin(elapsed*1.4+0.5)
			measurementY := setpointY - 6*math.Cos(elapsed*1.1+0.2)
			s.Update(model.TelemetryFrame{
				Timestamp:  now.UTC(),
				Source:     "mock",
				LoopTimeMS: 10 + 2*math.Sin(elapsed*2),
				AxisX: model.AxisState{
					Setpoint:    setpointX,
					Measurement: measurementX,
					Output:      52 + 18*math.Sin(elapsed*1.9),
				},
				AxisY: model.AxisState{
					Setpoint:    setpointY,
					Measurement: measurementY,
					Output:      48 + 15*math.Cos(elapsed*1.3),
				},
				Notes: "mock telemetry",
			})
		case <-ctx.Done():
			return
		}
	}
}
