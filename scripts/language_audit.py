#!/usr/bin/env python3
"""Report potential French text for human review; this is not language detection.

Scan tracked product sources and generated resources, including embedded code.
Identifiers and historical fixtures can be reported as candidates; never use
this report alone to decide whether a translation is safe or complete.
"""
import argparse
import hashlib
import json
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
    r"erreur|fiche|fiches|mémoire|pour|sélectionner|utilisateur|"
    r"vous|votre)\b", re.IGNORECASE)


def candidates(text):
    for number, line in enumerate(text.splitlines(), 1):
        if PATTERN.search(line):
            yield number, line.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='exit nonzero if candidates remain; review false positives')
    args = parser.parse_args()
    exceptions = json.loads((ROOT / 'scripts/language_exceptions.json').read_text())
    allowed = {(entry['path'], entry['line_sha256']): entry['reason'] for entry in exceptions}
    # Include untracked files so a new source cannot silently evade the audit.
    result = subprocess.run(['git', 'ls-files', '-co', '--exclude-standard', '-z'],
                            cwd=ROOT, check=True, capture_output=True)
    paths = sorted(set(result.stdout.decode().split('\0')) - {''})
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
        for line, content in candidates(source):
            key = (name, hashlib.sha256(content.encode('utf-8')).hexdigest())
            if key in allowed:
                seen.add(key)
                continue
            print(f'{name}:{line}: {content}')
            count += 1
    stale = set(allowed) - seen
    for name, digest in sorted(stale):
        print(f'{name}: stale exception {digest}')
    print(f'{count} candidate lines, {len(stale)} stale exceptions; manual review is required.')
    if args.check and (count or stale):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
