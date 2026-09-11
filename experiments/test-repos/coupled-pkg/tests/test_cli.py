"""Tests for CLI module."""
import subprocess
import sys


def test_analyze_help():
    result = subprocess.run(
        [sys.executable, '-m', 'src.cli', 'analyze', '--help'],
        capture_output=True, text=True
    )
    assert result.returncode == 0


def test_module_imports():
    import src.cli
    assert hasattr(src.cli, 'main')
