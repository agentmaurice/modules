"""Offline checks of the document-studio Module: references, pins, embedded templates, JavaScript steps.

Every code step is executed under Node with a mocked Storage and a mocked artifact tool, on synthetic data. Nothing
here touches a One, a model or the network, so none of it proves the runtime behaviour: that is a separate replay.
"""
import base64
import datetime
import hashlib
import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
YEAR = datetime.datetime.now(datetime.timezone.utc).year
MODULE = ROOT / 'document-studio'
TOOLING = ROOT / 'tooling/document-studio'
WORKFLOWS = MODULE / 'agents/main/workflows'
TEMPLATES = MODULE / 'examples/templates'
CONTRACT_CHECK = ROOT.parent.parent / 'pilote-maurice/contracts/template/v1/tools/template_check.py'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


spec = importlib.util.spec_from_file_location('document_studio_build', TOOLING / 'build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

HARNESS = r'''
const fs = require("fs");
const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const {code, ctx, opts} = payload;
const store = payload.fs;
const calls = [];
const sha = (buf) => require("crypto").createHash("sha256").update(buf).digest("hex");
const b64 = (s) => Buffer.from(s).toString("base64");
const buffers = {};
let races = opts.race || 0, hijacks = opts.hijack || 0;
function pdf(label) { const bytes = Buffer.from("%PDF-1.7 fake " + label); return {bytes, sha: sha(bytes)}; }
const RECORD = /\/record\.json$/;
function cancelStored() {
  for (const path of Object.keys(store)) if (RECORD.test(path)) { const r = JSON.parse(store[path].text); r.status = "cancelled"; r.revision += 1; store[path] = {text: JSON.stringify(r)}; }
}
let firstRead = true;
async function callTool(name, args) {
  calls.push({name, args: JSON.parse(JSON.stringify(args, (k, v) => (k === "files" ? "[files]" : v)))});
  if (name === "artifact_render_v1") {
    if (opts.render_error) throw new Error(opts.render_error);
    if (opts.concurrent === "render") cancelStored();
    calls[calls.length - 1].full = args;
    const f = pdf(args.mode + ":" + args.context.doc.number + (opts.nonce || "")), p = pdf("png:" + args.mode);
    const file = {filename: "document.pdf", mime_type: "application/pdf", bytes: f.bytes.length + (opts.bad_bytes ? 1 : 0), sha256: opts.bad_sha ? "0000" : f.sha};
    const prev = {page: 1, filename: "page-1.png", mime_type: "image/png", bytes: p.bytes.length, sha256: p.sha};
    if (opts.render_mode === "ref") { buffers["buf-doc-" + calls.length] = f.bytes.toString("base64"); file.ref = "buf-doc-" + calls.length; buffers["buf-png-" + calls.length] = p.bytes.toString("base64"); prev.ref = "buf-png-" + calls.length; }
    else { file.content_base64 = f.bytes.toString("base64"); prev.content_base64 = p.bytes.toString("base64"); }
    if (opts.evil_name) { file.filename = "../x.pdf"; prev.filename = "document.pdf"; }
    const previews = [prev];
    if (opts.dup_page) previews.push({...prev});
    if (opts.bad_page) previews.push({...prev, page: opts.bad_page});
    return {status: "ok", mode: args.mode, output: "pdf", file, pages: 1, previews, provenance: {engine: "mock"}};
  }
  if (name === "read_file") {
    if (opts.read_error && args.path.includes(opts.read_error_path || "") && args.encoding === undefined) throw new Error(opts.read_error);
    const e = store[args.path];
    if (!e) throw new Error("not found: " + args.path);
    if (args.encoding === "base64") return {content: e.b64 !== undefined ? e.b64 : b64(e.text)};
    if (e.text === undefined) throw new Error("binary file");
    if (opts.concurrent === "first_read" && RECORD.test(args.path) && firstRead) { firstRead = false; const copy = e.text; cancelStored(); return {content: copy}; }
    return {content: e.text};
  }
  if (name === "write_file") {
    if (args.overwrite === false) {
      if (races > 0 && /\/numbers\//.test(args.path)) { races--; store[args.path] = {text: JSON.stringify({doc_id: "other-doc"})}; }
      if (store[args.path]) throw new Error("file exists: " + args.path);
    }
    if (args.buffer_ref) store[args.path] = {b64: buffers[args.buffer_ref]};
    else if (args.encoding === "base64") store[args.path] = {b64: args.content};
    else store[args.path] = {text: args.content};
    if (hijacks > 0 && /\/numbers\//.test(args.path)) { hijacks--; store[args.path] = {text: JSON.stringify({doc_id: "other-doc"})}; }
    return {ok: true};
  }
  if (name === "list_files") {
    if (opts.list_error) throw new Error(opts.list_error);
    const prefix = args.path.replace(/\/$/, "") + "/";
    const paths = Object.keys(store).filter((p) => p.startsWith(prefix));
    if (opts.list_mode === "dirs") return Array.from(new Set(paths.map((p) => prefix + p.slice(prefix.length).split("/")[0]))).map((p) => ({path: p}));
    return paths.map((p) => ({path: p}));
  }
  throw new Error("unexpected tool " + name);
}
const source = code.replace("import { callTool } from './tools/nats_bridge.ts';", "").split("{{ json . }}").join(JSON.stringify(ctx));
const main = new Function("callTool", "return (async () => {" + source + "})();");
main(callTool).then((result) => console.log(JSON.stringify({result, fs: store, calls})))
  .catch((error) => console.log(JSON.stringify({error: String(error.message), fs: store, calls})));
'''


def run_node(workflow, node_id, ctx, fs=None, **opts):
    wf = load(WORKFLOWS / f'{workflow}.json')
    action = next(a for a in wf['actions'] if a['id'] == node_id)
    payload = json.dumps({'code': action['code'], 'ctx': ctx, 'fs': fs or {}, 'opts': opts})
    with tempfile.TemporaryDirectory() as tmp:
        harness = Path(tmp) / 'harness.js'
        harness.write_text(HARNESS, encoding='utf-8')
        proc = subprocess.run(['node', str(harness)], input=payload, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return json.loads(proc.stdout)


def ok(case, out):
    case.assertNotIn('error', out, out.get('error'))
    return out['result']


def text_file(content):
    return {'text': content}


PROFILE = {
    'schema_version': 1,
    'company': {'legal_name': 'Atelier Exemple SAS', 'trade_name': 'Atelier Exemple', 'siret': '000 000 000 00000',
                'address': {'line1': '1 rue de l\'Exemple', 'postal_code': '00000', 'city': 'Exemple-sur-Seine', 'country': 'France'},
                'email': 'contact@atelier-exemple.invalid', 'legal_mentions': 'Societe fictive.'},
    'brand': {'colors': {'primary': '#1F3A5F', 'secondary': '#4F6D8F', 'accent': '#E07A1F', 'text': '#1B1B1F', 'muted': '#6B7280', 'background': '#F5F7FA'},
              'fonts': {'heading': {'family': 'Libertinus Serif'}, 'body': {'family': 'Libertinus Serif'}, 'mono': {'family': 'DejaVu Sans Mono'}},
              'logo': {'ref': 'storage:///logos/exemple.svg', 'alt': 'Logo Atelier Exemple'},
              'page': {'size': 'A4', 'margins_mm': {'top': 22, 'right': 20, 'bottom': 22, 'left': 20}}},
}
QUOTE_DRAFT = {
    'customer': {'name': 'Cabinet Fictif & Associes', 'address_lines': ['12 avenue de l\'Echantillon'], 'contact': 'contact@fictif.invalid'},
    'lines': [{'description': 'Atelier de cadrage', 'quantity': 2, 'unit': 'forfaits', 'unit_price_ht': 600, 'vat_rate': 20},
              {'description': 'Developpement du prototype', 'quantity': 5, 'unit': 'jours', 'unit_price_ht': 700, 'vat_rate': 20},
              {'description': 'Formation', 'quantity': 1, 'unit': 'jour', 'unit_price_ht': 650.5, 'vat_rate': 5.5}],
    'valid_until': '2026-12-06', 'terms': ['Acompte de 30 %.'], 'payment_terms': '30 jours.',
}
MINUTES_DRAFT = load(TEMPLATES / 'meeting-minutes/examples/default.json')


def seeded(profile=True):
    return {'/document-studio/profile.json': text_file(json.dumps(PROFILE))} if profile else {}


def create_quote(case, fs, **extra):
    ctx = {'prep': {'template_key': 'quote', 'locale': 'fr'}, 'draft': QUOTE_DRAFT, 'doc_id': 'devis-test', **extra}
    out = run_node('document-studio-draft', 'create', ctx, fs)
    return ok(case, out), out['fs']


class ResourcesTest(unittest.TestCase):
    def setUp(self):
        self.workflows = {p.stem: load(p) for p in WORKFLOWS.glob('*.json')}

    def test_manifest_lists_every_resource(self):
        manifest = load(MODULE / 'module.yaml')
        refs = {r['workflow_id'] for kind in ('actions', 'queries') for r in manifest['provides'][kind]}
        self.assertEqual(refs, set(self.workflows))
        self.assertEqual(len(refs), 11)
        apps = {r['miniapp_id'] for r in manifest['provides']['apps']}
        self.assertEqual(apps, {p.stem for p in (MODULE / 'agents/main/miniapps').glob('*.json')})
        self.assertEqual((manifest['key'], manifest['schema_version']), ('document-studio', 2))

    def test_input_schemas_are_closed(self):
        for name, wf in self.workflows.items():
            self.assertEqual(wf['input_schema']['type'], 'object', name)
            self.assertIs(wf['input_schema']['additionalProperties'], False, name)
            for form in wf.get('forms', []):
                for field in form['fields']:
                    self.assertIn(field['name'], wf['input_schema']['properties'], f'{name}: {field["name"]}')

    def test_code_has_no_template_action_and_declares_its_tools(self):
        for name, wf in self.workflows.items():
            for action in wf['actions']:
                if action['type'] != 'code_execution':
                    continue
                source = action['code']
                self.assertNotIn('{{', source.replace('{{ json . }}', ''), f'{name}/{action["id"]}')
                used = set(re.findall(r'callTool\("([^"]+)"', source))
                declared = set(action.get('context', {}).get('allowed_tools', []))
                self.assertLessEqual(used, declared, f'{name}/{action["id"]}')
                self.assertEqual('callTool' in source.replace("import { callTool }", ''), bool(used), name)

    def test_publish_and_finalize_and_cancel_demand_a_manual_confirmation(self):
        for name in ('document-studio-finalize', 'document-studio-publish', 'document-studio-cancel', 'document-studio-profile-save'):
            self.assertIn('confirmation_manuelle', self.workflows[name]['input_schema']['required'], name)
        for name, extra in (('document-studio-finalize', {}), ('document-studio-publish', {}), ('document-studio-cancel', {'reason': 'test'})):
            node = self.workflows[name]['actions'][0]['id']
            for value in ('non', False, '', None, 'false'):
                out = run_node(name, node, {'doc_id': 'devis-test', 'confirmation_manuelle': value, **extra}, {})
                self.assertTrue(out['error'].startswith('manual_confirmation_required'), (name, value, out))
                self.assertEqual(out['calls'], [], 'nothing may be read or written before the confirmation')
        out = run_node('document-studio-profile-save', 'save', {'profile': PROFILE, 'confirmation_manuelle': 'non'}, {})
        self.assertTrue(out['error'].startswith('manual_confirmation_required'))

    def test_no_llm_step_writes_and_llm_steps_are_text_parsed_as_json(self):
        for name, wf in self.workflows.items():
            for action in wf['actions']:
                if action['type'] == 'llm_call':
                    # text: the module validator requires a closed llm_response_schema for json,
                    # and the schema depends on the template; the next step parses and validates.
                    self.assertEqual(action['llm_response_format'], 'text', name)
                    self.assertNotIn('llm_response_schema', action, name)
        for name in ('document-studio-plan',):
            self.assertFalse(any('write_file' in json.dumps(a) for a in self.workflows[name]['actions']))

    def test_miniapp_events_point_at_existing_workflows(self):
        app = load(MODULE / 'agents/main/miniapps/document-studio-review.json')
        for event in app['events']:
            self.assertIn(event['workflow']['workflow_id'], self.workflows)
            props = self.workflows[event['workflow']['workflow_id']]['input_schema']['properties']
            self.assertLessEqual(set(event['workflow']['input']), set(props))

    def test_generator_reproduces_the_published_files(self):
        files = [p for p in MODULE.rglob('*') if p.is_file() and 'examples' not in p.relative_to(MODULE).parts[:1] and p.name != 'README.md']
        before = {p: p.read_bytes() for p in files}
        build.build()
        after = {p: p.read_bytes() for p in MODULE.rglob('*') if p.is_file() and p in before}
        self.assertEqual(before, after)
        self.assertEqual({p for p in MODULE.rglob('*') if p.is_file() and p.suffix == '.json' and 'examples' not in p.relative_to(MODULE).parts[:1]} - set(before), set())


class TemplatesTest(unittest.TestCase):
    def test_embedded_templates_send_no_platform_file(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('ds_build', ROOT / 'tooling' / 'document-studio' / 'build.py')
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        for key, entry in build.load_templates(True).items():
            for rel in entry['files']:
                self.assertFalse(rel.startswith('fragments/') or rel in ('brand.typ', 'values.json'), f'{key}/{rel}')
            self.assertIn(entry['manifest']['source']['entry'], entry['files'], key)

    def test_pin_matches_the_local_files(self):
        pin = load(TOOLING / 'contract/PIN.json')
        self.assertRegex(pin['source_commit'], r'^[0-9a-f]{40}$')
        self.assertEqual(sorted(pin['templates']), ['meeting-minutes', 'quote'])
        for key, files in pin['templates'].items():
            local = {p.relative_to(TEMPLATES / key).as_posix() for p in (TEMPLATES / key).rglob('*') if p.is_file()}
            self.assertEqual(local, set(files), key)
            for rel, entry in files.items():
                self.assertEqual(hashlib.sha256((TEMPLATES / key / rel).read_bytes()).hexdigest(), entry['sha256'], f'{key}/{rel}')
                self.assertEqual(entry['modified'], entry['sha256'] != entry['source_sha256'], f'{key}/{rel}')
        modified = sorted(f'{k}/{r}' for k, files in pin['templates'].items() for r, e in files.items() if e['modified'])
        self.assertEqual(modified, ['quote/main.typ'])
        shared = pin['shared']['i18n.fr.json']
        self.assertEqual(hashlib.sha256((TOOLING / 'contract/i18n.fr.json').read_bytes()).hexdigest(), shared['sha256'])

    def test_quote_states_it_is_not_an_invoice(self):
        self.assertIn("ce n'est pas une facture", (TEMPLATES / 'quote/main.typ').read_text(encoding='utf-8'))

    @unittest.skipUnless(CONTRACT_CHECK.exists(), 'the contract checkout is not next to this repository')
    def test_contract_checker_accepts_both_templates(self):
        for key in ('quote', 'meeting-minutes'):
            proc = subprocess.run(['python3', str(CONTRACT_CHECK), 'check', str(TEMPLATES / key)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_example_data_matches_the_input_schema(self):
        for key in ('quote', 'meeting-minutes'):
            manifest = load(TEMPLATES / key / 'manifest.json')
            self.assertEqual(manifest['source']['engine'], 'typst')
            for example in manifest['examples']:
                self.assertTrue((TEMPLATES / key / example['data']).exists())

    def test_render_receives_the_embedded_templates_unchanged(self):
        fs = seeded()
        quote, fs = create_quote(self, fs)
        out = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs)
        ok(self, out)
        call = next(c for c in out['calls'] if c['name'] == 'artifact_render_v1')['full']
        directory = TEMPLATES / 'quote'
        self.assertEqual(call['template']['files'], {p.relative_to(directory).as_posix(): p.read_text(encoding='utf-8') for p in sorted(directory.rglob('*')) if p.is_file() and not p.relative_to(directory).as_posix().startswith('fragments/')})
        self.assertEqual(call['template']['manifest'], load(directory / 'manifest.json'))
        self.assertEqual(call['context']['i18n'], load(TOOLING / 'contract/i18n.fr.json'))
        self.assertEqual((call['output'], call['mode']), ('pdf', 'preview'))
        self.assertEqual(call['context']['doc']['number'], 'BROUILLON')
        self.assertEqual(call['context']['company']['trade_name'], 'Atelier Exemple')
        self.assertEqual(call['context']['company']['phone'], '')


class MiniAppTest(unittest.TestCase):
    def test_the_document_id_is_typed_in_a_workflow_form_and_buttons_target_events(self):
        # The MiniApp vocabulary has no input component: fields come from the form of the targeted Workflow.
        app = load(MODULE / 'agents/main/miniapps/document-studio-review.json')
        workflows = {p.stem: load(p) for p in WORKFLOWS.glob('*.json')}
        events = {e['event_id']: e for e in app['events']}
        for event in events.values():
            if event['trigger'] == 'form.submit':
                forms = workflows[event['workflow']['workflow_id']].get('forms', [])
                self.assertTrue(forms and any(f['name'] == 'doc_id' for f in forms[0]['fields']), event['event_id'])
        self.assertEqual(events['review']['workflow']['workflow_id'], 'document-studio-review-read')
        self.assertEqual(events['review']['workflow']['input'], {'doc_id': '{{ state.doc_id }}'})
        self.assertEqual(events['load']['workflow']['workflow_id'], 'document-studio-review-read')
        buttons = []

        def walk(node):
            if isinstance(node, dict):
                if node.get('type') == 'button':
                    buttons.append(node['on_click'])
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(app['ui'])
        self.assertTrue(buttons)
        for target in buttons:
            self.assertIn(target, events)


class DraftTest(unittest.TestCase):
    def test_quote_numbers_are_checked_and_the_displayed_quantity_matches_the_total(self):
        def line(**over):
            return {**QUOTE_DRAFT, 'lines': [{**QUOTE_DRAFT['lines'][0], **over}]}
        for label, draft, needle in (
                ('tiny quantity', line(quantity=0.0004), 'quantity : 3 décimales'),
                ('4 decimals', line(quantity=1.2345), 'quantity : 3 décimales'),
                ('huge quantity', line(quantity=1000001), 'quantity'),
                ('price 3 decimals', line(unit_price_ht=10.005), 'unit_price_ht : 2 décimales'),
                ('negative price', line(unit_price_ht=-1), 'unit_price_ht'),
                ('odd vat', line(vat_rate=7), 'vat_rate : taux autorisés'),
                ('vat 19.6', line(vat_rate=19.6), 'vat_rate : taux autorisés')):
            out = run_node('document-studio-draft', 'create', {'prep': {'template_key': 'quote', 'locale': 'fr'}, 'draft': draft, 'doc_id': 'devis-test'}, {})
            self.assertTrue(out['error'].startswith('data_invalid'), (label, out))
            self.assertIn(needle, out['error'], label)
            self.assertEqual(out['calls'], [], label)
        for label, over, needle in (('1e-10', {'quantity': 0.0000000001}, 'quantity'), ('big quantity', {'quantity': 1e7}, 'quantity'), ('big price', {'unit_price_ht': 2e9}, 'unit_price_ht')):
            out = run_node('document-studio-draft', 'create', {'prep': {'template_key': 'quote', 'locale': 'fr'}, 'draft': line(**over), 'doc_id': 'devis-test'}, {})
            self.assertTrue(out['error'].startswith('data_invalid') and needle in out['error'], (label, out))
        huge = {**QUOTE_DRAFT, 'lines': [{**QUOTE_DRAFT['lines'][0], 'quantity': 1000000, 'unit_price_ht': 1000000000}] * 40}
        out = run_node('document-studio-draft', 'create', {'prep': {'template_key': 'quote', 'locale': 'fr'}, 'draft': huge, 'doc_id': 'devis-test'}, {})
        self.assertIn('error', out)
        for rate in (0, 2.1, 5.5, 10, 20):
            ok(self, run_node('document-studio-draft', 'create', {'prep': {'template_key': 'quote', 'locale': 'fr'}, 'draft': line(vat_rate=rate), 'doc_id': 'devis-test'}, {}))
        summary = ok(self, run_node('document-studio-draft', 'create', {'prep': {'template_key': 'quote', 'locale': 'fr'}, 'draft': line(quantity=0.001, unit_price_ht=1500, unit='jour'), 'doc_id': 'devis-test'}, {}))
        row = summary['computed']['lines'][0]
        self.assertEqual((row['quantity'], row['total_ht']), ('0,001 jour', '1,50 €'))
        summary = ok(self, run_node('document-studio-draft', 'create', {'prep': {'template_key': 'quote', 'locale': 'fr'}, 'draft': line(quantity=2.125, unit_price_ht=0.33, unit='h'), 'doc_id': 'devis-test'}, {}))
        row = summary['computed']['lines'][0]
        self.assertEqual((row['quantity'], row['total_ht']), ('2,125 h', '0,70 €'))  # 2.125 x 0.33 = 0.70125


    def test_quote_totals_are_computed_from_the_lines_and_never_from_the_model(self):
        draft = {**QUOTE_DRAFT, 'totals': {'total_ht': '1,00 €', 'total_ttc': '1,00 €'}, 'amount': 5}
        summary, _ = create_quote(self, seeded(), draft=draft)
        computed = summary['computed']
        self.assertEqual(computed['lines'][0], {'description': 'Atelier de cadrage', 'quantity': '2 forfaits', 'unit_price_ht': '600,00 €', 'vat_rate': '20 %', 'total_ht': '1 200,00 €'})
        self.assertEqual(computed['lines'][2]['unit_price_ht'], '650,50 €')
        self.assertEqual(computed['lines'][2]['vat_rate'], '5,5 %')
        # 1200 + 3500 + 650.50 = 5350.50 ; VAT 20 % on 4700 = 940.00 ; VAT 5.5 % on 650.50 = 35.78 (35.7775)
        self.assertEqual(computed['totals'], {'total_ht': '5 350,50 €', 'vat': [{'rate': '5,5 %', 'amount': '35,78 €'}, {'rate': '20 %', 'amount': '940,00 €'}], 'total_ttc': '6 326,28 €'})
        self.assertEqual(computed['reference'], 'DEVIS-TEST')
        self.assertEqual(summary['status'], 'draft')
        self.assertEqual((summary['revision'], summary['renders']), (1, 0))

    def test_the_stored_record_is_complete_and_created_without_overwrite(self):
        summary, fs = create_quote(self, seeded())
        record = json.loads(fs['/document-studio/docs/devis-test/record.json']['text'])
        self.assertEqual(record['schema'], 'document-studio.record/v1')
        self.assertEqual((record['status'], record['number'], record['revision'], record['issued']), ('draft', None, 1, None))
        self.assertEqual(record['template_version'], '1.0.0')
        self.assertEqual(record['title'], 'Devis Cabinet Fictif & Associes')
        self.assertEqual(record['history'][0]['action'], 'created')
        out = run_node('document-studio-draft', 'create', {'prep': {'template_key': 'quote', 'locale': 'fr'}, 'draft': QUOTE_DRAFT, 'doc_id': 'devis-test'}, fs)
        self.assertTrue(out['error'].startswith('document_create_failed'))
        create = [c for c in out['calls'] if c['name'] == 'write_file'][0]
        self.assertIs(create['args']['overwrite'], False)

    def test_invalid_drafts_are_refused_before_any_write(self):
        cases = {
            'negative price': {**QUOTE_DRAFT, 'lines': [{**QUOTE_DRAFT['lines'][0], 'unit_price_ht': -1}]},
            'zero quantity': {**QUOTE_DRAFT, 'lines': [{**QUOTE_DRAFT['lines'][0], 'quantity': 0}]},
            'impossible date': {**QUOTE_DRAFT, 'valid_until': '2026-02-30'},
            'no line': {**QUOTE_DRAFT, 'lines': []},
            'text price': {**QUOTE_DRAFT, 'lines': [{**QUOTE_DRAFT['lines'][0], 'unit_price_ht': '600,00 €'}]},
            'no customer': {k: v for k, v in QUOTE_DRAFT.items() if k != 'customer'},
        }
        for label, draft in cases.items():
            out = run_node('document-studio-draft', 'create', {'prep': {'template_key': 'quote', 'locale': 'fr'}, 'draft': draft, 'doc_id': 'devis-test'}, {})
            self.assertTrue(out['error'].startswith('data_invalid'), (label, out))
            self.assertEqual(out['calls'], [], label)

    def test_a_model_that_reports_missing_data_stops_the_draft(self):
        out = run_node('document-studio-draft', 'create', {'prep': {'template_key': 'quote', 'locale': 'fr'}, 'draft': {'missing': ['le nom du client']}}, {})
        self.assertTrue(out['error'].startswith('data_missing: le nom du client'))

    def test_draft_accepts_a_json_string_from_the_model_and_derives_the_id(self):
        out = run_node('document-studio-draft', 'create', {'prep': {'template_key': 'quote', 'locale': 'fr'}, 'draft': '```json\n' + json.dumps(QUOTE_DRAFT) + '\n```'}, {})
        summary = ok(self, out)
        self.assertRegex(summary['doc_id'], r'^devis-cabinet-fictif-associes-[0-9a-f]{6}$')

    def test_meeting_minutes_draft_and_prepare_steps(self):
        out = run_node('document-studio-draft', 'create', {'prep': {'template_key': 'meeting-minutes', 'locale': 'fr'}, 'draft': MINUTES_DRAFT, 'doc_id': 'cr-test'}, {})
        summary = ok(self, out)
        self.assertEqual(summary['template_key'], 'meeting-minutes')
        prep = ok(self, run_node('document-studio-draft', 'prepare', {'brief': 'Compte rendu du comite', 'template_key': 'meeting-minutes'}))
        self.assertIn('Compte rendu du comite', prep['prompt'])
        for bad in ({'brief': '', 'template_key': 'quote'}, {'brief': 'x', 'template_key': 'invoice'}, {'brief': 'x', 'template_key': 'quote', 'doc_id': 'Bad Id'}, {'brief': 'x', 'template_key': 'quote', 'locale': 'en'}):
            self.assertIn('error', run_node('document-studio-draft', 'prepare', bad))

    def test_plan_normalizes_the_model_answer_and_writes_nothing(self):
        prep = ok(self, run_node('document-studio-plan', 'prepare', {'brief': 'Un devis pour un client'}))
        out = run_node('document-studio-plan', 'normalize', {'prep': prep, 'plan_draft': json.dumps({'template_key': 'quote', 'title': ' Devis client ', 'missing': ['client', ''], 'questions': ['Quel client ?']})})
        plan = ok(self, out)
        self.assertEqual((plan['template_key'], plan['title'], plan['missing'], plan['questions']), ('quote', 'Devis client', ['client'], ['Quel client ?']))
        self.assertEqual(out['calls'], [])
        bad = run_node('document-studio-plan', 'normalize', {'prep': prep, 'plan_draft': {'template_key': 'invoice'}})
        self.assertTrue(bad['error'].startswith('template_unknown'))
        forced = ok(self, run_node('document-studio-plan', 'prepare', {'brief': 'x', 'template_key': 'meeting-minutes'}))
        self.assertEqual(forced['template_key'], 'meeting-minutes')

    def test_plan_refuses_malformed_model_answers(self):
        prep = ok(self, run_node('document-studio-plan', 'prepare', {'brief': 'Un devis'}))
        good = {'template_key': 'quote', 'title': 'T', 'missing': [], 'questions': []}
        for label, bad in (('missing string', {**good, 'missing': 'client, prix'}), ('questions string', {**good, 'questions': 'Quel client ?'}),
                           ('missing mixed', {**good, 'missing': ['a', 3]}), ('title number', {**good, 'title': 5}),
                           ('template_key number', {**good, 'template_key': 7})):
            out = run_node('document-studio-plan', 'normalize', {'prep': prep, 'plan_draft': {'text': json.dumps(bad)}})
            self.assertTrue(out['error'].startswith('llm_output_invalid'), (label, out))
        ok(self, run_node('document-studio-plan', 'normalize', {'prep': prep, 'plan_draft': good}))

    def test_null_handling_in_drafts(self):
        minutes = json.loads(json.dumps(MINUTES_DRAFT))
        minutes['meeting']['time'] = None
        minutes['meeting']['place'] = None
        summary = ok(self, run_node('document-studio-draft', 'create', {'prep': {'template_key': 'meeting-minutes', 'locale': 'fr'}, 'draft': minutes, 'doc_id': 'cr-test'}, {}))
        self.assertNotIn('time', summary['data']['meeting'])
        for label, mutate in (('required null', lambda d: d['meeting'].__setitem__('title', None)),
                              ('null item', lambda d: d['agenda'].append(None)),
                              ('wrong item type', lambda d: d['agenda'].append(3)),
                              ('wrong optional type', lambda d: d['meeting'].__setitem__('time', 12)),
                              ('bad date', lambda d: d['meeting'].__setitem__('date', '2026-13-01')),
                              ('empty title', lambda d: d['meeting'].__setitem__('title', ''))):
            bad = json.loads(json.dumps(MINUTES_DRAFT))
            mutate(bad)
            out = run_node('document-studio-draft', 'create', {'prep': {'template_key': 'meeting-minutes', 'locale': 'fr'}, 'draft': bad, 'doc_id': 'cr-test'}, {})
            self.assertTrue(out['error'].startswith('data_invalid'), (label, out))
        quote = json.loads(json.dumps(QUOTE_DRAFT))
        quote['customer']['contact'] = None
        ok(self, run_node('document-studio-draft', 'create', {'prep': {'template_key': 'quote', 'locale': 'fr'}, 'draft': quote, 'doc_id': 'devis-test'}, {}))

    def test_template_read(self):
        listing = ok(self, run_node('document-studio-template-read', 'read', {}))
        self.assertEqual({t['template_key'] for t in listing['templates']}, {'quote', 'meeting-minutes'})
        one = ok(self, run_node('document-studio-template-read', 'read', {'template_key': 'quote'}))
        self.assertEqual(one['template']['prefix'], 'DEV')
        self.assertIn('required', one['template']['input_schema'])
        self.assertIn('error', run_node('document-studio-template-read', 'read', {'template_key': 'invoice'}))


class LifecycleTest(unittest.TestCase):
    def render(self, fs, **opts):
        out = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs, **opts)
        return ok(self, out), out['fs']

    def run_lifecycle(self, **opts):
        _, fs = create_quote(self, seeded())
        rendered, fs = self.render(fs, **opts)
        self.assertEqual((rendered['status'], rendered['revision'], rendered['renders']), ('draft', 2, 1))
        sha12 = rendered['last_render']['sha256'][:12]
        self.assertEqual(rendered['last_render']['path'], f'/document-studio/docs/devis-test/r2-{sha12}/document.pdf')
        self.assertIn(f'/document-studio/docs/devis-test/r2-{sha12}/page-1.png', fs)
        approved = run_node('document-studio-finalize', 'finalize', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs)
        self.assertEqual(ok(self, approved)['status'], 'approved')
        published = run_node('document-studio-publish', 'publish', {'doc_id': 'devis-test', 'confirmation_manuelle': True}, approved['fs'], **opts)
        return ok(self, published), published

    def test_full_lifecycle_with_inline_base64(self):
        result, out = self.run_lifecycle()
        number = f'DEV-{YEAR}-0001'
        self.assertEqual((result['status'], result['number']), ('issued', number))
        fs = out['fs']
        record = json.loads(fs['/document-studio/docs/devis-test/record.json']['text'])
        pdf = fs[record['issued']['file']['path']]['b64']
        self.assertRegex(record['issued']['file']['path'], rf'/issued/{number}-[0-9a-f]{{12}}\.pdf$')
        self.assertEqual(record['issued']['file']['sha256'], hashlib.sha256(base64.b64decode(pdf)).hexdigest())
        self.assertEqual(record['issued']['number'], number)
        self.assertEqual([r['mode'] for r in record['renders']], ['preview', 'final'])
        self.assertEqual(record['revision'], 5)
        self.assertEqual([h['action'] for h in record['history']], ['created', 'rendered', 'approved', 'number_reserved', 'issued'])
        self.assertEqual(json.loads(fs[f'/document-studio/numbers/quote/{YEAR}/0001.json']['text'])['doc_id'], 'devis-test')
        call = [c for c in out['calls'] if c['name'] == 'artifact_render_v1'][0]['full']
        self.assertEqual((call['mode'], call['context']['doc']['number'], call['context']['doc']['status']), ('final', number, 'issued'))
        write = [c for c in out['calls'] if c['name'] == 'write_file' and c['args']['path'].endswith('.pdf')][0]['args']
        self.assertEqual((write['encoding'], write['overwrite']), ('base64', True))

    def test_lifecycle_stores_by_buffer_reference_when_the_engine_gives_one(self):
        result, out = self.run_lifecycle(render_mode='ref')
        self.assertEqual(result['status'], 'issued')
        writes = [c['args'] for c in out['calls'] if c['name'] == 'write_file' and 'buffer_ref' in c['args']]
        self.assertTrue(writes)
        for args in writes:
            self.assertNotIn('content', args)
        record = json.loads(out['fs']['/document-studio/docs/devis-test/record.json']['text'])
        pdf = out['fs'][record['issued']['file']['path']]['b64']
        self.assertEqual(record['issued']['file']['sha256'], hashlib.sha256(base64.b64decode(pdf)).hexdigest())

    def test_a_wrong_fingerprint_or_size_is_detected_in_every_storage_mode(self):
        for mode in ('inline', 'ref'):
            for label, opts in (('sha', {'bad_sha': True}), ('size', {'bad_bytes': True})):
                _, fs = create_quote(self, seeded())
                before = fs['/document-studio/docs/devis-test/record.json']['text']
                out = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs, render_mode='ref' if mode == 'ref' else 'inline', **opts)
                self.assertTrue(out['error'].startswith('render_integrity_failed'), (mode, label, out))
                self.assertEqual(out['fs']['/document-studio/docs/devis-test/record.json']['text'], before, 'the record must not be updated')
        _, fs = create_quote(self, seeded())
        fs = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs)['fs']
        fs = run_node('document-studio-finalize', 'finalize', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs)['fs']
        issued = run_node('document-studio-publish', 'publish', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs, render_mode='ref', bad_sha=True)
        self.assertTrue(issued['error'].startswith('render_integrity_failed'), issued)
        record = json.loads(issued['fs']['/document-studio/docs/devis-test/record.json']['text'])
        self.assertEqual(record['status'], 'approved')

    def test_renderer_file_names_are_not_trusted(self):
        _, fs = create_quote(self, seeded())
        out = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs, evil_name=True)
        result = ok(self, out)
        pdf = out['fs'][result['last_render']['path']]['b64']
        self.assertTrue(result['last_render']['path'].endswith('/document.pdf'))
        self.assertEqual(hashlib.sha256(base64.b64decode(pdf)).hexdigest(), result['last_render']['sha256'])
        self.assertTrue(any(k.endswith('/page-1.png') for k in out['fs']))
        self.assertFalse(any('x.pdf' in k for k in out['fs']))
        for opts in ({'dup_page': True}, {'bad_page': 5}, {'bad_page': -1}):
            bad = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs, **opts)
            self.assertTrue(bad['error'].startswith('render_invalid'), (opts, bad))

    def test_what_is_approved_is_what_is_issued(self):
        def approved(fs=None):
            _, fs = create_quote(self, fs or seeded())
            fs = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs)['fs']
            return run_node('document-studio-finalize', 'finalize', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs)['fs']
        def publish(fs):
            return run_node('document-studio-publish', 'publish', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs)
        fs = approved()
        record = json.loads(fs['/document-studio/docs/devis-test/record.json']['text'])
        self.assertRegex(record['renders'][-1]['profile_sha256'], r'^[0-9a-f]{64}$')
        self.assertRegex(record['renders'][-1]['data_sha256'], r'^[0-9a-f]{64}$')
        changed = dict(fs)
        profile = json.loads(json.dumps(PROFILE))
        profile['brand']['colors']['primary'] = '#000000'
        changed['/document-studio/profile.json'] = text_file(json.dumps(profile))
        out = publish(changed)
        self.assertTrue(out['error'].startswith('profile_changed') and 'rendez et approuvez à nouveau' in out['error'], out)
        self.assertFalse([k for k in out['fs'] if '/numbers/' in k], 'no number may be reserved')
        edited = dict(fs)
        record['data']['payment_terms'] = '90 jours.'
        edited['/document-studio/docs/devis-test/record.json'] = text_file(json.dumps(record))
        out = publish(edited)
        self.assertTrue(out['error'].startswith('data_changed'), out)
        self.assertFalse([k for k in out['fs'] if '/numbers/' in k])
        old = dict(fs)
        legacy = json.loads(fs['/document-studio/docs/devis-test/record.json']['text'])
        for render in legacy['renders']:
            render.pop('profile_sha256'); render.pop('data_sha256')
        old['/document-studio/docs/devis-test/record.json'] = text_file(json.dumps(legacy))
        out = publish(old)
        self.assertTrue(out['error'].startswith('render_outdated'), out)
        self.assertFalse([k for k in out['fs'] if '/numbers/' in k])
        self.assertEqual(ok(self, publish(fs))['status'], 'issued')

    def test_each_attempt_writes_its_own_files(self):
        _, fs = create_quote(self, seeded())
        first = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs, nonce='a')
        second = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs, nonce='b')
        a, b = ok(self, first)['last_render'], ok(self, second)['last_render']
        self.assertNotEqual(a['path'], b['path'])
        merged = {**first['fs'], **second['fs']}
        for item in (a, b):
            self.assertEqual(hashlib.sha256(base64.b64decode(merged[item['path']]['b64'])).hexdigest(), item['sha256'])
            self.assertIn(item['sha256'][:12], item['path'])
        # issued file: one name per number and per attempt
        fs2 = run_node('document-studio-finalize', 'finalize', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, first['fs'])['fs']
        issued = ok(self, run_node('document-studio-publish', 'publish', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs2))
        self.assertRegex(issued['issued']['file']['path'], r'/issued/DEV-\d{4}-0001-[0-9a-f]{12}\.pdf$')

    def test_read_errors_are_never_swallowed(self):
        _, fs = create_quote(self, seeded())
        _, fs = create_quote(self, fs, doc_id='devis-deux')
        for node, wf, ctx in (('list', 'document-studio-list', {}), ('read', 'document-studio-review-read', {'doc_id': 'devis-test'}),
                              ('render', 'document-studio-render', {'doc_id': 'devis-test'})):
            out = run_node(wf, node, ctx, fs, read_error='503 unavailable', read_error_path='devis-deux' if node == 'list' else 'devis-test')
            self.assertTrue(out['error'].startswith('storage_unavailable: 503'), (wf, out))
        vanished = ok(self, run_node('document-studio-list', 'list', {}, fs, read_error='file not found', read_error_path='devis-deux'))
        self.assertEqual([i['doc_id'] for i in vanished['items']], ['devis-test'])
        broken = dict(fs)
        broken['/document-studio/docs/devis-deux/record.json'] = text_file('{not json')
        for wf, node, ctx in (('document-studio-list', 'list', {}), ('document-studio-review-read', 'read', {'doc_id': 'devis-deux'}), ('document-studio-render', 'render', {'doc_id': 'devis-deux'})):
            out = run_node(wf, node, ctx, broken)
            self.assertTrue(out['error'].startswith('record_corrupt: devis-deux') or 'devis-deux' in out['error'] and out['error'].startswith('record_corrupt'), (wf, out))
        self.assertTrue(run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, seeded(False) | {k: v for k, v in fs.items() if 'devis-test' in k}, read_error='permission denied', read_error_path='profile.json')['error'].startswith('storage_unavailable'))
        self.assertTrue(run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, {k: v for k, v in fs.items() if 'devis-test' in k} | {'/document-studio/profile.json': text_file('{oops')})['error'].startswith('profile_corrupt'))

    def test_a_storage_outage_is_not_an_empty_list(self):
        _, fs = create_quote(self, seeded())
        out = run_node('document-studio-list', 'list', {}, fs, list_error='503 service unavailable ' + 'x' * 500)
        self.assertTrue(out['error'].startswith('storage_unavailable: 503'), out)
        self.assertLess(len(out['error']), 260)
        self.assertEqual(ok(self, run_node('document-studio-list', 'list', {}, {}, list_error='directory not found'))['count'], 0)
        fs = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs)['fs']
        fs = run_node('document-studio-finalize', 'finalize', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs)['fs']
        fs['/document-studio/numbers/quote/%d/0007.json' % YEAR] = text_file(json.dumps({'doc_id': 'autre'}))
        down = run_node('document-studio-publish', 'publish', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs, list_error='permission denied')
        self.assertTrue(down['error'].startswith('storage_unavailable: permission denied'), down)
        self.assertFalse([c for c in down['calls'] if c['name'] == 'write_file'])
        self.assertEqual(json.loads(down['fs']['/document-studio/docs/devis-test/record.json']['text'])['number'], None)
        up = ok(self, run_node('document-studio-publish', 'publish', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs))
        self.assertEqual(up['number'], f'DEV-{YEAR}-0008')

    def test_a_concurrent_cancel_is_never_overwritten(self):
        _, fs = create_quote(self, seeded())
        out = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs, concurrent='render')
        self.assertTrue(out['error'].startswith('concurrent_update'), out)
        self.assertEqual(json.loads(out['fs']['/document-studio/docs/devis-test/record.json']['text'])['status'], 'cancelled')
        _, fs = create_quote(self, seeded())
        fs = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs)['fs']
        for name, node_id, extra in (('document-studio-finalize', 'finalize', {}), ('document-studio-cancel', 'cancel', {'reason': 'x'})):
            out = run_node(name, node_id, {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui', **extra}, fs, concurrent='first_read')
            self.assertTrue(out['error'].startswith('concurrent_update'), (name, out))
            self.assertEqual(json.loads(out['fs']['/document-studio/docs/devis-test/record.json']['text'])['status'], 'cancelled')
        fs = run_node('document-studio-finalize', 'finalize', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs)['fs']
        out = run_node('document-studio-publish', 'publish', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs, concurrent='render')
        self.assertTrue(out['error'].startswith('concurrent_update'), out)
        self.assertEqual(json.loads(out['fs']['/document-studio/docs/devis-test/record.json']['text'])['status'], 'cancelled')

    def test_issued_and_cancelled_documents_are_locked(self):
        _, out = self.run_lifecycle()
        locked = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, out['fs'])
        self.assertTrue(locked['error'].startswith('document_locked'))
        self.assertEqual([c['name'] for c in locked['calls']], ['read_file'])
        cancelled = run_node('document-studio-cancel', 'cancel', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui', 'reason': 'erreur de client'}, out['fs'])
        record = ok(self, cancelled)
        self.assertEqual((record['status'], record['number'] is not None), ('cancelled', True))
        again = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, cancelled['fs'])
        self.assertTrue(again['error'].startswith('document_locked'))
        twice = run_node('document-studio-cancel', 'cancel', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui', 'reason': 'x'}, cancelled['fs'])
        self.assertTrue(twice['error'].startswith('status_invalid'))
        self.assertIn('error', run_node('document-studio-cancel', 'cancel', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui', 'reason': ' '}, out['fs']))

    def test_numbers_continue_and_are_never_reused(self):
        _, out = self.run_lifecycle()
        fs = out['fs']
        run_node('document-studio-cancel', 'cancel', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui', 'reason': 'x'}, fs)
        _, fs = create_quote(self, fs, doc_id='devis-deux')
        fs = run_node('document-studio-render', 'render', {'doc_id': 'devis-deux'}, fs)['fs']
        fs = run_node('document-studio-finalize', 'finalize', {'doc_id': 'devis-deux', 'confirmation_manuelle': 'oui'}, fs)['fs']
        second = ok(self, run_node('document-studio-publish', 'publish', {'doc_id': 'devis-deux', 'confirmation_manuelle': 'oui'}, fs))
        self.assertEqual(second['number'], f'DEV-{YEAR}-0002')

    def test_number_reservation_survives_lost_races_and_gives_up_after_five(self):
        def approved_fs():
            _, fs = create_quote(self, seeded())
            fs = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs)['fs']
            return run_node('document-studio-finalize', 'finalize', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs)['fs']
        raced = run_node('document-studio-publish', 'publish', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, approved_fs(), race=2)
        self.assertEqual(ok(self, raced)['number'], f'DEV-{YEAR}-0003')
        hijacked = run_node('document-studio-publish', 'publish', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, approved_fs(), hijack=1)
        self.assertEqual(ok(self, hijacked)['number'], f'DEV-{YEAR}-0002')
        lost = run_node('document-studio-publish', 'publish', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, approved_fs(), race=9)
        self.assertTrue(lost['error'].startswith('number_conflict'), lost)
        record = json.loads(lost['fs']['/document-studio/docs/devis-test/record.json']['text'])
        self.assertEqual((record['status'], record['number']), ('approved', None))
        self.assertFalse([c for c in lost['calls'] if c['name'] == 'artifact_render_v1'])

    def test_a_reserved_number_is_kept_when_the_render_fails(self):
        _, fs = create_quote(self, seeded())
        fs = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs)['fs']
        fs = run_node('document-studio-finalize', 'finalize', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs)['fs']
        failed = run_node('document-studio-publish', 'publish', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs, render_error='moteur indisponible')
        self.assertIn('moteur indisponible', failed['error'])
        record = json.loads(failed['fs']['/document-studio/docs/devis-test/record.json']['text'])
        self.assertEqual(record['status'], 'approved')
        number = record['number']
        self.assertTrue(number)
        retry = ok(self, run_node('document-studio-publish', 'publish', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, failed['fs']))
        self.assertEqual(retry['number'], number)

    def test_status_rules(self):
        _, fs = create_quote(self, seeded())
        self.assertTrue(run_node('document-studio-finalize', 'finalize', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs)['error'].startswith('render_required'))
        self.assertTrue(run_node('document-studio-publish', 'publish', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs)['error'].startswith('status_invalid'))
        self.assertTrue(run_node('document-studio-render', 'render', {'doc_id': 'devis-absent'}, fs)['error'].startswith('document_not_found'))
        fs = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs)['fs']
        fs = run_node('document-studio-finalize', 'finalize', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui'}, fs)['fs']
        reopened = ok(self, run_node('document-studio-render', 'render', {'doc_id': 'devis-test', 'data_patch': {'payment_terms': '45 jours.'}}, fs))
        self.assertEqual(reopened['status'], 'draft')

    def test_render_patch_is_validated_and_merged(self):
        _, fs = create_quote(self, seeded())
        bad = run_node('document-studio-render', 'render', {'doc_id': 'devis-test', 'data_patch': {'valid_until': 'demain'}}, fs)
        self.assertTrue(bad['error'].startswith('data_invalid'))
        self.assertFalse([c for c in bad['calls'] if c['name'] == 'artifact_render_v1'])
        good = run_node('document-studio-render', 'render', {'doc_id': 'devis-test', 'data_patch': {'valid_until': '2027-01-31'}}, fs)
        ok(self, good)
        record = json.loads(good['fs']['/document-studio/docs/devis-test/record.json']['text'])
        self.assertEqual(record['data']['valid_until'], '2027-01-31')
        self.assertEqual(record['data']['customer']['name'], QUOTE_DRAFT['customer']['name'])
        self.assertIn('error', run_node('document-studio-render', 'render', {'doc_id': 'devis-test', 'data_patch': 'texte'}, fs))

    def test_render_needs_the_company_profile(self):
        _, fs = create_quote(self, seeded(profile=False))
        out = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs)
        self.assertTrue(out['error'].startswith('profile_missing'))
        self.assertIn('document-studio-profile-save', out['error'])

    def test_profile_save_validates_and_writes(self):
        out = run_node('document-studio-profile-save', 'save', {'profile': PROFILE, 'confirmation_manuelle': 'oui'}, {})
        result = ok(self, out)
        self.assertEqual(result['legal_name'], 'Atelier Exemple SAS')
        stored = json.loads(out['fs']['/document-studio/profile.json']['text'])
        self.assertEqual(stored['company']['legal_name'], 'Atelier Exemple SAS')
        bad_colour = json.loads(json.dumps(PROFILE))
        bad_colour['brand']['colors']['primary'] = 'blue'
        no_name = json.loads(json.dumps(PROFILE))
        del no_name['company']['legal_name']
        bad_iban = json.loads(json.dumps(PROFILE))
        bad_iban['company']['bank'] = {'iban': 'FR76'}
        for label, profile in (('colour', bad_colour), ('name', no_name), ('iban', bad_iban)):
            refused = run_node('document-studio-profile-save', 'save', {'profile': profile, 'confirmation_manuelle': 'oui'}, {})
            self.assertIn('error', refused, label)
            self.assertNotIn('/document-studio/profile.json', refused['fs'], label)
        example = load(MODULE / 'examples/profile.example.json')
        self.assertIn('result', run_node('document-studio-profile-save', 'save', {'profile': example, 'confirmation_manuelle': 'oui'}, {}))

    def test_export_copies_the_issued_pdf_outside_the_studio(self):
        _, out = self.run_lifecycle()
        copied = run_node('document-studio-export', 'export', {'doc_id': 'devis-test', 'destination_path': '/envois/devis.pdf'}, out['fs'])
        result = ok(self, copied)
        record = json.loads(copied['fs']['/document-studio/docs/devis-test/record.json']['text'])
        self.assertEqual((result['sha256'], result['draft']), (record['issued']['file']['sha256'], False))
        self.assertEqual(copied['fs']['/envois/devis.pdf']['b64'], copied['fs'][record['issued']['file']['path']]['b64'])
        for bad in ('/document-studio/copie.pdf', 'relatif.pdf', '/envois/../x.pdf', '/envois/'):
            self.assertTrue(run_node('document-studio-export', 'export', {'doc_id': 'devis-test', 'destination_path': bad}, out['fs'])['error'].startswith('destination_invalid'), bad)
        clash = run_node('document-studio-export', 'export', {'doc_id': 'devis-test', 'destination_path': '/envois/devis.pdf'}, copied['fs'])
        self.assertIn('error', clash)

    def test_export_of_a_cancelled_document_is_refused(self):
        _, out = self.run_lifecycle()
        cancelled = run_node('document-studio-cancel', 'cancel', {'doc_id': 'devis-test', 'confirmation_manuelle': 'oui', 'reason': 'Erreur'}, out['fs'])
        ok(self, cancelled)
        refused = run_node('document-studio-export', 'export', {'doc_id': 'devis-test', 'destination_path': '/envois/devis.pdf'}, cancelled['fs'])
        self.assertTrue(refused['error'].startswith('document_cancelled'))
        self.assertNotIn('/envois/devis.pdf', refused['fs'])

    def test_export_of_a_draft_is_flagged(self):
        _, fs = create_quote(self, seeded())
        fs = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs)['fs']
        result = ok(self, run_node('document-studio-export', 'export', {'doc_id': 'devis-test', 'destination_path': '/envois/brouillon.pdf'}, fs))
        self.assertIs(result['draft'], True)
        self.assertIn('brouillon', result['warning'])
        empty = run_node('document-studio-export', 'export', {'doc_id': 'devis-test', 'destination_path': '/envois/x.pdf'}, create_quote(self, seeded())[1])
        self.assertTrue(empty['error'].startswith('no_render'))

    def test_list_and_review_read(self):
        _, fs = create_quote(self, seeded())
        _, fs = create_quote(self, fs, doc_id='devis-deux')
        fs = run_node('document-studio-render', 'render', {'doc_id': 'devis-test'}, fs)['fs']
        for mode in ('recursive', 'dirs'):
            listing = ok(self, run_node('document-studio-list', 'list', {}, fs, list_mode=mode))
            self.assertEqual([i['doc_id'] for i in listing['items']], ['devis-deux', 'devis-test'], mode)
        only = ok(self, run_node('document-studio-list', 'list', {'status': 'approved'}, fs))
        self.assertEqual(only['count'], 0)
        self.assertIn('error', run_node('document-studio-list', 'list', {'status': 'wip'}, fs))
        review = ok(self, run_node('document-studio-review-read', 'read', {'doc_id': 'devis-test'}, fs))
        self.assertEqual((review['status'], review['revision'], review['pages'], review['number']), ('draft', 2, 1, ''))
        self.assertRegex(review['previews'][0]['path'], r'^/document-studio/docs/devis-test/r2-[0-9a-f]{12}/page-1\.png$')
        self.assertEqual(len(review['previews']), 1)
        self.assertEqual(review['renders'][0]['mode'], 'preview')


if __name__ == '__main__':
    unittest.main()
