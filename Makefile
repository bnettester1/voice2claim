.PHONY: dev build test clean

dev:
    @echo "Starting development environment..."
    cd backend && make run

build:
    cd backend && make build

test:
    cd backend && make test

clean:
    cd backend && make clean

setup:
    chmod +x scripts/*.sh
    @echo "Setup complete!"
