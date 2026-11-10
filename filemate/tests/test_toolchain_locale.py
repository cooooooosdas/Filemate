"""Compiler language follows the resources copied into its isolated toolchain."""

import pytest

from filemate.programming.toolchain import compiler_environment


@pytest.mark.parametrize("locales,expected", [
    (["1033"], "1033"),
    (["2052"], "2052"),
    (["2052", "1033"], "1033"),
])
def test_compiler_environment_uses_an_installed_language(tmp_path, locales, expected):
    for locale in locales:
        resource = tmp_path / "bin" / locale / "clui.dll"
        resource.parent.mkdir(parents=True)
        resource.touch()
    assert compiler_environment(tmp_path, tmp_path / "run")["VSLANG"] == expected
