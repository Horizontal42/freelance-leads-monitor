# Project Guidelines & Rules

## 1. Git Commit Granularity and Standards
- **Strict Rule:** 1 commit = 1 major feature OR a few small, strictly logically connected changes.
- Never bundle multiple independent features or unrelated fixes into a single monolithic commit.
- If a user prompt requests multiple independent changes (e.g. parser fix + new bot buttons + dashboard filter), commit them incrementally as separate, atomic commits.
- Follow the Conventional Commits specification:
  - `feat(...)`: new feature or enhancement
  - `fix(...)`: bug fix
  - `refactor(...)`: code restructuring without behavior changes
  - `test(...)`: adding or updating tests
  - `docs(...)`: documentation changes
  - `chore(...)`: maintenance, dependencies, configuration
- Every commit must leave the codebase in a working state where all tests pass.

## 2. Typography & Communication Style
- **Strict Prohibition on Em-Dashes:** Never use em-dashes (`—`). Always use regular hyphens (`-`).
- Keep responses concise, clear, and focused on results.
- Always provide clickable links to modified or created files using markdown links with the `file://` scheme.

## 3. Verification & Quality Assurance
- Always run the test suite (`pytest`) before committing.
- Ensure 100% test passing rate and zero regression before pushing.

## 4. Background Tasks & No-Polling Policy
- **Strict Prohibition on Task Polling:** Never poll the status of background tasks or commands in a loop (e.g. repeated calls to `manage_task(Action='status')` or rapid sleep checks).
- Launch background tasks/commands and immediately conclude turn or proceed to other independent work. The system will deliver a message notification when the task completes.
