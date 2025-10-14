# Usage

## CLI Usage

### Running Simulations

Magentic Marketplace provides a command-line interface for running experiments and analyzing results.

### Run an Experiment

```bash
# Run an experiment with a specific data directory
magentic-marketplace run data/mexican_3_9 --experiment-name test_exp
```

The `--experiment-name` parameter is optional. If not provided, a unique name will be generated automatically.

### Analyze Results

After running an experiment, analyze the results:

```bash
magentic-marketplace analyze test_exp
```

This will generate a detailed report of the simulation including:
- Transaction summary
- Agent behavior metrics
- Market welfare analysis

---

### CLI Commands Reference

View all available CLI options:

```bash
magentic-marketplace --help
```

### `run` - Run a Marketplace Experiment

Run a marketplace simulation using YAML configuration files.

**Usage:**

```bash
magentic-marketplace run DATA_DIR [OPTIONS]
```

**Arguments:**

- `DATA_DIR` - Path to the data directory containing `businesses/` and `customers/` subdirectories

**Options:**

- `--experiment-name NAME` - Name for this experiment (used as PostgreSQL schema name). If not provided, a unique name will be generated.
- `--search-algorithm ALGORITHM` - Search algorithm for customer agents (default: `lexical`)
- `--search-bandwidth N` - Search bandwidth for customer agents (default: `10`)
- `--customer-max-steps N` - Maximum number of steps a customer agent can take before stopping (default: `100`)
- `--env-file PATH` - Path to .env file with environment variables (default: `.env`)
- `--postgres-host HOST` - PostgreSQL host (default: `localhost`)
- `--postgres-port PORT` - PostgreSQL port (default: `5432`)
- `--postgres-password PASSWORD` - PostgreSQL password (default: `postgres`)
- `--log-level LEVEL` - Set logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` (default: `INFO`)
- `--override-db` - Override the existing database schema if it exists
- `--export` - Export the experiment to SQLite after completion
- `--export-dir DIR` - Output directory for SQLite export (default: current directory). Only used with `--export`
- `--export-filename FILE` - Output filename for SQLite export (default: `<experiment_name>.db`). Only used with `--export`

**Example:**

```bash
magentic-marketplace run data/mexican_3_9 \
  --experiment-name my_experiment \
  --customer-max-steps 50 \
  --override-db \
  --export
```

---

### `analyze` - Analyze Experiment Results

Analyze marketplace simulation data and generate reports.

**Usage:**

```bash
magentic-marketplace analyze DATABASE_NAME [OPTIONS]
```

**Arguments:**


- `DATABASE_NAME` - PostgreSQL schema name or path to SQLite database file

**Options:**


- `--db-type TYPE` - Type of database: `sqlite` or `postgres` (default: `postgres`)
- `--no-save-json` - Disable saving analytics to JSON file

**Example:**

```bash
magentic-marketplace analyze my_experiment --db-type postgres
```

**Generates:**

- Console output with detailed analytics report
- JSON file with analytics results (unless `--no-save-json` is specified)

---

### `extract-traces` - Extract LLM Traces

Extract LLM traces from marketplace simulation and save to markdown files.

**Usage:**

```bash
magentic-marketplace extract-traces DATABASE_NAME [OPTIONS]
```

**Arguments:**

- `DATABASE_NAME` - PostgreSQL schema name or path to SQLite database file

**Options:**

- `--db-type TYPE` - Type of database: `sqlite` or `postgres` (default: `postgres`)

**Example:**

```bash
magentic-marketplace extract-traces my_experiment
```

**Generates:**

- Markdown files containing LLM interaction traces for each agent

---

### `audit` - Audit Marketplace Simulation

Audit marketplace simulation to verify customers received all proposals and check for issues.

**Usage:**

```bash
magentic-marketplace audit DATABASE_NAME [OPTIONS]
```

**Arguments:**

- `DATABASE_NAME` - PostgreSQL schema name or path to SQLite database file

**Options:**

- `--db-type TYPE` - Type of database: `sqlite` or `postgres` (default: `postgres`)
- `--no-save-json` - Disable saving audit results to JSON file

**Example:**

```bash
magentic-marketplace audit my_experiment --db-type postgres
```

**Checks:**

- Whether customers received all expected proposals
- Data consistency and integrity
- Agent behavior patterns

---

### `export` - Export PostgreSQL to SQLite

Export a PostgreSQL experiment to a SQLite database file for easier sharing and portability.

**Usage:**

```bash
magentic-marketplace export EXPERIMENT_NAME [OPTIONS]
```

**Arguments:**

- `EXPERIMENT_NAME` - Name of the experiment (PostgreSQL schema name)

**Options:**

- `-o, --output-dir DIR` - Output directory for SQLite database file (default: current directory)
- `-f, --output-filename FILE` - Output filename for SQLite database (default: `<experiment_name>.db`)
- `--postgres-host HOST` - PostgreSQL host (default: `localhost`)
- `--postgres-port PORT` - PostgreSQL port (default: `5432`)
- `--postgres-user USER` - PostgreSQL user (default: `postgres`)
- `--postgres-password PASSWORD` - PostgreSQL password (default: `postgres`)

**Example:**

```bash
magentic-marketplace export my_experiment \
  -o ./exports \
  -f my_experiment_export.db
```

---

### `list` - List All Experiments

List all marketplace experiments stored in PostgreSQL.

**Usage:**

```bash
magentic-marketplace list [OPTIONS]
```

**Options:**

- `--postgres-host HOST` - PostgreSQL host (default: `localhost`)
- `--postgres-port PORT` - PostgreSQL port (default: `5432`)
- `--postgres-database DB` - PostgreSQL database name (default: `marketplace`)
- `--postgres-user USER` - PostgreSQL user (default: `postgres`)
- `--postgres-password PASSWORD` - PostgreSQL password (default: `postgres`)
- `--limit N` - Maximum number of experiments to display

**Example:**

```bash
magentic-marketplace list --limit 10
```

---

### Common Workflows

**Run a new experiment and analyze it:**

```bash
magentic-marketplace run data/mexican_3_9 --experiment-name exp1
magentic-marketplace analyze exp1
```

**Run with custom settings and export:**

```bash
magentic-marketplace run data/mexican_3_9 \
  --experiment-name exp2 \
  --customer-max-steps 200 \
  --search-bandwidth 20 \
  --export \
  --export-dir ./results
```

**Analyze SQLite export:**

```bash
magentic-marketplace analyze ./results/exp2.db --db-type sqlite
```

**Full workflow with audit:**

```bash
magentic-marketplace run data/mexican_3_9 --experiment-name exp3
magentic-marketplace analyze exp3
magentic-marketplace audit exp3
magentic-marketplace extract-traces exp3
```

---

## Python API Usage

You can run experiments programmatically from Python scripts using the Python API.

### Basic Example

```python
import asyncio

from magentic_marketplace.experiments.run_analytics import run_analytics
from magentic_marketplace.experiments.run_experiment import run_marketplace_experiment


async def main():
    """Run a basic experiment and analytics."""
    experiment_name = "example_experiment"

    await run_marketplace_experiment(
        data_dir="data/mexican_3_9",
        experiment_name=experiment_name,
        customer_max_steps=100,
        override=True,
    )
    results = await run_analytics(
        experiment_name, db_type="postgres", save_to_json=False, print_results=False
    )

    print("Experiment and analytics complete.")
    print("Results: ", results)


if __name__ == "__main__":
    print("Running example experiment...")
    asyncio.run(main())
```

### API Functions

All Python API functions are async and should be called with `await` inside an async context.

**[`run_marketplace_experiment()`](reference/magentic_marketplace/experiments/run_experiment.md#magentic_marketplace.experiments.run_experiment.run_marketplace_experiment)** - Run a marketplace simulation

**[`run_analytics()`](reference/magentic_marketplace/experiments/run_analytics.md#magentic_marketplace.experiments.run_analytics.run_analytics)** - Analyze experiment results

**[`run_audit()`](reference/magentic_marketplace/experiments/run_audit.md#magentic_marketplace.experiments.run_audit.run_audit)** - Audit marketplace simulation

**[`run_extract_traces()`](reference/magentic_marketplace/experiments/extract_agent_llm_traces.md#magentic_marketplace.experiments.extract_agent_llm_traces.run_extract_traces)** - Extract LLM traces

**[`export_experiment()`](reference/magentic_marketplace/experiments/export_experiment.md#magentic_marketplace.experiments.export_experiment.export_experiment)** - Export PostgreSQL to SQLite

For complete API documentation, browse the [Reference](reference/magentic_marketplace/index.md) section.
