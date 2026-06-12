# -*- coding: utf-8 -*-
"""src/version.py 단위 테스트."""
import pytest
from src.version import parse_ver, is_newer, __version__


@pytest.mark.parametrize("s,expected", [
    ("1.2.0",     (1, 2, 0)),
    ("v1.2.0",    (1, 2, 0)),
    ("V1.2.0",    (1, 2, 0)),
    ("1.2.10",    (1, 2, 10)),
    ("1.2.0-beta",(1, 2, 0)),
    ("1.2.0+build",(1,2, 0)),
    ("2.0",       (2, 0, 0)),
    ("",          (0, 0, 0)),
    (None,        (0, 0, 0)),
])
def test_parse_ver(s, expected):
    assert parse_ver(s) == expected


def test_is_newer_detects_patch():
    assert is_newer("1.2.1", "1.2.0")

def test_is_newer_detects_minor():
    assert is_newer("1.3.0", "1.2.10")

def test_is_newer_detects_major():
    assert is_newer("2.0.0", "1.99.99")

def test_is_newer_same_version():
    assert not is_newer("1.2.0", "1.2.0")

def test_is_newer_older_version():
    assert not is_newer("1.2.0", "1.2.1")

def test_is_newer_uses_current_default():
    # __version__ 보다 높은 버전이면 True
    major, minor, patch = parse_ver(__version__)
    newer_tag = f"v{major}.{minor}.{patch + 1}"
    assert is_newer(newer_tag)

def test_is_newer_same_as_current():
    assert not is_newer(__version__)
