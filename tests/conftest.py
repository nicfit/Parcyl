import sys
import textwrap
import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def parcyl_d(tmpdir):
    return ParcylDir(tmpdir)


class ParcylDir:
    _PARCYL_PY = Path(__file__).parent.parent.absolute() / "parcyl.py"
    _SETUP_PY_FORMAT = textwrap.dedent("""\
    import parcyl
    assert parcyl._UNIT_TESTING == True

    setup = parcyl.Setup({setup_kwargs})
    setup()
    """)

    def __init__(self, tmp_d):
        self._tmpdir = tmp_d
        self.path = Path(str(tmp_d))

        # Write project parcyl.py to the new dir so it used for `setup`
        self.path.joinpath("parcyl.py")\
                 .write_text(self._PARCYL_PY.read_text() +
                             "\n_UNIT_TESTING = True")

    def _withFile(self, fname, contents):
        f = self.path / fname
        f.write_text(contents)

    def withSetupPy(self, setup_kwargs: dict=None, contents: str=None):
        if contents is None:
            if setup_kwargs:
                kwarg_s = "\n".join([f"{name}=\"{value}\","
                                      for name, value in setup_kwargs.items()])
            else:
                kwarg_s = ""
            contents = self._SETUP_PY_FORMAT.format(setup_kwargs=kwarg_s)

        self._withFile("setup.py", contents)
        return self

    def withSetupCfg(self, contents):
        self._withFile("setup.cfg", contents)
        return self

    def setup(self, cmd, check=True):
        proc = subprocess.run(f"{sys.executable} setup.py {cmd}",
                              cwd=str(self.path), shell=True, check=check)
        return proc
