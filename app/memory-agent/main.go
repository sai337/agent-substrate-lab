// memory-agent is a tiny stateful "agent" for Agent Substrate.
//
// It keeps working memory in RAM and a notes file on a durable volume, so a
// suspend/resume cycle can be checked from the outside: if both counters keep
// counting after a resume, Substrate restored the process memory and the disk.
// It also exposes the probes the lab needs: an egress attempt and a self-check
// that reports what an attacker inside the sandbox would see.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"syscall"
	"time"
)

type agent struct {
	mu        sync.Mutex
	memory    []string // working memory: survives only a MEMORY-fidelity snapshot
	notesPath string   // durable volume: survives every snapshot fidelity
	bootID    string   // set once per real process start
	started   time.Time
	client    *http.Client
}

func newAgent(notesPath string) *agent {
	return &agent{
		notesPath: notesPath,
		bootID:    fmt.Sprintf("%d-%d", os.Getpid(), time.Now().UnixNano()),
		started:   time.Now().UTC(),
		client:    &http.Client{Timeout: 10 * time.Second},
	}
}

func (a *agent) fileCount() int {
	b, err := os.ReadFile(a.notesPath)
	if err != nil {
		return 0
	}
	return strings.Count(string(b), "\n")
}

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func (a *agent) state() map[string]any {
	host, _ := os.Hostname()
	return map[string]any{
		"memory_count": len(a.memory),
		"file_count":   a.fileCount(),
		"boot_id":      a.bootID,
		"started_at":   a.started.Format(time.RFC3339Nano),
		"hostname":     host,
	}
}

func (a *agent) remember(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "POST only"})
		return
	}
	note := r.URL.Query().Get("note")
	if note == "" {
		note = "note"
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	a.memory = append(a.memory, note)
	f, err := os.OpenFile(a.notesPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	defer f.Close()
	if _, err := fmt.Fprintln(f, note); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, a.state())
}

func (a *agent) recall(w http.ResponseWriter, _ *http.Request) {
	a.mu.Lock()
	defer a.mu.Unlock()
	writeJSON(w, http.StatusOK, a.state())
}

// fetch tries an outbound GET. The lab uses it to prove default-deny egress
// and the allow-list from an EgressPolicy. It never returns the body.
func (a *agent) fetch(w http.ResponseWriter, r *http.Request) {
	url := r.URL.Query().Get("url")
	if !strings.HasPrefix(url, "http://") && !strings.HasPrefix(url, "https://") {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "url must be http(s)"})
		return
	}
	t0 := time.Now()
	resp, err := a.client.Get(url)
	out := map[string]any{"url": url, "ms": time.Since(t0).Milliseconds()}
	if err != nil {
		out["ok"], out["error"] = false, err.Error()
		writeJSON(w, http.StatusOK, out)
		return
	}
	resp.Body.Close()
	out["ok"], out["status"] = resp.StatusCode < 400, resp.StatusCode
	writeJSON(w, http.StatusOK, out)
}

var secretEnv = regexp.MustCompile(`(?i)(API_?KEY|SECRET|TOKEN|PASSWORD)`)

// selfcheck reports what a hostile agent could find: kernel, identity,
// mounted service-account token, secrets in the environment.
func selfcheck(w http.ResponseWriter, _ *http.Request) {
	var uts syscall.Utsname
	_ = syscall.Uname(&uts)
	release := charsToString(uts.Release[:])
	var leaked []string
	for _, kv := range os.Environ() {
		k, v, _ := strings.Cut(kv, "=")
		if secretEnv.MatchString(k) && v != "" {
			leaked = append(leaked, k)
		}
	}
	_, tokenErr := os.Stat("/var/run/secrets/kubernetes.io/serviceaccount/token")
	writeJSON(w, http.StatusOK, map[string]any{
		"kernel_release": release,
		"uid":            os.Getuid(),
		"sa_token":       tokenErr == nil,
		"secret_env":     leaked,
	})
}

func charsToString(ca []int8) string {
	b := make([]byte, 0, len(ca))
	for _, c := range ca {
		if c == 0 {
			break
		}
		b = append(b, byte(c))
	}
	return string(b)
}

func main() {
	port := flag.Int("port", 8080, "listen port")
	dir := flag.String("data", "/home/agent", "durable data directory")
	flag.Parse()
	if err := os.MkdirAll(*dir, 0o700); err != nil {
		log.Fatalf("data dir: %v", err)
	}
	a := newAgent(filepath.Join(*dir, "notes.txt"))
	mux := http.NewServeMux()
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusOK) })
	mux.HandleFunc("/remember", a.remember)
	mux.HandleFunc("/recall", a.recall)
	mux.HandleFunc("/fetch", a.fetch)
	mux.HandleFunc("/selfcheck", selfcheck)
	log.Printf("memory-agent listening on :%d", *port)
	srv := &http.Server{Addr: fmt.Sprintf(":%d", *port), Handler: mux, ReadHeaderTimeout: 5 * time.Second}
	log.Fatal(srv.ListenAndServe())
}
