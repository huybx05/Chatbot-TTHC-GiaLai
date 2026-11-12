"""Rebuild collection Qdrant cho FAQ toàn cục.

```bash
uv run python scripts/index_global_faqs.py
```
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.rag.faq_global import (  # noqa: E402
    collection_name,
    index_global_faqs,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


async def main() -> int:
    count = await index_global_faqs(recreate=True)
    print(f"{collection_name()}: {count} point")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
