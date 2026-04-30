package webhook

import (
	"context"
	"errors"
	"log/slog"

	"github.com/duckdb/duckdb-ci/bot/internal/events"
	"github.com/google/go-github/v61/github"
)

type Router struct {
	PullRequestOpened events.PullRequestOpenedHandler
	Logger            *slog.Logger
}

func (r Router) Dispatch(ctx context.Context, eventType string, event any) error {
	switch eventType {
	case "pull_request":
		prEvent, ok := event.(*github.PullRequestEvent)
		if !ok {
			return errors.New("unexpected pull_request event payload")
		}
		if prEvent.GetAction() != "opened" {
			r.Logger.Debug("ignoring pull_request action", slog.String("action", prEvent.GetAction()))
			return nil
		}
		return r.PullRequestOpened.Handle(ctx, prEvent)
	default:
		r.Logger.Debug("ignoring unsupported event", slog.String("event_type", eventType))
		return nil
	}
}
