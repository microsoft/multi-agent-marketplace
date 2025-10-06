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

# # If we are using codespaces, GPU is not available, so we need to install the CPU version of torch
# if [ -n "${CODESPACES:-}" ] && ! command -v nvidia-smi >/dev/null; then
#   uv remove sentence-transformers # Will sync all dependencies in addition to removing sentence-transformers
#   uv pip install --index-url https://download.pytorch.org/whl/cpu torch
#   uv pip install sentence-transformers
# else
#   uv sync
# fi

# Set up shell environment
echo "Configuring shell environment..."

# # Add uv to PATH permanently
# echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc

# Add virtual environment activation
if [ -d ".venv" ]; then
    echo 'if [ -d ".venv" ]; then source .venv/bin/activate; fi' >> ~/.bashrc
    echo "Virtual environment created successfully"
else
    echo "Warning: .venv directory not created"
fi

echo "Development environment setup complete!"
# echo "Restart your terminal or run 'source ~/.bashrc' to activate the environment"