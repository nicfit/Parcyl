from parcyl import Setup, setup

setup_attrs = Setup.attrsFromFile("parcyl.py",
                                  extra_attrs={
                                      "entry_points": {
                                          "console_scripts": [
                                              "parcyl = parcyl:main"
                                          ]
                                      }
                                  })[0]

setup(py_modules=["parcyl"], **setup_attrs)
