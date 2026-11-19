package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
)

func decode(t *testing.T, rr *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var m map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &m); err != nil {
		t.Fatalf("bad json %q: %v", rr.Body.String(), err)
	}
	return m
}

func TestRememberCountsMemoryAndFile(t *testing.T) {
	a := newAgent(filepath.Join(t.TempDir(), "notes.txt"))
	for i := 1; i <= 3; i++ {
		rr := httptest.NewRecorder()
		a.remember(rr, httptest.NewRequest(http.MethodPost, "/remember?note=x", nil))
		m := decode(t, rr)
		if int(m["memory_count"].(float64)) != i || int(m["file_count"].(float64)) != i {
			t.Fatalf("after %d: %v", i, m)
		}
	}
}

func TestFileSurvivesProcessRestart(t *testing.T) {
	p := filepath.Join(t.TempDir(), "notes.txt")
	a := newAgent(p)
	a.remember(httptest.NewRecorder(), httptest.NewRequest(http.MethodPost, "/remember", nil))
	b := newAgent(p) // a cold boot: memory gone, disk kept
	rr := httptest.NewRecorder()
	b.recall(rr, httptest.NewRequest(http.MethodGet, "/recall", nil))
	m := decode(t, rr)
	if m["memory_count"].(float64) != 0 || m["file_count"].(float64) != 1 || m["boot_id"] == a.bootID {
		t.Fatalf("unexpected state after restart: %v", m)
	}
}

func TestRememberRejectsGet(t *testing.T) {
	a := newAgent(filepath.Join(t.TempDir(), "n"))
	rr := httptest.NewRecorder()
	a.remember(rr, httptest.NewRequest(http.MethodGet, "/remember", nil))
	if rr.Code != http.StatusMethodNotAllowed {
		t.Fatalf("got %d", rr.Code)
	}
}

func TestFetchReportsAllowedAndDenied(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(204) }))
	defer up.Close()
	a := newAgent(filepath.Join(t.TempDir(), "n"))
	rr := httptest.NewRecorder()
	a.fetch(rr, httptest.NewRequest(http.MethodGet, "/fetch?url="+up.URL, nil))
	if m := decode(t, rr); m["ok"] != true {
		t.Fatalf("want ok: %v", m)
	}
	rr = httptest.NewRecorder()
	a.fetch(rr, httptest.NewRequest(http.MethodGet, "/fetch?url=http://127.0.0.1:1", nil))
	if m := decode(t, rr); m["ok"] != false || m["error"] == nil {
		t.Fatalf("want error: %v", m)
	}
	rr = httptest.NewRecorder()
	a.fetch(rr, httptest.NewRequest(http.MethodGet, "/fetch?url=file:///etc/passwd", nil))
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("non-http scheme must be rejected, got %d", rr.Code)
	}
}

func TestSelfcheckFlagsSecretEnv(t *testing.T) {
	t.Setenv("OPENAI_API_KEY", "sk-test")
	rr := httptest.NewRecorder()
	selfcheck(rr, httptest.NewRequest(http.MethodGet, "/selfcheck", nil))
	m := decode(t, rr)
	leaked := m["secret_env"].([]any)
	found := false
	for _, k := range leaked {
		if k == "OPENAI_API_KEY" {
			found = true
		}
	}
	if !found || m["kernel_release"] == "" {
		t.Fatalf("selfcheck missed the planted key: %v", m)
	}
}
