import json
import os
from typing import Dict, List, Optional

class KnowledgeBase:
    """Loads subject‑wise JSON knowledge files from ``study_lib/data/``.

    The directory layout is::

        study_lib/data/<subject>.json

    Each JSON file should contain a mapping of ``topic`` → ``content`` strings.
    The class aggregates all subjects into ``self._db`` as ``{subject: {topic: content}}``.
    """

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self.data_dir = data_dir or os.path.join(os.path.dirname(__file__), "data")
        self._db: Dict[str, Dict[str, str]] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Iterate over ``*.json`` files in ``self.data_dir`` and load them.
        Files that cannot be parsed are ignored with a warning printed to stdout.
        """
        if not os.path.isdir(self.data_dir):
            os.makedirs(self.data_dir, exist_ok=True)
            return
        for fname in os.listdir(self.data_dir):
            if not fname.lower().endswith('.json'):
                continue
            subject = os.path.splitext(fname)[0].lower()
            fpath = os.path.join(self.data_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    self._db[subject] = json.load(f)
            except Exception as e:
                print(f"[KnowledgeBase] Failed to load {fpath}: {e}")

    def subjects(self) -> List[str]:
        """Return a list of loaded subject names."""
        return list(self._db.keys())

    def get_topic(self, subject: str, topic: str) -> Optional[str]:
        """Return the content for a given *subject* and *topic* if present."""
        return self._db.get(subject.lower(), {}).get(topic)

    def search(self, subject: str, query: str) -> Optional[Dict[str, str]]:
        """Very small keyword search.

        Returns a mapping of matching ``topic`` → ``content`` where the query is a
        case‑insensitive substring of the topic. If *subject* is ``None`` the
        search runs across all subjects and merges results.
        """
        q = query.lower().strip()
        if not q:
            return None
        results: Dict[str, str] = {}
        subjects = [subject] if subject else self.subjects()
        for sub in subjects:
            for topic, content in self._db.get(sub, {}).items():
                if q in topic.lower():
                    results[topic] = content
        return results or None

# Global knowledge base instance for easy import
KB = KnowledgeBase()
