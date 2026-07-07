MODULE  := github.com/warungbudina/akses-vps/grpc-server
IMAGE   := akses-vps/grpc-server
TAG     ?= latest

.PHONY: proto build run test lint docker-build docker-run clean

proto: ## Generate Go stubs dari proto/device.proto ke proto/gen
	mkdir -p proto/gen
	protoc \
		--go_out=proto/gen --go_opt=paths=source_relative \
		--go-grpc_out=proto/gen --go-grpc_opt=paths=source_relative \
		--proto_path=proto proto/device.proto

build: proto ## Build binary lokal
	CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o bin/grpc-server ./cmd/server

run: build ## Jalankan lokal (baca configs/config.yaml + env)
	JWT_SECRET=devsecret INTERNAL_API_KEY=devkey ./bin/grpc-server

test: ## Unit test
	go test ./... -race -cover

lint: ## Static analysis
	go vet ./...
	gofmt -l .

docker-build: ## Build image multi-stage
	docker build -t $(IMAGE):$(TAG) .

docker-run: docker-build
	docker run --rm -p 50051:50051 -p 8443:8443 \
		-e JWT_SECRET=devsecret -e INTERNAL_API_KEY=devkey \
		$(IMAGE):$(TAG)

clean:
	rm -rf bin proto/gen
