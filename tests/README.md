# Regression checks

Run from the repository root:

```sh
python -m unittest discover -s tests -v
node tests/frontend_recovery.cjs
```

Uses Python standard-library and Node built-in modules. Python tests use temporary directories, no movie API token, and local HTTP servers. Frontend tests execute the actual inline script with simulated responses dropped after an accepted action. Production data is untouched.
