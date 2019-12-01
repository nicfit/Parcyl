import sys
import pytest
from parcyl import Requirement, parseVersion


def test_Req_parse():
    r = Requirement.parse("eyeD3_extra")
    assert r.name == "eyeD3_extra"
    assert r.project_name == "eyeD3-extra"
    assert r.key == "eyed3-extra"
    assert r.specs == []
    assert r.marker is None

    r = Requirement.parse("pathlib==1.0.1;python_version < '3.4'")
    assert r.project_name == r.name == r.key == "pathlib"
    assert r.specs == [("==", "1.0.1")]
    assert str(r.marker) == "python_version < \"3.4\""

    r = Requirement.parse("pathlib;python_version < '3.4'")
    assert r.project_name == r.name == r.key == "pathlib"
    assert r.specs == []
    assert str(r.marker) == "python_version < \"3.4\""

    r = Requirement.parse("pathlib== 1.0.1")
    assert r.project_name == r.name == r.key == "pathlib"
    assert r.specs == [("==", "1.0.1")]
    assert r.marker is None

    r = Requirement.parse("PathLib>=3,<2")
    assert r.project_name == r.name == "PathLib"
    assert r.key == "pathlib"
    assert sorted(r.specs) == [
        ("<", "2"),
        (">=", "3"),
    ]

    rstr = "hg+https://nicfit@bitbucket.org/nicfit/sphinxcontrib-bitbucket"
    r = Requirement.parse(rstr)
    assert r.project_name == r.name == r.key == "sphinxcontrib-bitbucket"
    assert r._scm_requirement_string == rstr
    assert r.marker is None
    assert r.specs == []
    assert not r.extras

    r = Requirement.parse("Parcyl[requirements]")
    assert r.name == r.project_name == "Parcyl"
    assert r.key == "parcyl"
    assert r.marker is None
    assert r.specs == []
    assert r.extras == ("requirements",)

    r = Requirement.parse("MishMash[postgres,web]~=0.3")
    assert r.name == r.project_name == "MishMash"
    assert r.key == "mishmash"
    assert r.marker is None
    assert r.specs == [("~=", "0.3")]
    assert sorted(r.extras) == sorted(("web", "postgres"))
    assert str(r) in ("MishMash[postgres,web]~=0.3", "MishMash[web,postgres]~=0.3")


def test_Req_markereval():
    assert not Requirement.parse("rhcp ; python_version < '3'").marker.evaluate()
    assert not Requirement.parse("rhcp ; python_version < '3.4'").marker.evaluate()
    assert not Requirement.parse("rhcp ; python_version < '3.5'").marker.evaluate()
    assert (Requirement.parse("rhcp ; python_version <= '3.6'").marker.evaluate()
            == (sys.version_info[:2] <= (3, 6)))
    assert (Requirement.parse("rhcp ; python_version < '3.6'").marker.evaluate()
            == (sys.version_info[:2] < (3, 6)))
    assert (Requirement.parse("rhcp ; python_version > '3.6'").marker.evaluate()
            == (sys.version_info[:2] > (3, 6)))
    assert (Requirement.parse("rhcp ; python_version == '3.6'").marker.evaluate()
            == (sys.version_info[:2] == (3, 6)))
    assert (Requirement.parse("rhcp ; python_version == '3.7'").marker.evaluate()
            == (sys.version_info[:2] == (3, 7)))
    assert (Requirement.parse("rhcp ; implementation_name == 'pypy'").marker.evaluate()
            == (sys.implementation.name == "pypy"))


def test_parseVersion():
    for V in ("0.8.10a3", "0.8.10-a3"):
        vstr, v = parseVersion(V)
        assert v.major == 0
        assert v.minor == 8
        assert v.maint == 10
        assert v.release == "a3"
        assert vstr == "0.8.10a3"

    for V in ("0.3b14", "0.3b14.dev2", "0.3-b14.post1"):
        vstr, v = parseVersion(V)
        assert v.major == 0
        assert v.minor == 3
        assert v.maint == 0
        assert v.release == "b14"
        assert vstr == V.replace("-", "")

    vstr, v = parseVersion("1")
    assert v.major == 1
    assert v.minor == 0
    assert v.maint == 0
    assert v.release == "final"
    assert vstr == "1"


def test_parseVersionInvalid():
    for V in ("Slapshot", "Slapshot-1.0"):
        with pytest.raises(ValueError):
            parseVersion(V)
