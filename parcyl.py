#!/usr/bin/env python
import os
import sys
import shlex
import logging
import warnings
import functools
import setuptools
import subprocess
import configparser
from enum import Enum
from pathlib import Path
from operator import attrgetter
from collections import namedtuple, defaultdict

from distutils.version import StrictVersion
from pkg_resources import (RequirementParseError,
                           Requirement as _RequirementBase)
from setuptools.command.test import test as _TestCommand
from setuptools.command.develop import develop as _DevelopCommand
from setuptools.command.install import install as _InstallCommand

# FIXME: dup'd in setup.cfg, which should be the source of truth
VERSION = "1.0a4"

_EXTRA = "extra_"
_REQ_D = Path("requirements")
_CFG_INFO_SECT = "parcyl"
_CFG_REQS_SECT = "parcyl:requirements"

STATUS_CLASSIFIERS = {
    # "alpha": "Development Status :: 1 - Planning",
    # "alpha": "Development Status :: 2 - Pre-Alpha",
    "alpha": "Development Status :: 3 - Alpha",
    "beta": "Development Status :: 4 - Beta",
    "final": "Development Status :: 5 - Production/Stable",
    # "final": "Development Status :: 6 - Mature",
    # "final": "Development Status :: 7 - Inactive",
}
_log = logging.getLogger("parcyl")

SETUP_ATTRS = {
    "name": "project_name",
    "version": "version",
    "author": "author",
    "author_email": "author_email",
    "url": "url",
    "license": "license",
    "description": "description",
    "long_description": "long_description",
    "classifiers": "classifiers",
    "keywords": "keywords",
}
EXTRA_ATTRS = {
    "release_name": "release_name",
    "github_url": "github_url",
    "years": "years",
}


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


class SetupCfg(configparser.ConfigParser):
    SETUP_CFG = Path("setup.cfg")

    def __init__(self):
        super().__init__()

        if self.SETUP_CFG.exists():
            self.read([str(self.SETUP_CFG)])

        self.attrs = self._initAttrs()
        self.requirements = self._initRequirements(self.attrs)

    def _initAttrs(self):
        attrs = {}
        for attr, var in dict(SETUP_ATTRS, **EXTRA_ATTRS).items():
            val = self.get(_CFG_INFO_SECT, var, fallback=None)

            if attr == "name" and val:
                attrs["project_name"] = val
                attrs["pypi_name"] = val
                attrs["project_slug"] = val.lower()
            elif attr == "version" and val:
                # Note, val becomes normalized
                val, version_info = parseVersion(val)
                attrs["release"] = version_info.release
                attrs["version_info"] = version_info
            elif attr == "classifiers" and val:
                val = list([c.strip() for c in val.split("\n") if c.strip()])
            elif attr == "keywords":
                kwords = list()  # If keywords is passed to setup it must be a list, not None
                if val:
                    for item in val.split():
                        csvals = item.split(",")
                        kwords += [v.strip(" ,\n") for v in csvals if v]
                val = kwords

            attrs[attr] = val

        return attrs

    def _initRequirements(self, attrs):
        requirements = SetupRequirements(self)

        for setup_arg, attr in [("install_requires", attrgetter("install")),
                                ("tests_require", attrgetter("test")),
                                ("extras_require", attrgetter("extras")),
                                ("setup_requires", attrgetter("setup")),
                               ]:
            if setup_arg not in attrs:
                if setup_arg != "extras_require":
                    attrs[setup_arg] = list([str(r) for r in attr(requirements)])
                else:
                    extras = attr(requirements)
                    attrs[setup_arg] = dict(
                        {extra: list([str(r) for r in extras[extra]])
                         for extra, reqs in attr(requirements).items()
                         })
            else:
                raise ValueError(f"`{setup_arg}` must be set via requirements file.")

        return requirements


class Setup:
    def __init__(self, info_file=None, **setup_attrs):
        self.config = SetupCfg()
        self.attrs = self.config.attrs
        self.requirements = self.config.requirements

        for what in SETUP_ATTRS:
            if what not in self.attrs:
                print(f"setup attribute not found: {what}", file=sys.stderr)

        # Install commands (TODO: merge with any existing commands)
        setup_attrs["cmdclass"] = {"install": InstallCommand,
                                   "test": TestCommand,
                                   "pytest": PyTestCommand,
                                   "develop": DevelopCommand,
                                  }

        # Final args
        self._ctor_setup_attrs = dict(setup_attrs)

        if info_file is not None:
            vinfo = self.attrs["version_info"]
            # TODO: log this like setuptools formats msgs, and move to a build stage
            Path(info_file).write_text(f"""
import dataclasses

project_name = "{self.attrs['name']}"
version      = "{self.attrs['version']}"
release_name = "{self.attrs['release_name']}"
author       = "{self.attrs['author']}"
author_email = "{self.attrs['author_email']}"
years        = "{self.attrs['years']}"

@dataclasses.dataclass
class Version:
    major: int
    minor: int
    maint: int
    release: str
    release_name: str

version_info = Version({vinfo.major}, {vinfo.minor}, {vinfo.maint}, "{vinfo.release}", "{self.attrs['release_name']}")
""".strip())   # noqa: E501

    def __call__(self, add_status_classifiers=True, **setup_attrs):
        attrs = {}
        attrs.update(self.attrs)
        attrs.update(self._ctor_setup_attrs)
        attrs.update(setup_attrs)

        if add_status_classifiers:
            if attrs["classifiers"] in (None, ""):
                attrs["classifiers"] = []

            release = (attrs["release"] or "") if "release" in attrs else ""
            if release.startswith("a"):
                attrs["classifiers"].append(STATUS_CLASSIFIERS["alpha"])
            elif release.startswith("b"):
                attrs["classifiers"].append(STATUS_CLASSIFIERS["beta"])
            else:
                attrs["classifiers"].append(STATUS_CLASSIFIERS["final"])

        # Found it difficult to hook into setuptools to *add* this option.
        # Ideally, `setup.py --version --release-name` would do the right order, not here.
        if "--release-name" in sys.argv[1:]:
            print(self.attrs["release_name"])
            sys.argv.remove("--release-name")

        # The extra command line options we added cause warnings, quell that.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Unknown distribution option")
            warnings.filterwarnings("ignore", message="Normalizing")

            setuptools.setup(**attrs)

    def with_packages(self, *pkg_dirs, exclude=None):
        pkgs = []
        if "packages" not in self.attrs:
            self.attrs["packages"] = []
        for d in pkg_dirs:
            pkgs += find_packages(d, exclude=exclude)
        self.attrs["packages"] += pkgs
        return self


@functools.total_ordering
class Requirement:

    class SpecsOpt(Enum):
        NONE = 0
        CURRENT = 1

    def __init__(self, requirement, scm_req=None):
        self._scm_requirement_string = scm_req
        self._requirement = requirement

        self._dist = None

    def __str__(self):
        return self.toString()

    def toString(self, specs=SpecsOpt.CURRENT, marker=True):
        specs = specs or self.SpecsOpt.NONE

        if self._scm_requirement_string:
            return self._scm_requirement_string

        s = self.project_name

        if self.extras:
            s += f"[{','.join(self.extras)}]"

        if specs == self.SpecsOpt.CURRENT:
            final_specs = []
            op_specs = defaultdict(list)
            for op, ver in self.specs:
                op_specs[op].append(ver)
            for op, versions in op_specs.items():
                if len(versions) > 1:
                    for v in versions:
                        try:
                            _ = StrictVersion(v)
                        except ValueError:
                            _log.info(f"Ignoring invalid version: {v}")
                            versions.remove(v)

                    if op[0] == ">":
                        op_specs[op] = [sorted(versions, key=StrictVersion, reverse=True).pop(0)]
                    elif op[0] == "<":
                        op_specs[op] = [sorted(versions, key=StrictVersion, reverse=False).pop(0)]
                    elif op[0] == "=":
                        raise ValueError(f"Version conflict: ==[{','.join(versions)}]")
                    elif op[0] == "!":
                        pass  # All excluded version get listed
                    elif op[0] == "~":
                        pass  # Hmm, let pip figure it out.
                    else:
                        raise NotImplementedError(f"No support for op {op}")

            for op, versions in op_specs.items():
                for v in versions:
                    final_specs.append((op, v))

            s += ",".join([f"{op}{ver}" for op, ver in sorted(final_specs, reverse=True)])

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
    def extras(self):
        return self._requirement.extras

    @property
    def requires(self):
        return list([Requirement.parse(r) for r in self.dist.requires])

    @classmethod
    def parse(klass, s):
        parse_string = s
        scm_requirement = None

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
                parse_string = parse_string.split("/")[-1]

            scm_requirement = s

        req = _RequirementBase.parse(parse_string)
        return klass(req, scm_req=scm_requirement)


class SetupRequirements:
    _EXTRA = _EXTRA
    _PINS = "pins"
    GROUPS = ["install", "test", "dev", "setup"]

    def __init__(self, req_config=None):
        if not req_config:
            req_config = SetupCfg()

        self._req_dict = self._loadCfg(req_config)

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
        for sect in [s for s in self._req_dict if s.startswith(self._EXTRA)]:
            extras[sect[len(self._EXTRA):]] = self._req_dict[sect]
        return extras

    @property
    def pins(self):
        return self._getter(self._PINS)

    def _loadCfg(self, req_config):
        if not req_config.has_section(_CFG_REQS_SECT):
            return {}

        reqs = {}
        for opt in req_config.options(_CFG_REQS_SECT):
            if opt in self.GROUPS or opt.startswith(self._EXTRA) or opt == self._PINS:
                reqs[opt] = list()
                deps = req_config.get(_CFG_REQS_SECT, opt)
                if deps:
                    for line in [l for l in deps.split("\n") if l.strip()]:
                        reqs[opt] += [Requirement.parse(s.strip()) for s in line.split(",")]

        return reqs

    def iterReqs(self, groups=None):
        groups = groups or list([k for k in self._req_dict.keys()
                                    if self._req_dict[k] and (k in self.GROUPS or
                                                              k.startswith(_EXTRA))
                                ]) + ["requirements"]

        for req_grp in [k for k in self._req_dict.keys() if self._req_dict[k] and k in groups]:
            # Individual requirements files
            yield RequirementsDotText(_REQ_D / f"{req_grp}.txt", reqs=self._req_dict[req_grp],
                                      pins=self.pins)

    def write(self, groups=None, requirements_txt=False):
        if not _REQ_D.exists():
            raise NotADirectoryError(str(_REQ_D))

        for reqs_txt in self.iterReqs(groups=groups):
            reqs_txt.write()

        # TODO: Future option of not including extras
        include_extras = True

        if requirements_txt:
            # Make top-level requirements.txt files
            pkg_reqs = []
            for name, pkgs in self._req_dict.items():
                if name == "install" or (name.startswith(self._EXTRA) and include_extras):
                    pkg_reqs += pkgs or []

            if pkg_reqs:
                RequirementsDotText("requirements/requirements.txt", reqs=pkg_reqs,
                                    pins=self.pins).write()

    def __bool__(self):
        return bool(self._req_dict)


class RequirementsDotText:
    def __init__(self, filepath, file=None, reqs=None, pins=None):
        self._reqs = {}

        if file:
            self._readReqsTxt(file)
        elif reqs:
            self._reqs = dict({r.key: r for r in reqs})
        else:
            with open(filepath) as fp:
                self._readReqsTxt(fp)

        self.filepath = filepath
        self._pins = list(pins) if pins else []

    @property
    def requirements(self):
        return iter(self._reqs.values())

    @property
    def packages(self):
        return iter(self._reqs.keys())

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

    def write(self):

        def specfmt(req: Requirement):
            if req.specs:
                return Requirement.SpecsOpt.CURRENT

        all_reqs = {}
        # FIXME: unused pins
        pins = {r.key: r for r in self._pins}  # noqa
        for req in sorted(self._reqs.values()):
            all_reqs[req.key] = req

        filepath = Path(self.filepath)
        file_exists = filepath.exists()
        with filepath.open("r+" if file_exists else "w") as fp:
            # FIXME: unused curr_reqs
            curr_reqs = RequirementsDotText(filepath, file=fp if file_exists else None)  # noqa

            fp.seek(0)
            fp.truncate(0)
            for req in all_reqs.values():
                fp.write(f"{req.toString(specfmt(req))}\n")

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


def find_package_files(directory, prefix=".."):
    paths = []
    for (path, _, filenames) in os.walk(directory):
        if "__pycache__" in path:
            continue
        for filename in filenames:
            if filename.endswith(".pyc"):
                continue
            paths.append(os.path.join(prefix, path, filename))
    return paths


def parseVersion(v):
    from pkg_resources import parse_version
    from pkg_resources.extern.packaging.version import Version

    # Some validation and normalization (e.g. 1.0-a1 -> 1.0a1)
    V = parse_version(v)
    if not isinstance(V, Version):
        raise ValueError(f"Invalid version: {v}")

    ver = str(V)
    if V._version.pre:
        rel = "".join([str(v) for v in V._version.pre])
    else:
        rel = "final"

    # Although parsed the following components are not captured: post, dev, local, epoch
    Version = namedtuple("Version", "major, minor, maint, release")
    ver_info = Version(V._version.release[0],
                       V._version.release[1] if len(V._version.release) > 1 else 0,
                       V._version.release[2] if len(V._version.release) > 2 else 0,
                       rel)
    return ver, ver_info


def _pipCompile(path):
    print(f"Compiling {path}...")
    subprocess.run(f"pip-compile --annotate --upgrade -o {path} {path}", shell=True, check=True)


def _main():
    import argparse

    p = argparse.ArgumentParser(description="Python project packaging helper.")
    p.add_argument("--version", action="version", version=VERSION)

    subcmds = p.add_subparsers(dest="cmd")
    inst_p = subcmds.add_parser("install",
                                help="Write a `parcyl.py` file to the current directory.")
    inst_p.add_argument("--force", action="store_true", help="Overwrite an existing parcyl.py")

    reqs_p = subcmds.add_parser("requirements",
                                help="Generate requirement files (setup.cfg -> *.txt)")
    reqs_p.add_argument("req_group", action="store", nargs="*",
                        help="Which requirements group/file to operate on.")
    reqs_p.add_argument("-R", "--requirements.txt", dest="requirements_txt", action="store_true",
                        help="Write a requirements.txt file composed of install and all extras.")
    reqs_p.add_argument("-C", "--compile", dest="compile", action="store_true",
                        help="Compile requirement files.")

    args = p.parse_args()

    if args.cmd == "install":
        parcyl_py = Path(f"parcyl.py")
        if parcyl_py.exists() and not args.force:
            print(f"{parcyl_py} already exists (use --force to overwrite)", file=sys.stderr)
            return 1

        print(f"Writing {parcyl_py}")
        parcyl_py.write_bytes(Path(__file__).read_bytes())
        parcyl_py.chmod(0o755)

    elif args.cmd == "requirements":
        try:
            req = SetupRequirements()
            if req:
                req.write(groups=args.req_group or None, requirements_txt=args.requirements_txt)

            if args.compile:
                for req_txt in req.iterReqs(groups=args.req_group or None):
                    _pipCompile(req_txt.filepath)
        except (RequirementParseError, subprocess.CalledProcessError) as req_err:
            print(req_err, file=sys.stderr)
            return 1


find_packages = setuptools.find_packages
__all__ = ["Setup", "setup", "find_packages", "find_package_files"]
if __name__ == "__main__":
    try:
        sys.exit(_main() or 0)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(127)
