"""Study library package – provides subject resources and a lightweight QA helper.

Modules:
- `math`, `physics`, `chemistry`, `biology`, `engineering`, `neet`
- each module exposes `load_content()` returning a dict of topics → notes.
- `knowledge_base` loads all JSON resources from `study_lib/data/`.
- `search(subject, query)` performs a simple keyword lookup in the local data.
"""

from .knowledge import KnowledgeBase, KB
from .qa import QA, QAEngine

# Exported symbols
__all__ = [
    "KnowledgeBase",
    "KB",
    "QA",
    "QAEngine",
    "math",
    "physics",
    "chemistry",
    "biology",
    "engineering",
    "neet",
]

