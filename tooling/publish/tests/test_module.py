"""Offline checks of the publish Module: references, guard rails, JavaScript steps.

Every code step is executed under Node with a mocked Storage and mocked tools (ssh, social, e-mail), on synthetic
data. Nothing here touches a One, a model, a server or the network, so none of it proves the runtime behaviour:
that is a separate replay.
"""
import base64
import hashlib
import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / 'publish'
TOOLING = ROOT / 'tooling/publish'
WORKFLOWS = MODULE / 'agents/main/workflows'
NOW = '2026-11-07T10:00:00Z'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


spec = importlib.util.spec_from_file_location('publish_build', TOOLING / 'build.py')
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
const atCall = [];
let logWrites = 0, destWrites = 0;
function snapshot(name) { const logs = {}; const dests = {}; for (const p of Object.keys(store)) if (p.startsWith("/publish/dest/")) dests[p] = JSON.parse(store[p].text); for (const p of Object.keys(store)) if (p.startsWith("/publish/log/")) logs[p] = JSON.parse(store[p].text); atCall.push({name, logs, dests}); }
function tamper() { for (const p of Object.keys(store)) if (p.startsWith("/publish/log/")) { const r = JSON.parse(store[p].text); r.revision += 5; store[p] = {text: JSON.stringify(r)}; } }
async function rawTool(name, args) {
  const shown = JSON.parse(JSON.stringify(args, (k, v) => (k === "content_base64" ? "[b64:" + sha(Buffer.from(v, "base64")).slice(0, 8) + "]" : v)));
  calls.push({name, args: shown, raw: args});
  const re = opts.ret_error;
  if (re && re.tool === name && (!re.prefix || String(args.path).startsWith(re.prefix))) return re.mode === "raw" ? re.raw : re.mode === "error" ? {error: re.msg} : re.mode === "object" ? {error: {code: "disk_full"}} : re.mode === "status" ? {status: "error", message: re.msg} : re.mode === "json" ? {content: [{type: "text", text: JSON.stringify({error: {code: "disk_full"}})}]} : re.mode === "string" ? JSON.stringify({error: "disk_full"}) : {isError: true, content: [{type: "text", text: re.msg}]};
  if (name === "read_file") {
    if (opts.read_error && args.path.includes(opts.read_error_path || "")) throw new Error(opts.read_error);
    const e = store[args.path];
    if (!e) throw new Error("failed to download file: object not found");
    if (args.encoding === "base64") return {content: e.b64 !== undefined ? e.b64 : b64(e.text)};
    if (e.text === undefined) throw new Error("binary file");
    return {content: e.text};
  }
  if (name === "write_file") {
    if (opts.dest_fail_from && args.path.startsWith("/publish/dest/")) { destWrites += 1; if (destWrites >= opts.dest_fail_from) return {error: {code: "disk_full"}}; }
    if (opts.drop_writes && args.path.startsWith("/publish/")) return {ok: true};
    if (opts.drop_from && args.path.startsWith("/publish/log/")) { logWrites += 1; if (logWrites >= opts.drop_from) return {ok: true}; }
    if (opts.write_error && args.path.startsWith("/publish/")) throw new Error(opts.write_error);
    if (args.overwrite === false && store[args.path]) throw new Error("file exists: " + args.path);
    store[args.path] = {text: args.content};
    if (opts.steal_dest && args.path.startsWith("/publish/log/") && JSON.parse(args.content).history.slice(-1)[0].action === "remove_requested") {
      for (const p of Object.keys(store)) if (p.startsWith("/publish/dest/")) { const d = JSON.parse(store[p].text); d.owner = "page-9"; store[p] = {text: JSON.stringify(d)}; }
    }
    return {ok: true};
  }
  if (name === "list_files") {
    if (opts.list_error) throw new Error(opts.list_error);
    const prefix = args.path.replace(/\/$/, "") + "/";
    return Object.keys(store).filter((p) => p.startsWith(prefix)).map((p) => ({path: p}));
  }
  if (name === "ssh_upload_v1") {
    snapshot(name);
    if (opts.tamper) tamper();
    if (opts.hijack_dest) for (const p of Object.keys(store)) if (p.startsWith("/publish/dest/")) store[p] = {text: JSON.stringify({...JSON.parse(store[p].text), owner: opts.hijack_owner || "page-2", state: opts.hijack_state || "pending_owner", attempt: 1})};
    if (opts.vanish_dest) for (const p of Object.keys(store)) if (p.startsWith("/publish/dest/")) delete store[p];
    if (opts.upload_throw) throw new Error(opts.upload_throw);
    if (opts.upload_error) throw new Error(JSON.stringify({error: opts.upload_error, message: "refused"}));
    const bytes = Buffer.from(args.file.content_base64, "base64");
    return {status: "ok", target: args.target, path: args.path, bytes: bytes.length, sha256: opts.bad_sha ? "00" : sha(bytes)};
  }
  if (name === "ssh_remove_v1") {
    snapshot(name);
    if (opts.remove_error) throw new Error(JSON.stringify({error: opts.remove_error, message: "refused"}));
    return {status: "ok", removed: opts.removed === false ? false : true};
  }
  if (name === "social_post_create_v1") {
    snapshot(name);
    if (opts.social_throw) throw new Error(opts.social_throw);
    if (opts.social_error) throw new Error(JSON.stringify({error: opts.social_error, message: "slow down", retry_after_s: 60}));
    if (opts.no_post_id) return {status: "ok"};
    return {status: "ok", post_id: opts.post_id_len ? "p".repeat(opts.post_id_len) : "post-1", state: args.mode === "now" ? "published" : args.mode === "schedule" ? "scheduled" : "draft", group: "g-1", channels: args.channels.map((id) => ({id, state: "draft"}))};
  }
  if (name === "social_post_get_v1") return {post_id: args.post_id, state: "published", channels: [{id: "c1", state: "published", url: "https://social.example.invalid/p/1"}]};
  if (name === "social_post_delete_v1") { snapshot(name); if (opts.delete_error) throw new Error(JSON.stringify({error: opts.delete_error})); return {status: "ok", deleted: true}; }
  if (name === "google_mail_send") {
    snapshot(name);
    if (opts.mail_error) throw new Error(JSON.stringify({error_code: opts.mail_error, connector_key: "google-mail"}));
    if (opts.mail_enveloped) return {isError: true, content: [{type: "text", text: opts.mail_enveloped === true ? JSON.stringify({error_code: "not_connected", connector_key: "google-mail", connect_available: true}) : opts.mail_enveloped}]};
    if (opts.mail_throw) throw new Error(opts.mail_throw);
    if (opts.mail_empty) return {};
    if (opts.mail_no_id) return {status_code: 200, body: {}};
    if (opts.mail_body_string) return {status_code: 200, body: JSON.stringify({id: "msg-s", threadId: "t"})};
    if (opts.mail_returned_error) return {error_code: "authorization_required", authorization_id: "a1"};
    if (opts.mail_status) return {status_code: opts.mail_status, body: {}};
    return {status_code: 200, body: {id: opts.mail_id_len ? "m".repeat(opts.mail_id_len) : "msg-1", threadId: "thr-1"}, assistant_summary: "sent"};
  }
  throw new Error("unexpected tool " + name);
}
async function callTool(name, args) {
  const r = await rawTool(name, args);
  if (opts.status_error && ["ssh_upload_v1", "google_mail_send", "social_post_create_v1"].includes(name)) return {status: "error", message: "upstream timeout"};
  if (opts.structured_error && ["ssh_upload_v1", "google_mail_send", "social_post_create_v1", "social_post_get_v1"].includes(name)) return {content: [{type: "text", text: "ok"}], structuredContent: {...r, error: {code: "remote_boom"}}};
  if (opts.ok_with_error && ["ssh_upload_v1", "ssh_remove_v1", "social_post_create_v1", "social_post_get_v1", "social_post_delete_v1"].includes(name) && r && typeof r === "object") return {...r, error: {code: "remote_boom"}};
  if (opts.iserror_env && ["ssh_upload_v1", "google_mail_send", "social_post_create_v1"].includes(name)) {
    const code = {ssh_upload_v1: "file_exists", google_mail_send: "not_connected", social_post_create_v1: "rate_limited"}[name];
    return {isError: true, structuredContent: r, content: [{type: "text", text: opts.iserror_env === "code" ? JSON.stringify({error_code: code}) : "ok"}]};
  }
  if (!opts.envelope || (r && (r.isError || r.error))) return r;
  if (opts.envelope === "structured") return {content: [{type: "text", text: "ignored"}], structuredContent: Array.isArray(r) ? {entries: r} : (name === "read_file" ? r : r)};
  return {content: [{type: "text", text: JSON.stringify(r)}]};
}
globalThis.__pubNow = opts.now || "2026-11-07T10:00:00Z";
const source = code.replace("import { callTool } from './tools/nats_bridge.ts';", "").split("{{ json . }}").join(opts.raw_ctx !== undefined ? opts.raw_ctx : JSON.stringify(ctx));
const main = new Function("callTool", "return (async () => {" + source + "})();");
main(callTool).then((result) => console.log(JSON.stringify({result, fs: store, calls, atCall})))
  .catch((error) => console.log(JSON.stringify({error: String(error.message), fs: store, calls, atCall})));
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


def names(out):
    return [c['name'] for c in out['calls']]


def external(out):
    return [c for c in out['calls'] if c['name'] not in ('read_file', 'write_file', 'list_files')]


def writes(out):
    return [c for c in out['calls'] if c['name'] == 'write_file']


HTML = '<h1>Hello</h1>'
HTML_SHA = hashlib.sha256(HTML.encode()).hexdigest()
FILES = {'/docs/page.html': {'text': HTML}, '/docs/post.md': {'text': 'Bonjour le monde'},
         '/docs/note.pdf': {'b64': base64.b64encode(b'%PDF-1.7 fake').decode()}, '/docs/logo.png': {'b64': base64.b64encode(b'\x89PNG fake').decode()}}
CONFIRMED = {'confirmation_manuelle': 'oui'}
WEB = {'source_path': '/docs/page.html', 'target': 'site-main', 'remote_path': 'news/page.html', 'publication_id': 'page-1', **CONFIRMED}
EMAIL = {'to': ['ada@example.invalid', 'bob@example.invalid'], 'subject': 'Nouvelles', 'body': 'Bonjour', 'publication_id': 'mail-1', **CONFIRMED}
SOCIAL = {'channels': ['c1', 'c2'], 'content': 'Un post', 'publication_id': 'post-a', **CONFIRMED}


def web(**kw):
    ctx = {**WEB, **kw.pop('ctx', {})}
    return run_node('publish-web', 'publish', ctx, kw.pop('fs', dict(FILES)), **kw)


def email(**kw):
    ctx = {**EMAIL, **kw.pop('ctx', {})}
    return run_node('publish-email', 'publish', ctx, kw.pop('fs', dict(FILES)), **kw)


def social(**kw):
    ctx = {**SOCIAL, **kw.pop('ctx', {})}
    return run_node('publish-social', 'publish', ctx, kw.pop('fs', dict(FILES)), **kw)


def record(out, pid):
    return json.loads(out['fs'][f'/publish/log/{pid}.json']['text'])


class ResourcesTest(unittest.TestCase):
    def setUp(self):
        self.workflows = {p.stem: load(p) for p in WORKFLOWS.glob('*.json')}

    def test_manifest_lists_every_resource(self):
        manifest = load(MODULE / 'module.yaml')
        refs = {r['workflow_id'] for kind in ('actions', 'queries') for r in manifest['provides'][kind]}
        self.assertEqual(refs, set(self.workflows))
        self.assertEqual(refs, {'publish-plan', 'publish-web', 'publish-email', 'publish-social', 'publish-remove', 'publish-status', 'publish-list', 'publish-read'})
        apps = {r['miniapp_id'] for r in manifest['provides']['apps']}
        self.assertEqual(apps, {p.stem for p in (MODULE / 'agents/main/miniapps').glob('*.json')})
        self.assertEqual((manifest['key'], manifest['schema_version']), ('publish', 2))

    def test_input_schemas_are_closed_and_forms_match(self):
        for name, wf in self.workflows.items():
            self.assertEqual(wf['input_schema']['type'], 'object', name)
            self.assertIs(wf['input_schema']['additionalProperties'], False, name)
            for form in wf.get('forms', []):
                for field in form['fields']:
                    self.assertIn(field['name'], wf['input_schema']['properties'], f'{name}: {field["name"]}')

    def test_code_has_no_template_action_and_declares_exactly_its_tools(self):
        expected = {'publish-web': {'read_file', 'write_file', 'ssh_upload_v1'}, 'publish-email': {'read_file', 'write_file', 'google_mail_send'},
                    'publish-social': {'read_file', 'write_file', 'social_post_create_v1'}, 'publish-remove': {'read_file', 'write_file', 'ssh_remove_v1', 'social_post_delete_v1'},
                    'publish-status': {'read_file', 'write_file', 'social_post_get_v1'}, 'publish-list': {'read_file', 'list_files'}, 'publish-read': {'read_file'},
                    'publish-plan': {'read_file'}}
        for name, wf in self.workflows.items():
            declared_all = set()
            for action in wf['actions']:
                if action['type'] != 'code_execution':
                    continue
                source = action['code']
                self.assertNotIn('{{', source.replace('{{ json . }}', ''), f'{name}/{action["id"]}')
                used = set(re.findall(r'(?:callTool|callExternal|storageCall)\("([^"]+)"', source))
                declared = set(action.get('context', {}).get('allowed_tools', []))
                self.assertEqual(used, declared, f'{name}/{action["id"]}')
                self.assertNotIn('--', ''.join(used), 'tools are called by their bare name')
                declared_all |= declared
            self.assertEqual(declared_all, expected[name], name)

    def test_plan_writes_nothing_and_llm_answers_text(self):
        plan = self.workflows['publish-plan']
        self.assertNotIn('write_file', json.dumps(plan))
        for action in plan['actions']:
            if action['type'] == 'llm_call':
                self.assertEqual(action['llm_response_format'], 'text')
                self.assertNotIn('llm_response_schema', action)

    def test_every_diffusion_demands_a_manual_confirmation_before_any_call(self):
        for name, node_id in (('publish-web', 'publish'), ('publish-email', 'publish'), ('publish-social', 'publish'), ('publish-remove', 'remove')):
            self.assertIn('confirmation_manuelle', self.workflows[name]['input_schema']['required'], name)
            base = {'publish-web': WEB, 'publish-email': EMAIL, 'publish-social': SOCIAL, 'publish-remove': {'publication_id': 'page-1'}}[name]
            for value in ('non', False, '', None, 'false'):
                out = run_node(name, node_id, {**base, 'confirmation_manuelle': value}, dict(FILES))
                self.assertTrue(out['error'].startswith('manual_confirmation_required'), (name, value, out))
                self.assertEqual(out['calls'], [], 'nothing may be read or written before the confirmation')
        self.assertNotIn('confirmation_manuelle', self.workflows['publish-status']['input_schema']['properties'])

    def test_destinations_are_explicit_arguments(self):
        self.assertLessEqual({'target', 'remote_path'}, set(self.workflows['publish-web']['input_schema']['required']))
        self.assertIn('to', self.workflows['publish-email']['input_schema']['required'])
        self.assertIn('channels', self.workflows['publish-social']['input_schema']['required'])
        for name in ('publish-web', 'publish-email', 'publish-social'):
            self.assertNotIn('llm_call', json.dumps([a['type'] for a in self.workflows[name]['actions']]), name)

    def test_miniapp_events_point_at_existing_workflows_and_forms(self):
        app = load(MODULE / 'agents/main/miniapps/publish-tracker.json')
        events = {e['event_id']: e for e in app['events']}
        for event in events.values():
            wf = self.workflows[event['workflow']['workflow_id']]
            self.assertLessEqual(set(event['workflow']['input']), set(wf['input_schema']['properties']))
            if event['trigger'] == 'form.submit':
                self.assertTrue(wf.get('forms') and any(f['name'] == 'publication_id' for f in wf['forms'][0]['fields']), event['event_id'])
        self.assertEqual(events['remove']['workflow']['input']['confirmation_manuelle'], '{{ state.confirmation_manuelle }}')
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
        self.assertTrue(buttons and set(buttons) <= set(events))

    def test_generator_reproduces_the_published_files(self):
        files = [p for p in MODULE.rglob('*') if p.is_file() and p.name != 'README.md']
        before = {p: p.read_bytes() for p in files}
        build.build()
        after = {p: p.read_bytes() for p in MODULE.rglob('*') if p.is_file() and p in before}
        self.assertEqual(before, after)
        self.assertEqual({p for p in MODULE.rglob('*') if p.is_file() and p.suffix == '.json'} - set(before), set())


class WebTest(unittest.TestCase):
    def test_upload_goes_through_base64_and_the_journal_is_written_before(self):
        out = web()
        res = ok(self, out)
        self.assertEqual((res['status'], res['channel'], res['publication_id'], res['already_published']), ('published', 'web', 'page-1', False))
        self.assertEqual(res['remote']['sha256'], HTML_SHA)
        up = external(out)
        self.assertEqual([c['name'] for c in up], ['ssh_upload_v1'])
        self.assertEqual(up[0]['raw'], {'target': 'site-main', 'path': 'news/page.html', 'file': {'content_base64': base64.b64encode(HTML.encode()).decode()}, 'overwrite': False})
        # the source is read as base64 and the journal already says requested when the upload is called
        self.assertTrue(any(c['name'] == 'read_file' and c['args'].get('encoding') == 'base64' for c in out['calls']))
        before = out['atCall'][0]['logs']['/publish/log/page-1.json']
        self.assertEqual((before['status'], before['attempts'], before['remote']), ('requested', 1, None))
        rec = record(out, 'page-1')
        self.assertEqual((rec['schema'], rec['status'], rec['revision']), ('publish.record/v1', 'published', 2))
        self.assertEqual(rec['source'], {'kind': 'storage', 'path': '/docs/page.html', 'sha256': HTML_SHA, 'bytes': len(HTML)})
        self.assertEqual((rec['target'], rec['options']), ({'ssh_target': 'site-main', 'path': 'news/page.html'}, {'overwrite': False}))
        self.assertEqual([h['action'] for h in rec['history']], ['requested', 'published'])

    def test_a_derived_id_and_a_published_publication_is_not_published_twice(self):
        first = web(ctx={'publication_id': None})
        res = ok(self, first)
        self.assertRegex(res['publication_id'], r'^web-[0-9a-f]{12}$')
        second = run_node('publish-web', 'publish', {**WEB, 'publication_id': None}, first['fs'])
        again = ok(self, second)
        self.assertEqual((again['publication_id'], again['already_published'], again['status']), (res['publication_id'], True, 'published'))
        self.assertEqual(external(second), [])
        self.assertEqual(writes(second), [])

    def test_same_id_with_another_request_is_a_conflict(self):
        first = ok(self, web()) and web()
        out = run_node('publish-web', 'publish', {**WEB, 'remote_path': 'news/other.html'}, first['fs'])
        self.assertTrue(out['error'].startswith('publication_conflict'), out)
        self.assertEqual(external(out), [])

    def test_upload_error_is_journaled_failed_then_retried(self):
        out = web(upload_error='publish_not_enabled')
        self.assertTrue(out['error'].startswith('publication_failed: page-1 : publish_not_enabled'), out)
        rec = record(out, 'page-1')
        self.assertEqual((rec['status'], rec['error']['code']), ('failed', 'publish_not_enabled'))
        retry = run_node('publish-web', 'publish', WEB, out['fs'])
        res = ok(self, retry)
        self.assertEqual((res['status'], res['attempts']), ('published', 2))

    def test_returned_sha256_is_checked(self):
        out = web(bad_sha=True)
        self.assertIn('remote_integrity_failed', out['error'])
        self.assertEqual(record(out, 'page-1')['status'], 'failed')

    def test_source_integrity_and_storage_errors(self):
        out = web(ctx={'source_sha256': '0' * 64})
        self.assertTrue(out['error'].startswith('source_integrity_failed'), out)
        self.assertEqual((writes(out), external(out)), ([], []))
        ok(self, web(ctx={'source_sha256': HTML_SHA.upper()}))
        out = web(fs={})
        self.assertTrue(out['error'].startswith('source_not_found'), out)
        out = web(read_error='backend down')
        self.assertTrue(out['error'].startswith('storage_unavailable'), out)
        self.assertEqual((writes(out), external(out)), ([], []))

    def test_storage_write_errors_are_not_swallowed(self):
        out = web(write_error='disk full')
        self.assertTrue(out['error'].startswith('storage_unavailable'), out)
        self.assertEqual(external(out), [], 'no external call when the journal cannot be written')

    def test_concurrent_update_of_the_journal_is_reported_with_the_remote_ids(self):
        out = web(tamper=True)
        self.assertTrue(out['error'].startswith('log_write_failed'), out)
        self.assertIn('concurrent_update', out['error'])
        self.assertIn(HTML_SHA, out['error'])

    def test_bad_arguments_are_refused_before_any_call(self):
        for extra in ({'remote_path': '../x.html'}, {'remote_path': '/abs.html'}, {'remote_path': 'a//b'}, {'remote_path': 'a/./b'}, {'remote_path': 'a/'},
                      {'target': 'x y'}, {'target': ''}, {'source_path': '/publish/log/page-1.json'}, {'source_path': '/docs/../etc'}, {'source_path': 'docs/page.html'},
                      {'publication_id': 'Bad_ID'}, {'source_path': '/docs/x.html\n'}):
            out = web(ctx=extra)
            self.assertIn('error', out, extra)
            self.assertEqual((writes(out), external(out)), ([], []), extra)

    def test_unsafe_keys_are_refused(self):
        raw = json.dumps({**WEB}).rstrip('}') + ', "__proto__": {"x": 1}}'
        out = run_node('publish-web', 'publish', WEB, dict(FILES), raw_ctx=raw)
        self.assertTrue(out['error'].startswith('data_invalid'), out)
        out = web(ctx={'extra': {'constructor': 1}})
        self.assertTrue(out['error'].startswith('data_invalid'), out)
        self.assertEqual(out['calls'], [])

    def test_a_binary_source_goes_through_unchanged(self):
        out = web(ctx={'source_path': '/docs/note.pdf', 'remote_path': 'files/note.pdf', 'publication_id': 'pdf-1'})
        res = ok(self, out)
        self.assertEqual(res['remote']['sha256'], hashlib.sha256(b'%PDF-1.7 fake').hexdigest())

    def test_overwrite_is_an_explicit_choice(self):
        out = web(ctx={'overwrite': 'oui'})
        self.assertIs(external(ok(self, out) and out)[0]['raw']['overwrite'], True)


class EmailTest(unittest.TestCase):
    def test_send_email_shape_and_journal(self):
        out = email()
        res = ok(self, out)
        self.assertEqual((res['status'], res['channel']), ('published', 'email'))
        sent = external(out)
        self.assertEqual([c['name'] for c in sent], ['google_mail_send'])
        self.assertEqual(sent[0]['raw'], {'to': 'ada@example.invalid, bob@example.invalid', 'subject': 'Nouvelles', 'body': 'Bonjour'})
        self.assertEqual(out['atCall'][0]['logs']['/publish/log/mail-1.json']['status'], 'requested')
        rec = record(out, 'mail-1')
        self.assertEqual((rec['status'], rec['remote']['message_id'], rec['remote']['thread_id']), ('published', 'msg-1', 'thr-1'))
        self.assertEqual(rec['target']['to'], EMAIL['to'])

    def test_recipients_can_be_a_comma_separated_string_and_body_a_text_file(self):
        out = email(ctx={'to': 'ada@example.invalid, bob@example.invalid', 'body': None, 'source_path': '/docs/post.md'})
        ok(self, out)
        self.assertEqual(external(out)[0]['raw']['body'], 'Bonjour le monde')

    def test_header_injection_and_bad_addresses_are_refused(self):
        for extra in ({'subject': 'a\r\nBcc: x@example.invalid'}, {'to': ['not-an-address']}, {'to': ['a@example.invalid\nBcc: b@example.invalid']},
                      {'to': []}, {'to': ['a@example.invalid'] * 2}, {'to': [f'u{i}@example.invalid' for i in range(11)]}, {'subject': ''},
                      {'body': 'x', 'source_path': '/docs/post.md'}, {'body': None}, {'body': None, 'source_path': '/docs/note.pdf'},
                      {'body': None, 'source_path': '/docs/page.html'}):
            out = email(ctx=extra)
            self.assertIn('error', out, extra)
            self.assertEqual((writes(out), external(out)), ([], []), extra)

    def test_connector_error_is_journaled_with_its_code(self):
        out = email(mail_error='not_connected')
        self.assertIn('publication_failed: mail-1 : not_connected', out['error'])
        self.assertEqual(record(out, 'mail-1')['status'], 'failed')

    def test_a_4xx_answer_is_a_failure(self):
        out = email(mail_status=400)
        self.assertIn('email_rejected', out['error'])
        self.assertEqual(record(out, 'mail-1')['status'], 'failed')

    def test_an_unknown_outcome_is_never_retried_automatically(self):
        out = email(write_error=None)
        done = ok(self, out) and out
        rec = record(done, 'mail-1')
        rec['status'] = 'requested'
        done['fs']['/publish/log/mail-1.json'] = {'text': json.dumps(rec)}
        retry = run_node('publish-email', 'publish', EMAIL, done['fs'])
        self.assertTrue(retry['error'].startswith('publication_outcome_unknown'), retry)
        self.assertEqual(external(retry), [])

    def test_a_sent_email_is_not_sent_twice(self):
        first = email()
        again = run_node('publish-email', 'publish', EMAIL, first['fs'])
        self.assertIs(ok(self, again)['already_published'], True)
        self.assertEqual(external(again), [])


class SocialTest(unittest.TestCase):
    def test_draft_post_uses_the_publication_id_as_idempotency_key(self):
        out = social()
        res = ok(self, out)
        self.assertEqual((res['status'], res['remote']['post_id'], res['remote']['state']), ('published', 'post-1', 'draft'))
        call = external(out)[0]
        self.assertEqual(call['name'], 'social_post_create_v1')
        self.assertEqual(call['raw'], {'channels': ['c1', 'c2'], 'content': 'Un post', 'mode': 'draft', 'idempotency_key': 'post-a'})
        self.assertEqual(out['atCall'][0]['logs']['/publish/log/post-a.json']['status'], 'requested')

    def test_derived_id_is_the_idempotency_key_and_repeat_does_not_republish(self):
        first = social(ctx={'publication_id': None})
        pid = ok(self, first)['publication_id']
        self.assertEqual(external(first)[0]['raw']['idempotency_key'], pid)
        again = run_node('publish-social', 'publish', {**SOCIAL, 'publication_id': None}, first['fs'])
        self.assertIs(ok(self, again)['already_published'], True)
        self.assertEqual(external(again), [])

    def test_schedule_rules(self):
        out = social(ctx={'mode': 'schedule', 'schedule_at': '2026-12-01T09:00:00+01:00'})
        self.assertEqual(ok(self, out)['remote']['state'], 'scheduled')
        self.assertEqual(external(out)[0]['raw']['schedule_at'], '2026-12-01T09:00:00+01:00')
        for extra in ({'mode': 'schedule'}, {'mode': 'schedule', 'schedule_at': '2026-11-07T09:00:00Z'}, {'mode': 'schedule', 'schedule_at': 'tomorrow'},
                      {'mode': 'draft', 'schedule_at': '2026-12-01T09:00:00Z'}, {'mode': 'later'}):
            out = social(ctx=extra)
            self.assertIn('error', out, extra)
            self.assertEqual((writes(out), external(out)), ([], []), extra)

    def test_media_and_text_file(self):
        out = social(ctx={'content': None, 'source_path': '/docs/post.md', 'media_paths': ['/docs/logo.png'], 'mode': 'now'})
        res = ok(self, out)
        self.assertEqual(res['remote']['state'], 'published')
        raw = external(out)[0]['raw']
        self.assertEqual(raw['content'], 'Bonjour le monde')
        self.assertEqual([(m['filename'], m['mime_type']) for m in raw['media']], [('logo.png', 'image/png')])
        self.assertEqual(record(out, 'post-a')['target']['media'][0]['path'], '/docs/logo.png')

    def test_bad_arguments(self):
        for extra in ({'channels': []}, {'channels': ['a b']}, {'channels': ['c1', 'c1']}, {'channels': [f'c{i}' for i in range(11)]}, {'content': ''},
                      {'content': 'x' * 5001}, {'content': 'x', 'source_path': '/docs/post.md'}, {'media_paths': ['/docs/note.pdf']},
                      {'media_paths': ['/docs/logo.png'] * 5}):
            out = social(ctx=extra)
            self.assertIn('error', out, extra)
            self.assertEqual((writes(out), external(out)), ([], []), extra)

    def test_service_errors_are_journaled(self):
        out = social(social_error='rate_limited')
        self.assertIn('rate_limited', out['error'])
        self.assertEqual(record(out, 'post-a')['status'], 'failed')
        out = social(no_post_id=True)
        self.assertIn('remote_response_invalid', out['error'])
        self.assertEqual(record(out, 'post-a')['status'], 'failed')
        retry = run_node('publish-social', 'publish', SOCIAL, out['fs'])
        self.assertEqual(ok(self, retry)['attempts'], 2)


class RemoveStatusTest(unittest.TestCase):
    def published(self, kind):
        out = {'web': web, 'email': email, 'social': social}[kind]()
        ok(self, out)
        return out['fs'], {'web': 'page-1', 'email': 'mail-1', 'social': 'post-a'}[kind]

    def remove(self, fs, pid, **opts):
        return run_node('publish-remove', 'remove', {'publication_id': pid, **CONFIRMED}, fs, **opts)

    def test_remove_web_uses_the_recorded_target(self):
        fs, pid = self.published('web')
        out = self.remove(fs, pid)
        res = ok(self, out)
        self.assertEqual(res['status'], 'removed')
        call = external(out)[0]
        self.assertEqual((call['name'], call['raw']), ('ssh_remove_v1', {'target': 'site-main', 'path': 'news/page.html'}))
        # the intent is journaled before the call and the status stays published until it is confirmed
        mid = out['atCall'][0]['logs'][f'/publish/log/{pid}.json']
        self.assertEqual((mid['status'], mid['history'][-1]['action']), ('published', 'remove_requested'))
        self.assertEqual([h['action'] for h in record(out, pid)['history']], ['requested', 'published', 'remove_requested', 'removed'])

    def test_remove_social_and_republish_after_removal(self):
        fs, pid = self.published('social')
        out = self.remove(fs, pid)
        self.assertEqual(external(out)[0]['raw'], {'post_id': 'post-1'})
        self.assertEqual(record(out, pid)['status'], 'removed')
        again = run_node('publish-social', 'publish', SOCIAL, out['fs'])
        res = ok(self, again)
        self.assertEqual((res['already_removed'], res['status'], res['attempts']), (True, 'removed', 1))
        self.assertEqual((external(again), writes(again)), ([], []))
        # a new publication needs a new id: explicit attempt on a derived id
        derived = {**SOCIAL, 'publication_id': None}
        a = social(ctx={'publication_id': None})
        pid1 = ok(self, a)['publication_id']
        rm = self.remove(a['fs'], pid1)
        same = ok(self, run_node('publish-social', 'publish', derived, rm['fs']))
        self.assertEqual((same['publication_id'], same['already_removed']), (pid1, True))
        second = run_node('publish-social', 'publish', {**derived, 'attempt': 2}, rm['fs'])
        res2 = ok(self, second)
        self.assertEqual((res2['publication_id'], res2['status'], res2['already_removed']), (pid1 + '-a2', 'published', False))
        self.assertTrue(run_node('publish-social', 'publish', {**SOCIAL, 'attempt': 2}, {})['error'].startswith('attempt_invalid'))
        self.assertTrue(run_node('publish-social', 'publish', {**derived, 'attempt': 100}, {})['error'].startswith('attempt_invalid'))

    def test_an_email_is_not_removable(self):
        fs, pid = self.published('email')
        out = self.remove(fs, pid)
        self.assertTrue(out['error'].startswith('not_removable'), out)
        self.assertEqual((external(out), writes(out)), ([], []))

    def test_only_a_published_publication_is_removed(self):
        fs, pid = self.published('web')
        done = self.remove(fs, pid)
        again = self.remove(done['fs'], pid)
        self.assertTrue(again['error'].startswith('status_invalid'), again)
        out = self.remove({}, 'unknown')
        self.assertTrue(out['error'].startswith('publication_not_found'), out)
        bad = web(upload_error='x')
        self.assertTrue(self.remove(bad['fs'], 'page-1')['error'].startswith('status_invalid'))

    def test_a_failed_removal_keeps_the_status_and_the_trace(self):
        fs, pid = self.published('web')
        out = self.remove(fs, pid, remove_error='permission_denied')
        self.assertTrue(out['error'].startswith('removal_failed'), out)
        self.assertIn('permission_denied', out['error'])
        rec = record(out, pid)
        self.assertEqual((rec['status'], rec['history'][-1]['action']), ('published', 'remove_failed'))

    def test_a_tampered_journal_cannot_aim_the_removal_elsewhere(self):
        fs, pid = self.published('web')
        rec = json.loads(fs[f'/publish/log/{pid}.json']['text'])
        rec['target']['path'] = '../../etc/passwd'
        fs[f'/publish/log/{pid}.json'] = {'text': json.dumps(rec)}
        out = self.remove(fs, pid)
        self.assertTrue(out['error'].startswith('remote_path_invalid'), out)
        self.assertEqual(external(out), [])

    def test_status_reads_the_social_post_again(self):
        fs, pid = self.published('social')
        out = run_node('publish-status', 'status', {'publication_id': pid}, fs)
        res = ok(self, out)
        self.assertIs(res['remote_checked'], True)
        self.assertEqual((external(out)[0]['name'], external(out)[0]['raw']), ('social_post_get_v1', {'post_id': 'post-1'}))
        rec = record(out, pid)
        self.assertEqual((rec['remote']['state'], rec['remote']['channels'][0]['url']), ('published', 'https://social.example.invalid/p/1'))
        self.assertEqual(rec['history'][-1]['action'], 'status_checked')

    def test_status_of_a_web_or_email_publication_is_the_journal(self):
        for kind in ('web', 'email'):
            fs, pid = self.published(kind)
            out = run_node('publish-status', 'status', {'publication_id': pid}, fs)
            self.assertIs(ok(self, out)['remote_checked'], False)
            self.assertEqual((external(out), writes(out)), ([], []))


class ReviewTest(unittest.TestCase):
    def test_email_is_published_only_on_proof(self):
        for opts, status, code in (({'mail_empty': True}, 'outcome_unknown', 'outcome_unknown'), ({'mail_no_id': True}, 'outcome_unknown', 'outcome_unknown'),
                                   ({'mail_status': 400}, 'failed', 'email_rejected'), ({'mail_status': 500}, 'outcome_unknown', 'outcome_unknown'), ({'mail_error': 'quota_exceeded'}, 'outcome_unknown', 'outcome_unknown'), ({'mail_returned_error': True}, 'failed', 'authorization_required'),
                                   ({'mail_error': 'identity_unproven'}, 'failed', 'identity_unproven')):
            out = email(**opts)
            self.assertIn('error', out, opts)
            rec = record(out, 'mail-1')
            self.assertEqual((rec['status'], rec['error']['code']), (status, code), opts)
        done = email(mail_body_string=True)
        self.assertEqual(record(done, 'mail-1')['remote']['message_id'], 'msg-s')

    def test_an_error_raised_during_the_call_is_an_unknown_outcome(self):
        for runner, opts, pid in ((email, {'mail_throw': 'deadline exceeded'}, 'mail-1'), (web, {'upload_throw': 'connection reset'}, 'page-1'),
                                  (social, {'social_throw': 'timeout'}, 'post-a')):
            out = runner(**opts)
            self.assertTrue(out['error'].startswith('publication_outcome_unknown'), out)
            self.assertEqual(record(out, pid)['status'], 'outcome_unknown')
            retry_ctx = {'mail-1': EMAIL, 'page-1': WEB, 'post-a': SOCIAL}[pid]
            wf = {'mail-1': 'publish-email', 'page-1': 'publish-web', 'post-a': 'publish-social'}[pid]
            again = run_node(wf, 'publish', retry_ctx, out['fs'])
            self.assertTrue(again['error'].startswith('publication_outcome_unknown'), again)
            self.assertEqual(external(again), [])
            forced = run_node(wf, 'publish', {**retry_ctx, 'resend_after_unknown': 'oui'}, out['fs'])
            res = ok(self, forced)
            self.assertEqual((res['status'], res['attempts']), ('published', 2))
            self.assertIn('resend_after_unknown', [h['action'] for h in record(forced, pid)['history']])
            # the explicit resend still needs the manual confirmation
            no = run_node(wf, 'publish', {**retry_ctx, 'resend_after_unknown': 'oui', 'confirmation_manuelle': 'non'}, out['fs'])
            self.assertTrue(no['error'].startswith('manual_confirmation_required'))

    def test_a_tool_error_with_a_code_stays_a_definitive_failure_and_failed_retries(self):
        out = web(upload_error='publish_not_enabled')
        self.assertEqual(record(out, 'page-1')['status'], 'failed')
        self.assertEqual(ok(self, run_node('publish-web', 'publish', WEB, out['fs']))['attempts'], 2)

    def test_storage_errors_returned_instead_of_raised_are_errors(self):
        for tool, prefix, runner, ctx in (('write_file', '/publish/', 'publish-web', WEB), ('read_file', '/docs/', 'publish-web', WEB)):
            for mode in ('isError', 'error'):
                out = run_node(runner, 'publish', ctx, dict(FILES), ret_error={'tool': tool, 'prefix': prefix, 'mode': mode, 'msg': 'backend down'})
                self.assertTrue(out['error'].startswith('storage_unavailable'), (tool, mode, out))
                self.assertEqual(external(out), [], tool)
        # the journal read: a returned error is not "no record"
        for mode in ('isError', 'error'):
            out = run_node('publish-web', 'publish', WEB, dict(FILES), ret_error={'tool': 'read_file', 'prefix': '/publish/', 'mode': mode, 'msg': 'backend down'})
            self.assertTrue(out['error'].startswith('storage_unavailable'), out)
            self.assertEqual((external(out), writes(out)), ([], []))
            out = run_node('publish-list', 'list', {}, {}, ret_error={'tool': 'list_files', 'mode': mode, 'msg': 'backend down'})
            self.assertTrue(out['error'].startswith('storage_unavailable'), out)
        # only a returned "not found" counts as absent
        out = run_node('publish-list', 'list', {}, {}, ret_error={'tool': 'list_files', 'mode': 'error', 'msg': 'failed to list files: object not found'})
        self.assertEqual(ok(self, out)['total'], 0)
        out = run_node('publish-web', 'publish', WEB, dict(FILES), ret_error={'tool': 'read_file', 'prefix': '/docs/', 'mode': 'isError', 'msg': 'failed to download file: status 404'})
        self.assertTrue(out['error'].startswith('source_not_found'), out)
        # a write answer carrying an error after the external call: the journal write fails, remote ids reported
        out = run_node('publish-web', 'publish', WEB, dict(FILES), ret_error={'tool': 'write_file', 'prefix': '/publish/log/page-1.json', 'mode': 'error', 'msg': 'disk full'})
        self.assertTrue(out['error'].startswith('storage_unavailable'), out)

    def test_removed_is_terminal_and_failed_is_the_only_state_that_retries(self):
        a = web()
        rm = run_node('publish-remove', 'remove', {'publication_id': 'page-1', **CONFIRMED}, a['fs'])
        again = ok(self, run_node('publish-web', 'publish', WEB, rm['fs']))
        self.assertEqual((again['already_removed'], again['status']), (True, 'removed'))
        self.assertEqual(ok(self, run_node('publish-web', 'publish', {**WEB, 'publication_id': None, 'attempt': 2}, rm['fs']))['publication_id'][-3:], '-a2')


class Review2Test(unittest.TestCase):
    CASES = (('publish-web', WEB, 'ssh_upload_v1'), ('publish-email', EMAIL, 'google_mail_send'), ('publish-social', SOCIAL, 'social_post_create_v1'))

    def test_a_structured_storage_error_on_the_first_journal_write_stops_before_any_external_call(self):
        for mode in ('object', 'status', 'json', 'string', 'error', 'isError'):
            for wf, ctx, tool in self.CASES:
                out = run_node(wf, 'publish', ctx, dict(FILES), ret_error={'tool': 'write_file', 'prefix': '/publish/', 'mode': mode, 'msg': 'disk full'})
                self.assertTrue(out['error'].startswith('storage_unavailable'), (wf, mode, out))
                self.assertEqual(external(out), [], (wf, mode))
                self.assertNotIn('/publish/log/' + ctx['publication_id'] + '.json', out['fs'])

    def test_a_write_that_is_not_really_stored_stops_before_any_external_call(self):
        for wf, ctx, tool in self.CASES:
            out = run_node(wf, 'publish', ctx, dict(FILES), drop_writes=True)
            self.assertTrue(out['error'].startswith('journal_unverified'), (wf, out))
            self.assertEqual(external(out), [], wf)

    def test_a_read_file_whose_content_mentions_error_is_not_an_error(self):
        fs = {**FILES, '/docs/e.md': {'text': '{"error": "just text"}'}}
        out = social(fs=fs, ctx={'content': None, 'source_path': '/docs/e.md'})
        self.assertEqual(ok(self, out)['status'], 'published')

    def test_a_published_scheduled_post_replays_after_its_date_on_every_channel(self):
        sched = {**SOCIAL, 'mode': 'schedule', 'schedule_at': '2026-11-07T11:00:00Z'}
        first = run_node('publish-social', 'publish', sched, dict(FILES))
        self.assertEqual(ok(self, first)['status'], 'published')
        late = run_node('publish-social', 'publish', sched, first['fs'], now='2026-11-08T10:00:00Z')
        self.assertIs(ok(self, late)['already_published'], True)
        self.assertEqual((external(late), writes(late)), ([], []))
        # a new schedule in the past is still refused, and writes nothing
        fresh = run_node('publish-social', 'publish', {**sched, 'publication_id': 'post-b'}, dict(FILES), now='2026-11-08T10:00:00Z')
        self.assertTrue(fresh['error'].startswith('schedule_at_invalid'), fresh)
        self.assertEqual((external(fresh), writes(fresh)), ([], []))
        # same order on web and e-mail: a published publication answers before anything else can refuse it
        for wf, ctx, runner in (('publish-web', WEB, web), ('publish-email', EMAIL, email)):
            done = runner()
            again = run_node(wf, 'publish', ctx, done['fs'], now='2030-01-01T00:00:00Z')
            self.assertIs(ok(self, again)['already_published'], True, wf)
            self.assertEqual((external(again), writes(again)), ([], []), wf)

    def test_overwrite_resume_after_an_integrity_failure(self):
        bad = web(bad_sha=True)
        self.assertEqual(record(bad, 'page-1')['status'], 'failed')
        resumed = run_node('publish-web', 'publish', {**WEB, 'overwrite': 'oui'}, bad['fs'])
        res = ok(self, resumed)
        self.assertEqual((res['status'], res['attempts'], res['publication_id']), ('published', 2, 'page-1'))
        self.assertIs(external(resumed)[0]['raw']['overwrite'], True)
        self.assertEqual(record(resumed, 'page-1')['options'], {'overwrite': True})
        # derived id: overwrite, resend and attempt do not change it
        a = web(ctx={'publication_id': None}, bad_sha=True)
        pid = [k for k in a['fs'] if k.startswith('/publish/log/')][0].split('/')[-1][:-5]
        b = run_node('publish-web', 'publish', {**WEB, 'publication_id': None, 'overwrite': 'oui'}, a['fs'])
        self.assertEqual(ok(self, b)['publication_id'], pid)


class Review3Test(unittest.TestCase):
    CASES = (('publish-web', WEB, 'page-1'), ('publish-email', EMAIL, 'mail-1'), ('publish-social', SOCIAL, 'post-a'))

    def test_every_journal_write_is_read_back(self):
        # published: the call happened, the journal write is not visible
        for wf, ctx, pid in self.CASES:
            out = run_node(wf, 'publish', ctx, dict(FILES), drop_from=2)
            self.assertTrue(out['error'].startswith('journal_unverified'), (wf, out))
            self.assertIn('la diffusion a eu lieu', out['error'])
            self.assertEqual(len(external(out)), 1, wf)
        # failed
        out = web(upload_error='publish_not_enabled', drop_from=2)
        self.assertTrue(out['error'].startswith('journal_unverified'), out)
        self.assertIn('publish_not_enabled', out['error'])
        # outcome_unknown
        out = email(mail_throw='deadline exceeded', drop_from=2)
        self.assertTrue(out['error'].startswith('journal_unverified'), out)
        self.assertIn('inconnue', out['error'])
        # removed
        done = web()
        out = run_node('publish-remove', 'remove', {'publication_id': 'page-1', **CONFIRMED}, done['fs'], drop_from=2)
        self.assertTrue(out['error'].startswith('journal_unverified'), out)
        self.assertIn('retrait a eu lieu', out['error'])

    def test_a_newer_publication_on_the_same_destination_cannot_be_removed_by_the_older_one(self):
        fs = dict(FILES)
        fs['/docs/other.html'] = {'text': '<h1>New</h1>'}
        a = run_node('publish-web', 'publish', WEB, fs)
        b = run_node('publish-web', 'publish', {**WEB, 'publication_id': 'page-2', 'source_path': '/docs/other.html', 'overwrite': 'oui'}, a['fs'])
        self.assertEqual(ok(self, b)['status'], 'published')
        rm = run_node('publish-remove', 'remove', {'publication_id': 'page-1', **CONFIRMED}, b['fs'])
        self.assertTrue(rm['error'].startswith('destination_superseded'), rm)
        self.assertIn('page-2', rm['error'])
        self.assertEqual((external(rm), writes(rm)), ([], []))
        self.assertEqual(record(rm, 'page-1')['status'], 'published')
        rm2 = run_node('publish-remove', 'remove', {'publication_id': 'page-2', **CONFIRMED}, b['fs'])
        self.assertEqual(ok(self, rm2)['status'], 'removed')
        self.assertEqual(external(rm2)[0]['raw'], {'target': 'site-main', 'path': 'news/page.html'})
        # a reservation that cannot be confirmed: no upload at all
        out = run_node('publish-web', 'publish', WEB, dict(FILES), ret_error={'tool': 'write_file', 'prefix': '/publish/dest/', 'mode': 'object', 'msg': 'x'})
        self.assertIn('destination_index_failed', out['error'])
        self.assertEqual(external(out), [])
        # a final index that cannot be confirmed leaves the publication in outcome_unknown, never published
        out = run_node('publish-web', 'publish', WEB, dict(FILES), dest_fail_from=2)
        self.assertTrue(out['error'].startswith('publication_outcome_unknown'), out)
        self.assertEqual(record(out, 'page-1')['status'], 'outcome_unknown')

    def test_remote_ids_are_never_truncated(self):
        long_id = 'p' * 1024
        out = social(post_id_len=1024)
        self.assertEqual(record(out, 'post-a')['remote']['post_id'], long_id)
        st = run_node('publish-status', 'status', {'publication_id': 'post-a'}, out['fs'])
        self.assertEqual(external(st)[0]['raw'], {'post_id': long_id})
        rm = run_node('publish-remove', 'remove', {'publication_id': 'post-a', **CONFIRMED}, out['fs'])
        self.assertEqual(external(rm)[0]['raw'], {'post_id': long_id})
        bad = social(post_id_len=1025)
        self.assertTrue(bad['error'].startswith('publication_failed'), bad)
        self.assertIn('remote_id_invalid', bad['error'])
        self.assertEqual(record(bad, 'post-a')['status'], 'failed')
        mail = email(mail_id_len=1025)
        self.assertEqual(record(mail, 'mail-1')['status'], 'outcome_unknown')
        self.assertEqual(record(email(mail_id_len=1024), 'mail-1')['remote']['message_id'], 'm' * 1024)


class Review4Test(unittest.TestCase):
    def test_the_destination_is_reserved_before_the_upload_and_a_failed_replacement_still_supersedes(self):
        fs = dict(FILES)
        fs['/docs/other.html'] = {'text': '<h1>New</h1>'}
        for opts in ({}, {'upload_error': 'internal_error'}, {'upload_throw': 'connection reset'}):
            a = run_node('publish-web', 'publish', WEB, dict(fs))
            b = run_node('publish-web', 'publish', {**WEB, 'publication_id': 'page-2', 'source_path': '/docs/other.html', 'overwrite': 'oui'}, a['fs'], **opts)
            dests = list(b['atCall'][0]['dests'].values())
            self.assertEqual([(d['owner'], d['state']) for d in dests], [('page-2', 'pending_owner')], opts)
            rm = run_node('publish-remove', 'remove', {'publication_id': 'page-1', **CONFIRMED}, b['fs'])
            self.assertTrue(rm['error'].startswith('destination_superseded'), (opts, rm))
            self.assertEqual(external(rm), [], opts)

    def test_an_error_in_an_envelope_is_an_error_on_every_storage_tool(self):
        wrapped = {'data': {'error': {'code': 'disk_full'}}}
        for tool, wf, node_id, ctx in (('list_files', 'publish-list', 'list', {}), ('write_file', 'publish-web', 'publish', WEB), ('read_file', 'publish-read', 'read', {'publication_id': 'x'})):
            for payload in (wrapped, {'result': {'data': {'error': 'disk_full'}}}, {'content': [{'type': 'text', 'text': json.dumps(wrapped)}]}):
                if tool == 'read_file' and 'content' in payload:
                    continue
                out = run_node(wf, node_id, ctx, dict(FILES), ret_error={'tool': tool, 'prefix': '/publish/' if tool != 'read_file' else None, 'mode': 'raw', 'raw': payload})
                self.assertTrue(out['error'].startswith('storage_unavailable'), (tool, payload, out))
                self.assertEqual(external(out), [], tool)
        # depth is bounded and plain data is untouched
        out = run_node('publish-read', 'read', {'publication_id': 'x'}, {'/publish/log/x.json': {'text': json.dumps({'error': {'code': 'in the file'}})}})
        self.assertTrue(out['error'].startswith('record_invalid'), out)

    def test_an_email_5xx_is_an_unknown_outcome_and_is_not_replayed(self):
        out = email(mail_status=500)
        self.assertTrue(out['error'].startswith('publication_outcome_unknown'), out)
        self.assertEqual(record(out, 'mail-1')['status'], 'outcome_unknown')
        again = run_node('publish-email', 'publish', EMAIL, out['fs'])
        self.assertTrue(again['error'].startswith('publication_outcome_unknown'), again)
        self.assertEqual(external(again), [])


class Review5Test(unittest.TestCase):
    def test_the_owner_is_read_again_right_before_the_removal(self):
        done = web()
        out = run_node('publish-remove', 'remove', {'publication_id': 'page-1', **CONFIRMED}, done['fs'], steal_dest=True)
        self.assertTrue(out['error'].startswith('destination_superseded'), out)
        self.assertEqual(external(out), [])
        rec = record(out, 'page-1')
        self.assertEqual((rec['status'], rec['history'][-1]['action']), ('published', 'remove_refused'))

    def test_an_enveloped_mcp_error_is_classified_by_its_code(self):
        out = email(mail_enveloped=True)
        self.assertTrue(out['error'].startswith('publication_failed'), out)
        rec = record(out, 'mail-1')
        self.assertEqual((rec['status'], rec['error']['code']), ('failed', 'not_connected'))
        out = email(mail_enveloped='boom')
        self.assertEqual(record(out, 'mail-1')['status'], 'outcome_unknown')
        out = email(mail_enveloped=json.dumps({'error_code': 'quota_exceeded'}))
        self.assertEqual(record(out, 'mail-1')['status'], 'outcome_unknown')

    def test_the_destination_index_is_read_before_it_is_written(self):
        for mode in ('error', 'isError', 'object'):
            out = run_node('publish-web', 'publish', WEB, dict(FILES), ret_error={'tool': 'read_file', 'prefix': '/publish/dest/', 'mode': mode, 'msg': 'backend down'})
            self.assertTrue(out['error'].startswith('storage_unavailable'), (mode, out))
            self.assertEqual(external(out), [], mode)
            self.assertEqual([k for k in out['fs'] if k.startswith('/publish/dest/')], [], mode)
            self.assertTrue(any(c['name'] == 'write_file' for c in out['calls']) is True)


class Review6Test(unittest.TestCase):
    def test_successful_mcp_envelopes_are_opened_on_the_three_channels(self):
        for env in ('text', 'structured'):
            for runner, pid, channel in ((web, 'page-1', 'web'), (email, 'mail-1', 'email'), (social, 'post-a', 'social')):
                out = runner(envelope=env)
                res = ok(self, out)
                self.assertEqual((res['status'], res['channel']), ('published', channel), (env, channel))
                rec = record(out, pid)
                self.assertEqual(rec['status'], 'published')
                if channel == 'web':
                    self.assertEqual(rec['remote']['sha256'], HTML_SHA)
                if channel == 'email':
                    self.assertEqual(rec['remote']['message_id'], 'msg-1')
                if channel == 'social':
                    self.assertEqual(rec['remote']['post_id'], 'post-1')
        done = web(envelope='text')
        rm = run_node('publish-remove', 'remove', {'publication_id': 'page-1', **CONFIRMED}, done['fs'], envelope='text')
        self.assertEqual(ok(self, rm)['status'], 'removed')
        listed = run_node('publish-list', 'list', {}, done['fs'], envelope='text')
        self.assertEqual(ok(self, listed)['total'], 1)
        listed = run_node('publish-list', 'list', {}, done['fs'], envelope='structured')
        self.assertEqual(ok(self, listed)['total'], 1)

    def test_a_definitive_refusal_gives_the_destination_back_to_the_previous_owner(self):
        fs = dict(FILES)
        fs['/docs/other.html'] = {'text': '<h1>New</h1>'}
        a = run_node('publish-web', 'publish', WEB, fs)
        for code in ('file_exists', 'publish_not_enabled', 'invalid_arguments', 'file_too_large', 'atomic_replace_unavailable'):
            b = run_node('publish-web', 'publish', {**WEB, 'publication_id': 'page-2', 'source_path': '/docs/other.html'}, a['fs'], upload_error=code)
            self.assertIn(code, b['error'])
            dests = [json.loads(v['text']) for k, v in b['fs'].items() if k.startswith('/publish/dest/')]
            self.assertEqual([(d['owner'], d['state']) for d in dests], [('page-1', 'owner')], code)
            rm = run_node('publish-remove', 'remove', {'publication_id': 'page-1', **CONFIRMED}, b['fs'])
            self.assertEqual(ok(self, rm)['status'], 'removed', code)
        # an unknown outcome keeps the reservation
        c = run_node('publish-web', 'publish', {**WEB, 'publication_id': 'page-2', 'source_path': '/docs/other.html'}, a['fs'], upload_throw='connection reset')
        self.assertTrue(run_node('publish-remove', 'remove', {'publication_id': 'page-1', **CONFIRMED}, c['fs'])['error'].startswith('destination_superseded'))


class Review7Test(unittest.TestCase):
    def test_absence_rests_on_a_structured_signal_not_on_free_text(self):
        credential = {'error': {'code': 'backend_unavailable', 'message': 'Storage credential not found'}}
        for tool, wf, node_id, ctx in (('list_files', 'publish-list', 'list', {}), ('read_file', 'publish-read', 'read', {'publication_id': 'x'})):
            out = run_node(wf, node_id, ctx, {}, ret_error={'tool': tool, 'mode': 'raw', 'raw': credential})
            self.assertTrue(out['error'].startswith('storage_unavailable'), (tool, out))
            out = run_node(wf, node_id, ctx, {}, ret_error={'tool': tool, 'mode': 'error', 'msg': 'Storage credential not found'})
            self.assertTrue(out['error'].startswith('storage_unavailable'), (tool, out))
        # a thrown error too
        out = run_node('publish-list', 'list', {}, {}, list_error='Storage credential not found')
        self.assertTrue(out['error'].startswith('storage_unavailable'), out)
        # absence: a code, an explicit 404, or the exact message of the storage tools
        for raw in ({'error': {'code': 'not_found'}}, {'error': {'code': 'ENOENT', 'message': 'x'}}, {'error': 'file_not_found'}, {'error': {'message': 'gone'}, 'status_code': 404},
                    {'error': 'failed to list files: object not found'}):
            out = run_node('publish-list', 'list', {}, {}, ret_error={'tool': 'list_files', 'mode': 'raw', 'raw': raw})
            self.assertEqual(ok(self, out)['total'], 0, raw)
        out = run_node('publish-read', 'read', {'publication_id': 'x'}, {})
        self.assertTrue(out['error'].startswith('publication_not_found'), out)
        for raw in ({'error': 'something not found somewhere'}, {'error': 'no such backend'}):
            out = run_node('publish-list', 'list', {}, {}, ret_error={'tool': 'list_files', 'mode': 'raw', 'raw': raw})
            self.assertTrue(out['error'].startswith('storage_unavailable'), (raw, out))


class Review8Test(unittest.TestCase):
    def test_a_delayed_confirmation_does_not_take_the_destination_back(self):
        fs = dict(FILES)
        out = run_node('publish-web', 'publish', WEB, fs, hijack_dest=True)
        res = ok(self, out)
        self.assertEqual(res['status'], 'published')
        rec = record(out, 'page-1')
        self.assertEqual((rec['superseded_by'], rec['remote']['superseded_by']), ('page-2', 'page-2'))
        dests = [json.loads(v['text']) for k, v in out['fs'].items() if k.startswith('/publish/dest/')]
        self.assertEqual([(d['owner'], d['state']) for d in dests], [('page-2', 'pending_owner')])
        rm = run_node('publish-remove', 'remove', {'publication_id': 'page-1', **CONFIRMED}, out['fs'])
        self.assertTrue(rm['error'].startswith('destination_superseded'), rm)
        self.assertEqual(external(rm), [])
        # an unclear situation (index gone) is an unknown outcome
        out = run_node('publish-web', 'publish', WEB, dict(FILES), vanish_dest=True)
        self.assertTrue(out['error'].startswith('publication_outcome_unknown'), out)
        self.assertEqual(record(out, 'page-1')['status'], 'outcome_unknown')

    def test_is_error_always_wins_on_the_three_channels(self):
        for runner, pid, code in ((web, 'page-1', 'file_exists'), (email, 'mail-1', 'not_connected'), (social, 'post-a', 'rate_limited')):
            out = runner(iserror_env='nocode')
            self.assertIn('error', out, pid)
            self.assertEqual(record(out, pid)['status'], 'outcome_unknown', pid)
            out = runner(iserror_env='code')
            rec = record(out, pid)
            self.assertEqual(rec['error']['code'], code, pid)
            self.assertNotEqual(rec['status'], 'published', pid)


class Review9Test(unittest.TestCase):
    def test_a_restoration_never_overwrites_a_newer_owner(self):
        fs = dict(FILES)
        fs['/docs/other.html'] = {'text': '<h1>New</h1>'}
        p = run_node('publish-web', 'publish', WEB, fs)
        a = run_node('publish-web', 'publish', {**WEB, 'publication_id': 'page-2', 'source_path': '/docs/other.html'}, p['fs'], upload_error='file_exists', hijack_dest=True, hijack_owner='page-3', hijack_state='owner')
        self.assertIn('file_exists', a['error'])
        dests = [json.loads(v['text']) for k, v in a['fs'].items() if k.startswith('/publish/dest/')]
        self.assertEqual([(d['owner'], d['state']) for d in dests], [('page-3', 'owner')])
        self.assertEqual(record(a, 'page-2')['status'], 'failed')

    def test_an_error_field_wins_over_status_and_state(self):
        for runner, pid in ((web, 'page-1'), (social, 'post-a')):
            out = runner(ok_with_error=True)
            self.assertEqual(record(out, pid)['status'], 'outcome_unknown', pid)
            self.assertNotEqual(record(out, pid)['status'], 'published', pid)
        done = social()
        st = run_node('publish-status', 'status', {'publication_id': 'post-a'}, done['fs'], ok_with_error=True)
        self.assertTrue(st['error'].startswith('remote_boom'), st)
        self.assertEqual(writes(st), [])
        self.assertEqual(record(st, 'post-a'), record(done, 'post-a'))
        for pid, runner in (('post-a', social), ('page-1', web)):
            d = runner()
            rm = run_node('publish-remove', 'remove', {'publication_id': pid, **CONFIRMED}, d['fs'], ok_with_error=True)
            self.assertTrue(rm['error'].startswith('removal_failed'), rm)
            self.assertEqual(record(rm, pid)['status'], 'published')


class Review10Test(unittest.TestCase):
    def test_an_error_inside_structured_content_wins(self):
        for runner, pid, status in ((web, 'page-1', 'outcome_unknown'), (email, 'mail-1', 'outcome_unknown'), (social, 'post-a', 'outcome_unknown')):
            out = runner(structured_error=True)
            self.assertIn('error', out, pid)
            self.assertEqual(record(out, pid)['status'], status, pid)
            self.assertNotEqual(record(out, pid)['status'], 'published', pid)
        done = social()
        st = run_node('publish-status', 'status', {'publication_id': 'post-a'}, done['fs'], structured_error=True)
        self.assertTrue(st['error'].startswith('remote_boom'), st)
        self.assertEqual((writes(st), record(st, 'post-a')), ([], record(done, 'post-a')))


class Review11Test(unittest.TestCase):
    CASES = ((web, 'publish-web', WEB, 'page-1', '/docs/page.html', {}), (email, 'publish-email', {**EMAIL, 'body': None, 'source_path': '/docs/post.md'}, 'mail-1', '/docs/post.md', {}),
             (social, 'publish-social', {**SOCIAL, 'content': None, 'source_path': '/docs/post.md'}, 'post-a', '/docs/post.md', {}))

    def test_an_error_without_a_documented_refusal_code_is_an_unknown_outcome_and_replays_without_a_call(self):
        for runner, wf, ctx, pid, src, _ in self.CASES:
            out = runner(status_error=True, ctx=ctx)
            self.assertTrue(out['error'].startswith('publication_outcome_unknown'), (pid, out))
            self.assertEqual(record(out, pid)['status'], 'outcome_unknown', pid)
            again = run_node(wf, 'publish', ctx, out['fs'])
            self.assertTrue(again['error'].startswith('publication_outcome_unknown'), (pid, again))
            self.assertEqual(external(again), [], pid)
        # a documented refusal stays failed
        self.assertEqual(record(social(social_error='validation_failed'), 'post-a')['status'], 'failed')

    def test_a_replay_is_decided_on_the_journal_alone(self):
        for runner, wf, ctx, pid, src, _ in self.CASES:
            done = runner(ctx=ctx)
            fs = {k: v for k, v in done['fs'].items() if k != src}
            again = run_node(wf, 'publish', ctx, fs)
            self.assertIs(ok(self, again)['already_published'], True, pid)
            self.assertFalse(any(c['name'] == 'read_file' and c['args']['path'].startswith('/docs/') for c in again['calls']), pid)
            self.assertEqual((external(again), writes(again)), ([], []), pid)
            conflict = run_node(wf, 'publish', {**ctx, 'source_sha256': 'a' * 64}, fs)
            self.assertTrue(conflict['error'].startswith('publication_conflict'), (pid, conflict))
            rm = run_node('publish-remove', 'remove', {'publication_id': pid, **CONFIRMED}, done['fs']) if pid != 'mail-1' else None
            if rm:
                fs2 = {k: v for k, v in rm['fs'].items() if k != src}
                gone = run_node(wf, 'publish', ctx, fs2)
                self.assertIs(ok(self, gone)['already_removed'], True, pid)
                self.assertFalse(any(c['name'] == 'read_file' and c['args']['path'].startswith('/docs/') for c in gone['calls']), pid)
        # outcome_unknown, source deleted
        out = email(mail_throw='deadline exceeded')
        fs = {k: v for k, v in out['fs'].items() if k != '/docs/post.md'}
        again = run_node('publish-email', 'publish', EMAIL, fs)
        self.assertTrue(again['error'].startswith('publication_outcome_unknown'), again)
        self.assertEqual(external(again), [])


class QueryTest(unittest.TestCase):
    def test_list_and_read(self):
        a = web()
        b = run_node('publish-email', 'publish', EMAIL, a['fs'])
        c = run_node('publish-social', 'publish', SOCIAL, b['fs'])
        fs = c['fs']
        out = run_node('publish-list', 'list', {}, fs)
        res = ok(self, out)
        self.assertEqual((res['total'], [i['publication_id'] for i in res['items']]), (3, ['mail-1', 'page-1', 'post-a']))
        self.assertEqual({i['publication_id']: i['target'] for i in res['items']}['page-1'], 'site-main : news/page.html')
        self.assertEqual(ok(self, run_node('publish-list', 'list', {'channel': 'email'}, fs))['total'], 1)
        self.assertEqual(ok(self, run_node('publish-list', 'list', {'status': 'failed'}, fs))['total'], 0)
        self.assertTrue(run_node('publish-list', 'list', {'status': 'bogus'}, fs)['error'].startswith('status_invalid'))
        read = ok(self, run_node('publish-read', 'read', {'publication_id': 'page-1'}, fs))
        self.assertEqual((read['status'], read['record']['publication_id'], len(read['history'])), ('published', 'page-1', 2))

    def test_empty_folder_is_empty_but_a_storage_error_is_not(self):
        self.assertEqual(ok(self, run_node('publish-list', 'list', {}, {}))['total'], 0)
        out = run_node('publish-list', 'list', {}, {}, list_error='backend down')
        self.assertTrue(out['error'].startswith('storage_unavailable'), out)

    def test_read_errors(self):
        self.assertTrue(run_node('publish-read', 'read', {'publication_id': 'nope'}, {})['error'].startswith('publication_not_found'))
        out = run_node('publish-read', 'read', {'publication_id': 'x'}, {'/publish/log/x.json': {'text': '{'}})
        self.assertTrue(out['error'].startswith('record_corrupt'), out)
        out = run_node('publish-read', 'read', {'publication_id': 'x'}, {'/publish/log/x.json': {'text': '{}'}})
        self.assertTrue(out['error'].startswith('record_invalid'), out)
        out = run_node('publish-read', 'read', {'publication_id': 'x'}, {}, read_error='backend down')
        self.assertTrue(out['error'].startswith('storage_unavailable'), out)


class PlanTest(unittest.TestCase):
    def test_prepare_reads_without_writing_and_never_asks_for_a_destination(self):
        out = run_node('publish-plan', 'prepare', {'source_path': '/docs/page.html', 'goal': 'annoncer'}, dict(FILES))
        res = ok(self, out)
        self.assertEqual(names(out), ['read_file'])
        self.assertEqual((res['source']['sha256'], res['source']['textual'], res['source']['extension']), (HTML_SHA, True, 'html'))
        self.assertIn('Ne propose JAMAIS de destination', res['prompt'])
        self.assertIn('<h1>Hello</h1>', res['prompt'])
        binary = ok(self, run_node('publish-plan', 'prepare', {'source_path': '/docs/note.pdf'}, dict(FILES)))
        self.assertFalse(binary['source']['textual'])
        self.assertNotIn('%PDF', binary['prompt'])
        text = ok(self, run_node('publish-plan', 'prepare', {'text': 'Bonjour'}, {}))
        self.assertEqual(text['source']['kind'], 'text')
        for extra in ({}, {'text': 'a', 'source_path': '/docs/page.html'}):
            self.assertTrue(run_node('publish-plan', 'prepare', extra, dict(FILES))['error'].startswith('source_required'))

    def normalize(self, answer):
        prep = {'source': {'kind': 'storage', 'path': '/docs/note.pdf', 'extension': 'pdf', 'bytes': 3, 'sha256': 'a' * 64, 'textual': False}}
        return run_node('publish-plan', 'normalize', {'prep': prep, 'plan_draft': answer}, {})

    def test_normalize_is_strict(self):
        out = self.normalize({'text': json.dumps({'channel': 'email', 'reasons': ['court'], 'email_subject': 'Hello', 'post_text': 'x', 'warnings': [], 'server': 'evil.example.invalid'}), 'model': 'm'})
        res = ok(self, out)
        self.assertEqual((res['channel'], res['email_subject']), ('email', 'Hello'))
        self.assertNotIn('server', res)
        self.assertIn('destination', res)
        social = ok(self, self.normalize('```json\n{"channel": "social"}\n```'))
        self.assertTrue(any('image' in w for w in social['warnings']))
        for bad in ('not json', '{"channel": "fax"}', '{"channel": "web", "reasons": "x"}', '{"channel": "web", "post_text": 3}', '[]',
                    '{"channel": "web", "__proto__": {"a": 1}}'):
            out = self.normalize(bad)
            self.assertIn('error', out, bad)
            self.assertEqual(out['calls'], [])


if __name__ == '__main__':
    unittest.main()
