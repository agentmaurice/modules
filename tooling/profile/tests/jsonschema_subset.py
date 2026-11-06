"""Minimal JSON Schema (2020-12 subset) validator, so the offline tests need no extra package.

It supports exactly the keywords the pinned template/v1 schemas use and raises on any other keyword,
so a schema change that the subset cannot judge fails loudly instead of being skipped.
"""
import re
from urllib.parse import urljoin

ANNOTATIONS = {"$schema", "$id", "title", "description", "$defs", "format"}
KEYWORDS = {"$ref", "type", "enum", "required", "properties", "additionalProperties", "items", "pattern",
            "minLength", "maxLength", "minimum"}
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool}


class Registry:
    def __init__(self, *documents):
        self.by_id = {doc["$id"]: doc for doc in documents}


def _type_ok(kind, value):
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "string" or kind == "object" or kind == "array":
        return isinstance(value, TYPES[kind])
    if kind == "boolean":
        return isinstance(value, bool)
    raise ValueError(f"unsupported type {kind}")


def _resolve(ref, doc, registry):
    base, _, fragment = ref.partition("#")
    target = registry.by_id[urljoin(doc["$id"], base)] if base else doc
    node = target
    for part in [p for p in fragment.split("/") if p]:
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node, target


def validate(schema, instance, registry, doc=None, path=""):
    doc = doc or schema
    errors = []
    unknown = set(schema) - KEYWORDS - ANNOTATIONS
    if unknown:
        raise ValueError(f"unsupported schema keyword(s) {sorted(unknown)} at {path or '(root)'}")
    if "$ref" in schema:
        node, target = _resolve(schema["$ref"], doc, registry)
        errors += validate(node, instance, registry, target, path)
    kind = schema.get("type")
    if kind and not _type_ok(kind, instance):
        return errors + [f"{path or '(root)'}: expected {kind}"]
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: not in enum")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: too short")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: too long")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: pattern mismatch")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool) and "minimum" in schema and instance < schema["minimum"]:
        errors.append(f"{path}: below minimum")
    if isinstance(instance, dict):
        for name in schema.get("required", []):
            if name not in instance:
                errors.append(f"{path}/{name}: required")
        props = schema.get("properties", {})
        for name, value in instance.items():
            if name in props:
                errors += validate(props[name], value, registry, doc, f"{path}/{name}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}/{name}: additional property")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors += validate(schema["additionalProperties"], value, registry, doc, f"{path}/{name}")
    if isinstance(instance, list) and "items" in schema:
        for index, value in enumerate(instance):
            errors += validate(schema["items"], value, registry, doc, f"{path}/{index}")
    return errors
