# Installation

## Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- Docker (for database)

## Setup

1. **Clone the repository**

    ```bash
    git clone https://github.com/microsoft/multi-agent-marketplace.git
    cd multi-agent-marketplace
    ```

2. **Install dependencies**

    ```bash
    # Install dependencies with uv
    uv sync --all-extras
    source .venv/bin/activate
    ```

3. **Configure environment variables**

    ```bash
    # Copy the sample environment file
    cp sample.env .env

    # Edit .env in your favorite editor to add your API keys
    ```

4. **Start the database server**

    ```bash
    docker compose up -d
    ```

You're now ready to run simulations! See the [Usage](usage.md) guide to get started.
