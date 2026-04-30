package webhook

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/duckdb/duckdb-ci/bot/internal/events"
	"github.com/stretchr/testify/require"
)

type fakeLabeler struct{}

func (f *fakeLabeler) AddLabelToPR(_ context.Context, _ int64, _, _ string, _ int, _ string) error {
	return nil
}

type prWebhookPayload struct {
	Action       string              `json:"action"`
	Installation installationPayload `json:"installation"`
	Sender       userPayload         `json:"sender"`
	Repository   repositoryPayload   `json:"repository"`
	PullRequest  pullRequestPayload  `json:"pull_request"`
}

type installationPayload struct {
	ID int64 `json:"id"`
}

type userPayload struct {
	Login string `json:"login"`
}

type repositoryPayload struct {
	Name  string      `json:"name"`
	Owner userPayload `json:"owner"`
}

type pullRequestPayload struct {
	Number            int         `json:"number"`
	AuthorAssociation string      `json:"author_association"`
	User              userPayload `json:"user"`
}

func TestReceiverPullRequestOpenedStatusOK(t *testing.T) {
	secret := []byte("topsecret")
	receiver := newTestReceiver(secret, &fakeLabeler{})

	payload := prWebhookPayload{
		Action:       "opened",
		Installation: installationPayload{ID: 99},
		Sender:       userPayload{Login: "contrib"},
		Repository: repositoryPayload{
			Name:  "repo1",
			Owner: userPayload{Login: "duckdb"},
		},
		PullRequest: pullRequestPayload{
			Number:            17,
			AuthorAssociation: "MEMBER",
			User:              userPayload{Login: "contrib"},
		},
	}

	req := signedWebhookRequest(t, secret, payload)
	rr := httptest.NewRecorder()

	receiver.ServeHTTP(rr, req)

	require.Equal(t, http.StatusOK, rr.Code)
}

func TestReceiverInvalidSignatureUnauthorized(t *testing.T) {
	secret := []byte("topsecret")
	receiver := newTestReceiver(secret, &fakeLabeler{})

	body := []byte(`{"action":"opened"}`)
	req := httptest.NewRequest(http.MethodPost, "/webhook", bytes.NewReader(body))
	req.Header.Set("X-GitHub-Event", "pull_request")
	req.Header.Set("X-Hub-Signature-256", "sha256=invalid")
	rr := httptest.NewRecorder()

	receiver.ServeHTTP(rr, req)

	require.Equal(t, http.StatusUnauthorized, rr.Code)
}

func TestReceiverPullRequestNonOpenedActionNoopStatusOK(t *testing.T) {
	secret := []byte("topsecret")
	receiver := newTestReceiver(secret, &fakeLabeler{})

	payload := prWebhookPayload{
		Action:       "synchronize",
		Installation: installationPayload{ID: 99},
		Sender:       userPayload{Login: "contrib"},
		Repository: repositoryPayload{
			Name:  "repo1",
			Owner: userPayload{Login: "duckdb"},
		},
		PullRequest: pullRequestPayload{
			Number:            17,
			AuthorAssociation: "MEMBER",
			User:              userPayload{Login: "contrib"},
		},
	}

	req := signedWebhookRequest(t, secret, payload)
	rr := httptest.NewRecorder()

	receiver.ServeHTTP(rr, req)

	require.Equal(t, http.StatusOK, rr.Code)
}

func TestReceiverMethodNotAllowed(t *testing.T) {
	receiver := newTestReceiver([]byte("topsecret"), &fakeLabeler{})
	req := httptest.NewRequest(http.MethodGet, "/webhook", nil)
	rr := httptest.NewRecorder()

	receiver.ServeHTTP(rr, req)

	require.Equal(t, http.StatusMethodNotAllowed, rr.Code)
}

func newTestReceiver(secret []byte, labeler events.Labeler) Receiver {
	logger := slog.New(slog.NewTextHandler(bytes.NewBuffer(nil), nil))
	return Receiver{
		Secret: secret,
		Logger: logger,
		Router: Router{
			Logger: logger,
			PullRequestOpened: events.PullRequestOpenedHandler{
				Labeler: labeler,
				Logger:  logger,
			},
		},
	}
}

func signedWebhookRequest(t *testing.T, secret []byte, payload prWebhookPayload) *http.Request {
	t.Helper()

	body, err := json.Marshal(payload)
	require.NoError(t, err)

	h := hmac.New(sha256.New, secret)
	_, err = h.Write(body)
	require.NoError(t, err)
	sig := "sha256=" + hex.EncodeToString(h.Sum(nil))

	req := httptest.NewRequest(http.MethodPost, "/webhook", bytes.NewReader(body))
	req.Header.Set("X-GitHub-Event", "pull_request")
	req.Header.Set("X-Hub-Signature-256", sig)
	req.Header.Set("Content-Type", "application/json")
	return req
}
