# Work cases and Management — cib-work-dossiers

This shared case Module records an objective, operational owner, references,
next action, blocker and evidence of internal closure. Management receives only
records accessible to the authenticated person.

```sh
python3 tooling/work-cases/compose.py --consumer-dir /path/to/consumer --owner-alias veille
python3 tooling/work-cases/compose.py --consumer-dir /path/to/consumer --owner-alias veille --write
```

The owning Agent must be initialized. The server must provide the human broker
`recipe--application_data_v1`, per-record ACLs and revision CAS. Data is held
in the native `cib-cases` partition and is private by default. The `usage` and
`qualification` sets separate real work from synthetic data.

Selection rereads the record and prefills the form; writing uses the expected
revision. The owner can share a record for reading or writing with an existing
member and revoke that permission. A writer cannot reshare. Declared titles
and owners confer no permissions. Internal closure requires evidence and
review; it does not attest external delivery or commitment.

The composer refuses unknown divergence. See [installation](../../docs/INSTALLATION.md),
[permissions](../../docs/SECURITY.md) and [tests](../../docs/TESTING.md).
