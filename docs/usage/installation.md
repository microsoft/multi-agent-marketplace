# Getting Started

To run simulations with Magentic Marketplace you need Python 3.10 or higher, the [uv](https://docs.astral.sh/uv/) package manager, and [Docker](https://www.docker.com/get-started/).

## Install

1. **Clone the repository**

   ```bash
   git clone https://github.com/microsoft/multi-agent-marketplace.git
   cd multi-agent-marketplace
   ```

2. **Install dependencies**

   ```bash
   uv sync --all-extras
   source .venv/bin/activate
   ```

3. **Configure environment variables**

   ```bash
   # Copy the sample environment file
   cp sample.env .env

   # Edit your .env to add API keys and change model
   ```

4. **Start the database server**

   We use docker to run a Postgres database to store experiment data

   ```bash
   docker compose up -d
   ```

## Run an experiment

You're now ready to run an experiment!

```bash
magentic-marketplace run data/mexican_3_9
```
