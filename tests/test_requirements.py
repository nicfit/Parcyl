import sys
from parcyl import Requirement


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
