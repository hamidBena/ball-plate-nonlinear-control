package feed

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"time"

	"github.com/tarm/serial"

	"golangext/internal/ingest"
	"golangext/internal/store"
)

func RunSerial(ctx context.Context, portName string, baudRate int, s *store.Store) error {
	backoff := 250 * time.Millisecond
	maxBackoff := 5 * time.Second

	for {
		if ctx.Err() != nil {
			return nil
		}

		port, err := serial.OpenPort(&serial.Config{Name: portName, Baud: baudRate, ReadTimeout: 500 * time.Millisecond})
		if err != nil {
			log.Printf("serial open failed for %s: %v", portName, err)
			select {
			case <-time.After(backoff):
				backoff *= 2
				if backoff > maxBackoff {
					backoff = maxBackoff
				}
			case <-ctx.Done():
				return nil
			}
			continue
		}

		backoff = 250 * time.Millisecond
		if err := readSerialLoop(ctx, port, portName, s); err != nil && !errors.Is(err, context.Canceled) {
			log.Printf("serial reader reset for %s: %v", portName, err)
			select {
			case <-time.After(backoff):
				backoff *= 2
				if backoff > maxBackoff {
					backoff = maxBackoff
				}
			case <-ctx.Done():
				return nil
			}
		}
	}
}

func readSerialLoop(ctx context.Context, port io.ReadWriteCloser, portName string, s *store.Store) error {
	defer port.Close()

	reader := bufio.NewReader(port)
	for {
		if ctx.Err() != nil {
			return context.Canceled
		}

		line, err := reader.ReadString('\n')
		if line != "" {
			if frame, ok := ingest.ParseLine(line, "serial:"+portName, time.Now()); ok {
				s.Update(frame)
			}
		}
		if err != nil {
			if errors.Is(err, io.EOF) {
				continue
			}
			return fmt.Errorf("read serial line: %w", err)
		}
	}
}
