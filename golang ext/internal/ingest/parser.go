package ingest

import (
	"encoding/json"
	"regexp"
	"strconv"
	"strings"
	"time"

	"golangext/internal/model"
)

var legacyPattern = regexp.MustCompile(`(?i)setpoints:\s*\(\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\)\s*\|\s*measurements:\s*\(\s*([-+0-9.eE]+)\s*,\s*([-+0-9.eE]+)\s*\)\s*\|\s*pidx:\s*([-+0-9.eE]+)\s*\|\s*pidy:\s*([-+0-9.eE]+)\s*$`)

type axisPayload struct {
	Setpoint    *float64 `json:"setpoint"`
	Measurement *float64 `json:"measurement"`
	Output      *float64 `json:"output"`
}

type framePayload struct {
	Timestamp  *time.Time   `json:"timestamp"`
	LoopTimeMS *float64     `json:"loopTimeMs"`
	AxisX      *axisPayload `json:"axisX"`
	AxisY      *axisPayload `json:"axisY"`
	SetpointX  *float64     `json:"setpointX"`
	SetpointY  *float64     `json:"setpointY"`
	MeasureX   *float64     `json:"measurementX"`
	MeasureY   *float64     `json:"measurementY"`
	OutputX    *float64     `json:"outputX"`
	OutputY    *float64     `json:"outputY"`
	Notes      string       `json:"notes"`
	Source     string       `json:"source"`
}

func ParseLine(raw string, source string, now time.Time) (model.TelemetryFrame, bool) {
	line := strings.TrimSpace(raw)
	if line == "" {
		return model.TelemetryFrame{}, false
	}

	if strings.HasPrefix(line, "{") {
		frame, ok := parseJSON(line, source, now)
		if ok {
			return frame, true
		}
	}

	if frame, ok := parseLegacy(line, source, now); ok {
		return frame, true
	}

	return model.TelemetryFrame{}, false
}

func parseJSON(raw string, source string, now time.Time) (model.TelemetryFrame, bool) {
	var payload framePayload
	if err := json.Unmarshal([]byte(raw), &payload); err != nil {
		return model.TelemetryFrame{}, false
	}

	frame := model.TelemetryFrame{Timestamp: now, Source: source, Notes: payload.Notes}
	if payload.Timestamp != nil {
		frame.Timestamp = payload.Timestamp.UTC()
	}
	if payload.LoopTimeMS != nil {
		frame.LoopTimeMS = *payload.LoopTimeMS
	}
	applyPayload(&frame.AxisX, payload.AxisX, payload.SetpointX, payload.MeasureX, payload.OutputX)
	applyPayload(&frame.AxisY, payload.AxisY, payload.SetpointY, payload.MeasureY, payload.OutputY)
	if payload.Source != "" {
		frame.Source = payload.Source
	}
	return finalizeFrame(frame), true
}

func parseLegacy(raw string, source string, now time.Time) (model.TelemetryFrame, bool) {
	matches := legacyPattern.FindStringSubmatch(raw)
	if len(matches) != 7 {
		return model.TelemetryFrame{}, false
	}

	setpointX, err := strconv.ParseFloat(matches[1], 64)
	if err != nil {
		return model.TelemetryFrame{}, false
	}
	setpointY, err := strconv.ParseFloat(matches[2], 64)
	if err != nil {
		return model.TelemetryFrame{}, false
	}
	measurementX, err := strconv.ParseFloat(matches[3], 64)
	if err != nil {
		return model.TelemetryFrame{}, false
	}
	measurementY, err := strconv.ParseFloat(matches[4], 64)
	if err != nil {
		return model.TelemetryFrame{}, false
	}
	outputX, err := strconv.ParseFloat(matches[5], 64)
	if err != nil {
		return model.TelemetryFrame{}, false
	}
	outputY, err := strconv.ParseFloat(matches[6], 64)
	if err != nil {
		return model.TelemetryFrame{}, false
	}

	frame := model.TelemetryFrame{
		Timestamp: now,
		Source:    source,
		AxisX: model.AxisState{
			Setpoint:    setpointX,
			Measurement: measurementX,
			Output:      outputX,
		},
		AxisY: model.AxisState{
			Setpoint:    setpointY,
			Measurement: measurementY,
			Output:      outputY,
		},
	}
	return finalizeFrame(frame), true
}

func applyPayload(axis *model.AxisState, payload *axisPayload, setpoint *float64, measurement *float64, output *float64) {
	if payload != nil {
		if payload.Setpoint != nil {
			axis.Setpoint = *payload.Setpoint
		}
		if payload.Measurement != nil {
			axis.Measurement = *payload.Measurement
		}
		if payload.Output != nil {
			axis.Output = *payload.Output
		}
	}
	if setpoint != nil {
		axis.Setpoint = *setpoint
	}
	if measurement != nil {
		axis.Measurement = *measurement
	}
	if output != nil {
		axis.Output = *output
	}
}

func finalizeFrame(frame model.TelemetryFrame) model.TelemetryFrame {
	frame.AxisX.Error = frame.AxisX.Setpoint - frame.AxisX.Measurement
	frame.AxisY.Error = frame.AxisY.Setpoint - frame.AxisY.Measurement
	return frame
}
