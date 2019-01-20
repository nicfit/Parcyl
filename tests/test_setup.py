import sys
import subprocess
from collections import defaultdict
import pytest

class _ArgsDict(defaultdict):
    def __init__(self, copy):
        super().__init__(lambda: None)
        self.update(copy)


def test_empty_setup(parcyl_d):
    assert parcyl_d.withSetupPy(contents="").setup("")


def test_default_setup_noargs(parcyl_d):
    with pytest.raises(subprocess.CalledProcessError):
        parcyl_d.withSetupPy().setup("")


def test_default_setup_build(parcyl_d):
    assert not parcyl_d.path.joinpath("__pycache__").exists()
    for cmd in ["build", "build_py", "build_ext", "build_clib",
                "build_scripts"]:
        parcyl_d.withSetupPy().setup(cmd)


def test_default_setup_install(parcyl_d):
    if sys.implementation.name != "pypy":
        assert not parcyl_d.path.joinpath("tmp", "lib").exists()
    else:
        assert not parcyl_d.path.joinpath("tmp", "site-packages").exists()

    parcyl_d.withSetupPy().setup("install --prefix ./tmp")

    if sys.implementation.name != "pypy":
        assert parcyl_d.path.joinpath("tmp", "lib").exists()
        files = list(parcyl_d.path.joinpath("tmp", "lib").iterdir())
    else:
        assert parcyl_d.path.joinpath("tmp", "site-packages").exists()
        files = list(parcyl_d.path.joinpath("tmp", "site-packages").iterdir())
    assert files


def test_default_setup_sdist(parcyl_d, setup_kwargs=None):
    setup_kwargs = _ArgsDict(setup_kwargs if setup_kwargs else {})

    parcyl = parcyl_d.withSetupPy(setup_kwargs=setup_kwargs)
    assert not parcyl_d.path.joinpath("dist").exists()

    parcyl.setup("sdist")

    name = setup_kwargs["name"] if "name" in setup_kwargs else "UNKNOWN"
    version = setup_kwargs["version"] if "version" in setup_kwargs else "0.0.0"
    assert parcyl_d.path.joinpath("dist", f"{name}-{version}.tar.gz").exists()


def test_default_setup_bdist(parcyl_d, setup_kwargs=None):
    setup_kwargs = _ArgsDict(setup_kwargs if setup_kwargs else {})

    parcyl = parcyl_d.withSetupPy(setup_kwargs=setup_kwargs)
    assert not parcyl_d.path.joinpath("build").exists()
    assert not parcyl_d.path.joinpath("dist").exists()

    parcyl.setup("bdist")

    assert parcyl_d.path.joinpath("build").exists()
    bfile = list(parcyl_d.path.joinpath("dist").iterdir())[0].name
    name = setup_kwargs["name"] if "name" in setup_kwargs else "UNKNOWN"
    version = setup_kwargs["version"] if "version" in setup_kwargs else "0.0.0"
    assert bfile.startswith(f"{name}-{version}") and bfile.endswith(".tar.gz")


def test_setup_bdist_name(parcyl_d):
    test_default_setup_bdist(parcyl_d, setup_kwargs={"name": "SheerTerror"})


def test_setup_bdist_name_version(parcyl_d):
    test_default_setup_bdist(parcyl_d, setup_kwargs={"name": "SheerTerror",
                                                     "version": "6.6.6"})


def test_setup_sdist(parcyl_d):
    test_default_setup_sdist(parcyl_d, setup_kwargs={"name": "Grandaddy",
                                                     "version": "1.0.8"})
