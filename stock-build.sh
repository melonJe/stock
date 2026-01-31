#!/bin/bash

# Enable strict mode
set -euo pipefail

# Configuration
REPO_DIR="stock"
REPO_URL="git@github.com:melonJe/stock.git"
DEFAULT_BRANCH="main"
DOCKER_IMAGE="stock:latest"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
    exit 1
}

# Validate branch name
validate_branch() {
    local branch=$1
    if ! git ls-remote --heads "$REPO_URL" "$branch" | grep -q "refs/heads/$branch"; then
        log_error "Branch '$branch' does not exist in the repository"
    fi
}

# Main execution
main() {
    local branch=${1:-$DEFAULT_BRANCH}
    local current_dir
    current_dir=$(pwd)

    log_info "Starting build process for branch: $branch"
    
    # Validate branch exists
    log_info "Validating branch '$branch'..."
    validate_branch "$branch"

    # Handle repository
    if [ -d "$REPO_DIR" ]; then
        log_info "Repository exists, checking for updates..."
        cd "$REPO_DIR" || log_error "Failed to enter $REPO_DIR"
        
        # Fetch and check for updates
        git fetch origin "$branch" || log_error "Failed to fetch from origin"
        
        local local_commit
        local remote_commit
        local_commit=$(git rev-parse "$branch")
        remote_commit=$(git rev-parse "origin/$branch")
        
        if [ "$local_commit" = "$remote_commit" ]; then
            log_info "Repository is already up to date. No changes to pull."
        else
            log_info "Updates found. Pulling changes..."
            git checkout "$branch" || log_error "Failed to checkout branch $branch"
            git reset --hard "origin/$branch" || log_error "Failed to reset to origin/$branch"
            git clean -fd || log_warn "Failed to clean untracked files"
        fi
    else
        log_info "Cloning repository..."
        git clone --depth 1 --branch "$branch" "$REPO_URL" "$REPO_DIR" || 
            log_error "Failed to clone repository"
        cd "$REPO_DIR" || log_error "Failed to enter $REPO_DIR"
    fi

    # Build Docker image with build cache
    log_info "Building Docker image..."
    docker build --pull --cache-from "$DOCKER_IMAGE" -t "$DOCKER_IMAGE" . || 
        log_error "Docker build failed"

    # Copy docker-compose.yml if it exists
    if [ -f "docker-compose.yml" ]; then
        log_info "Updating docker-compose.yml..."
        cp -f ./docker-compose.yml "$current_dir/" || 
            log_warn "Failed to update docker-compose.yml"
    fi

    # Return to original directory
    cd "$current_dir" || log_error "Failed to return to original directory"

    # Validate .env files
    log_info "Validating environment files..."
    if [ ! -f ".env.stock" ]; then
        log_warn ".env.stock not found. Please create it from .env.example"
    fi
    if [ ! -f ".env.db" ]; then
        log_warn ".env.db not found. Please create it"
    fi

    # Create logs directory if it doesn't exist
    log_info "Setting up logs directory..."
    mkdir -p logs
    chmod 755 logs  # 755로 변경 (보안 강화)

    # Start services
    log_info "Starting services..."
    if command -v docker-compose &> /dev/null; then
        docker-compose down || log_warn "Failed to stop existing containers"
        docker-compose up -d --remove-orphans || log_error "Failed to start services"
        
        # Wait for health checks
        log_info "Waiting for services to be healthy..."
        sleep 5
        docker-compose ps
    else
        docker compose down || log_warn "Failed to stop existing containers"
        docker compose up -d --remove-orphans || log_error "Failed to start services"
        
        # Wait for health checks
        log_info "Waiting for services to be healthy..."
        sleep 5
        docker compose ps
    fi

    # Clean up unused images
    log_info "Cleaning up..."
    docker image prune -af --filter "until=24h" || 
        log_warn "Failed to clean up unused images"

    log_info "Build and deployment completed successfully!"
}

# Execute main function
main "$@"
