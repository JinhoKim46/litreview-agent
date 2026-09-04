"""connectors/registry.py -- discovers every connectors/<source>.py module by
glob (excluding __init__.py, _shared.py, and this file), so /prisma-search
and /prisma-add-source never need a hardcoded source list to stay in sync
with what connectors are actually installed on disk.

CLI: python3 -m connectors.registry --list
    Prints each discovered source's key, base URL, and whether it takes an
    optional API key. None of the six shipped connectors (openalex, crossref,
    semanticscholar, pubmed, europepmc, arxiv) REQUIRE a key -- this column
    is informational (a key raises the rate limit for pubmed/semanticscholar).
"""
import argparse
import glob
import importlib
import os

_PACKAGE = "connectors"
_EXCLUDE = {"__init__.py", "_shared.py", "registry.py"}

# Known optional API-key env vars per source, for --list's "needs key?" column.
OPTIONAL_API_KEY_ENV = {
    "pubmed": "NCBI_API_KEY",
    "semanticscholar": "S2_API_KEY",
}


def list_source_files():
    """Return sorted module names (without .py) for every connector module on disk."""
    here = os.path.dirname(__file__)
    names = []
    for path in glob.glob(os.path.join(here, "*.py")):
        base = os.path.basename(path)
        if base in _EXCLUDE:
            continue
        names.append(base[: -len(".py")])
    return sorted(names)


def get_source_module(name):
    """Import and return the connectors.<name> module."""
    return importlib.import_module(f"{_PACKAGE}.{name}")


def list_sources():
    """Return a list of {name, source_key, base_url, api_key_env} dicts, one
    per connector module discovered on disk. A connector that fails to
    import is still listed (so one broken module doesn't hide the rest),
    with base_url set to the import error."""
    sources = []
    for name in list_source_files():
        try:
            mod = get_source_module(name)
        except Exception as exc:  # noqa: BLE001 -- deliberately broad: any import failure is reportable, not fatal to discovery
            sources.append({"name": name, "source_key": name, "base_url": f"<import failed: {exc}>", "api_key_env": None})
            continue
        source_key = getattr(mod, "SOURCE_KEY", None) or getattr(mod, "SOURCE", None) or name
        base_url = getattr(mod, "BASE_URL", None) or getattr(mod, "EUTILS_BASE", None) or "n/a"
        sources.append(
            {
                "name": name,
                "source_key": source_key,
                "base_url": base_url,
                "api_key_env": OPTIONAL_API_KEY_ENV.get(source_key),
            }
        )
    return sources


def _print_table(sources):
    if not sources:
        print("No connectors installed.")
        return
    name_w = max(len(s["name"]) for s in sources)
    key_w = max(len(s["source_key"]) for s in sources)
    for s in sources:
        note = f"optional key: {s['api_key_env']}" if s["api_key_env"] else "no key required"
        print(f"{s['name'].ljust(name_w)}  key={s['source_key'].ljust(key_w)}  {s['base_url']}  ({note})")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="connectors.registry")
    parser.add_argument("--list", action="store_true", help="list every discovered connector module")
    args = parser.parse_args(argv)
    if args.list:
        _print_table(list_sources())
    else:
        parser.error("use --list to show installed connectors")


if __name__ == "__main__":
    main()
