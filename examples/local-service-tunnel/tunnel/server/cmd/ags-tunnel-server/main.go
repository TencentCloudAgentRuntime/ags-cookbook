package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto/sha1"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"math"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

const (
	opText   = 1
	opClose  = 8
	opPing   = 9
	opPong   = 10
	wsGUID   = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
	maxFrame = 64 * 1024 * 1024
)

var hopByHopHeaders = map[string]bool{
	"connection":          true,
	"keep-alive":          true,
	"proxy-authenticate":  true,
	"proxy-authorization": true,
	"te":                  true,
	"trailer":             true,
	"transfer-encoding":   true,
	"upgrade":             true,
}

type frame struct {
	Type    string            `json:"type"`
	ID      string            `json:"id,omitempty"`
	Method  string            `json:"method,omitempty"`
	Path    string            `json:"path,omitempty"`
	Headers map[string]string `json:"headers,omitempty"`
	BodyB64 string            `json:"body_b64,omitempty"`
	Status  int               `json:"status,omitempty"`
	Error   string            `json:"error,omitempty"`
}

type activeRequest struct {
	startCh chan frame
	bodyCh  chan []byte
	doneCh  chan error
}

type tunnelState struct {
	token          string
	requestTimeout time.Duration
	maxBodyBytes   int64

	mu       sync.Mutex
	client   *wsConn
	inflight map[string]*activeRequest
	nextID   uint64
}

func newTunnelState(token string, requestTimeout time.Duration, maxBodyBytes int64) *tunnelState {
	return &tunnelState{
		token:          token,
		requestTimeout: requestTimeout,
		maxBodyBytes:   maxBodyBytes,
		inflight:       make(map[string]*activeRequest),
	}
}

func (s *tunnelState) setClient(c *wsConn) {
	s.mu.Lock()
	old := s.client
	s.client = c
	s.mu.Unlock()
	if old != nil {
		_ = old.Close()
	}
}

func (s *tunnelState) clearClient(c *wsConn) {
	s.mu.Lock()
	if s.client == c {
		s.client = nil
		for id, ar := range s.inflight {
			delete(s.inflight, id)
			ar.doneCh <- errors.New("local tunnel client disconnected")
		}
	}
	s.mu.Unlock()
}

func (s *tunnelState) nextRequestID() string {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.nextID++
	return fmt.Sprintf("%d-%d", time.Now().UnixNano(), s.nextID)
}

func (s *tunnelState) sendRequest(req frame, ar *activeRequest) error {
	s.mu.Lock()
	c := s.client
	if c != nil {
		s.inflight[req.ID] = ar
	}
	s.mu.Unlock()
	if c == nil {
		return errors.New("local tunnel client is not connected")
	}
	if err := c.WriteJSON(req); err != nil {
		s.removeRequest(req.ID)
		return err
	}
	return nil
}

func (s *tunnelState) removeRequest(id string) {
	s.mu.Lock()
	delete(s.inflight, id)
	s.mu.Unlock()
}

func (s *tunnelState) deliver(resp frame) {
	s.mu.Lock()
	ar := s.inflight[resp.ID]
	s.mu.Unlock()
	if ar == nil {
		return
	}
	switch resp.Type {
	case "response_start":
		ar.startCh <- resp
	case "response_body":
		body, err := base64.StdEncoding.DecodeString(resp.BodyB64)
		if err != nil {
			ar.doneCh <- fmt.Errorf("invalid response body frame: %w", err)
			return
		}
		ar.bodyCh <- body
	case "response_end":
		ar.doneCh <- nil
	case "error":
		ar.doneCh <- errors.New(resp.Error)
	}
}

type wsConn struct {
	conn   net.Conn
	reader *bufio.Reader
	writeM sync.Mutex
}

func (c *wsConn) Close() error {
	return c.conn.Close()
}

func (c *wsConn) WriteJSON(v any) error {
	raw, err := json.Marshal(v)
	if err != nil {
		return err
	}
	return c.writeFrame(opText, raw)
}

func (c *wsConn) writeFrame(opcode byte, payload []byte) error {
	c.writeM.Lock()
	defer c.writeM.Unlock()
	header := []byte{0x80 | opcode}
	n := len(payload)
	switch {
	case n < 126:
		header = append(header, byte(n))
	case n <= math.MaxUint16:
		header = append(header, 126, byte(n>>8), byte(n))
	default:
		header = append(header, 127)
		var b [8]byte
		binary.BigEndian.PutUint64(b[:], uint64(n))
		header = append(header, b[:]...)
	}
	if _, err := c.conn.Write(header); err != nil {
		return err
	}
	_, err := c.conn.Write(payload)
	return err
}

func (c *wsConn) ReadFrame() (byte, []byte, error) {
	var header [2]byte
	if _, err := io.ReadFull(c.reader, header[:]); err != nil {
		return 0, nil, err
	}
	opcode := header[0] & 0x0f
	masked := header[1]&0x80 != 0
	length := uint64(header[1] & 0x7f)
	if length == 126 {
		var b [2]byte
		if _, err := io.ReadFull(c.reader, b[:]); err != nil {
			return 0, nil, err
		}
		length = uint64(binary.BigEndian.Uint16(b[:]))
	} else if length == 127 {
		var b [8]byte
		if _, err := io.ReadFull(c.reader, b[:]); err != nil {
			return 0, nil, err
		}
		length = binary.BigEndian.Uint64(b[:])
	}
	if length > maxFrame {
		return 0, nil, fmt.Errorf("websocket frame too large: %d", length)
	}
	var mask [4]byte
	if masked {
		if _, err := io.ReadFull(c.reader, mask[:]); err != nil {
			return 0, nil, err
		}
	}
	payload := make([]byte, length)
	if length > 0 {
		if _, err := io.ReadFull(c.reader, payload); err != nil {
			return 0, nil, err
		}
	}
	if masked {
		for i := range payload {
			payload[i] ^= mask[i%4]
		}
	}
	return opcode, payload, nil
}

func websocketAccept(key string) string {
	sum := sha1.Sum([]byte(key + wsGUID))
	return base64.StdEncoding.EncodeToString(sum[:])
}

func checkBearer(r *http.Request, token string) bool {
	if token == "" {
		return true
	}
	return r.Header.Get("Authorization") == "Bearer "+token
}

func upgradeWebSocket(w http.ResponseWriter, r *http.Request) (*wsConn, error) {
	if !strings.EqualFold(r.Header.Get("Upgrade"), "websocket") {
		return nil, errors.New("missing websocket upgrade")
	}
	if !strings.Contains(strings.ToLower(r.Header.Get("Connection")), "upgrade") {
		return nil, errors.New("missing connection upgrade")
	}
	key := r.Header.Get("Sec-WebSocket-Key")
	if key == "" {
		return nil, errors.New("missing websocket key")
	}
	hijacker, ok := w.(http.Hijacker)
	if !ok {
		return nil, errors.New("http hijacker is not available")
	}
	netConn, rw, err := hijacker.Hijack()
	if err != nil {
		return nil, err
	}
	response := "HTTP/1.1 101 Switching Protocols\r\n" +
		"Upgrade: websocket\r\n" +
		"Connection: Upgrade\r\n" +
		"Sec-WebSocket-Accept: " + websocketAccept(key) + "\r\n\r\n"
	if _, err := rw.WriteString(response); err != nil {
		_ = netConn.Close()
		return nil, err
	}
	if err := rw.Flush(); err != nil {
		_ = netConn.Close()
		return nil, err
	}
	return &wsConn{conn: netConn, reader: rw.Reader}, nil
}

func cleanHeaders(in http.Header) map[string]string {
	out := make(map[string]string)
	for k, values := range in {
		lower := strings.ToLower(k)
		if hopByHopHeaders[lower] || lower == "host" {
			continue
		}
		if len(values) > 0 {
			out[k] = values[0]
		}
	}
	return out
}

func writeResponseHeaders(w http.ResponseWriter, status int, headers map[string]string) {
	for k, v := range headers {
		lower := strings.ToLower(k)
		if hopByHopHeaders[lower] || lower == "content-length" || lower == "content-encoding" {
			continue
		}
		w.Header().Set(k, v)
	}
	w.WriteHeader(status)
}

func makeWorkloadHandler(state *tunnelState) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, state.maxBodyBytes))
		if err != nil {
			http.Error(w, "request body too large", http.StatusRequestEntityTooLarge)
			return
		}
		id := state.nextRequestID()
		ar := &activeRequest{
			startCh: make(chan frame, 1),
			bodyCh:  make(chan []byte, 16),
			doneCh:  make(chan error, 1),
		}
		req := frame{
			Type:    "request",
			ID:      id,
			Method:  r.Method,
			Path:    r.URL.RequestURI(),
			Headers: cleanHeaders(r.Header),
			BodyB64: base64.StdEncoding.EncodeToString(body),
		}
		if err := state.sendRequest(req, ar); err != nil {
			http.Error(w, "local tunnel client is not connected", http.StatusBadGateway)
			return
		}
		defer state.removeRequest(id)

		timer := time.NewTimer(state.requestTimeout)
		defer timer.Stop()
		var start frame
		select {
		case start = <-ar.startCh:
			if start.Status == 0 {
				start.Status = http.StatusBadGateway
			}
			writeResponseHeaders(w, start.Status, start.Headers)
		case err := <-ar.doneCh:
			if err == nil {
				err = errors.New("response ended before response_start")
			}
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		case <-timer.C:
			http.Error(w, "local tunnel client timed out", http.StatusGatewayTimeout)
			return
		case <-r.Context().Done():
			return
		}

		flusher, _ := w.(http.Flusher)
		for {
			select {
			case chunk := <-ar.bodyCh:
				if len(chunk) > 0 {
					if _, err := w.Write(chunk); err != nil {
						return
					}
					if flusher != nil {
						flusher.Flush()
					}
				}
			case err := <-ar.doneCh:
				if err != nil {
					log.Printf("request %s ended with tunnel error: %v", id, err)
				}
				return
			case <-timer.C:
				return
			case <-r.Context().Done():
				return
			}
		}
	}
}

func makeControlHandler(state *tunnelState, demoHandler http.HandlerFunc) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		if !checkBearer(r, state.token) {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"ok":true}`))
	})
	mux.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		if !checkBearer(r, state.token) {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		conn, err := upgradeWebSocket(w, r)
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		state.setClient(conn)
		defer state.clearClient(conn)
		defer conn.Close()
		log.Printf("local tunnel client connected from %s", r.RemoteAddr)
		for {
			opcode, payload, err := conn.ReadFrame()
			if err != nil {
				log.Printf("local tunnel client disconnected: %v", err)
				return
			}
			switch opcode {
			case opText:
				var f frame
				if err := json.Unmarshal(payload, &f); err != nil {
					log.Printf("invalid tunnel frame: %v", err)
					continue
				}
				state.deliver(f)
			case opPing:
				_ = conn.writeFrame(opPong, payload)
			case opClose:
				return
			}
		}
	})
	mux.HandleFunc("/demo/run", func(w http.ResponseWriter, r *http.Request) {
		if !checkBearer(r, state.token) {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		demoHandler(w, r)
	})
	return mux
}

func runDemoWorkload(prompt, workloadHome, llmBaseURL string, timeout time.Duration) (int, string, string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	model := os.Getenv("ANTHROPIC_MODEL")
	if model == "" {
		model = "deepseek-v4-pro[1m]"
	}
	args := claudeArgs(prompt)
	cmd := execCommandContext(ctx, workloadHome+"/bin/claude", args...)
	env := os.Environ()
	env = append(env,
		"ANTHROPIC_BASE_URL="+llmBaseURL,
		"ANTHROPIC_AUTH_TOKEN="+envOr("ANTHROPIC_AUTH_TOKEN", "placeholder"),
		"ANTHROPIC_MODEL="+model,
		"ANTHROPIC_DEFAULT_OPUS_MODEL="+envOr("ANTHROPIC_DEFAULT_OPUS_MODEL", model),
		"ANTHROPIC_DEFAULT_SONNET_MODEL="+envOr("ANTHROPIC_DEFAULT_SONNET_MODEL", model),
		"ANTHROPIC_DEFAULT_HAIKU_MODEL="+envOr("ANTHROPIC_DEFAULT_HAIKU_MODEL", "deepseek-v4-flash"),
		"CLAUDE_CODE_SUBAGENT_MODEL="+envOr("CLAUDE_CODE_SUBAGENT_MODEL", "deepseek-v4-flash"),
		"CLAUDE_CONFIG_DIR="+envOr("CLAUDE_CONFIG_DIR", "/tmp/claude-config-deepseek"),
		"DISABLE_AUTOUPDATER=1",
		"DISABLE_UPDATES=1",
	)
	cmd.Env = env
	out, errOut, err := runCommand(cmd)
	if ctx.Err() == context.DeadlineExceeded {
		return -1, out, errOut, ctx.Err()
	}
	if err != nil {
		if exit, ok := commandExitCode(err); ok {
			return exit, out, errOut, nil
		}
		return -1, out, errOut, err
	}
	return 0, out, errOut, nil
}

func claudeArgs(prompt string) []string {
	args := []string{}
	if mode := strings.TrimSpace(os.Getenv("CLAUDE_PERMISSION_MODE")); mode != "" {
		args = append(args, "--permission-mode", mode)
	}
	if isTruthy(os.Getenv("CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS")) {
		args = append(args, "--dangerously-skip-permissions")
	}
	if allowedTools := strings.TrimSpace(os.Getenv("CLAUDE_ALLOWED_TOOLS")); allowedTools != "" {
		for _, tool := range splitList(allowedTools) {
			args = append(args, "--allowedTools", tool)
		}
	}
	args = append(args, "-p", prompt, "--output-format", "text")
	return args
}

func splitList(value string) []string {
	fields := strings.FieldsFunc(value, func(r rune) bool {
		return r == ',' || r == '\n' || r == '\t' || r == ' '
	})
	out := make([]string, 0, len(fields))
	for _, field := range fields {
		if trimmed := strings.TrimSpace(field); trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}

func isTruthy(value string) bool {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "1", "true", "yes", "y", "on":
		return true
	default:
		return false
	}
}

func execCommandContext(ctx context.Context, name string, args ...string) *exec.Cmd {
	return exec.CommandContext(ctx, name, args...)
}

func runCommand(cmd *exec.Cmd) (string, string, error) {
	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	return stdout.String(), stderr.String(), err
}

func commandExitCode(err error) (int, bool) {
	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) {
		return exitErr.ExitCode(), true
	}
	return 0, false
}

func makeDemoHandler(workloadHome, llmBaseURL string, workloadTimeout time.Duration, maxBodyBytes int64) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, maxBodyBytes))
		if err != nil {
			http.Error(w, "request body too large", http.StatusRequestEntityTooLarge)
			return
		}
		var payload struct {
			Prompt string `json:"prompt"`
		}
		if err := json.Unmarshal(body, &payload); err != nil || payload.Prompt == "" {
			http.Error(w, "prompt is required", http.StatusBadRequest)
			return
		}
		code, stdout, stderr, err := runDemoWorkload(payload.Prompt, workloadHome, llmBaseURL, workloadTimeout)
		if err != nil && errors.Is(err, context.DeadlineExceeded) {
			http.Error(w, "demo workload timed out", http.StatusGatewayTimeout)
			return
		}
		status := http.StatusOK
		if err != nil || code != 0 {
			status = http.StatusBadGateway
		}
		if len(stderr) > 4000 {
			stderr = stderr[len(stderr)-4000:]
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(status)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"ok":         err == nil && code == 0,
			"returncode": code,
			"stdout":     stdout,
			"stderr":     stderr,
		})
	}
}

func envOr(name, fallback string) string {
	if v := os.Getenv(name); v != "" {
		return v
	}
	return fallback
}

func listenFromEnv(hostName, portName, fallback string) string {
	host := os.Getenv(hostName)
	port := os.Getenv(portName)
	if host == "" || port == "" {
		return fallback
	}
	return net.JoinHostPort(host, port)
}

func parseDurationSeconds(value string, fallback time.Duration) time.Duration {
	if value == "" {
		return fallback
	}
	seconds, err := strconv.ParseFloat(value, 64)
	if err != nil {
		return fallback
	}
	return time.Duration(seconds * float64(time.Second))
}

func main() {
	var workloadListen string
	var controlListen string
	var token string
	var requestTimeoutSeconds float64
	var workloadHome string
	var workloadLLMBaseURL string
	var workloadTimeoutSeconds float64
	var maxBodyBytes int64
	flag.StringVar(&workloadListen, "workload-listen", listenFromEnv("WORKLOAD_TUNNEL_HOST", "WORKLOAD_TUNNEL_PORT", "127.0.0.1:18080"), "HTTP listen address used by sandbox workload")
	flag.StringVar(&controlListen, "control-listen", listenFromEnv("CONTROL_TUNNEL_HOST", "REMOTE_TUNNEL_PORT", "0.0.0.0:18081"), "WebSocket control listen address used by local client")
	flag.StringVar(&token, "token", envOr("AGS_TUNNEL_TOKEN", ""), "Bearer token required by local tunnel client")
	flag.Float64Var(&requestTimeoutSeconds, "request-timeout", 120, "workload request timeout in seconds")
	flag.Int64Var(&maxBodyBytes, "max-body-bytes", 20*1024*1024, "maximum single request body size")
	flag.StringVar(&workloadHome, "workload-home", envOr("WORKLOAD_HOME", envOr("CLAUDE_HOME", "/mnt/workload")), "mounted workload home")
	flag.StringVar(&workloadLLMBaseURL, "workload-llm-base-url", envOr("LLM_BASE_URL", "http://127.0.0.1:18080"), "base URL injected into demo workload")
	flag.Float64Var(&workloadTimeoutSeconds, "workload-timeout", parseDurationSeconds(envOr("WORKLOAD_TIMEOUT_SECONDS", envOr("CLAUDE_TIMEOUT_SECONDS", "")), 180*time.Second).Seconds(), "demo workload timeout in seconds")
	flag.Parse()
	if token == "" {
		log.Fatal("--token is required")
	}

	state := newTunnelState(token, time.Duration(requestTimeoutSeconds*float64(time.Second)), maxBodyBytes)
	demoHandler := makeDemoHandler(workloadHome, workloadLLMBaseURL, time.Duration(workloadTimeoutSeconds*float64(time.Second)), maxBodyBytes)
	workloadMux := http.NewServeMux()
	workloadMux.HandleFunc("/", makeWorkloadHandler(state))
	workloadMux.HandleFunc("/demo/run", demoHandler)
	controlServer := &http.Server{Addr: controlListen, Handler: makeControlHandler(state, demoHandler)}
	workloadServer := &http.Server{Addr: workloadListen, Handler: workloadMux}

	go func() {
		log.Printf("workload listener ready on %s", workloadListen)
		if err := workloadServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("workload listener failed: %v", err)
		}
	}()
	go func() {
		log.Printf("control websocket listener ready on %s", controlListen)
		if err := controlServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("control listener failed: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGTERM, syscall.SIGINT)
	<-stop
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = workloadServer.Shutdown(ctx)
	_ = controlServer.Shutdown(ctx)
}
