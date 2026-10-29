# Action-Auto

Runner repo: only the GitHub Actions workflows live here. Code, app builds and results are
kept in a private repository and accessed through the `PRIVATE_REPO_TOKEN` secret.

Workflow: **Android Phase 1 - Guest to Lobby** (`.github/workflows/android-phase1.yml`). Start it from the Actions tab with *Run workflow*.

## 4B Multi Space

Code: private repo `4BornGithub/4b-multi-space` (all code, no workflows). The workflows
here build and test it; they read it with the `MULTISPACE_REPO_TOKEN` secret (a fine-grained
token with *Contents: read and write* on that repo; `PRIVATE_REPO_TOKEN` is used when the
first one is not set). Logs, screenshots and test reports go to branch `results` of the
private repo, APKs to its release `multispace-ci-<branch>`.

- **MultiSpace - build and unit tests** (`multispace-build.yml`): compiles all modules,
  runs the unit tests, builds debug/release APKs.
- **MultiSpace - emulator end-to-end** (`multispace-e2e.yml`): low (2 GB), mid and high-end
  emulators; clones a test app 3 times and checks each copy is isolated.
