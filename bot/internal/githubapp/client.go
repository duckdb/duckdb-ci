package githubapp

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"

	"github.com/bradleyfalzon/ghinstallation/v2"
	"github.com/google/go-github/v61/github"
)

type Config struct {
	AppID          int64
	PrivateKeyPath string
}

type ClientFactory struct {
	appID      int64
	privateKey []byte
}

func NewClientFactory(cfg Config) (*ClientFactory, error) {
	if cfg.AppID <= 0 {
		return nil, errors.New("GITHUB_APP_ID must be set")
	}
	if cfg.PrivateKeyPath == "" {
		return nil, errors.New("GITHUB_APP_PRIVATE_KEY_PATH must be set")
	}

	pemBytes, err := os.ReadFile(cfg.PrivateKeyPath)
	if err != nil {
		return nil, fmt.Errorf("read private key: %w", err)
	}

	return &ClientFactory{appID: cfg.AppID, privateKey: pemBytes}, nil
}

func (f *ClientFactory) NewClient(ctx context.Context, installationID int64) (*github.Client, error) {
	itr, err := ghinstallation.New(http.DefaultTransport, f.appID, installationID, f.privateKey)
	if err != nil {
		return nil, fmt.Errorf("create installation transport: %w", err)
	}
	return github.NewClient(&http.Client{Transport: itr}), nil
}

type InstallationClientFactory interface {
	NewClient(ctx context.Context, installationID int64) (*github.Client, error)
}

type InstallationLabeler struct {
	Factory InstallationClientFactory
}

func (l InstallationLabeler) AddLabelToPR(ctx context.Context, installationID int64, owner, repo string, prNumber int, label string) error {
	if installationID <= 0 {
		return errors.New("installation id is required")
	}

	client, err := l.Factory.NewClient(ctx, installationID)
	if err != nil {
		return err
	}

	_, _, err = client.Issues.AddLabelsToIssue(ctx, owner, repo, prNumber, []string{label})
	if err == nil {
		return nil
	}

	var ghErr *github.ErrorResponse
	if errors.As(err, &ghErr) && ghErr.Response != nil && ghErr.Response.StatusCode == http.StatusUnprocessableEntity {
		if strings.Contains(strings.ToLower(ghErr.Message), "already") {
			return nil
		}
	}

	return err
}
