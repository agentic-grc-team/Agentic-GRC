# Coding standards

Use the existing conventions in the area you edit. Keep changes focused, and avoid formatting unrelated files in a feature PR.

## Frontend

- Use the shared Prettier configuration for JavaScript, JSX, CSS, HTML, and JSON. Use two-space indentation and double quotes in JavaScript.
- Run `npm run format -- src/path/to/file.jsx` from `frontend/` after editing a file. Run `npm run format:check` to check changed frontend files against `origin/main` plus uncommitted changes.
- Run `npm run lint`, `npm test`, and `npm run build` before requesting review. ESLint checks basic JavaScript errors and React Hook usage; existing Hook dependency warnings remain visible while they are addressed separately.
- The CI formatting check covers files changed in each PR, so existing files become consistently formatted as they are modified. This avoids a large unrelated formatting diff.

## Backend

- Follow the Python conventions in `backend/ruff.toml`. Run `ruff check .` and the relevant tests from `backend/` before requesting review. CI runs Ruff, migrations, and the full test suite.

Use peer review for naming, clarity, design decisions, and cases that automated checks cannot assess.
