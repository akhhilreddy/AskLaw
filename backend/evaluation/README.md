# AskLaw evaluation harness

The curated cases cover document, web, hybrid, isolation, and claim-support
behavior. The harness prints individual observations and counts; it deliberately
does not manufacture an aggregate accuracy percentage.

Offline routing and deterministic verification evaluation:

```bash
cd backend
.venv/bin/python evaluation/run_evaluation.py
```

Live retrieval evaluation against an already-running local stack:

```bash
cd backend
.venv/bin/python evaluation/run_evaluation.py --live \
  --user-id USER_ID \
  --other-user-id SECOND_USER_ID \
  --document-id DOCUMENT_ID \
  --expected-filename document.pdf
```

The live mode reports whether retrieval returned evidence, the selected route,
source filenames, expected-source presence, and document-isolation behavior.
It does not call Groq or claim that an answer is legally correct.
