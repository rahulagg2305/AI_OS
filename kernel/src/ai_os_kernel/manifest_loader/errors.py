"""Errors raised by the Manifest Loader."""


class ManifestError(Exception):
    """A manifest could not be found, parsed, or failed schema validation.

    Always raised with a message naming the manifest path and the
    specific violation, per the fail-clearly rule in
    docs/03_architecture/kernel/manifest_loader.md.
    """
