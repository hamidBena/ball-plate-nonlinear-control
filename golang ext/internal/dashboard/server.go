package dashboard

import (
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"strconv"
	"strings"
	"time"

	"golangext/internal/ingest"
	"golangext/internal/store"
)

type Server struct {
	store  *store.Store
	static http.Handler
}

func New(staticFS fs.FS, telemetryStore *store.Store) (http.Handler, error) {
	content, err := fs.Sub(staticFS, "static")
	if err != nil {
		return nil, err
	}

	srv := &Server{
		store:  telemetryStore,
		static: http.FileServer(http.FS(content)),
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", srv.healthz)
	mux.HandleFunc("/api/state", srv.state)
	mux.HandleFunc("/api/history", srv.history)
	mux.HandleFunc("/api/ingest", srv.ingest)
	mux.HandleFunc("/api/stream", srv.stream)
	mux.Handle("/", srv.static)
	return mux, nil
}

func (s *Server) healthz(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func (s *Server) state(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	limit := limitFromRequest(r, 240)
	writeJSON(w, s.store.Snapshot(limit))
}

func (s *Server) history(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	limit := limitFromRequest(r, 240)
	writeJSON(w, s.store.Snapshot(limit))
}

func (s *Server) ingest(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	defer r.Body.Close()

	body, err := io.ReadAll(io.LimitReader(r.Body, 64<<10))
	if err != nil {
		http.Error(w, "unable to read body", http.StatusBadRequest)
		return
	}
	frame, ok := ingest.ParseLine(string(body), "http", time.Now())
	if !ok {
		http.Error(w, "unsupported telemetry payload", http.StatusBadRequest)
		return
	}
	s.store.Update(frame)
	writeJSON(w, map[string]any{"accepted": true})
}

func (s *Server) stream(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming unsupported", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")

	updates, cancel := s.store.Subscribe()
	defer cancel()

	if err := writeEvent(w, "snapshot", s.store.Snapshot(240)); err != nil {
		return
	}
	flusher.Flush()

	heartbeat := time.NewTicker(20 * time.Second)
	defer heartbeat.Stop()

	for {
		select {
		case frame, ok := <-updates:
			if !ok {
				return
			}
			if err := writeEvent(w, "frame", frame); err != nil {
				return
			}
			flusher.Flush()
		case <-heartbeat.C:
			if _, err := fmt.Fprint(w, ": ping\n\n"); err != nil {
				return
			}
			flusher.Flush()
		case <-r.Context().Done():
			return
		}
	}
}

func writeJSON(w http.ResponseWriter, payload any) {
	w.Header().Set("Content-Type", "application/json")
	encoder := json.NewEncoder(w)
	encoder.SetIndent("", "  ")
	_ = encoder.Encode(payload)
}

func writeEvent(w io.Writer, name string, payload any) error {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	if _, err := fmt.Fprintf(w, "event: %s\ndata: %s\n\n", name, encoded); err != nil {
		return err
	}
	return nil
}

func limitFromRequest(r *http.Request, fallback int) int {
	limit := fallback
	if raw := strings.TrimSpace(r.URL.Query().Get("limit")); raw != "" {
		if parsed, err := strconv.Atoi(raw); err == nil && parsed > 0 {
			limit = parsed
		}
	}
	if limit > 1200 {
		limit = 1200
	}
	return limit
}
