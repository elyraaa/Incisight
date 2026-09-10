import pytest
from app.ingestion import UnsafeSource, validate_source_url

def test_source_requires_https_and_allowlist():
    with pytest.raises(UnsafeSource): validate_source_url("http://status.example.com/x", {"status.example.com"}, resolve_dns=False)
    with pytest.raises(UnsafeSource): validate_source_url("https://evil.example/x", {"status.example.com"}, resolve_dns=False)
    assert validate_source_url("https://status.example.com/advisory", {"status.example.com"}, resolve_dns=False)=="status.example.com"

def test_source_rejects_embedded_credentials():
    with pytest.raises(UnsafeSource): validate_source_url("https://user:pass@status.example.com/x", {"status.example.com"}, resolve_dns=False)

