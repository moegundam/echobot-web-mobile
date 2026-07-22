from __future__ import annotations

import errno
import http.client
import ipaddress
import socket
import sys
from functools import partial
from urllib.parse import urlparse
from urllib.request import (
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPSHandler,
    ProxyHandler,
    Request,
    build_opener,
)


_HTTP_URL_SCHEMES = {"http", "https"}
_BLOCKED_HOSTNAMES = {"localhost", "metadata", "metadata.google.internal"}


class ValidatedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, *, allow_private: bool) -> None:
        super().__init__()
        self._allow_private = allow_private

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_http_url(
            newurl,
            field_name="redirect URL",
            allow_private=self._allow_private,
        )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _PinnedConnectionMixin:
    def __init__(self, *args, allow_private: bool, **kwargs) -> None:
        self._allow_private = allow_private
        super().__init__(*args, **kwargs)

    def _connect_pinned(self) -> None:
        sys.audit("http.client.connect", self, self.host, self.port)
        self.sock = _create_pinned_connection(
            self.host,
            self.port,
            timeout=self.timeout,
            source_address=self.source_address,
            allow_private=self._allow_private,
        )
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError as exc:
            if exc.errno != errno.ENOPROTOOPT:
                raise
        if self._tunnel_host:
            self._tunnel()


class _PinnedHTTPConnection(_PinnedConnectionMixin, http.client.HTTPConnection):
    def connect(self) -> None:
        self._connect_pinned()


class _PinnedHTTPSConnection(_PinnedConnectionMixin, http.client.HTTPSConnection):
    def connect(self) -> None:
        self._connect_pinned()
        server_hostname = self._tunnel_host or self.host
        self.sock = self._context.wrap_socket(
            self.sock,
            server_hostname=server_hostname,
        )


class _PinnedHTTPHandler(HTTPHandler):
    def __init__(self, *, allow_private: bool) -> None:
        super().__init__()
        self._allow_private = allow_private

    def http_open(self, req):
        connection = partial(
            _PinnedHTTPConnection,
            allow_private=self._allow_private,
        )
        return self.do_open(connection, req)


class _PinnedHTTPSHandler(HTTPSHandler):
    def __init__(self, *, allow_private: bool) -> None:
        super().__init__()
        self._allow_private = allow_private

    def https_open(self, req):
        connection = partial(
            _PinnedHTTPSConnection,
            allow_private=self._allow_private,
        )
        return self.do_open(connection, req, context=self._context)


def validate_http_url(
    url: str,
    *,
    field_name: str = "URL",
    allow_private: bool = False,
) -> str:
    """Validate an absolute HTTP(S) URL against the shared SSRF policy."""
    cleaned_url = str(url or "").strip()
    parsed = urlparse(cleaned_url)
    if parsed.scheme.lower() not in _HTTP_URL_SCHEMES or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError(f"{field_name} must not include URL credentials")
    if not allow_private and is_private_http_target(parsed.hostname or ""):
        raise ValueError(f"{field_name} must not target a private network host")
    return cleaned_url


def open_http_url(
    url_or_request: str | Request,
    *,
    timeout_seconds: float,
    allow_private: bool = False,
):
    """Open an HTTP(S) request only after applying the shared SSRF policy."""
    raw_url = url_or_request.full_url if isinstance(url_or_request, Request) else url_or_request
    validate_http_url(
        str(raw_url),
        field_name="request URL",
        allow_private=allow_private,
    )
    opener = build_http_opener(allow_private=allow_private)
    response = opener.open(url_or_request, timeout=timeout_seconds)  # nosec B310
    final_url = getattr(response, "geturl", lambda: str(raw_url))()
    try:
        validate_http_url(
            str(final_url),
            field_name="response URL",
            allow_private=allow_private,
        )
    except ValueError:
        response.close()
        raise
    return response


def build_http_opener(
    *,
    allow_private: bool,
    redirect_handler: HTTPRedirectHandler | None = None,
):
    """Build a direct opener whose connection uses the validated DNS answer."""
    return build_opener(
        ProxyHandler({}),
        _PinnedHTTPHandler(allow_private=allow_private),
        _PinnedHTTPSHandler(allow_private=allow_private),
        redirect_handler or ValidatedRedirectHandler(allow_private=allow_private),
    )


def is_private_http_target(hostname: str) -> bool:
    """Return whether a hostname is unsafe for public-network HTTP access."""
    host = hostname.strip().strip("[]").lower().rstrip(".")
    if not host:
        return True
    if host in _BLOCKED_HOSTNAMES or host.endswith(".localhost") or host.endswith(".local"):
        return True
    if "." not in host and ":" not in host:
        return True
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return _hostname_resolves_to_private_address(host)
    return not address.is_global


def _hostname_resolves_to_private_address(hostname: str) -> bool:
    try:
        addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return True

    for item in addresses:
        sockaddr = item[4]
        if not sockaddr:
            return True
        try:
            address = ipaddress.ip_address(str(sockaddr[0]).split("%", 1)[0])
        except ValueError:
            return True
        if not address.is_global:
            return True
    return False


def _create_pinned_connection(
    hostname: str,
    port: int,
    *,
    timeout,
    source_address,
    allow_private: bool,
):
    host = hostname.strip().strip("[]")
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    if not addresses:
        raise OSError(f"No addresses found for {hostname}")

    if not allow_private:
        for item in addresses:
            sockaddr = item[4]
            if not sockaddr or not _is_global_address(sockaddr[0]):
                raise ValueError("request URL must not target a private network host")

    last_error: OSError | None = None
    for family, socktype, protocol, _canonical_name, sockaddr in addresses:
        connection = None
        try:
            connection = socket.socket(family, socktype, protocol)
            if timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
                connection.settimeout(timeout)
            if source_address:
                connection.bind(source_address)
            connection.connect(sockaddr)
            return connection
        except OSError as exc:
            last_error = exc
            if connection is not None:
                connection.close()

    if last_error is not None:
        raise last_error
    raise OSError(f"Unable to connect to {hostname}")


def _is_global_address(value: object) -> bool:
    try:
        address = ipaddress.ip_address(str(value).split("%", 1)[0])
    except ValueError:
        return False
    return address.is_global
