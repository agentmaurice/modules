#!/usr/bin/env python3
"""Report potential French text for human review; this is not language detection.

Scan tracked product sources and generated resources, including embedded code.
Identifiers and historical fixtures can be reported as candidates; never use
this report alone to decide whether a translation is safe or complete.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Technical instructions and legal notice are managed outside the product.
EXCLUDED_FILES = {'AGENTS.md', 'CLAUDE.md', 'NOTICE', 'scripts/language_audit.py', 'scripts/language_exceptions.json'}
EXCLUDED_PARTS = {'fixtures', '_archive'}
PATTERN = re.compile(
    r"[àâçéèêëîïôùûüœÀÂÇÉÈÊËÎÏÔÙÛÜŒ]|"
    r"\b(?:aucun|aucune|avec|dans|depuis|données|enregistrer|"
    r"erreur|fiche|fiches|identifiant|mémoire|pour|sélectionner|utilisateur|"
    r"vous|votre)\b", re.IGNORECASE)


def candidates(text):
    for number, line in enumerate(text.splitlines(), 1):
        if PATTERN.search(line):
            yield number, line.strip()


def presentation_candidates(document):
    """Inspect only declared presentation fields, never option values or user data."""
    if not isinstance(document, dict) or document.get('kind') not in {'workflow', 'miniapp'}:
        return []
    short = {'oui', 'non', 'objectif', 'relecture', 'dossier', 'lecture', 'partage'}
    hits = []

    def is_french_label(text):
        normalized = text.strip().casefold()
        # A bare header or a French permission-summary label, not the
        # ordinary English word "lecture" in prose.
        return normalized in short or bool(re.search(r'\b(?:lecture|partage)\s*:', normalized))

    def walk(value, pointer):
        if isinstance(value, dict):
            for key, child in value.items():
                child_pointer = pointer + '/' + key.replace('~', '~0').replace('/', '~1')
                if isinstance(child, str) and (key in {'label', 'title', 'placeholder', 'help'} or
                    (key == 'value' and value.get('type') == 'text')) and is_french_label(child):
                    hits.append((child_pointer, child))
                if key == 'column_labels' and isinstance(child, dict):
                    for column, label in child.items():
                        if isinstance(label, str) and is_french_label(label):
                            hits.append((child_pointer + '/' + column.replace('~', '~0').replace('/', '~1'), label))
                walk(child, child_pointer)
        elif isinstance(value, list):
            for i, child in enumerate(value): walk(child, pointer + '/' + str(i))

    for key in ('ui', 'forms'):
        if key in document: walk(document[key], '/' + key)
    for key in ('title', 'description'):
        if isinstance(document.get(key), str) and is_french_label(document[key]):
            hits.append(('/' + key, document[key]))
    return hits


def apply_code_fragments(source, name, entries):
    """Mask only approved exact fragments in a decoded action's code, in memory."""
    if not entries:
        return source, set()
    try:
        document = json.loads(source)
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError(f'{name}: invalid JSON for code fragments: {error}') from error
    groups = {}
    for key, entry in entries.items():
        groups.setdefault((entry['json_pointer'], entry['action_id']), []).append((key, entry))
    seen = set()
    for (pointer, action_id), group in groups.items():
        match = re.fullmatch(r'/actions/(0|[1-9][0-9]*)/code', pointer)
        if not match:
            raise ValueError(f'{name}: invalid action code pointer {pointer}')
        try:
            action = document['actions'][int(match.group(1))]
            original = action['code']
            if action['id'] != action_id or not isinstance(original, str):
                raise ValueError('action ID or code mismatch')
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ValueError(f'{name}: stale code exception {pointer}: {error}') from error
        fragments = [entry['fragment'] for _, entry in group]
        if any(a != b and a in b for a in fragments for b in fragments):
            raise ValueError(f'{name}: overlapping code fragments at {pointer}')
        masked = original
        for key, entry in group:
            fragment = entry['fragment']
            if original.count(fragment) != entry['expected_count']:
                raise ValueError(f'{name}: stale code fragment at {pointer} for {action_id}')
            masked = masked.replace(fragment, ' ' * len(fragment))
            seen.add(key)
        old_json = json.dumps(original, ensure_ascii=False)
        if source.count(old_json) != 1:
            raise ValueError(f'{name}: action code serialization is ambiguous at {pointer}')
        source = source.replace(old_json, json.dumps(masked, ensure_ascii=False), 1)
    return source, seen


def source_paths():
    """Use Git's inventory only for this exact checkout; scan archives on disk."""
    try:
        top = subprocess.run(['git', 'rev-parse', '--show-toplevel'], cwd=ROOT,
                             capture_output=True, text=True, check=False)
        if top.returncode == 0 and Path(top.stdout.strip()).resolve() == ROOT.resolve():
            result = subprocess.run(['git', 'ls-files', '-co', '--exclude-standard', '-z'],
                                    cwd=ROOT, check=True, capture_output=True)
            return sorted(set(result.stdout.decode().split('\0')) - {''}), 'git'
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    paths = []
    for directory, dirs, files in os.walk(ROOT, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in {'.git', '.venv', '__pycache__', 'node_modules', *EXCLUDED_PARTS}
                         and not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if not path.is_symlink(): paths.append(path.relative_to(ROOT).as_posix())
    return sorted(paths), 'filesystem'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='exit nonzero if candidates remain; review false positives')
    args = parser.parse_args()
    exceptions = json.loads((ROOT / 'scripts/language_exceptions.json').read_text())
    allowed = {}
    fragments = {}
    for entry in exceptions:
        if not entry.get('reason'):
            raise SystemExit(f"language exception requires a reason: {entry.get('path', '?')}")
        if 'fragment' in entry:
            fragment = entry['fragment']
            if (not isinstance(fragment, str) or not fragment or len(fragment) > 200 or '\n' in fragment
                    or not PATTERN.search(fragment) or not isinstance(entry.get('expected_count'), int)
                    or isinstance(entry.get('expected_count'), bool) or entry['expected_count'] < 1
                    or not isinstance(entry.get('action_id'), str) or not entry['action_id']):
                raise SystemExit(f"invalid bounded code exception: {entry.get('path', '?')}")
            key = ('fragment', entry['path'], entry.get('json_pointer'), entry['action_id'], fragment)
            if key in fragments:
                raise SystemExit(f'duplicate language exception: {entry["path"]}')
            fragments[key] = entry
        else:
            key = ('line', entry['path'], entry['line_sha256'])
            if key in allowed:
                raise SystemExit(f'duplicate language exception: {entry["path"]} {entry["line_sha256"]}')
            allowed[key] = entry['reason']
    paths, mode = source_paths()
    count = 0
    seen = set()
    for name in paths:
        path = Path(name)
        if name in EXCLUDED_FILES or set(path.parts) & EXCLUDED_PARTS:
            continue
        try:
            source = (ROOT / path).read_text(encoding='utf-8')
        except (UnicodeError, FileNotFoundError, IsADirectoryError):
            continue
        if name.endswith('.json'):
            try:
                document = json.loads(source)
            except json.JSONDecodeError:
                document = None  # The distribution checker reports malformed JSON.
            for pointer, label in presentation_candidates(document):
                print(f'{name}:{pointer}: display label {label}')
                count += 1
        scoped = {key: value for key, value in fragments.items() if value['path'] == name}
        try:
            source, applied = apply_code_fragments(source, name, scoped)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        seen.update(applied)
        for line, content in candidates(source):
            key = ('line', name, hashlib.sha256(content.encode('utf-8')).hexdigest())
            if key in allowed:
                if name.endswith('.json') and re.match(r'"code"\s*:', content):
                    raise SystemExit(f'{name}:{line}: unbounded serialized code exception is forbidden')
                seen.add(key)
                continue
            print(f'{name}:{line}: {content}')
            count += 1
    stale = (set(allowed) | set(fragments)) - seen
    for key in sorted(stale):
        print(f'{key[1]}: stale exception {key[2]}')
    print(f'{count} candidate lines, {len(stale)} stale exceptions; scan={mode}; manual review is required.')
    if args.check and (count or stale):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
