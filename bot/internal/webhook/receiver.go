package webhook

import (
	"log/slog"
	"net/http"

	"github.com/google/go-github/v61/github"
)

type Receiver struct {
	Secret []byte
	Router Router
	Logger *slog.Logger
}

func (r Receiver) ServeHTTP(w http.ResponseWriter, req *http.Request) {
	if req.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	payload, err := github.ValidatePayload(req, r.Secret)
	if err != nil {
		http.Error(w, "invalid signature", http.StatusUnauthorized)
		return
	}

	eventType := github.WebHookType(req)
	event, err := github.ParseWebHook(eventType, payload)
	if err != nil {
		http.Error(w, "invalid payload", http.StatusBadRequest)
		return
	}

	if err := r.Router.Dispatch(req.Context(), eventType, event); err != nil {
		r.Logger.Error("webhook dispatch failed", slog.String("event_type", eventType), slog.String("error", err.Error()))
		http.Error(w, "failed to process event", http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
}
