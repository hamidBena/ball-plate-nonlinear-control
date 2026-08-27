package model

import "time"

type AxisState struct {
	Setpoint    float64 `json:"setpoint"`
	Measurement float64 `json:"measurement"`
	Error       float64 `json:"error"`
	Output      float64 `json:"output,omitempty"`
}

type TelemetryFrame struct {
	Timestamp  time.Time `json:"timestamp"`
	Source     string    `json:"source"`
	LoopTimeMS float64   `json:"loopTimeMs,omitempty"`
	AxisX      AxisState `json:"axisX"`
	AxisY      AxisState `json:"axisY"`
	Notes      string    `json:"notes,omitempty"`
}

type Snapshot struct {
	Latest    TelemetryFrame   `json:"latest"`
	History   []TelemetryFrame `json:"history"`
	UpdatedAt time.Time        `json:"updatedAt"`
	Samples   int              `json:"samples"`
	Source    string           `json:"source"`
}
