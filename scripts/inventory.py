#!/usr/bin/env python3
"""Generate the documentary catalogue from top-level Module manifests."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LIBRARY_COMMIT = 'dc935630764b24c819defd03cc487bddf8f87399'
MEMORY_COMMIT = '8cb35a14b825dcdae4515d46e3b4c5149c154901'
GENERATORS = {
    'work-cases': ['tooling/work-cases/build.py', 'tooling/work-cases/compose.py'],
    'daily-routine': ['tooling/daily-routine/build.py', 'tooling/daily-routine/compose.py'],
    'enterprise-admin': ['tooling/enterprise-admin/build.py', 'tooling/enterprise-admin/compose.py'],
    'marketing-launch': ['tooling/marketing-launch/build.py', 'tooling/marketing-launch/compose.py'],
    'watch': ['templates/company-in-a-box/compose.py'],
    'content': ['templates/company-in-a-box/compose.py'],
    'support': ['templates/company-in-a-box/compose.py'],
    'watch-memory': ['tooling/memory-integration/compose.py'],
    'content-memory': ['tooling/memory-integration/compose.py'],
    'support-memory': ['tooling/memory-integration/compose.py'],
    'company-memory': ['tooling/company-memory/compose.py'],
}
OLD_PATHS = {
    'watch': 'solutions/company-in-a-box/modules/veille',
    'content': 'solutions/company-in-a-box/modules/contenu',
    'support': 'solutions/company-in-a-box/modules/accompagnement',
    'watch-memory': 'solutions/company-in-a-box/memory-integration/modules/veille',
    'content-memory': 'solutions/company-in-a-box/memory-integration/modules/contenu',
    'support-memory': 'solutions/company-in-a-box/memory-integration/modules/accompagnement',
    'work-cases': 'solutions/company-in-a-box/common-dossier/module',
    'daily-routine': 'solutions/company-in-a-box/daily-routine/module',
    'enterprise-admin': 'solutions/company-in-a-box/enterprise-admin/module',
    'marketing-launch': 'solutions/company-in-a-box/marketing-launch/module',
    'company-memory': 'solutions/company-memory/module',
}
SOURCES = {
    **{name: {'repository': 'github.com/agentmaurice/company-in-a-box', 'commit': LIBRARY_COMMIT,
               'historical_library_commit': LIBRARY_COMMIT}
       for name in ('watch', 'content', 'support', 'watch-memory', 'content-memory', 'support-memory',
                    'work-cases', 'daily-routine', 'enterprise-admin', 'marketing-launch')},
    'company-memory': {'repository': 'gitlab.com/mcpchatui/pilote-maurice', 'commit': MEMORY_COMMIT,
                       'historical_library_commit': LIBRARY_COMMIT},
}
# Modules created in this repository: no historical source to reconcile and
# not part of the Company in a Box template.
NATIVE = {
    'image-studio': {'generators': ['tooling/image-studio/build.py'],
                     'language': 'English source', 'publication': 'native to this repository, unpublished'},
    'profile': {'generators': ['tooling/profile/build.py', 'tooling/profile/compose.py'],
                'language': 'English source', 'publication': 'native to this repository, unpublished'},
    'document-studio': {'generators': ['tooling/document-studio/build.py'],
                        'language': 'English source', 'publication': 'native to this repository, unpublished'},
}
CONSUMERS = {
    'watch-memory': ['watch', 'company-memory'], 'content-memory': ['content', 'company-memory'],
    'support-memory': ['support', 'company-memory'],
    'daily-routine': ['watch', 'content', 'support', 'company-memory'],
}

def workflow_actions(path):
    """Describe action definitions, including any nested action lists, without executing them."""
    workflow = json.loads(path.read_text(encoding='utf-8'))
    actions = []

    def walk(value, location):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'actions' and isinstance(child, list):
                    for index, action in enumerate(child):
                        action_path = f'{location}/actions/{index}'
                        if isinstance(action, dict) and 'id' in action and 'type' in action:
                            entry = {'path': action_path, 'id': action['id'], 'type': action['type']}
                            if action['type'] == 'code_execution':
                                entry['runtime'] = action.get('runtime', 'deno')
                                entry['runtime_source'] = ('declared' if 'runtime' in action
                                                           else 'contract default')
                                if isinstance(action.get('code'), str):
                                    entry['code_sha256'] = hashlib.sha256(action['code'].encode('utf-8')).hexdigest()
                            actions.append(entry)
                        walk(action, action_path)
                else:
                    walk(child, f'{location}/{key}')
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f'{location}/{index}')

    walk(workflow, '')
    return {'workflow_id': workflow.get('workflow_id'), 'actions': actions}

def render():
    rows = []
    details = []
    seen = set()
    for path in sorted(ROOT.glob('*/module.yaml')):
        module = json.loads(path.read_text(encoding='utf-8'))
        key, version = module['key'], module['version']
        if key in seen:
            raise ValueError(f'duplicate module key: {key}')
        seen.add(key)
        root = path.parent
        if root.name in NATIVE:
            workflow_paths = sorted(root.glob('agents/main/workflows/*.json'))
            app_paths = sorted(root.glob('agents/main/miniapps/*.json'))
            row = {'key': key, 'version': version, 'manifest': str(path.relative_to(ROOT)),
                   'workflows': len(workflow_paths), 'miniapps': len(app_paths)}
            rows.append(row)
            native = NATIVE[root.name]
            details.append({**row, 'source': {'repository': 'github.com/agentmaurice/modules', 'native': True},
                'generators_and_composers': native['generators'],
                'resources': {'workflows': [str(p.relative_to(ROOT)) for p in workflow_paths],
                              'miniapps': [str(p.relative_to(ROOT)) for p in app_paths],
                              'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                         for p in [path, *workflow_paths, *app_paths]}},
                'workflow_actions': {str(p.relative_to(ROOT)): workflow_actions(p) for p in workflow_paths},
                'provides': module.get('provides', {}), 'requires': module.get('requires', {}),
                'composition_dependencies': [], 'known_consumers': [],
                'language': native['language'],
                'runtime': 'Static observation of Agent Spec V2 definitions; runtime execution and qualification are not inferred',
                'publication': native['publication']})
            continue
        if root.name not in OLD_PATHS or root.name not in GENERATORS or root.name not in SOURCES:
            raise ValueError(
                f'Unreconciled provenance for {root.name}: add its source mapping to '
                'OLD_PATHS, GENERATORS and SOURCES after reconciling its repository and commit before generating the inventory'
            )
        workflow_paths = sorted(root.glob('agents/main/workflows/*.json'))
        app_paths = sorted(root.glob('agents/main/miniapps/*.json'))
        row = {'key': key, 'version': version, 'manifest': str(path.relative_to(ROOT)),
               'workflows': len(workflow_paths), 'miniapps': len(app_paths)}
        rows.append(row)
        details.append({**row, 'source': {**SOURCES[root.name], 'old_path': OLD_PATHS[root.name]},
            'generators_and_composers': GENERATORS.get(root.name, []),
            'resources': {'workflows': [str(p.relative_to(ROOT)) for p in workflow_paths],
                          'miniapps': [str(p.relative_to(ROOT)) for p in app_paths],
                          'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in [path, *workflow_paths, *app_paths]}},
            'workflow_actions': {str(p.relative_to(ROOT)): workflow_actions(p) for p in workflow_paths},
            'provides': module.get('provides', {}), 'requires': module.get('requires', {}),
            'composition_dependencies': CONSUMERS.get(root.name, []),
            'known_consumers': sorted(name for name, deps in CONSUMERS.items() if root.name in deps),
            'language': 'Inherited French content is present in the library; M5 review remains pending and language is not qualified', 'runtime': 'Static observation of Agent Spec V2 definitions; runtime execution and qualification are not inferred',
            'publication': 'historical GitHub 0.2.0; 0.3.0 from GitLab source, local integration' if root.name == 'company-memory' else 'present in historical GitHub source at specified commit',
            'migration_m5_m6': 'to define and qualify; deployment status is not inferred'})
    catalogue = {'schema_version': 1, 'modules': rows}
    pins = {'schema_version': 1, 'modules': [r for r in rows if r['manifest'].split('/')[0] not in NATIVE]}
    inventory = {'schema_version': 1, 'description': 'Documentary inventory, not a runtime contract.',
        'discovery': 'top-level */module.yaml; no numerical cap',
        'exclusions': ['fixtures', 'cache', '_archive', 'worktrees', 'artifacts and private replays'],
        'modules': details}
    return {'modules.json': catalogue, 'templates/company-in-a-box/modules.json': pins,
            'inventory/modules.json': inventory}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    bad = []
    for name, value in render().items():
        path = ROOT / name
        data = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8') != data:
                bad.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data, encoding='utf-8')
    if bad:
        print('Inventory differs: ' + ', '.join(bad), file=sys.stderr)
        return 1
    print('Inventory consistent' if args.check else 'Inventory generated')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
