# Releasing

## PyPI (enables `uvx localrank`)

One-time: create an API token at https://pypi.org/manage/account/token/

```bash
uv build
uv publish --token pypi-XXXX
```

Note: the distribution is currently named `localrank-mcp`. To make plain
`uvx localrank` work, rename `[project] name` in `pyproject.toml` to
`localrank` before the first publish (both console scripts — `localrank`
and `localrank-mcp` — ship either way). Existing
`uvx --from git+...` commands keep working regardless.

After the first PyPI publish, flip `PACKAGE_SPEC` in
`npm/bin/localrank.js` from the git URL to the PyPI name so the npm
wrapper resolves the published package (faster, versioned).

## npm (enables `npx localrank`)

One-time: `npm login` (or set `NPM_TOKEN`).

```bash
cd npm
npm publish
```

Bump `version` in `npm/package.json` on every publish. Keep it in sync
with the Python package version when possible.
