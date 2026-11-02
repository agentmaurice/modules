#!/usr/bin/env python3
"""Generate the public module catalog (catalog.json) from the modules and their catalog entries.

catalog.json is the enriched index of this repository: for each module listed by modules.json it carries what a
person, an agent or a One needs to find and install it (descriptions, capabilities, requirements, price) together
with the fingerprints the One checks at import. It is generated, never edited by hand:

  python3 scripts/catalog.py          # write catalog.json
  python3 scripts/catalog.py --check  # compare without writing; also validate every field

Inputs: modules.json (the list), <module>/module.yaml (key, name, version, provides, requires; JSON despite its
name) and catalog/<module directory>.yaml (descriptions, capabilities, extra credentials, price; JSON as well).
Everything derivable is derived: runtimes and language-model use come from the workflows, MCP connectors from the
manifest, module dependencies from scripts/inventory.py, and both fingerprints from the files themselves.

The catalog is public: texts are checked for URLs, e-mail addresses, IP addresses, internal host names, secrets
and the internal identifier forbidden in public content.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 'agentmaurice.module_catalog/v1'
ENTRY_SCHEMA = 'agentmaurice.module_catalog_entry/v1'
CAPABILITY = re.compile(r'^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')
PRICE_MODELS = ('free',)
TEXT_MAX = 400
LANGUAGES = ('fr', 'en')
# Content that must never reach a public file. The first list is the secret shapes check.py already refuses.
FORBIDDEN = {
    'url': r'(?i)\b(?:https?|ftp|ssh|git)://',
    'bare-host': r'(?i)\b[a-z0-9-]+\.(?:com|net|org|io|app|ai|dev|local|internal|lan)\b',
    'e-mail': r'[\w.+-]+@[\w-]+\.[\w.-]+',
    'ip-address': r'\b\d{1,3}(?:\.\d{1,3}){3}\b',
    # Spelled in two parts so that this file does not hold the identifier it forbids elsewhere.
    'internal-identifier': r'(?i)' + 'kraf' + 'tek',
    'private-key': r'-----BEGIN [A-Z ]*PRIVATE' + r' KEY-----',
    'github-token': r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})',
    'provider-key': r'\bsk-(?:ant-[A-Za-z0-9_-]{20,}|[A-Za-z0-9_-]{24,})',
    'jwt': r'\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}',
    'private-home-path': r'/(?:Us' + r'ers|home)/[a-zA-Z][^\s/]+/',
}


def tree_sha256(root):
    """Fingerprint of a module directory, as the One computes it at import (ComputeModuleDirectoryHash).

    Every regular file under root except .git, ordered by its slash-separated relative path (bytewise); the hash
    takes, for each file, the path, a zero byte, the raw SHA-256 of the content and a zero byte."""
    root = Path(root)
    entries = []
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if '.git' in relative.parts:
            continue
        if path.is_symlink():
            raise ValueError(f'module symlinks are forbidden: {relative}')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f'module contains a non-regular file: {relative}')
        entries.append(relative.as_posix())
    digest = hashlib.sha256()
    for relative in sorted(entries, key=lambda name: name.encode('utf-8')):
        digest.update(relative.encode('utf-8') + b'\0')
        digest.update(hashlib.sha256((root / relative).read_bytes()).digest() + b'\0')
    return digest.hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def canonical(value):
    """The one text form of a catalog entry: any other spelling of the same entry (whitespace, key order: keys are sorted) is a diff."""
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def workflow_facts(directory):
    """Runtimes used by code_execution actions and whether any step calls a language model."""
    runtimes, llm = set(), False
    for path in sorted((directory / 'agents/main/workflows').glob('*.json')):
        for node in walk(load_json(path)):
            if node.get('type') == 'code_execution':
                runtimes.add(node.get('runtime', 'deno'))
            if node.get('type') == 'llm_call':
                llm = True
    return sorted(runtimes), llm


def text_problems(label, value):
    problems = []
    if not isinstance(value, str) or not value.strip():
        return [f'{label}: texte vide ou absent']
    if len(value) > TEXT_MAX:
        problems.append(f'{label}: {len(value)} caractères, {TEXT_MAX} au plus')
    for name, pattern in FORBIDDEN.items():
        if re.search(pattern, value):
            problems.append(f'{label}: motif interdit dans un contenu public ({name})')
    return problems


def entry_problems(directory, entry):
    problems = []
    if entry.get('schema') != ENTRY_SCHEMA:
        problems.append(f'catalog/{directory}.yaml: schema attendu {ENTRY_SCHEMA}')
    unknown = set(entry) - {'schema', 'description', 'capabilities', 'credentials', 'price'}
    if unknown:
        problems.append(f'catalog/{directory}.yaml: champs inconnus {sorted(unknown)}')
    description = entry.get('description')
    if not isinstance(description, dict) or set(description) != set(LANGUAGES):
        problems.append(f'catalog/{directory}.yaml: description fr et en exigées')
    else:
        for language in LANGUAGES:
            problems += text_problems(f'catalog/{directory}.yaml description.{language}', description[language])
    capabilities = entry.get('capabilities')
    if not isinstance(capabilities, list) or not 1 <= len(capabilities) <= 12 or len(set(capabilities)) != len(capabilities):
        problems.append(f'catalog/{directory}.yaml: 1 à 12 capacités distinctes')
    else:
        for capability in capabilities:
            if not isinstance(capability, str) or not CAPABILITY.match(capability) or len(capability) > 40:
                problems.append(f'catalog/{directory}.yaml: capacité invalide {capability!r}')
    credentials = entry.get('credentials')
    if not isinstance(credentials, list) or len(set(credentials)) != len(credentials):
        problems.append(f'catalog/{directory}.yaml: credentials doit être une liste sans doublon')
    else:
        for credential in credentials:
            if not isinstance(credential, str) or not CAPABILITY.match(credential):
                problems.append(f'catalog/{directory}.yaml: identifiant de credential invalide {credential!r}')
    price = entry.get('price')
    if not isinstance(price, dict) or price.get('model') not in PRICE_MODELS or set(price) != {'model'}:
        problems.append(f'catalog/{directory}.yaml: price.model parmi {PRICE_MODELS} seulement')
    return problems


def render():
    # Importing inventory must not leave a scripts/__pycache__ behind: check.py refuses any bytecode file.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import inventory  # composition dependencies are declared once, there
    index = load_json(ROOT / 'modules.json')['modules']
    keys_by_directory = {Path(item['manifest']).parent.name: item['key'] for item in index}
    problems, modules, noncanonical = [], [], []
    sidecars = {path.stem for path in (ROOT / 'catalog').glob('*.yaml')}
    for extra in sorted(sidecars - set(keys_by_directory)):
        problems.append(f'catalog/{extra}.yaml: aucun module de ce dossier dans modules.json')
    for item in index:
        directory = Path(item['manifest']).parent
        name = directory.name
        manifest = ROOT / item['manifest']
        module = load_json(manifest)
        sidecar = ROOT / 'catalog' / f'{name}.yaml'
        if not sidecar.exists():
            problems.append(f'catalog/{name}.yaml: fiche de catalogue absente pour le module {module["key"]}')
            continue
        entry = load_json(sidecar)
        problems += entry_problems(name, entry)
        if sidecar.read_text(encoding='utf-8') != canonical(entry):
            noncanonical.append(sidecar)
            problems.append(f'catalog/{name}.yaml: forme non canonique (espaces, ordre des clés) : python3 scripts/catalog.py la réécrit')
        provides = module.get('provides', {})
        runtimes, llm = workflow_facts(ROOT / directory)
        connectors = [{'name': mcp['name'], 'tools': sorted(mcp.get('required_tools', []))}
                      for mcp in module.get('requires', {}).get('mcp', [])]
        modules.append({
            'key': module['key'], 'name': module['name'], 'version': module['version'],
            'subpath': name, 'manifest': item['manifest'],
            'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
            'tree_sha256': tree_sha256(ROOT / directory),
            'description': entry.get('description'), 'capabilities': entry.get('capabilities'),
            'actions': [{'key': action['key'], 'name': action.get('name', action['key'])} for action in provides.get('actions', [])],
            'queries': [query['key'] for query in provides.get('queries', [])],
            'requires': {
                'runtimes': runtimes, 'language_model': llm, 'connectors': connectors,
                'credentials': entry.get('credentials'),
                'modules': sorted(keys_by_directory[d] for d in inventory.CONSUMERS.get(name, []) if d in keys_by_directory),
            },
            'price': entry.get('price'),
            'maturity': 'preview',
            'workflows': item['workflows'], 'miniapps': item['miniapps'],
        })
    modules.sort(key=lambda module: module['key'])
    render.noncanonical = noncanonical
    return {'schema': SCHEMA, 'schema_version': 1, 'modules': modules}, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    catalog, problems = render()
    if not args.check and render.noncanonical:
        # Writing normalises the hand-written entries; only their form can change, never their content.
        for sidecar in render.noncanonical:
            sidecar.write_text(canonical(load_json(sidecar)), encoding='utf-8')
        catalog, problems = render()
    if problems:
        print('\n'.join(problems), file=sys.stderr)
        return 1
    data = json.dumps(catalog, ensure_ascii=False, indent=2) + '\n'
    path = ROOT / 'catalog.json'
    if args.check:
        if not path.exists() or path.read_text(encoding='utf-8') != data:
            print('catalog.json differs: run python3 scripts/catalog.py', file=sys.stderr)
            return 1
        print('Catalog consistent')
        return 0
    path.write_text(data, encoding='utf-8')
    print('Catalog generated')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
