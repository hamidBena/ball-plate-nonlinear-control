package main

import (
	"context"
	"embed"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"golangext/internal/dashboard"
	"golangext/internal/feed"
	"golangext/internal/store"
)

//go:embed static/*
var embeddedStatic embed.FS

func main() {
	addr := flag.String("addr", ":8080", "HTTP listen address")
	serialPort := flag.String("serial-port", "COM5", "serial port to read ESP32 telemetry from")
	baudRate := flag.Int("baud", 115200, "serial baud rate")
	historySize := flag.Int("history", 600, "number of samples to keep in memory")
	flag.Parse()

	telemetryStore := store.New(*historySize)
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	go func() {
		if err := feed.RunSerial(ctx, *serialPort, *baudRate, telemetryStore); err != nil && ctx.Err() == nil {
			log.Printf("serial feed stopped: %v", err)
		}
	}()

	handler, err := dashboard.New(embeddedStatic, telemetryStore)
	if err != nil {
		log.Fatal(err)
	}

	server := &http.Server{
		Addr:         *addr,
		Handler:      handler,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	go func() {
		<-ctx.Done()
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutdownCancel()
		_ = server.Shutdown(shutdownCtx)
	}()

	log.Printf("dashboard listening on http://localhost%s", *addr)
	if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
