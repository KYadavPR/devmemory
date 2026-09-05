"""Local persistence: a single SQLite database under ``.devmemory/metadata.db``.

Only this package imports ``sqlite3``. Services talk to repositories; repositories
talk to :class:`~devmemory.storage.db.Database`.
"""

from devmemory.storage.db import Database

__all__ = ["Database"]
