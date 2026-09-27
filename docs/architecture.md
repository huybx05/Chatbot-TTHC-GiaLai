# Architecture

This project starts with a compact modular-monolith skeleton.

Offline data pipeline:

```text
crawler -> parser -> normalizer -> validator -> indexing
```

Online flow, later:

```text
FastAPI -> service -> fact lookup / retrieval / graph -> evidence -> answer
```
