## What

Prevent `_update_cwd()` from overwriting `self.cwd` with Git Bash POSIX paths on Windows.

```diff
 tools/environments/local.py | 9 +++++++++
 1 file changed, 9 insertions(+)
```

## Why

On Windows, `_update_cwd()` reads a temp file written by Git Bash's `pwd -P` command.  
Git Bash always returns POSIX-style paths (`/d/djh/hermes`), which are **not** valid for `subprocess.Popen(cwd=...)`:

```
Before this fix:
  Terminal command 1 → works (uses correct initial cwd)
  _update_cwd() → sets self.cwd = "/d/djh/hermes" (POSIX)
  Terminal command 2 → WinError 267 (invalid cwd)

After this fix:
  Terminal command 1 → works
  _update_cwd() → strips marker from stdout, preserves original cwd
  Terminal command 2 → works
```

## Root cause chain

1. `LocalEnvironment.init_session()` sets `self.cwd` correctly (Windows path from config or detection)
2. After each command, `_update_cwd()` reads Git Bash's `pwd -P` output → POSIX path (`/d/...`)
3. POSIX path stored into `self.cwd` → next `subprocess.Popen(cwd=...)` fails

## Fix

On Windows, `_update_cwd()` still calls `_extract_cwd_from_output()` to strip the CWD marker from stdout (keeping output clean), but restores the original `self.cwd` instead of using the POSIX path from the temp file.

The `_IS_WINDOWS` constant already exists at `local.py:12` for other platform guards.

## Verification

- Windows 10/11 with Git Bash in non-standard path (e.g. `D:\...\Git\bin\bash.exe`)
- `TERMINAL_CWD` set in `.env`
- Multiple consecutive `terminal()` calls succeed (previously the second call failed)

## Alternatives considered

| Approach | Decision |
|----------|----------|
| Convert POSIX → Windows path in `_update_cwd()` | Rejected — fragile regex/mount-point mapping, breaks with MSYS2 mount changes |
| Skip `_update_cwd()` entirely on Windows | **Chosen** — simpler, correct, `self.cwd` is already valid |
