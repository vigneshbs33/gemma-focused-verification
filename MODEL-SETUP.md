# Models, configuration and inference setup
11 November 2026.

## No training

The project compared inference-time selection procedures using existing models. It did not fine-tune Gemma or CodeRankEmbed, create a new checkpoint, train a new embedding model, generate repair patches or run repair tests. There is no project-trained model file to upload.

## Gemma inference used in the original experiments

- Repository: https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm
- Pinned revision: `3d48132a00cf76de57d926de30f5c5c5ed9b8c0d`
- Original weight filename: `gemma-4-E2B-it.litertlm`
- Weight SHA256: `181938105e0eefd105961417e8da75903eacda102c4fce9ce90f50b97139a63c`
- Runtime: LiteRT LM 0.19.1. Captured wheel SHA256: `93db43085401b208815a636150ae87576bb7e82adbada9f083ec16114dff8898`.
- Two CPU threads; context 1,536 tokens; raw prompt ceiling 960; output ceiling 12.
- Top-k 1, top-p 1.0, temperature 0, seed 42; thinking disabled.
- Per-call resource governor: 1,500 MiB RSS and 90 seconds. Captured numeric response and governor status are separate files.

These settings and hashes are preserved in the metadata and original call source. The model and runtime are not in this ZIP. Obtain upstream artifacts under their own terms and verify hashes rather than assuming a current default download is identical.

## Retrieval model

- Repository: https://huggingface.co/nomic-ai/CodeRankEmbed
- Pinned revision: `3c4b60807d71f79b43f3c4363786d9493691f8b1`
- Weight SHA256: `827529bcd58aef0d9082e66eeff7e7d53a02f62bd005f841a26b3d3e2fb17ebe`.
- FP32, normalized raw CLS, batch one, query limit 512, candidate limit 256, two CPU threads.
- Lexical pool limited to 320 candidates; fusion selects 20. This is bounded reranking, not exhaustive dense search of the entire repository.
- The original embedding source imports PyTorch and Transformers and uses reviewed model-specific code. Those libraries and third-party model code are not bundled here. See `earlier-study-complete/CODERANK-PROVENANCE-RECOVERED.json` for captured upstream file hashes.

## Data

- Source: https://huggingface.co/datasets/SWE-bench/SWE-bench
- Pinned full-test revision: `c6fe717fd7a4c3ac1daa4055a4fd082c6a1d28a2`.
- Captured Parquet SHA256: `d4f5a245c75319fa8240c540674958c4d491e82edf274b144d43836bdcbc4567`.
- Raw issues, patches and source trees are not bundled. Selected task IDs, repositories, base commits and input hashes are retained in cohort metadata.
- Prior development/Lite/earlier-study exclusions and duplicate checks are documented in the paper and captured qualification metadata. They do not establish globally unseen data or freedom from model-pretraining exposure.

## Running the verification and setting up inference

`python verify_evidence.py` runs offline with Python's standard library. Its package-integrity, captured-call, decision-replay and earlier-score checks were actually run. No inference is required.

The original scientific `.py` files are genuine source snapshots, not a freshly built portable distribution. Their syntax was parsed successfully during packaging. They were not executed as new model tests during packaging.

For end-to-end inference, `run_study.py` and `evaluate_verifier.py` require the original inputs and dependencies described below. They retain original directory assumptions and expect files intentionally absent from this package, including prepared source records, raw issue projection, patch/source archives, input prompt packs/call records, tokenizer caches, model/runtime files, and complete final output/label freezes. Some helper imports also refer to their original project locations; the recovered scorer/window helpers are supplied separately for inspection, not silently substituted into frozen code.

A complete inference reproduction would require restoring those inputs and dependencies, placing the original helper modules on their expected import paths or explicitly documenting path-only adaptations, validating source/model/input hashes and preparing all records under the frozen protocol. It would then require new CPU inference. None of those absent steps is claimed as completed by this upload.

## Later comparisons

The paper also reports an exploratory CodeSage-small-v2 comparison and a failed Qwen3-Embedding-0.6B resource gate. Their aggregate values are described in the paper; the offline verifier covers the captured records listed in README.md. No accuracy result is assigned to the failed Qwen gate. The current package must not be described as a matched reproduction of the strongest published systems.
