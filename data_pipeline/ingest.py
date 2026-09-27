"""Metadata ingest entrypoint: scan the raw PDF tree and emit the manifest.

Folder layout (Google Drive or ``DATA_ROOT``):

    <domain folder>/<source_field folder>/<procedure_code>.pdf

Folder names only seed the metadata. After ingest, nothing downstream reads
folder names as business logic.
"""


def main() -> None:
    """Placeholder until PHASE 3 — Metadata Ingest + Data Contract."""
    raise NotImplementedError("data_pipeline.ingest is implemented in PHASE 3")


if __name__ == "__main__":
    main()
