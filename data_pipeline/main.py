"""Offline pipeline entrypoint.

Orchestrates, in order:

    ingest -> parse -> normalize -> validate -> chunk -> index
"""


def main() -> None:
    raise NotImplementedError("data_pipeline.main is wired up phase by phase")


if __name__ == "__main__":
    main()
