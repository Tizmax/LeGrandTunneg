"""Environment-backed limits shared by HTTP, WebSocket and transport code."""

import math
import os
import ipaddress
import re
from dataclasses import dataclass, field, fields
from urllib.parse import urlsplit


def _integer(name: str, default: int):
    return field(default_factory=lambda: int(os.environ.get(name, str(default))))


def _number(name: str, default: float):
    return field(default_factory=lambda: float(os.environ.get(name, str(default))))


def valid_origin(origin: str) -> bool:
    """Accept only serialized HTTP(S) origins, never paths or credentials."""
    try:
        parsed = urlsplit(origin)
        port = parsed.port
        host = parsed.hostname or ""
        try:
            host = ipaddress.ip_address(host).compressed
            valid_host = True
        except ValueError:
            # Browsers interpret numeric final labels as IPv4, including short,
            # integer, hexadecimal and octal forms. Require canonical IPs above.
            if re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", host.rsplit(".", 1)[-1]):
                return False
            valid_host = bool(re.fullmatch(
                r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*", host
            )) and len(host) <= 253
        authority = f"[{host}]" if ":" in host else host
        if port is not None:
            authority += f":{port}"
        return bool(
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.netloc
            and valid_host
            and origin == f"{parsed.scheme}://{authority}"
            and (parsed.scheme, port) not in {("http", 80), ("https", 443)}
            and "%" not in host
            and parsed.username is None
            and parsed.password is None
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and "?" not in origin
            and "#" not in origin
            and not any(char.isspace() for char in origin)
            and "*" not in origin
            and "\\" not in origin
            and not parsed.netloc.endswith(":")
            and (port is None or 0 < port <= 65535)
        )
    except ValueError:
        return False


@dataclass
class Settings:
    app_env: str = field(default_factory=lambda: os.environ.get("APP_ENV", "development"))
    allowed_origins: tuple[str, ...] = field(default_factory=lambda: tuple(
        origin.strip() for origin in os.environ.get(
            "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
    ))
    trusted_proxy_hops: tuple[str, ...] = field(default_factory=lambda: tuple(
        hop.strip() for hop in os.environ.get("TRUSTED_PROXY_HOPS", "").split(",")
        if hop.strip()
    ))
    port: int = _integer("PORT", 8000)
    max_rooms: int = _integer("MAX_ROOMS", 10)
    max_players: int = _integer("MAX_PLAYERS", 16)
    max_screens: int = _integer("MAX_SCREENS", 4)
    max_themes: int = _integer("MAX_THEMES", 32)
    max_name_chars: int = _integer("MAX_NAME_CHARS", 24)
    max_theme_label_chars: int = _integer("MAX_THEME_LABEL_CHARS", 100)
    max_message_bytes: int = _integer("MAX_MESSAGE_BYTES", 8192)
    max_rest_body_bytes: int = _integer("MAX_REST_BODY_BYTES", 8192)
    rest_body_timeout_seconds: float = _number("REST_BODY_TIMEOUT_SECONDS", 5)
    max_rest_body_readers: int = _integer("MAX_REST_BODY_READERS", 32)
    max_rest_operations: int = _integer("MAX_REST_OPERATIONS", 32)
    rest_operation_timeout_seconds: float = _number("REST_OPERATION_TIMEOUT_SECONDS", 15)
    auth_timeout_seconds: float = _number("AUTH_TIMEOUT_SECONDS", 5)
    max_preauth_connections: int = _integer("MAX_PREAUTH_CONNECTIONS", 32)
    max_authenticated_connections: int = _integer("MAX_AUTHENTICATED_CONNECTIONS", 200)
    send_timeout_seconds: float = _number("SEND_TIMEOUT_SECONDS", 2)
    room_idle_ttl_seconds: float = _number("ROOM_IDLE_TTL_SECONDS", 86400)
    room_cleanup_interval_seconds: float = _number("ROOM_CLEANUP_INTERVAL_SECONDS", 60)
    rest_rate_per_second: float = _number("REST_RATE_PER_SECOND", 5)
    rest_rate_burst: int = _integer("REST_RATE_BURST", 20)
    ws_upgrade_rate_per_second: float = _number("WS_UPGRADE_RATE_PER_SECOND", 10)
    ws_upgrade_rate_burst: int = _integer("WS_UPGRADE_RATE_BURST", 20)
    ws_command_rate_per_second: float = _number("WS_COMMAND_RATE_PER_SECOND", 20)
    ws_command_rate_burst: int = _integer("WS_COMMAND_RATE_BURST", 40)
    ws_global_rate_per_second: float = _number("WS_GLOBAL_RATE_PER_SECOND", 200)
    ws_global_rate_burst: int = _integer("WS_GLOBAL_RATE_BURST", 400)

    def validate(self) -> None:
        for item in fields(self):
            if item.name in {"app_env", "allowed_origins", "trusted_proxy_hops"}:
                continue
            value = getattr(self, item.name)
            try:
                valid = not isinstance(value, bool) and math.isfinite(value) and value > 0
            except (TypeError, OverflowError):
                valid = False
            if not valid or (item.type is int and not isinstance(value, int)):
                raise ValueError(f"{item.name.upper()} must be positive and finite")
        if self.max_players > 16:
            raise ValueError("MAX_PLAYERS cannot exceed 16")
        if self.port > 65535:
            raise ValueError("PORT cannot exceed 65535")
        if self.room_cleanup_interval_seconds > self.room_idle_ttl_seconds:
            raise ValueError("ROOM_CLEANUP_INTERVAL_SECONDS cannot exceed ROOM_IDLE_TTL_SECONDS")
        if (not self.allowed_origins
                or len(set(self.allowed_origins)) != len(self.allowed_origins)
                or not all(valid_origin(origin) for origin in self.allowed_origins)):
            raise ValueError("ALLOWED_ORIGINS must contain distinct exact HTTP(S) origins")
        if self.app_env == "production" and (
            not os.environ.get("ALLOWED_ORIGINS", "").strip()
            or not all(origin.startswith("https://") for origin in self.allowed_origins)
        ):
            raise ValueError("Production requires explicit HTTPS ALLOWED_ORIGINS")
        for hop in self.trusted_proxy_hops:
            if hop.startswith("/") and not any(char.isspace() for char in hop):
                continue
            try:
                ipaddress.ip_network(hop, strict=False)
            except ValueError:
                raise ValueError("TRUSTED_PROXY_HOPS must list explicit IPs, networks or socket paths") from None
            if ipaddress.ip_network(hop, strict=False).prefixlen == 0:
                raise ValueError("TRUSTED_PROXY_HOPS cannot trust every proxy")


settings = Settings()
