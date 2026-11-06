from contextlib import contextmanager

from django.db import OperationalError, connection, transaction

LOCK_ID = 864203105
LOCK_NAME = f"uts_escritura_{LOCK_ID}"
LOCK_TIMEOUT_SECONDS = 10


@contextmanager
def escritura_atomica():
    # A single lock preserves the MVP's serialized writes across workers,
    # including schedule edits and approvals.
    if connection.vendor == "mysql":
        with _bloqueo_mysql(), transaction.atomic():
            yield
        return
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '10s'")
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [LOCK_ID])
        yield


@contextmanager
def _bloqueo_mysql():
    # MySQL/MariaDB have no transaction-scoped advisory lock. GET_LOCK is held by
    # the session, so it is taken BEFORE the transaction starts and released AFTER
    # it commits or rolls back: no other worker can read stale data in between.
    # Nested calls on the same connection reuse the outer lock.
    depth = getattr(connection, "_uts_lock_depth", 0)
    if depth:
        connection._uts_lock_depth = depth + 1
        try:
            yield
        finally:
            connection._uts_lock_depth -= 1
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, %s)", [LOCK_NAME, LOCK_TIMEOUT_SECONDS])
        acquired = cursor.fetchone()[0]
    if acquired != 1:
        raise OperationalError("No fue posible obtener el bloqueo de escritura. Intenta de nuevo.")
    connection._uts_lock_depth = 1
    try:
        yield
    finally:
        connection._uts_lock_depth = 0
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s)", [LOCK_NAME])
        except Exception:
            # If the connection broke, MySQL already released the lock with the session.
            if not connection.in_atomic_block:
                connection.close()
