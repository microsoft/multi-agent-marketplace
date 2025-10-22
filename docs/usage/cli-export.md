# `export`: Export results

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
