# LLM Provider
To make LLM calls, you need to set a `LLM_PROVIDER` and `LLM_MODEL`. Make a copy of [sample.env](./sample.env) and set your API keys, model provider, and model.

```
cp sample.env .env
```

# Database debugging
To see the postgres database, you can use `pgadmin` in your local browser. 

Go to [http://localhost:8080/](http://localhost:8080/).
- Account: admin@example.com
- Password: admin

# Troubleshooting
- With large simulations on linux, the default number of sockets might be taken up. You can see this value with `ulimit -n` and up it with `ulimit -n 60000`
