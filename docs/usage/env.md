# Environment Setup

When you clone the repo there is a sample environment setup in `sample.env`. You can configure variables for the models used in your simulation, your database, and to control the level of concurrency.

### Required Model Configuration

- API keys
- `LLM_PROVIDER` sets the api (options are `"openai"`, `"gemini"`, `"anthropic"`)
- `LLM_MODEL` sets the model (e.g. `"gpt-4.1"`)

### Optional Extra Model Configuration

- `LLM_REASONING_EFFORT` controls the depth of reasoning for models that support it (options: `"minimal"`, `"standard"`, `"high"`)
- `LLM_TEMPERATURE` controls response randomness
- `LLM_MAX_TOKENS` sets maximum tokens generated per response
- `LLM_MAX_CONCURRENCY` limits concurrent requests happening at once to prevent rate limiting

### Database Setup

There are several variables in the `sample.env` that must be set to determine database login. We encourage you to use the defaults. In addition you can set:

- `POSTGRES_MAX_CONNECTIONS` limits the number of simultaneous connections in the pool

## FAQ

- **_How can I prevent rate limiting errors?_**

  Try reducing the `LLM_MAX_CONCURRENCY` to something like 10 (setting to 1 means that each LLM call will happen sequentially).

- **_How can I fix errors related to too many database connections?_**

  Try reducing your `POSTGRES_MAX_CONNECTIONS`.

- **_How can I run more simulations in parallel with the same database?_**

  Try reducing your `POSTGRES_MAX_CONNECTIONS`.
