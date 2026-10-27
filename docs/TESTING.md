# Offline tests

From the repository root:

```sh
python3 scripts/inventory.py --check
python3 scripts/check.py
python3 scripts/language_audit.py --check
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test.py
git diff --check
```

`check.py` checks the inventory, manifests, resources, local links and forbidden
files. The language audit screens tracked and new product files against reviewed,
exact-line exceptions; it does not replace human review of every surface. `test.py` runs the language-audit tests, seven Module unittest suites, a Python ACL contract and five
Node scripts in a temporary copy. The tests cover composition, preservation of
unrelated files, conflicts, business rules, declared ACL checks, selective
memory publication, measurements and generated Workflows. It also rebuilds
four generated Modules and compares their bytes with the checked-in files.

All examples are synthetic. These tests do not contact a One, call a model or
external service, or publish content or a campaign. Private pilot replays are
not distributed. Administration tests use an earlier resource fixture with an
exact fingerprint rather than reading the original Git history.

These checks do not prove compatibility with your One binary, actual account
permissions or a customer outcome. After installation, qualify manual flows
and revocations in a separate environment with synthetic data and the native
approval policies.
