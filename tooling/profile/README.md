# Company profile — cib-profile 0.1.0

The company profile is the identity and brand of a company, entered once and
used by every generated document: legal name, trade name, legal form, capital,
SIREN/SIRET, VAT number, RCS, address, contact details, legal mentions,
optional bank details, and the brand (six colours, three font families, a logo
reference and the page size and margins). The Module stores it as **one
Application record** and projects it as the `{ company, brand }` pair of the
`agentmaurice.template/v1` contract.

| Item | Value |
|---|---|
| Module key | `cib-profile` (directory `profile`) |
| Record | namespace `cib-profile`, key `company-profile`, through `recipe--application_data_v1` |
| Query `read` | Workflow `cib-profile-read`: the body, the `{ company, brand }` projection, a colour preview, the revision and the permissions |
| Action `save` | Workflow `cib-admin-profile-save`: save with `expected_revision`, `cib_admin` only, `confirmation_manuelle` = `true` |
| App `profile-console` | MiniApp `cib-profile-console`: company and brand fields, colour preview, logo by `storage://` reference |

## Stored body and projection

The body is `{ "schema_version": 1, "company": {...}, "brand": {...} }`. It maps
onto the contract without transformation: `body.company` is `company` and
`body.brand` is `brand` (`tokens.schema.json`). The only derived value is
`company.logo`, set at read time to `{ "ref": brand.logo.ref }`. The logo has a
**single source**, `brand.logo` (`ref` and `alt`); a body that carries its own
`company.logo` is refused. `company.bank` (`account_holder`, `iban`, `bic`,
`bank_name`) is optional. IBAN and BIC are normalised (upper case, no spaces)
and checked by shape (15 to 34 characters for the IBAN); no check digit is
computed.

The save Workflow validates strictly and the read Workflow validates the stored
body again, so a record written by something else is refused rather than
projected. A stored body is projected as it is, never rewritten: if it is not already canonical
(trimmed, no empty value, IBAN and BIC normalised) the read fails with
`stored_body_not_canonical`. The projection adds nothing but `company.logo`. A save needs an explicit `expected_revision` (`0` to create); a
conflict is the broker's answer and is not retried.

## Contract copy

`contract/` holds a frozen, byte-for-byte copy of `namespaces.schema.json` and
`tokens.schema.json` (including `company.bank`), pinned in `contract/PIN.json`
by SHA-256 and by the commit of the contract repository that introduced them.
The tests validate the fixtures and every projection against this copy. To
follow a contract change, copy the new files in a reviewed change and update the
pin; the SHA-256 values are authoritative if the source commit is rewritten.

## Roles

Workflow roles live in the published Application surface, not in the manifest,
and the platform checks them at admission; the broker revalidates the required
role. The Workflow code receives no caller identity and cannot check a role
itself, so it ignores any role sent in its input. A person who has write access
to the record but not the `cib_admin` role is refused only if the surface says so.

`compose.py --write` therefore also writes a **surface draft**,
`<consumer>/surface-drafts/cib-profile.surface-draft.json`, that carries
`required_role: cib_admin` explicitly on `cib-admin-profile-save` (from
`service-gates.json`) and none on `cib-profile-read`. Merge it into the surface
you review, then publish the surface yourself; compose publishes nothing and
refuses a divergent existing draft. The `cib-admin-` name still lets
`tooling/enterprise-admin/service_roles.py` agree, but the gate no longer
depends on that convention. The role, the form confirmation and the broker ACL
are cumulative; none replaces another, and the identity comes from the server.

## How document-studio reads the profile

`document-studio` calls `recipe--application_data_v1` with operation `read`,
namespace `cib-profile` and key `company-profile`, then uses `company` and `brand`
of the projection (or calls the `read` query). Its Agent therefore needs the
namespace `cib-profile` in its allowlist for that broker, and the person running
the generation needs read access on the record. A saved profile is not touched
by the studio.

## Limits

- **Broker not wired (AGENT-1305).** `recipe--application_data_v1` is not wired
  in the One yet. This Module is code and offline tests on fixtures: it has not
  run on a One. Only the broker's explicit `NOT_FOUND` code (taken from the
  unmerged AGENT-1305 broker source, not from the wiki, which names none) means
  "no profile yet"; `permission_denied`, an empty or record-less response and any
  other error are explicit errors. How the sandbox surfaces that code is to be
  qualified when the broker exists.
- **Sharing is per person.** A record is private to its owner until the owner or
  a recovery administrator shares it with each person (`read` or `write`). There
  is no "everyone in the company" read with the current broker, and this Module
  does not work around it. `cib-admin-record-share` lists only four historical
  namespaces, so `cib-profile` is not shareable through it today either.
  Until a per-company read exists, a document is generated by a person who can
  read the record.
- **No logo upload.** The logo is a `storage://` reference to a file that is
  already in Storage. Uploading or converting a logo is out of scope.
- **No legal format.** No Factur-X or Peppol format is produced or validated. Bank
  details and identifiers are stored and projected as entered, checked by shape
  only.
- **Colour preview** is a table (token, hex, contrast against the background);
  no swatch component is used.

## Composition and tests

```sh
python3 tooling/profile/build.py
python3 tooling/profile/compose.py --consumer-dir /path/to/consumer --owner-alias admin
python3 tooling/profile/compose.py --consumer-dir /path/to/consumer --owner-alias admin --write
```

`build.py` generates the three resources and `module.yaml`; `compose.py` plans
or copies them under a consumer Agent, writes the surface draft with the explicit role gate, and refuses a divergent file. The tests
(`tooling/profile/tests`) run the Workflow code under Node with a mocked broker
on synthetic fixtures; they use a small built-in JSON Schema validator, so no
extra package is needed. Passing them is not a runtime qualification: after
installation, qualify the parcours (save, read, revision conflict, share and
revocation) on a separate One with fictitious data.

See [security boundaries](../../docs/SECURITY.md) and [tests](../../docs/TESTING.md).
