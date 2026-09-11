"""Property-based checks on URL and alias validation.

Example-based tests only prove the rejection rules the author thought to write down.
These generate inputs instead, and assert the invariants the service depends on:
validation never raises an unexpected exception, never mutates an accepted value, and
never admits a class of destination the design forbids.
"""

import ipaddress
import re
from urllib.parse import urlsplit

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from app.models import CODE_PATTERN, RESERVED, CreateLink

CONTROL = st.characters(min_codepoint=0, max_codepoint=32) | st.just("\x7f")
BUDGET = settings(max_examples=250, suppress_health_check=[HealthCheck.too_slow], deadline=None)


def validate(url):
    return CreateLink(url=url)


@BUDGET
@given(st.text(max_size=300))
def test_validation_terminates_with_a_typed_outcome(url):
    """Arbitrary text either validates or raises ValidationError, never anything else."""
    try:
        assert validate(url).url == url  # Accepted values are stored verbatim.
    except ValidationError:
        pass


@BUDGET
@given(
    st.sampled_from(["http", "https"]),
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=20),
    st.sampled_from(["com", "org", "net", "io"]),
    st.text(max_size=40),
)
def test_public_hosts_are_accepted_and_preserved(scheme, label, tld, path):
    """A syntactically public destination survives validation unchanged."""
    assume(not label.startswith("-") and not label.endswith("-"))
    assume(all(ord(character) > 32 and ord(character) != 127 for character in path))
    assume("\\" not in path and "%" not in path)
    url = f"{scheme}://{label}.{tld}/{path}"
    assert validate(url).url == url


@BUDGET
@given(st.text(max_size=200), CONTROL, st.text(max_size=200))
def test_control_characters_are_always_rejected(prefix, control, suffix):
    """No accepted destination may contain whitespace or control characters."""
    with pytest.raises(ValidationError):
        validate(f"https://example.com/{prefix}{control}{suffix}")


@BUDGET
@given(st.ip_addresses(v=4).filter(lambda address: not address.is_global))
def test_non_public_ipv4_literals_are_always_rejected(address):
    """Loopback, private, link-local, and reserved literals never become destinations."""
    with pytest.raises(ValidationError):
        validate(f"http://{address}/resource")


@BUDGET
@given(st.text(max_size=300))
def test_accepted_destinations_are_never_non_public(url):
    """The invariant behind the rule set: nothing accepted resolves to a non-global literal."""
    try:
        accepted = validate(url).url
    except ValidationError:
        return
    host = (urlsplit(accepted).hostname or "").rstrip(".").lower()
    assert host, "an accepted destination always carries a host"
    try:
        assert ipaddress.ip_address(host).is_global
    except ValueError:
        assert "." in host  # A name, not a literal: multi-label by rule.


@BUDGET
@given(st.text(max_size=40))
def test_alias_admission_matches_the_published_pattern(alias):
    """Alias acceptance is exactly the documented pattern minus the reserved set."""
    permitted = bool(re.fullmatch(CODE_PATTERN, alias)) and alias.lower() not in RESERVED
    try:
        CreateLink(url="https://example.com/destination", custom_alias=alias)
    except ValidationError:
        assert not permitted, f"rejected an alias the contract permits: {alias!r}"
    else:
        assert permitted, f"accepted an alias the contract forbids: {alias!r}"
