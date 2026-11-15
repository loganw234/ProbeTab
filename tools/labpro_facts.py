"""Read protocol/labpro-facts.toml, the single source for facts about the LabPro.

This is the one place that decides which tables in that file are facts.
tools/check.py and tools/generate.py read the facts through it, and so do
Python tools that need a value: they read the TOML here rather than a
generated copy.
"""
import tomllib
from pathlib import Path

FACTS = "protocol/labpro-facts.toml"


def load(root):
    """The facts file under root, parsed. Raises OSError or tomllib.TOMLDecodeError."""
    return tomllib.loads((Path(root) / FACTS).read_bytes().decode("utf-8"))


def facts(data, stray=None):
    """(name, table) for each fact, in file order.

    A fact is a table that holds no further tables, anywhere outside [source].
    A table inside an array is named with its index, as realtime.serial_max_rate[2].
    stray(name) is called for each value that sits outside every fact table.
    """
    found = []

    def walk(node, prefix):
        if isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{prefix}[{index}]")
            return
        nested = {key for key, value in node.items()
                  if isinstance(value, dict)
                  or (isinstance(value, list) and value and all(isinstance(x, dict) for x in value))}
        if not nested:
            found.append((prefix, node))
            return
        for key, value in node.items():
            name = f"{prefix}.{key}" if prefix else key
            if key not in nested:
                if stray:
                    stray(name)
            elif not (prefix == "" and key == "source"):
                walk(value, name)

    walk(data, "")
    return found
