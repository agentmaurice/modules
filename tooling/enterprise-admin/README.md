# Administration — cib-enterprise-admin

This Module provides bounded inspection and administration of people, existing
identities, service access and mandate revocations. It uses
`recipe--company_admin_v1` and `recipe--application_data_v1` with the human
identity resolved by the server, never an identity supplied by a form.

```sh
python3 tooling/enterprise-admin/compose.py --consumer-dir /path/to/consumer --owner-alias veille
python3 tooling/enterprise-admin/compose.py --consumer-dir /path/to/consumer --owner-alias veille --write
```

The human Application route and native brokers are prerequisites. The
`cib_admin`, `cib_marketing`, `cib_service_client`, `cib_direction` and
`cib_dossiers` profiles must be linked to existing people and `required_role`
gates. `service_roles.py` prepares a surface draft; it does not apply it and
refuses conflicting existing permissions.

The Module does not create accounts, send invitations or sign mandates. Changes
are explicit and require confirmation. Form confirmation replaces neither IAM
nor native approval. `cib-admin-approval-check` is a local read with
`require_approval`; only the authorized person may approve it in AM.

Historical record operations are individual, using a known namespace, key and
revision; there is no universal listing of private bodies, bulk transfer or
bulk sharing. `admin_recovery` remains restricted to sharing and is revalidated
by the server. Known 0.2.1 and 0.2.2 resources can be replaced by exact fingerprint; any
other divergence is a manual conflict. Inherited records stay private under
their custodian until explicit sharing is decided.

See [installation](../../docs/INSTALLATION.md), [permissions](../../docs/SECURITY.md)
and [tests](../../docs/TESTING.md).
