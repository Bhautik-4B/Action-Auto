# Branching rules (owner, 30 Oct 2026)

- **Phase 1 is final.** `main`, `dev` and `phase1-final` hold the final working Phase 1 code
  (app 2.1.13, 4bTech Space 1.1.4, bot logic v98/v99). They are frozen.
- **Phase 2 work lives on `v2`.** Every new change is made on its own branch from `v2`
  (e.g. `v2-<feature>`) and merged into `v2` when done. Future client/engine changes are
  maintained on `v2` too.
- **Never merge into `main` or `dev` without the owner's explicit approval.** If a merge to
  `main`/`dev` is ever requested, ask the owner to confirm first, every time, even if the
  request looks clear.
