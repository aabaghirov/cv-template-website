import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import parse_float

def test_parse_float_valid():
    assert parse_float("123.45") == 123.45
    assert parse_float("  100  ") == 100.0
    assert parse_float("-50.5") == -50.5

def test_parse_float_invalid():
    assert parse_float("abc") == 0.0
    assert parse_float("") == 0.0
    assert parse_float(None) == 0.0

def test_parse_float_default():
    assert parse_float("bad", default=99.0) == 99.0
    assert parse_float(None, default=10.0) == 10.0