Parcyl
======
Parcyl is built from and extends `setuptools`. It also provides a stradegy and
tools for managing project requirements.

Features
---------

- Extends `setuptools` commands to install project requirements using `pip`.
- Load project metadata (e.g. version, author, etc.) from python files
  (or any external file).
- Specify projects requirements in one location and generate .txt files
  with or without version pinning.


Project Dependencies
---------------------
All of the `setup` keyword arguments used for specifying requirements
(`install_requires`, etc.) are supported, but it is possible to let Parcyl
build the values automatically and even generate a `requirements.txt` file(s).
To achieve this simply list all of the projects dependencies in your
`setup.cfg`. ::

    [parcyl:requirements]
    install = requests
              pathlib ; python_version < '3.4'
    test = pytest, tox
    extra_foo = foo-pkg==1.0.6
                bazz~=5.0
    setup =
    dev = ipdb
          flake8
          check-manifest

Each value is mapped to the `setup` keyword arguments `install_requires`,
`tests_require`, `extras_require`, and `setup_requires`, respectively. There is
no corresponding keyword argument for the `dev` dependencies, but the
`setup.py develop` command has been extended to install these packages.

parcyl requirements
~~~~~~~~~~~~~~~~~~~~~~
Parcyl can generate use the same config to generate `requirements.txt` files
for use with `pip` directly. Note, no `setup.txt` file is produced since not
requirments were listed. ::

    $ parcyl requirements
    Wrote requirements/install.txt
    Wrote requirements/extra_foo.txt
    Wrote requirements/test.txt
    Wrote requirements/dev.txt
    Wrote requirements.txt


parcyl requirements --freeze/--upgrade
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Options exist to add (i.e. "pin") a version to each dependency. The `--freeze`
will pit to the currently installed version, or the latest version if the package
is not currently installed. Use `--upgrade` to pin to the latest version every
time. To expand the dependency tree and list each packages requirements add the
`--deep` option. ::

    $ parcyl requirements --upgrade --deep

Each of these options requires the `johnnydep` package to function. Install
by specifying the extra `requirements` package. ::

    $ pip install parcyl[requirements]


setup.py
---------
A project's initial `setup.py` can be pretty simple and might look something
like this: ::

    import setuptools
    setuptools.setup(name="ProjectX", version="1.0")

Using `parcyl` looks nearly the same, so provides some immediate benefits. ::

    import parcyl
    setup = parcyl.setup(name="ProjectX", version="1.0")

Benefits:

- Extends `setuptool` rather than replacing it.
- `install` command: Package installs of `install_requires` are performed using
  `pip`.
- `test` command: Package installs of `install_requires`, `tests_require`, and
  any `extras_require` are performed using `pip`.
- `pytest` command: An additional command to run tests using `pytest`.
- `develop` command: Install all the same requirements as `test` but all the
  `dev` requiments.
- A single location and tools for managing project dependencies
  (i.e. requirements.txt)

