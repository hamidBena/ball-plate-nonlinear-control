package store

import (
	"sync"
	"time"

	"golangext/internal/model"
)

type Store struct {
	mu         sync.RWMutex
	history    []model.TelemetryFrame
	latest     model.TelemetryFrame
	updatedAt  time.Time
	maxHistory int
	source     string
	subs       map[chan model.TelemetryFrame]struct{}
}

func New(maxHistory int) *Store {
	if maxHistory < 1 {
		maxHistory = 1
	}
	return &Store{
		maxHistory: maxHistory,
		history:    make([]model.TelemetryFrame, 0, maxHistory),
		subs:       make(map[chan model.TelemetryFrame]struct{}),
	}
}

func (s *Store) Update(frame model.TelemetryFrame) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if frame.Timestamp.IsZero() {
		frame.Timestamp = time.Now().UTC()
	}
	s.latest = frame
	s.updatedAt = frame.Timestamp
	s.source = frame.Source
	s.history = append(s.history, frame)
	if len(s.history) > s.maxHistory {
		s.history = append([]model.TelemetryFrame(nil), s.history[len(s.history)-s.maxHistory:]...)
	}

	for ch := range s.subs {
		select {
		case ch <- frame:
		default:
		}
	}
}

func (s *Store) Snapshot(limit int) model.Snapshot {
	s.mu.RLock()
	defer s.mu.RUnlock()

	if limit <= 0 || limit > len(s.history) {
		limit = len(s.history)
	}

	history := make([]model.TelemetryFrame, limit)
	if limit > 0 {
		copy(history, s.history[len(s.history)-limit:])
	}

	return model.Snapshot{
		Latest:    s.latest,
		History:   history,
		UpdatedAt: s.updatedAt,
		Samples:   len(s.history),
		Source:    s.source,
	}
}

func (s *Store) Subscribe() (<-chan model.TelemetryFrame, func()) {
	ch := make(chan model.TelemetryFrame, 16)

	s.mu.Lock()
	s.subs[ch] = struct{}{}
	s.mu.Unlock()

	return ch, func() {
		s.mu.Lock()
		if _, ok := s.subs[ch]; ok {
			delete(s.subs, ch)
			close(ch)
		}
		s.mu.Unlock()
	}
}
