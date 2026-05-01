package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"

	"github.com/duckdb/duckdb-ci/bot/internal/events"
	"github.com/duckdb/duckdb-ci/bot/internal/githubapp"
	"github.com/duckdb/duckdb-ci/bot/internal/logging"
	"github.com/duckdb/duckdb-ci/bot/internal/webhook"
)

func main() {
	logger := logging.New()

	secret := os.Getenv("GITHUB_WEBHOOK_SECRET")
	if secret == "" {
		log.Fatal("GITHUB_WEBHOOK_SECRET must be set")
	}

	appID, err := strconv.ParseInt(os.Getenv("GITHUB_APP_ID"), 10, 64)
	if err != nil {
		log.Fatalf("invalid GITHUB_APP_ID: %v", err)
	}

	factory, err := githubapp.NewClientFactory(githubapp.Config{
		AppID:          appID,
		PrivateKeyPath: os.Getenv("GITHUB_APP_PRIVATE_KEY_PATH"),
	})
	if err != nil {
		log.Fatalf("failed to configure github app client: %v", err)
	}

	labeler := githubapp.InstallationLabeler{Factory: factory}

	router := webhook.Router{
		Logger: logger,
		PullRequestOpened: events.PullRequestOpenedHandler{
			Labeler: labeler,
			Logger:  logger,
		},
	}

	receiver := webhook.Receiver{
		Secret: []byte(secret),
		Router: router,
		Logger: logger,
	}

	mux := http.NewServeMux()
	mux.Handle("/webhook", receiver)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	addr := fmt.Sprintf(":%s", port)
	logger.Info("starting webhook server", "addr", addr)
	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatalf("server failed: %v", err)
	}
}
