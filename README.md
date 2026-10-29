# Action-Auto

Runner repo: only the GitHub Actions workflows live here. Code, app builds and results are
kept in a private repository and accessed through the `PRIVATE_REPO_TOKEN` secret.

Workflow: **Android Phase 1 - Guest to Lobby** (`.github/workflows/android-phase1.yml`). Start it from the Actions tab with *Run workflow*.

## 4B Multi Space

Code: private repo `4BornGithub/4b-multi-space` (all code, no workflows). The workflows
here build and test it. They use the first of the secrets `MULTISPACE_REPO_TOKEN`,
`PRIVATE_REPO_TOKEN`, `PROJECTS_TOKEN` that can read that repo (one with write access is
preferred); the step "Pick a token" lists which secret can do what. Logs, screenshots and test reports go to branch `results` of the
private repo, APKs to its release `multispace-ci-<branch>`.

- **MultiSpace - build and unit tests** (`multispace-build.yml`): compiles all modules,
  runs the unit tests, builds debug/release APKs.
- **MultiSpace - end-to-end on Android (ARM)** (`multispace-e2e.yml`): real arm64 Android
  11, 13 and 15 (Redroid containers on `ubuntu-24.04-arm` runners) with 2 GB / 4 GB / 6 GB
  memory limits; clones a test app 3 times and checks each copy is isolated.
