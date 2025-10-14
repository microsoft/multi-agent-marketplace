#!/bin/bash
set -e

echo "Setting up Python development environment with uv..."

# Install uv
echo "Installing uv..."
curl -LsSf https://astral.sh/uv/install.sh | sh

# For large packages like pytorch
export UV_HTTP_TIMEOUT=300

# Verify uv installation
if ! command -v uv &> /dev/null; then
    echo "uv command not found in PATH, attempting alternative installation..."
    # Try pip installation as fallback
    pip install uv
fi

echo "uv version: $(uv --version)"

# Check if pyproject.toml exists
if [ ! -f "pyproject.toml" ]; then
    echo "Warning: No pyproject.toml found in current directory"
    echo "Current directory: $(pwd)"
    echo "Contents: $(ls -la)"
fi

# Create virtual environment and sync dependencies
echo "Syncing dependencies with uv..."
uv sync 

# Add virtual environment activation
if [ -d ".venv" ]; then
    echo 'if [ -d ".venv" ]; then source .venv/bin/activate; fi' >> ~/.bashrc
    echo "Virtual environment created successfully"
else
    echo "Warning: .venv directory not created"
fi

# Setup env vars
echo "Generating .env file from template..."
uv run scripts/generate_env.py sample.env .env

# Setup docker for the database server
docker compose up -d

echo "Development environment setup complete!"
