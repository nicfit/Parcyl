#!/usr/bin/env python
import io
import os
import re
import sys
import shlex
import typing
import logging
import functools
import importlib
import setuptools
import configparser
from enum import Enum
from pathlib import Path
from operator import attrgetter

from pkg_resources import (RequirementParseError,
                           Requirement as _RequirementBase)
from setuptools.command.test import test as _TestCommand
from setuptools.command.develop import develop as _DevelopCommand
from setuptools.command.install import install as _InstallCommand

try:
    import johnnydep
    from johnnydep.lib import JohnnyDist
    from johnnydep.logs import configure_logging
    configure_logging(0)
except ImportError:
    johnnydep = None

__version__ = "1.0a1"
__project_name__ = "Parcyl"
__url__ = "https://github.com/nicfit/parcyl"
__author__ = "Travis Shirk"
__author_email__ = "travis@pobox.com"

_EXTRA = "extra_"
_REQ_D = Path("requirements")
_SETUP_CFG = Path("setup.cfg")
_CFG_SECT = f"tool:{__project_name__.lower()}"
_log = logging.getLogger(__project_name__.lower())

SETUP_ATTRS = {"name", "version", "author", "author_email", "url", "license", "description",
               "entry_points",
              }
EXTRA_ATTRS = {"release_name", "github_url"}
about_file_attrs_map = {"name": "__project_name__",
                        "version": "__version__",
                        "author": "__author__",
                        "author_email": "__author_email__",
                        "url": "__url__",
                        "license": "__license__",
                        "description": "__description__",
                        "release_name": "__release_name__",
                        "github_url": "__github_url__",
                        }


find_packages = setuptools.find_packages


def setup(**setup_attrs):
    """A shortcut help function to use when you don't need the  `Setup` object.
    >>> import parcyl
    >>> setup =  parcyl.setup(...)
    instead of
    >>> import parcyl
    >>> setup =  parcyl.Setup(...)
    >>> setup()
    """
    s = Setup(**setup_attrs)
    s()
    return s


class Setup:
    def __init__(self, **setup_attrs):
        # Install commands (TODO: merge with any existing commands)
        setup_attrs["cmdclass"] = {"install": InstallCommand,
                                   "test": TestCommand,
                                   "pytest": PyTestCommand,
                                   "develop": DevelopCommand,
                                  }

        # Requirements
        self.requirements = None
        if _SETUP_CFG.exists():
            self.requirements = SetupRequirements()
            for setup_arg, attr in [("install_requires", attrgetter("install")),
                                    ("tests_require", attrgetter("test")),
                                    ("extras_require", attrgetter("extras")),
                                    ("setup_requires", attrgetter("setup")),
                                   ]:
                if setup_arg not in setup_attrs:
                    if setup_arg != "extras_require":
                        setup_attrs[setup_arg] = list([str(r) for r in attr(self.requirements)])
                    else:
                        extras = attr(self.requirements)
                        setup_attrs[setup_arg] = dict(
                            {extra: list([str(r) for r in extras[extra]])
                                       for extra, reqs in attr(self.requirements).items()
                            })
                else:
                    raise ValueError(
                        f"`{setup_arg}` must be set via requirements file.")

        # Final args
        self._setup_attrs = dict(setup_attrs)

    def __call__(self, **setup_attrs):
        attrs = dict(self._setup_attrs)
        attrs.update(setup_attrs)
        setuptools.setup(**attrs)

    def with_packages(self, *pkg_dirs, exclude=None):
        pkgs = []
        if "packages" not in self._setup_attrs:
            self._setup_attrs["packages"] = []
        for d in pkg_dirs:
            pkgs += find_packages(d, exclude=exclude)
        self._setup_attrs["packages"] += pkgs
        return self

    @staticmethod
    def attrsFromFile(info_filename: typing.Union[Path, str], attr_map=None, quiet=False,
                      extra_attrs=None):
        info_dict = {}
        extra_dict = {}
        if not isinstance(info_filename, Path):
            info_filename = Path(info_filename)
        attr_map = attr_map or about_file_attrs_map

        if info_filename.suffix == ".py":
            mod = importlib.import_module(info_filename.stem)
            for what in attr_map.keys():
                if hasattr(mod, attr_map[what]):
                    (info_dict if what in SETUP_ATTRS
                               else extra_dict)[what] = getattr(mod, attr_map[what])
        else:
            with io.open(str(info_filename), encoding='utf-8') as infof:
                for line in infof:
                    for what in attr_map.keys():
                        rex = re.compile(rf"{attr_map[what]}\s*=\s*['\"](.*?)['\"]")
                        m = rex.match(line.strip())
                        if not m:
                            continue

                        (info_dict if what in SETUP_ATTRS else extra_dict)[what] = m.groups()[0]

        vparts = info_dict["version"].split("-", maxsplit=1)
        extra_dict["release"] = vparts[1] if len(vparts) > 1 else "final"

        if not quiet:
            for what in attr_map:
                if what not in info_dict:
                    print(f"Package info not found: {what}", file=sys.stderr)

        for attr, val in (extra_attrs or {}).items():
            d = info_dict if attr in SETUP_ATTRS else extra_dict
            if attr in d and not quiet:
                print(f"extra_attrs override of {attr}", file=sys.stderr)
            d[attr] = val

        return info_dict, extra_dict


@functools.total_ordering
class Requirement:

    class SpecsOpt(Enum):
        NONE = 0
        CURRENT = 1
        VERSION_INSTALLED = 2
        VERSION_LATEST = 3

    def __init__(self, requirement, scm_req=None):
        self._scm_requirement_string = scm_req
        self._requirement = requirement

        self._dist = None
        self._version_installed = None
        self._version_latest_in_spec = None

    def __str__(self):
        return self.toString()

    def toString(self, specs=SpecsOpt.CURRENT, marker=True):
        specs = specs or self.SpecsOpt.NONE

        if self._scm_requirement_string:
            return self._scm_requirement_string

        s = self.project_name

        if specs == self.SpecsOpt.CURRENT:
            s += ",".join([f"{op}{ver}" for op, ver in self.specs])
        elif specs == self.SpecsOpt.VERSION_INSTALLED and self.version_installed:
            s += f"=={self.version_installed}"
        elif specs == self.SpecsOpt.VERSION_LATEST and self.version_latest_in_spec:
            s += f"=={self.version_latest_in_spec}"

        if marker and self.marker:
            s += f" ; {self.marker}"

        return s

    def __lt__(self, other):
        return self.key < other.key

    @property
    def name(self):
        return self._requirement.name

    @property
    def project_name(self):
        return self._requirement.project_name

    @property
    def key(self):
        return self._requirement.key

    @property
    def specs(self):
        return self._requirement.specs

    @property
    def marker(self):
        return self._requirement.marker

    @property
    def version_installed(self):
        return self.dist.version_installed

    @property
    def version_latest_in_spec(self):
        return self.dist.version_latest_in_spec

    @property
    def requires(self):
        return list([Requirement.parse(r) for r in self.dist.requires])

    @classmethod
    def parse(klass, s):
        parse_string = s
        scm_requirement = False

        if (s.startswith("git+") or s.startswith("hg+") or s.startswith("snv+")
                or s.startswith("bzr+")):
            # e.g. git+https://github.com/nicfit/nicfit.py.git@parcyl#egg=nicfit.py
            beg, end = s.find("@"), s.find("#")
            if beg == "-1":
                raise RequirementParseError(f"Error parsing SCM distribution: {s}")
            else:
                parse_string = s[beg + 1:]
                if end > beg:
                    parse_string = parse_string[:end - beg - 1]

            scm_requirement = s

        req = _RequirementBase.parse(parse_string)
        return klass(req, scm_req=scm_requirement)

    @property
    def dist(self):
        if self._dist is None:
            if self._scm_requirement_string:
                # Repo URLs have versions or a way for resolving requires
                class DummyDist:
                    requires = []
                    version_installed = None
                    version_latest_in_spec = None

                self._dist = DummyDist()
            else:
                # Be sure to ignore environment markers, a dist is wanted for version info and
                # should not infer determine installation.
                self._dist = JohnnyDist(self.project_name)

        return self._dist


class SetupRequirements:
    _SECTS = ("install", "test", "dev", "setup")

    def __init__(self):
        self._req_dict = self._loadIni(_SETUP_CFG)

    def _getter(self, sect):
        return self._req_dict[sect] if sect in self._req_dict else []

    @property
    def install(self):
        return self._getter("install")

    @property
    def test(self):
        return self._getter("test")

    @property
    def dev(self):
        return self._getter("dev")

    @property
    def setup(self):
        return self._getter("setup")

    @property
    def extras(self):
        extras = {}
        for sect in [s for s in self._req_dict if s.startswith(_EXTRA)]:
            extras[sect[len(_EXTRA):]] = self._req_dict[sect]
        return extras

    def _loadIni(self, req_ini):
        reqs = {}
        req_config = configparser.ConfigParser()
        req_config.read([str(req_ini)])

        for opt in req_config.options(_CFG_SECT):
            if opt in self._SECTS or opt.startswith(_EXTRA):
                reqs[opt] = list()
                deps = req_config.get(_CFG_SECT, opt)
                if deps:
                    for line in deps.split("\n"):
                        reqs[opt] += [Requirement.parse(s.strip()) for s in line.split(",")]

        return reqs

    def write(self, include_extras=False, freeze=False, upgrade=False, deep=False):

        if not _REQ_D.exists():
            raise NotADirectoryError(str(_REQ_D))

        for req_grp in [k for k in self._req_dict.keys() if self._req_dict[k]]:
            RequirementsDotText(_REQ_D / f"{req_grp}.txt", reqs=self._req_dict[req_grp])\
                .write(upgrade=upgrade, freeze=freeze, deep=deep)

        # Make top-level requirements.txt files
        pkg_reqs = []
        for name, pkgs in self._req_dict.items():
            if name == "install" or (name.startswith(_EXTRA) and include_extras):
                pkg_reqs += pkgs or []

        if pkg_reqs:
            RequirementsDotText("requirements.txt", reqs=pkg_reqs)\
                .write(upgrade=upgrade, freeze=freeze, deep=deep)


class RequirementsDotText:
    def __init__(self, filepath, file=None, reqs=None):
        self._reqs = {}

        if file:
            self._readReqsTxt(file)
        elif reqs:
            self._reqs = dict({r.key: r for r in reqs})
        else:
            with open(filepath) as fp:
                self._readReqsTxt(fp)

        self.filepath = filepath

    @property
    def requirements(self):
        return list(self._reqs.values())

    @property
    def packages(self):
        return list(self._reqs.keys())

    def get(self, package):
        try:
            return self._reqs[package]
        except KeyError:
            return None

    def _readReqsTxt(self, file):
        file.seek(0)
        for line in [l.strip() for l in file.readlines()
                     if l.strip() and not l.startswith("#")]:
            r = Requirement.parse(line)
            self._reqs[r.key] = r

    def write(self, upgrade=False, freeze=False, deep=False):

        def specfmt(req: Requirement, curr_reqs):
            if req.specs:
                return Requirement.SpecsOpt.CURRENT
            elif upgrade and req.version_latest_in_spec:
                return Requirement.SpecsOpt.VERSION_LATEST
            elif freeze:
                if req.version_installed:
                    return Requirement.SpecsOpt.VERSION_INSTALLED
                else:
                    curr = curr_reqs.get(req.key)
                    if curr and curr.specs:
                        req.specs.extend(curr.specs)
                        return Requirement.SpecsOpt.CURRENT
                    else:
                        return Requirement.SpecsOpt.VERSION_LATEST

        filepath = Path(self.filepath)
        file_exists = filepath.exists()
        with filepath.open("r+" if file_exists else "w") as fp:
            curr_reqs = RequirementsDotText(filepath, file=fp if file_exists else None)

            fp.seek(0)
            fp.truncate(0)
            for req in sorted(self._reqs.values()):
                if deep:
                    for dep in req.requires:
                        spec = specfmt(dep, curr_reqs)
                        fp.write(
                           f"{dep.toString(spec):<40} # Required by {req.project_name}\n"
                        )

                spec = specfmt(req, curr_reqs)
                fp.write(f"{req.toString(spec)}\n")

            print(f"Wrote {filepath}")


class Pip:
    @staticmethod
    def install(*pkgs):
        if len(pkgs):
            pkgs = list([shlex.quote(str(p)) for p in pkgs])
            os.system(f"pip install {' '.join(pkgs)}")


def _installExtras(dist):
    """Pip install a Distrubution's extras.

    Environment markers in install_requires are moved to extras by setuptools for some reason.
    Therefore `install_requires=["dataclasses ; python_version < '3.7'"]` becomes
    `{':python_version < "3.7"': ['dataclasses']}` (note the prefixed ':').
    """
    for extra in dist.extras_require:
        pkgs = list(dist.extras_require[extra])
        if extra.startswith(":"):
            # The packages common extras bundle under the environment marker.
            # Reassemble the markers so pip applies them
            pkgs = list([f"{p} ; {extra[1:]}" for p in pkgs])

        Pip.install(*pkgs)


class InstallCommand(_InstallCommand):
    def run(self):
        Pip.install(*self.distribution.install_requires)
        return super().run()


class DevelopCommand(_DevelopCommand):
    def run(self):
        Pip.install(*self.distribution.install_requires)
        Pip.install(*self.distribution.tests_require)
        Pip.install(*SetupRequirements().dev)
        _installExtras(self.distribution)

        return super().run()


class TestCommand(_TestCommand):
    def run(self):
        Pip.install(*self.distribution.tests_require)
        Pip.install(*self.distribution.install_requires)
        _installExtras(self.distribution)

        return super().run()


class PyTestCommand(TestCommand):
    user_options = [("pytest-args=", "a", "Arguments to pass to pytest")]

    def initialize_options(self):
        _TestCommand.initialize_options(self)
        self.pytest_args = ""

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(shlex.split(self.pytest_args))
        sys.exit(errno)


def main():
    import argparse

    p = argparse.ArgumentParser(description="Python project packaging helper.")
    p.add_argument("--version", action="version", version=__version__)
    subcmds = p.add_subparsers(dest="cmd")
    subcmds.add_parser("install",
                       help="Write a `parcyl.py` file to the current directory.")
    reqs_p = subcmds.add_parser("requirements",
                                help="Generate and freeze requirements (setup.cfg -> *.txt)")
    version_updater_grp = reqs_p.add_mutually_exclusive_group()
    version_updater_grp.add_argument("-F", "--freeze", action="store_true",
                        help="Pin packages to currently install versions")
    version_updater_grp.add_argument("-U", "--upgrade", action="store_true",
                        help="Pin packages to latest version matching version specs.")
    reqs_p.add_argument("-D", "--deep", action="store_true",
                        help="Include the dependencies of packages.")

    args = p.parse_args()
    if args.cmd == "install":
        parcyl_py = Path(f"{__project_name__.lower()}.py")
        if parcyl_py.exists():
            print(f"{parcyl_py} already exists, remove and try again",
                  file=sys.stderr)
            return 1
        print(f"Writing {parcyl_py}")
        parcyl_py.write_bytes(Path(__file__).read_bytes())
        parcyl_py.chmod(0o755)

    elif args.cmd == "requirements":
        req = SetupRequirements()
        if True in (args.freeze, args.upgrade, args.deep) and johnnydep is None:
            print("\nDependencies required for the --freeze/--upgrade/--deep options.\n"
                  "Try `pip install parcyl[requirements]` to install.\n", file=sys.stderr)
            args.freeze = args.upgrade = args.deep = False

        req.write(freeze=args.freeze, upgrade=args.upgrade, deep=args.deep)
    else:
        p.print_usage()


__all__ = ["Setup", "setup", "find_packages"]
if __name__ == "__main__":
    sys.exit(main() or 0)
