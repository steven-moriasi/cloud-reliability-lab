class DatabaseUnavailableError(RuntimeError):
    """Raised when a database operation cannot complete."""


class CacheUnavailableError(RuntimeError):
    """Raised when the external cache cannot complete an operation."""
