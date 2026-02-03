#!/bin/bash

# Build the YokeFlow Docker image with agent-browser support
# This image includes Playwright and agent-browser for AI-optimized browser automation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Building YokeFlow Docker image with agent-browser...${NC}"

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Check if Dockerfile exists
DOCKERFILE="$PROJECT_ROOT/docker/Dockerfile.agent-sandbox-playwright"
if [ ! -f "$DOCKERFILE" ]; then
    echo -e "${RED}Error: Dockerfile not found at $DOCKERFILE${NC}"
    exit 1
fi

# Image name and tag
IMAGE_NAME="yokeflow-playwright"
IMAGE_TAG="latest"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

echo -e "${YELLOW}Building Docker image: ${FULL_IMAGE}${NC}"
echo "Dockerfile: $DOCKERFILE"
echo ""

# Build the image
docker build -f "$DOCKERFILE" -t "$FULL_IMAGE" "$PROJECT_ROOT/docker"

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Docker image built successfully!${NC}"
    echo ""
    echo "Image details:"
    docker images | grep "$IMAGE_NAME" | head -1
    echo ""
    echo "Features included:"
    echo "  • Node.js 20 LTS"
    echo "  • Playwright with Chromium, Firefox, and WebKit"
    echo "  • agent-browser for AI-optimized browser automation"
    echo "  • Development tools (git, curl, build-essential, etc.)"
    echo ""
    echo "To use this image with YokeFlow:"
    echo "  1. Update your .yokeflow.yaml to enable Docker:"
    echo "     docker:"
    echo "       enabled: true"
    echo "       image: ${FULL_IMAGE}"
    echo ""
    echo "  2. Run YokeFlow normally - it will use this image automatically"
else
    echo -e "${RED}❌ Failed to build Docker image${NC}"
    exit 1
fi