package events

import (
	"bytes"
	"context"
	"testing"

	"github.com/google/go-github/v61/github"
	"github.com/stretchr/testify/require"
	"log/slog"
)

type fakeLabeler struct {
	calls int
	last  struct {
		installationID int64
		owner          string
		repo           string
		prNumber       int
		label          string
	}
}

func (f *fakeLabeler) AddLabelToPR(_ context.Context, installationID int64, owner, repo string, prNumber int, label string) error {
	f.calls++
	f.last.installationID = installationID
	f.last.owner = owner
	f.last.repo = repo
	f.last.prNumber = prNumber
	f.last.label = label
	return nil
}

func TestPullRequestOpenedHandlerLabelsAllowedAssociation(t *testing.T) {
	labeler := &fakeLabeler{}
	handler := PullRequestOpenedHandler{
		Labeler: labeler,
		Logger:  slog.New(slog.NewTextHandler(bytes.NewBuffer(nil), nil)),
	}

	event := testPREvent("opened", "MEMBER", 99)
	err := handler.Handle(context.Background(), event)

	require.NoError(t, err)
	require.Equal(t, 1, labeler.calls)
	require.Equal(t, int64(99), labeler.last.installationID)
	require.Equal(t, "duckdb", labeler.last.owner)
	require.Equal(t, "repo1", labeler.last.repo)
	require.Equal(t, 17, labeler.last.prNumber)
	require.Equal(t, memberLabel, labeler.last.label)
}

func TestPullRequestOpenedHandlerNoopDisallowedAssociation(t *testing.T) {
	labeler := &fakeLabeler{}
	handler := PullRequestOpenedHandler{
		Labeler: labeler,
		Logger:  slog.New(slog.NewTextHandler(bytes.NewBuffer(nil), nil)),
	}

	event := testPREvent("opened", "NONE", 99)
	err := handler.Handle(context.Background(), event)

	require.NoError(t, err)
	require.Equal(t, 0, labeler.calls)
}

func testPREvent(action, association string, installationID int64) *github.PullRequestEvent {
	return &github.PullRequestEvent{
		Action: github.String(action),
		Installation: &github.Installation{
			ID: github.Int64(installationID),
		},
		Sender: &github.User{Login: github.String("contrib")},
		Repo: &github.Repository{
			Name: github.String("repo1"),
			Owner: &github.User{
				Login: github.String("duckdb"),
			},
		},
		PullRequest: &github.PullRequest{
			Number:            github.Int(17),
			AuthorAssociation: github.String(association),
			User: &github.User{
				Login: github.String("contrib"),
			},
		},
	}
}
