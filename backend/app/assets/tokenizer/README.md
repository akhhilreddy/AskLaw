# Offline research token counter

`o200k_base.tiktoken` is the mergeable-rank vocabulary used by tiktoken 0.12.0
for both o200k_base and o200k_harmony ordinary text (GPT-OSS). Source:
https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken

Expected SHA-256, pinned by the upstream tiktoken 0.12.0 constructor:
`446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d`.
Constructor: https://github.com/openai/tiktoken/blob/0.12.0/tiktoken_ext/openai_public.py

The app reads this bundled file and checks its hash; it never fetches vocabulary
or model weights at runtime. Special-token-looking source text is encoded as
ordinary text, not interpreted as chat control tokens. Local text counts are
exact for this vocabulary; chat-template/server overhead is an explicit allowance,
not a claim that local totals equal Groq's billed usage.

Upstream license is included in `LICENSE`.
