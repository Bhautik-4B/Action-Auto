# Action-Auto

Runner repo: only the GitHub Actions workflows live here. Code, app builds and results are
kept in a private repository and accessed through the `PRIVATE_REPO_TOKEN` secret.

Workflow: **Android Phase 1 - Guest to Lobby** (`.github/workflows/android-phase1.yml`). Start it from the Actions tab with *Run workflow*.

## 4bTech Space

Code: private repo `4BornGithub/4b-multi-space` (all code, no workflows). The workflows
here build and test it. They use the first of the secrets `MULTISPACE_REPO_TOKEN`,
`PRIVATE_REPO_TOKEN`, `PROJECTS_TOKEN` that can read that repo (one with write access is
preferred); the step "Pick a token" lists which secret can do what. Logs, screenshots and test reports go to branch `results` of the
private repo, APKs to its release `multispace-ci-<branch>`.

- **4bTech Space - build and unit tests** (`multispace-build.yml`): compiles all modules,
  runs the unit tests, builds debug/release APKs.
- **4bTech Space - release APK** (`multispace-release.yml`): one universal release APK,
  uploaded to release `APK` of Game-Auto as `4bTech-Space-<version>.apk` / `4bTech-Space.apk`.
- **4bTech Space - end-to-end on Android (ARM)** (`multispace-e2e.yml`): real arm64 Android
  8.1, 9, 10, 11, 13 and 15 (Redroid containers on `ubuntu-24.04-arm` runners) with 2 GB / 4 GB / 6 GB
  memory limits; clones a test app 3 times and checks each copy is isolated.

## SMM Vault board

**SMM Vault board** (`smm-vault-board.yml`) keeps the project board
https://github.com/users/4BornGithub/projects/34 in step with the SMM Vault work
(`4BornGithub/smm-vault_mech`). Card requests (create, edit, status, assign, fields, comment,
convert to issue, archive) go into `smm-vault/requests.json` on branch `board` of the
private repository `Bhautik-4B/Game-Auto`; *Run workflow* applies them with `PROJECTS_TOKEN`
and saves the outcome (`last-run.json`, `history.json`) and a copy of the board (`board.json`,
`board.md`) next to it. Every 3 hours it refreshes the copy only. The request format is at the
top of `.github/scripts/board_ops.py`. No card text is printed in the log.
