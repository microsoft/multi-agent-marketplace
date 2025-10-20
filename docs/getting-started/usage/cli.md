# Command Line Usage

Magentic Marketplace provides a command-line interface for running experiments and analyzing results with the `magentic-marketplace` command.

- [`magentic-marketplace run`](#run-run-a-marketplace-experiment) to run an experiment
- [`magentic-marketplace analyze`](#analyze-analyze-experiment-results) to analyze the results
- [`magentic-marketplace export`](#export-export-results) to export results to shareable file
- [`magentic-marketplace list`](#list-list-all-experiments) to list all experiments
- [`magentic-marketplace ui`](#ui-launch-a-marketplace-ui) to launch the ui

See all the available commands and options with `magentic-marketplace --help`.

## `run`: Run a marketplace experiment

Run a marketplace simulation using YAML configuration files. You must provide the path to a directory with `/businesses` and `/customers` subdirectories that contain YAML files. See the [data](https://github.com/microsoft/multi-agent-marketplace/tree/main/data) folder in our repo for examples.

**Usage:**

```bash
magentic-marketplace run data/mexican_3_9 --experiment-name my_experiment
```

**Common arguments:**

`data_dir` _(required)_

&nbsp;&nbsp;&nbsp;&nbsp;Path to the data directory containing `businesses/` and `customers/` subdirectories

`--experiment-name` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Name for this experiment. If not provided, a unique name will be generated.

`--override-db` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Override the experiment with this name if it exists.

`--search-algorithm` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Search algorithm for customer agents (default: `lexical`).

`--search-bandwidth` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Search bandwidth for customer agents (default: `10`).

`--customer-max-steps` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Maximum number of steps a customer agent can take before stopping (default: `100`).

**Additional options:** See additional arguments with `magentic-marketplace run --help`.

## `analyze`: Analyze experiment results

After an experiment finishes, you can analyze the results with this command. By default it will print out analytics and save them to a json file.

**Usage:**

```bash
magentic-marketplace analyze my_experiment
```

**Common arguments:**

`experiment-name` _(required)_

&nbsp;&nbsp;&nbsp;&nbsp;Experiment name (PostgreSQL schema name).

`--db-type` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Type of database: `sqlite` or `postgres` (default: `postgres`). For postgres, the experiment name is the name of a schema in the database. For sqlite, it is the path to a database file.

`--no-save-json` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Disable saving analytics to JSON file

## `export`: Export results

Export a PostgreSQL experiment to a SQLite database file for easier sharing and portability.

**Usage:**

```bash
magentic-marketplace export my_experiment
```

**Common arguments:**

`experiment_name` _(required)_

&nbsp;&nbsp;&nbsp;&nbsp;Experiment name (PostgreSQL schema name).

`-o, --output-dir` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Output directory for SQLite database file (default: current directory).

`-f, --output-filename` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Output filename for SQLite database (default: `<experiment_name>.db`).

## `list`: List all experiments

List all marketplace experiments stored in PostgreSQL.

**Usage:**

```bash
magentic-marketplace list --limit 10
```

**Common arguments:**

`--limit` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Limit the number of experiments to display.

## `ui`: Launch a marketplace UI

Launches a marketplace visualizer in the browser, defaults to [http://localhost:5000/](http://localhost:5000/). You can use this ui to explore customer and business conversations after an experiment has finished or while an experiment is running.

**Usage:**

```bash
magentic-marketplace ui my_experiment
```

**Common arguments:**

`experiment_name` _(required)_

&nbsp;&nbsp;&nbsp;&nbsp;Experiment name (PostgreSQL schema name).

`--db-type` _(optional)_

&nbsp;&nbsp;&nbsp;&nbsp;Type of database: `sqlite` or `postgres` (default: `postgres`). For postgres, the experiment name is the name of a schema in the database. For sqlite, it is the path to a database file.
