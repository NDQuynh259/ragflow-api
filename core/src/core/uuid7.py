"""RFC 9562 compliant UUIDv7 generator.

UUIDv7 provides time-ordered (k-sortable) 128-bit identifiers, which drastically
improves B-Tree index performance in PostgreSQL by eliminating page splits
associated with purely random UUIDv4.
"""

from __future__ import annotations

import os
import time
import uuid

try:
    import uuid_utils

    def uuid7() -> uuid.UUID:
        """Generate an RFC 9562 UUIDv7 using uuid_utils (returns standard uuid.UUID)."""
        return uuid.UUID(bytes=uuid_utils.uuid7().bytes)

    def uuid7_str() -> str:
        """Generate an RFC 9562 UUIDv7 string representation using uuid_utils."""
        return str(uuid_utils.uuid7())

except ImportError:
    # Pure Python fallback when uuid_utils is not installed
    def uuid7() -> uuid.UUID:
        """Generate an RFC 9562 UUIDv7 (pure Python fallback)."""
        timestamp_ms = int(time.time() * 1000)
        rand_bytes = os.urandom(10)

        time_bytes = timestamp_ms.to_bytes(6, byteorder="big")
        b6 = (rand_bytes[0] & 0x0F) | 0x70
        b7 = rand_bytes[1]
        b8 = (rand_bytes[2] & 0x3F) | 0x80
        b_rest = rand_bytes[3:10]

        raw_bytes = time_bytes + bytes([b6, b7, b8]) + b_rest
        return uuid.UUID(bytes=raw_bytes)

    def uuid7_str() -> str:
        """Generate an RFC 9562 UUIDv7 string representation."""
        return str(uuid7())
