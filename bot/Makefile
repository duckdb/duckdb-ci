.PHONY: tidy build test cov image clean

tidy:
	go mod tidy

build:
	mkdir -p build
	go build -o build/server ./cmd/server

image:
	docker build -f docker/Dockerfile -t duckdb-ci-bot:ci .

test:
	go test ./...

cov:
	mkdir -p build
	go test -coverprofile=build/coverage.out ./...
	go tool cover -html=build/coverage.out -o build/coverage.html
	open build/coverage.html

clean:
	rm -rf build
