# Gemma Focused Verification

CPU-only candidate verification for software issue localization. Companion implementation for "Focused candidate verification for CPU-only software issue localization".

## Method and implementation

Given a software issue and existing candidate code symbols, the project compares pointwise Gemma relevance scoring against fixed-rotation tournament selection. It chooses an existing class or function; it does not generate or test a repair. No model was trained.

- **V20:** score 20 candidates separately with a 0-3 relevance rubric, then rank by score and semantic rank. Abstain if every score is zero or invalid.
- **T20:** four fixed-rotation tournaments over the same candidates, then vote among non-null winners.
- **T5:** reuse the first T20 rotation.
- **Dense1:** choose the top dense-cosine candidate without Gemma selection calls.

Retrieval uses a lexical top-320 pool, CodeRankEmbed and equal-channel reciprocal-rank fusion (constant 60) to select 20 candidates.

Original source files remain at their original relative paths:

- `current-study-captured/code/`: candidate preparation, source windows, prompts, model calls, scoring, evaluation and audits for the focused-verification study. Start with `method.py`, `prepare_candidates.py`, `prepare_packs.py`, `run_arm.py`, `run_study.py` and `evaluate_verifier.py`.
- `earlier-study-complete/code/`: source for the separate earlier structural-rescue experiment.
- `source-dependencies/`: original scorer and packing helpers.
- `MODEL-SETUP.md`: pinned model/runtime settings, data provenance and inference prerequisites. These original research scripts retain their original paths and require the listed models, data and runtime; this repository is not a one-command inference installation.

## Reported results and captured records

The reported current-study result on 60 evaluation tasks is V20 15/60 versus T20 10/60, T5 11/60 and Dense1 12/60. V20 minus T20 is +8.33 percentage points, with task-bootstrap 95% interval [-1.67, +18.33]. This is an observed gain, not demonstrated superiority. Both V20 and T20 use 20 calls per task, not equal compute. Relative to T20, reported V20 prompt tokens are 41.1% lower and measured generation time 31.7% lower; these are not end-to-end runtime or monetary savings. See `reported-final-aggregates.json` and `reported-final-audit-summary.json`.

The records include 480 current-study development outputs, 786 evaluation outputs, 12 completed development receipts, 19 completed evaluation receipts and rankings for all 72 selected tasks. They support captured-record checks and completed-receipt replay, not reproduction of the complete reported current-study result. The earlier experiment is separate and includes 192 development outputs, 960 evaluation outputs and 60 evaluation receipts with derived labels; its exact-success counts recompute to plain 11/60, semantic 16/60, structural 14/60 and fielded 12/60.

`records/captured-records-*.json` groups the original UTF-8 records by relative path and exact text. These lossless JSON collections keep the repository manageable for browser upload; they are not new measurements. `PROVENANCE.json` retains the original research-package provenance. No model weights, raw issue text, patches, repository source trees, full prompts or runtime wheels are redistributed. Upstream artifacts retain their own terms; this packaging does not make a new license election.

## Optional reviewer tooling

With Python 3.10+, `python tools/check_records.py` restores the logical record layout in a temporary folder and runs the supplied offline checker. It checks manifests, captured resource fields, response parsing and completed-receipt decisions, without model loading, inference or network requests. A passing check establishes consistency against supplied manifests, not independent timestamp authenticity or source/patch re-derivation of labels. These tools were written for packaging on 11 November 2026 and are not the experimental implementation or experimental results.
