# Phase 2 implementation coverage

This matrix maps `Bank_Loan_Processing_Phase2_Review2_Enhancements.pptx` to the repository. “Implemented” means the code path is usable now. “Adapter ready” means a real tenant, provider, credential, or governed dataset must be supplied before the feature can return real results.

| Deck requirement | Status | Implementation |
| --- | --- | --- |
| Governed, de-identified train/validation/test data | Implemented workflow | `models/prepare_governed_dataset.py` removes direct identifiers, creates reproducible stratified splits, and writes a source hash manifest. |
| Calibrated supervised baseline | Implemented workflow, labels required | `models/train_credit_model.py` trains a calibrated logistic baseline and records ROC AUC, Brier score, and accuracy. It cannot run responsibly without labelled data. |
| SHAP attributions and side-by-side reasons | Adapter ready | `backend/explainability.py` returns scorecard reasons and SHAP values after a validated artifact exists and the optional ML requirements are installed. |
| Live Isolation Forest fraud model | Implemented | The existing artifact runs during every score. Feature coverage controls its contribution, and its version appears in agent traces. |
| JWT, password security, and RBAC | Implemented | Scrypt password hashes, signed short-lived JWTs, bootstrap flow, optional mandatory auth, and officer/admin/auditor role dependencies. OIDC tenant validation remains provider-specific. |
| Encryption and audit controls | Implemented | Raw payloads, evidence, queries, agent output, overrides, and audit details use encrypted database types. Agent runs and overrides create audit events. |
| Background OCR/batch work | Implemented local worker | `/upload/async` persists job state and runs intake outside the request. The worker interface can move to Celery/RQ for multi-host deployment. |
| Retention/deletion controls | Implemented | Retention policy and dry-run/enforcement endpoints cover audit events and completed jobs. Application deletion stays subject to lender records policy. |
| Drift and model registry | Implemented | Governance endpoints expose standardized feature-shift monitoring and version/stage metadata for each scoring component. |
| Credit-bureau integration | Adapter ready | A verification-only adapter is disabled until a bureau URL/token is configured. It never silently substitutes unverified values. |
| Optional external LLM | Adapter ready | A clearly labelled narrative-only adapter accepts only a verified grounded report and never changes scoring or policy output. |
| Human override and adverse-action reasons | Implemented | Officers record status changes and reasons; notices expose versioned reason codes and model versions. |
| Fairness/disparate impact | Implemented monitoring | An allowlisted protected-attribute report computes group selection rates and the 80% review threshold with minimum-sample warnings. Protected attributes do not enter supervised features. |
| Agentic document handling | Implemented | PDF and image intake invokes OCR/classification/extraction. The document specialist reports missing, stale, and low-confidence evidence. |
| Agentic policy RAG | Implemented | A versioned local lending-policy corpus is retrieved and cited by the compliance agent. |
| Hybrid RAG and reranking | Implemented | BM25 and 384-dimensional local embeddings use reciprocal-rank fusion, structured-field boosts, intent metadata filters, and top-K reranking. PostgreSQL uses pgvector HNSW. |
| Source/page/section citations | Implemented | Evidence chunks preserve document source, page, section, document type, lexical rank, semantic rank, and final score. |
| Specialist agents and safety | Implemented | Planner, retriever, document specialist, fraud investigator, risk tool, compliance agent, answer writer, and verifier emit an encrypted trace. Document instructions are untrusted and prompt-injection phrases are flagged. |
| RAG/model evaluation | Implemented | Backtests persist Hit/Recall@K, MRR, groundedness, citation accuracy, hallucination, contradiction, latency, verification, and decision metrics. |

## Additions beyond the deck

- pgvector has a SQLite cosine fallback, so the same agent APIs work in tests and offline demonstrations.
- Evidence and audit payloads remain encrypted even though embeddings are indexed for similarity search.
- Upload allowlisting and configurable file-size limits reduce intake abuse.
- Prometheus HTTP metrics, structured JSON logs, search, pagination, CSV export, and mobile agent UI remain available.
- Agent approvals fail closed: if grounding verification fails, an approval becomes manual review.

## Important deployment boundaries

- The agent is advisory. `decision_authority` is the deterministic policy engine, and an authorized officer records the final decision or override.
- The bundled policy corpus is a software baseline, not legal validation. A lender’s compliance team must approve policy text, thresholds, reason codes, retention, and notices.
- OIDC/SSO needs issuer-specific token validation. Credit bureau and narrative LLM calls need contracted providers and secrets.
- Supervised calibration, SHAP stability, and fairness conclusions require a governed labelled dataset with adequate group sizes.
