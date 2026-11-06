"""Strict XML records and XML response serialization."""

from xml.etree import ElementTree as ET

from src.db import SCHEMAS


def encode(tag, values):
    """Encode a record or a list; escape text through ElementTree."""
    root = ET.Element(tag)
    if isinstance(values, list):
        for row in values:
            root.append(ET.fromstring(encode("item", row)))
    else:
        for key, value in values.items():
            child = ET.SubElement(root, key)
            if value is None:
                child.set("null", "true")
            else:
                child.text = str(value)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def decode(data, entity):
    """Read a flat XML record with only known, non-repeated fields."""
    if b"<!" in data:
        raise ValueError("XML declarations of entities are forbidden")
    root = ET.fromstring(data)
    if root.tag != entity:
        raise ValueError("Unexpected XML root")
    values = {}
    for child in root:
        if child.tag not in SCHEMAS[entity] or child.tag in values:
            raise ValueError("Unknown or repeated field")
        if len(child) or child.attrib:
            raise ValueError("Only plain field text is allowed")
        kind = SCHEMAS[entity][child.tag]
        values[child.tag] = kind(child.text or "")
    return values


def unpack(data):
    """Decode response values for the HTTP client."""
    root = ET.fromstring(data)
    if root.tag == "error":
        raise ValueError(root.findtext("message"))
    if root.tag in {"people", "queries", "results", "report"}:
        return [_row(item) for item in root]
    return _row(root)


def _row(root):
    integers = {"identifier", "time", "person", "query", "duration"}
    return {
        child.tag: (
            None
            if child.get("null")
            else int(child.text)
            if child.tag in integers
            else child.text or ""
        )
        for child in root
    }
