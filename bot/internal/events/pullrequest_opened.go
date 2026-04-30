package events

import (
	"context"
	"errors"
	"log/slog"
	"strings"

	"github.com/google/go-github/v61/github"
)

const memberLabel = "Member"

var allowedAssociations = map[string]struct{}{
	"MEMBER":       {},
	"OWNER":        {},
	"COLLABORATOR": {},
}

type Labeler interface {
	AddLabelToPR(ctx context.Context, installationID int64, owner, repo string, prNumber int, label string) error
}

type PullRequestOpenedHandler struct {
	Labeler Labeler
	Logger  *slog.Logger
}

func (h PullRequestOpenedHandler) Handle(ctx context.Context, event *github.PullRequestEvent) error {
	if event == nil || event.PullRequest == nil || event.Repo == nil || event.Repo.Owner == nil || event.Sender == nil || event.Installation == nil {
		return errors.New("missing fields in pull_request event")
	}

	association := strings.ToUpper(event.GetPullRequest().GetAuthorAssociation())
	login := event.GetPullRequest().GetUser().GetLogin()
	if login == "" {
		login = event.GetSender().GetLogin()
	}

	h.Logger.Info("pull_request opened received",
		slog.String("user", login),
		slog.String("author_association", association),
		slog.String("repo_owner", event.GetRepo().GetOwner().GetLogin()),
		slog.String("repo_name", event.GetRepo().GetName()),
		slog.Int("pr_number", event.GetPullRequest().GetNumber()),
	)

	if !isAllowedAssociation(association) {
		return nil
	}

	owner := event.GetRepo().GetOwner().GetLogin()
	repo := event.GetRepo().GetName()
	prNumber := event.GetPullRequest().GetNumber()
	installationID := event.GetInstallation().GetID()

	return h.Labeler.AddLabelToPR(ctx, installationID, owner, repo, prNumber, memberLabel)
}

func isAllowedAssociation(association string) bool {
	_, ok := allowedAssociations[association]
	return ok
}
