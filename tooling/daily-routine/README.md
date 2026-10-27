# Daily routine — cib-daily-routine

This Module is composed into each of the three roles. It prepares the daily
context, retrieves a selected memory revision and a case, and records declared
active time. Human time, machine waiting time and assistance remain separate.
No gain is calculated without a comparable baseline.

```sh
python3 tooling/daily-routine/compose.py --consumer-dir /path/to/consumer
python3 tooling/daily-routine/compose.py --consumer-dir /path/to/consumer --write
```

Each role must already have `<role>-read` and `company-memory-query`: compose
the role, memory and their integration before the routine. The composer
preserves unrelated files and refuses unknown divergence. The native storage
owner, access to measurements and the published surface must be configured in
the consumer; a form does not grant permission. Measurement files are not a
multi-writer ledger with row ACLs or transactional synchronization.

From Home, open the Application and the authorized role's
`daily-context-console`, `daily-report-console` and `daily-time-console`.
Record observed duration and difficulties; an absent duration remains unset.
The Module schedules no task and produces no external business effect.
See [installation](../../docs/INSTALLATION.md) and [tests](../../docs/TESTING.md).
