# Known limitations

## Deterministic title fit

Title fit is a token heuristic, not an org-chart or synonym model. Contact-title
modifiers (`intern`, `assistant`, `associate`, `junior`, `former`, `ex`, and
`student`) cap the result at 20, and seniority-only overlap does not earn the
influencer score. Other modifiers, unusual title spellings, abbreviations,
regional conventions, and genuine role equivalences may still be misclassified.
No external title dictionary or LLM is consulted.

## Local page embeddings

MiniLM-L6 has a model `max_seq_length` of 256 word pieces and silently truncates
longer inputs. Page text is split on whitespace into chunks of about 800
characters; at most six chunks are embedded, averaged, and renormalized. Text
after the sixth chunk is omitted, and averaging loses chunk order and local
context. An individual unusually long token can also exceed the approximate
character target before the model's token limit is applied.

The embedding model is loaded lazily. A failed model load is not cached, so a
later request tries loading again; when the model is not cached and the machine
is offline, repeated requests can incur model-hub timeouts before scoring falls
back to a partial result. This repeated-load behavior is accepted. Set
`HF_HUB_OFFLINE` in the shell before starting Python if an offline load is
intended; changing it after importing the embedding/model libraries may be too
late for their network configuration.
