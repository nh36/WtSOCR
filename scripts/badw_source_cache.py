#!/usr/bin/env python3
"""Resumable, content-addressed acquisition for public BAdW WTS sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Callable, Mapping
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit, urlunsplit, quote
from urllib.request import Request, urlopen


CONTRACT_VERSION = "badw-cache-response-v1"
DEFAULT_DELAY_SECONDS = 1.0
DEFAULT_USER_AGENT = "WtSOCR-BAdW-source-acquisition/1.0 (research cache; polite)"
TRANSIENT_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
RELEVANT_RESPONSE_HEADERS = frozenset(
    {
        "cache-control",
        "content-disposition",
        "content-length",
        "content-type",
        "date",
        "etag",
        "last-modified",
        "location",
        "retry-after",
    }
)


class CacheMissError(RuntimeError):
    """Raised when offline acquisition cannot satisfy a request."""


@dataclass(frozen=True)
class RequestSpec:
    url: str
    method: str = "GET"
    form: tuple[tuple[str, str], ...] = ()

    @classmethod
    def post_form(cls, url: str, form: Mapping[str, str]) -> "RequestSpec":
        return cls(url=url, method="POST", form=tuple(sorted(form.items())))

    @property
    def safe_url(self) -> str:
        return quote_iri(self.url)

    @property
    def key(self) -> str:
        payload = {
            "form": list(self.form),
            "method": self.method.upper(),
            "url": self.safe_url,
        }
        serialised = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(serialised).hexdigest()


@dataclass(frozen=True)
class NetworkResponse:
    status: int
    final_url: str
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class CachedResponse:
    cache_root: Path
    metadata: Mapping[str, object]
    cache_hit: bool

    @property
    def request_key(self) -> str:
        return str(self.metadata["request_key"])

    @property
    def object_path(self) -> Path | None:
        relative = self.metadata.get("object_path")
        return self.cache_root / str(relative) if relative else None

    @property
    def body(self) -> bytes:
        path = self.object_path
        return path.read_bytes() if path is not None else b""

    @property
    def is_valid_resource(self) -> bool:
        return bool(self.metadata.get("valid_resource"))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def quote_iri(url: str) -> str:
    """Convert a public Unicode URL to a request-safe URL deterministically."""

    parts = urlsplit(url)
    path = quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
    query = quote(parts.query, safe="=&;%:@!$'()*+,/?-._~")
    fragment = quote(parts.fragment, safe="-._~")
    return urlunsplit((parts.scheme, parts.netloc, path, query, fragment))


def delivery_type_for_url(url: str) -> str:
    path = urlsplit(url).path
    if path.startswith("/lemma/"):
        return "database_article"
    if path.startswith("/pdf/"):
        return "generated_pdf"
    if path.rstrip("/") == "/suche":
        return "search_results"
    return "other"


def _has_html_class(text: str, class_name: str) -> bool:
    pattern = rf"class\s*=\s*([\"'])[^\"']*\b{re.escape(class_name)}\b[^\"']*\1"
    return re.search(pattern, text, re.I) is not None


def classify_response(
    *,
    status: int,
    final_url: str,
    media_type: str,
    body: bytes,
    requested_url: str | None = None,
) -> tuple[str, bool]:
    """Classify content, including HTTP-200 error and unreleased pages."""

    if status < 200 or status >= 300:
        return "http_error", False

    final_delivery_type = delivery_type_for_url(final_url)
    requested_delivery_type = delivery_type_for_url(requested_url or final_url)
    delivery_type = (
        final_delivery_type
        if final_delivery_type != "other"
        else requested_delivery_type
    )
    if delivery_type == "generated_pdf":
        if body.lstrip().startswith(b"%PDF-"):
            return "generated_pdf", True
        return "unexpected_content", False

    text = body.decode("utf-8", errors="replace")
    lowered = text.casefold()
    if delivery_type == "database_article":
        if (
            _has_html_class(text, "text")
            and _has_html_class(text, "lemma-head")
            and _has_html_class(text, "lem")
        ):
            return "database_article", True
        unreleased_patterns = (
            r"noch\s+nicht\s+(?:verfügbar|freigeschaltet|erschienen)",
            r"nicht\s+(?:verfügbar|freigeschaltet)",
            r"unveröffentlich",
        )
        if any(re.search(pattern, lowered) for pattern in unreleased_patterns):
            return "unreleased_page", False
        error_patterns = (
            "gesuchte artikel",
            "seite wurde nicht gefunden",
            "page not found",
            "<title>fehler",
            'class="error"',
            "class='error'",
        )
        if any(pattern in lowered for pattern in error_patterns):
            return "error_page", False
        return "unexpected_content", False

    if delivery_type == "search_results":
        if "html" in media_type.casefold() or b"<html" in body[:1024].lower():
            return "search_results", True
        return "unexpected_content", False

    return "other", True


def _default_transport(request: Request, timeout: float) -> NetworkResponse:
    try:
        with urlopen(request, timeout=timeout) as response:
            return NetworkResponse(
                status=response.status,
                final_url=response.geturl(),
                headers=dict(response.headers.items()),
                body=response.read(),
            )
    except HTTPError as error:
        return NetworkResponse(
            status=error.code,
            final_url=error.geturl(),
            headers=dict(error.headers.items()) if error.headers else {},
            body=error.read(),
        )


class SourceCache:
    """Fetch BAdW resources into an exact-byte, content-addressed store."""

    def __init__(
        self,
        root: Path | str,
        *,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        timeout_seconds: float = 45.0,
        max_attempts: int = 4,
        backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 8.0,
        user_agent: str = DEFAULT_USER_AGENT,
        transport: Callable[[Request, float], NetworkResponse] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], str] = utc_now,
    ) -> None:
        if delay_seconds < 0 or max_attempts < 1:
            raise ValueError("delay_seconds must be non-negative and max_attempts positive")
        self.root = Path(root)
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.user_agent = user_agent
        self.transport = transport or _default_transport
        self.sleep = sleep
        self.monotonic = monotonic
        self.now = now
        self._last_request_at: float | None = None

    def metadata_path(self, request_key: str) -> Path:
        return self.root / "requests" / request_key[:2] / f"{request_key}.json"

    def object_path(self, sha256: str) -> Path:
        return self.root / "objects" / "sha256" / sha256[:2] / sha256

    def _load_metadata(self, spec: RequestSpec) -> dict[str, object] | None:
        path = self.metadata_path(spec.key)
        if not path.exists():
            return None
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if metadata.get("contract_version") != CONTRACT_VERSION:
            return None
        return metadata

    def _metadata_has_object(self, metadata: Mapping[str, object]) -> bool:
        relative = metadata.get("object_path")
        return bool(relative and (self.root / str(relative)).is_file())

    @staticmethod
    def _is_terminal(metadata: Mapping[str, object]) -> bool:
        return bool(metadata.get("terminal"))

    def lookup(self, spec: RequestSpec, *, include_incomplete: bool = True) -> CachedResponse | None:
        metadata = self._load_metadata(spec)
        if metadata is None:
            return None
        if not include_incomplete and not self._is_terminal(metadata):
            return None
        if metadata.get("sha256") and not self._metadata_has_object(metadata):
            return None
        return CachedResponse(self.root, metadata, cache_hit=True)

    def fetch(
        self, spec: RequestSpec, *, offline: bool = False, refresh: bool = False
    ) -> CachedResponse:
        existing = self.lookup(spec)
        if existing is not None and (
            offline or (not refresh and self._is_terminal(existing.metadata))
        ):
            return existing
        if offline:
            raise CacheMissError(f"no cached response for {spec.method} {spec.safe_url}")

        attempts: list[dict[str, object]] = []
        last_response: NetworkResponse | None = None
        last_error: str | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._respect_rate_limit()
            fetched_at = self.now()
            request = self._build_request(spec)
            try:
                response = self.transport(request, self.timeout_seconds)
                self._last_request_at = self.monotonic()
                last_response = response
                last_error = None
                attempts.append(
                    {"attempt": attempt, "fetched_at_utc": fetched_at, "http_status": response.status}
                )
                if response.status not in TRANSIENT_HTTP_STATUSES:
                    break
            except Exception as error:  # transport injection may raise several network errors
                self._last_request_at = self.monotonic()
                last_error = f"{type(error).__name__}: {error}"
                attempts.append(
                    {"attempt": attempt, "fetched_at_utc": fetched_at, "transport_error": last_error}
                )

            if attempt < self.max_attempts:
                self.sleep(self._backoff_delay(attempt, last_response))

        metadata = self._make_metadata(spec, last_response, last_error, attempts)
        if last_response is not None:
            sha256 = hashlib.sha256(last_response.body).hexdigest()
            object_path = self.object_path(sha256)
            if not object_path.exists():
                self._atomic_write_bytes(object_path, last_response.body)
            metadata["sha256"] = sha256
            metadata["byte_length"] = len(last_response.body)
            metadata["object_path"] = object_path.relative_to(self.root).as_posix()
        self._atomic_write_json(self.metadata_path(spec.key), metadata)
        return CachedResponse(self.root, metadata, cache_hit=False)

    def _build_request(self, spec: RequestSpec) -> Request:
        method = spec.method.upper()
        data = urlencode(spec.form).encode("utf-8") if spec.form else None
        headers = {"User-Agent": self.user_agent, "Accept": "*/*"}
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        return Request(spec.safe_url, data=data, headers=headers, method=method)

    def _respect_rate_limit(self) -> None:
        if self._last_request_at is None:
            return
        remaining = self.delay_seconds - (self.monotonic() - self._last_request_at)
        if remaining > 0:
            self.sleep(remaining)

    def _backoff_delay(
        self, attempt: int, response: NetworkResponse | None
    ) -> float:
        if response is not None:
            retry_after = next(
                (
                    value
                    for key, value in response.headers.items()
                    if key.casefold() == "retry-after"
                ),
                None,
            )
            if retry_after:
                try:
                    return min(float(retry_after), self.max_backoff_seconds)
                except ValueError:
                    pass
        return min(self.backoff_seconds * (2 ** (attempt - 1)), self.max_backoff_seconds)

    def _make_metadata(
        self,
        spec: RequestSpec,
        response: NetworkResponse | None,
        last_error: str | None,
        attempts: list[dict[str, object]],
    ) -> dict[str, object]:
        if response is None:
            status = None
            final_url = spec.safe_url
            media_type = ""
            headers: dict[str, str] = {}
            classification = "transport_failure"
            valid = False
            failure_kind = "transient_exhausted"
            terminal = False
        else:
            status = response.status
            final_url = response.final_url
            headers = {
                key.casefold(): value
                for key, value in response.headers.items()
                if key.casefold() in RELEVANT_RESPONSE_HEADERS
            }
            media_type = headers.get("content-type", "").split(";", 1)[0].strip()
            classification, valid = classify_response(
                status=status,
                final_url=final_url,
                media_type=media_type,
                body=response.body,
                requested_url=spec.safe_url,
            )
            transient = status in TRANSIENT_HTTP_STATUSES
            failure_kind = (
                "none"
                if valid
                else "transient_exhausted"
                if transient
                else "permanent"
            )
            terminal = not transient

        final_delivery_type = delivery_type_for_url(final_url)
        requested_delivery_type = delivery_type_for_url(spec.safe_url)
        delivery_type = (
            final_delivery_type
            if final_delivery_type != "other"
            else requested_delivery_type
        )
        return {
            "attempt_history": attempts,
            "attempts_in_fetch": len(attempts),
            "byte_length": None,
            "content_classification": classification,
            "contract_version": CONTRACT_VERSION,
            "delivery_type": delivery_type,
            "failure_kind": failure_kind,
            "fetched_at_utc": attempts[-1]["fetched_at_utc"] if attempts else self.now(),
            "final_url": final_url,
            "http_status": status,
            "media_type": media_type,
            "method": spec.method.upper(),
            "object_path": None,
            "request_form": dict(spec.form),
            "request_key": spec.key,
            "requested_delivery_type": requested_delivery_type,
            "requested_url": spec.safe_url,
            "final_delivery_type": final_delivery_type,
            "response_headers": headers,
            "sha256": None,
            "terminal": terminal,
            "transport_error": last_error,
            "user_agent": self.user_agent,
            "valid_resource": valid,
        }

    @staticmethod
    def _atomic_write_bytes(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)

    @staticmethod
    def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
