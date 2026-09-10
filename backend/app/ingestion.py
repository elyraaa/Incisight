"""Allowlisted evidence ingestion for future cached public sources.

The deterministic demo does not call the network; this module is the guarded path
for an operator-configured refresh job.
"""
import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


MAX_BYTES = 1_000_000
ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/json")


class UnsafeSource(ValueError):
    pass


@dataclass(frozen=True)
class FetchedEvidence:
    url: str
    title: str
    text: str
    content_hash: str


def validate_source_url(url: str, allowed_hosts: set[str], resolve_dns: bool = True) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeSource("Evidence sources must be credential-free HTTPS URLs.")
    host = parsed.hostname.lower().rstrip(".")
    if host not in {x.lower().rstrip(".") for x in allowed_hosts}:
        raise UnsafeSource("Evidence hostname is not allowlisted.")
    if resolve_dns:
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
        except socket.gaierror as exc:
            raise UnsafeSource("Evidence hostname did not resolve.") from exc
        for value in addresses:
            ip = ipaddress.ip_address(value)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise UnsafeSource("Evidence hostname resolves to a non-public address.")
    return host


async def fetch_evidence(url: str, allowed_hosts: set[str]) -> FetchedEvidence:
    validate_source_url(url, allowed_hosts)
    async with httpx.AsyncClient(timeout=httpx.Timeout(8), follow_redirects=False) as client:
        async with client.stream("GET", url, headers={"User-Agent": "Incisight/0.1 evidence-cache"}) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if content_type not in ALLOWED_CONTENT_TYPES:
                raise UnsafeSource("Evidence response has an unsupported content type.")
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_BYTES: raise UnsafeSource("Evidence response exceeds the size limit.")
                chunks.append(chunk)
    raw = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
    if content_type == "text/html":
        soup = BeautifulSoup(raw, "html.parser")
        for node in soup(["script", "style", "noscript"]): node.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else url
        normalized = " ".join(soup.get_text(" ", strip=True).split())
    else:
        title, normalized = url, " ".join(raw.split())
    return FetchedEvidence(url=url, title=title[:200], text=normalized, content_hash=hashlib.sha256(normalized.encode()).hexdigest())
