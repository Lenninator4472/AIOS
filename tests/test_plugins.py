"""Tests for ~/.ai-dos/tools/*.py — Plugin tools."""

import importlib
import os
import sys

import pytest


TOOLS_DIR = os.path.expanduser("~/.ai-dos/tools")


def _import_tool(name):
    """Dynamically import a tool module from the tools directory."""
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(TOOLS_DIR, f"{name}.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCalcPlugin:
    """tool_calc: safe arithmetic evaluation."""

    def setup_method(self):
        self.mod = _import_tool("calc")

    def test_calc_basic_arithmetic(self):
        assert self.mod.tool_calc("2 + 3") == "5"

    def test_calc_multiplication(self):
        assert self.mod.tool_calc("4 * 5") == "20"

    def test_calc_complex_expression(self):
        assert self.mod.tool_calc("(2 + 3) * 4") == "20"

    def test_calc_division(self):
        result = self.mod.tool_calc("10 / 3")
        assert float(result) == pytest.approx(3.333, rel=1e-2)

    def test_calc_rejects_unsafe_expression(self):
        import pytest
        with pytest.raises(Exception):
            self.mod.tool_calc("__import__('os').system('ls')")

    def test_calc_rejects_strings(self):
        import pytest
        with pytest.raises(Exception):
            self.mod.tool_calc("'hello'")

    def test_calc_exponentiation(self):
        assert self.mod.tool_calc("2 ** 10") == "1024"


class TestEncodePlugin:
    """tool_encode: text encoding."""

    def setup_method(self):
        self.mod = _import_tool("encode")

    def test_encode_base64(self):
        result = self.mod.tool_encode("hello", "base64")
        assert result == "aGVsbG8="

    def test_encode_hex(self):
        result = self.mod.tool_encode("hello", "hex")
        assert result == "68656c6c6f"

    def test_encode_rot13(self):
        result = self.mod.tool_encode("hello", "rot13")
        assert result == "uryyb"

    def test_encode_rot13_roundtrip(self):
        encoded = self.mod.tool_encode("test123", "rot13")
        decoded = self.mod.tool_encode(encoded, "rot13")
        assert decoded == "test123"

    def test_encode_invalid_method(self):
        import pytest
        with pytest.raises(ValueError):
            self.mod.tool_encode("test", "invalid")


class TestWeatherPlugin:
    """tool_weather: mock weather reporter."""

    def setup_method(self):
        self.mod = _import_tool("weather")

    def test_weather_returns_formatted_string(self):
        result = self.mod.tool_weather("London")
        assert result.startswith("Weather in London:")

    def test_weather_contains_temperature(self):
        result = self.mod.tool_weather("Tokyo")
        assert "°C" in result

    def test_weather_default_city(self):
        result = self.mod.tool_weather()
        assert result.startswith("Weather in London:")


class TestDatetimePlugin:
    """tool_now: date/time formatting."""

    def setup_method(self):
        self.mod = _import_tool("datetime_tool")

    def test_now_iso_format(self):
        result = self.mod.tool_now("iso")
        # ISO format: 2026-06-06T12:34:56
        assert "T" in result
        assert len(result) >= 16

    def test_now_unix_format(self):
        result = self.mod.tool_now("unix")
        # Unix timestamp is all digits
        assert result.isdigit()
        assert len(result) >= 9

    def test_now_date_format(self):
        result = self.mod.tool_now("date")
        # Date format: YYYY-MM-DD
        assert len(result) == 10
        assert result[4] == "-"
        assert result[7] == "-"

    def test_now_time_format(self):
        result = self.mod.tool_now("time")
        # Time format: HH:MM:SS
        assert len(result) == 8
        assert result[2] == ":"
        assert result[5] == ":"

    def test_now_default_format(self):
        result = self.mod.tool_now()
        assert "T" in result

    def test_now_invalid_format(self):
        import pytest
        with pytest.raises(ValueError):
            self.mod.tool_now("invalid")


class TestAllPluginsImportable:
    """All 5 tool plugins can be imported dynamically."""

    def test_all_plugins_importable(self):
        names = ["calc", "notes", "encode", "weather", "datetime_tool"]
        for name in names:
            mod = _import_tool(name)
            assert mod is not None
            # Verify tool_ function exists
            tool_funcs = [a for a in dir(mod) if a.startswith("tool_")]
            assert len(tool_funcs) >= 1, f"No tool_ function in {name}"
