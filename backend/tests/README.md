# AskLaw validation

Run the isolated backend suite without live infrastructure:

```bash
cd backend
.venv/bin/python -m unittest -v tests.test_document_workspace
```

For a live integration pass, start the full stack from the repository root:

```bash
./start.sh
```

Then use two newly-created test accounts and a small text-based PDF to verify:

1. signup, login, `/auth/me`, refresh, and unauthenticated rejection;
2. upload returns `uploaded`, `GET /documents` moves through `processing` to `indexed`;
3. document research streams an answer, sources, verification, and route events;
4. the second account cannot list, research, or delete the first account's document;
5. deleting the indexed document removes its MongoDB record and its Qdrant points;
6. normal, web, and hybrid chat still stream without a `document_id`.

Groq access is needed only for the live answer-generation checks. The unit suite
uses no Groq, MongoDB, Redis, Qdrant, SearXNG, or Celery network connection.
