"""Bounded Postgres-only connection settings, with no URL in representations."""

import math
import os
import ssl
from dataclasses import dataclass, field

from sqlalchemy.engine import make_url


@dataclass(frozen=True)
class DatabaseConfig:
    url: str = field(repr=False)
    pool_size: int = 5
    max_overflow: int = 0
    pool_timeout: float = 5
    connect_timeout: float = 5
    command_timeout: float = 5
    transaction_timeout: float = 10
    reconcile_timeout: float = 10
    cleanup_timeout: float = 2
    tls_mode: str = "verify-full"

    def __post_init__(self):
        try:
            url = make_url(self.url)
            valid = (url.drivername in ("postgres", "postgresql", "postgresql+asyncpg")
                     and bool(url.host and url.database and url.username)
                     and not url.query and (url.port is None or 0 < url.port <= 65535))
        except Exception:
            valid = False
        if not valid:
            raise ValueError("DATABASE_URL must be a valid Postgres URL.") from None
        if (self.tls_mode not in ("verify-full", "private-network")
                or (self.tls_mode == "private-network" and not (
                    url.host.lower().endswith(".railway.internal")
                    and all(part and part[0] != "-" and part[-1] != "-"
                            and all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in part)
                            for part in url.host.lower().split("."))))):
            raise ValueError("Invalid DB_TLS_MODE or private-network hostname.")
        if type(self.pool_size) is not int or self.pool_size <= 0:
            raise ValueError("DB_POOL_SIZE must be a positive integer.")
        if type(self.max_overflow) is not int or self.max_overflow < 0:
            raise ValueError("DB_MAX_OVERFLOW must be a nonnegative integer.")
        for key in ("pool_timeout", "connect_timeout", "command_timeout",
                    "transaction_timeout", "reconcile_timeout", "cleanup_timeout"):
            value = getattr(self, key)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("DB timeouts must be positive and finite.")
        if self.cleanup_timeout > 10:
            raise ValueError("DB_CLEANUP_TIMEOUT_SECONDS must not exceed 10.")

    def connect_args(self):
        return {"timeout": self.connect_timeout, "command_timeout": self.command_timeout,
                "ssl": ssl.create_default_context() if self.tls_mode == "verify-full" else False,
                "server_settings": {"statement_timeout": str(max(1, int(self.command_timeout * 1000)))}}

    @classmethod
    def from_environment(cls):
        try:
            return cls(
                # An explicitly configured private URL wins, even when invalid.
                # Never silently switch databases after a configuration error.
                url=os.environ.get("DATABASE_PRIVATE_URL", os.environ.get("DATABASE_URL", "")),
                pool_size=int(os.environ.get("DB_POOL_SIZE", "5")),
                max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "0")),
                tls_mode=os.environ.get("DB_TLS_MODE", "verify-full"),
                **{name: float(os.environ.get(f"DB_{name.upper()}_SECONDS", str(default)))
                   for name, default in (("pool_timeout", 5), ("connect_timeout", 5),
                                         ("command_timeout", 5), ("transaction_timeout", 10),
                                          ("reconcile_timeout", 10), ("cleanup_timeout", 2))},
            )
        except (ValueError, TypeError, OverflowError):
            raise ValueError("Invalid Postgres configuration.") from None
