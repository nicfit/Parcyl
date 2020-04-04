.PHONY: build dist requirements test

PYTEST_ARGS ?=
PYPI_REPO ?= pypitest
PROJECT_NAME = $(shell python setup.py --name 2> /dev/null)
VERSION = $(shell python setup.py --version 2> /dev/null)


all: build


build:
	./setup.py build

develop:
	./setup.py develop

lint:
	tox -e lint


requirements:
	@parcyl.py requirements --requirements.txt --compile


test:
	tox -e default,coverage,lint -- $(PYTEST_ARGS)


test-all:
	tox -e clean
	tox --parallel=all
	tox -e coverage


install: build
	./setup.py install


sdist: build
	./setup.py sdist --formats=gztar,zip

dist: clean sdist
	./setup.py bdist_egg
	./setup.py bdist_wheel


pre-release: maintainer-clean test dist
	tox -e check-manifest

	@echo "VERSION: $(VERSION)"
	$(eval RELEASE_TAG=v${VERSION})
	@echo "RELEASE_TAG: $(RELEASE_TAG)"
	@if git tag -l | grep -E '^$(shell echo $${RELEASE_TAG} | sed 's|\.|.|g')$$' > /dev/null; then \
        echo "Version tag '${RELEASE_TAG}' already exists!"; \
        false; \
    fi

	@git status -s -b


freeze-release:
	@(git diff --quiet && git diff --quiet --staged) || \
        (printf "\n!!! Working repo has uncommited/unstaged changes. !!!\n" && \
         printf "\nCommit and try again.\n" && false)


tag-release:
	git tag -a $(RELEASE_TAG) -m "Release $(RELEASE_TAG)"
	git push --tags origin


upload-release:
	for f in `find dist -type f \
	              -name ${PROJECT_NAME}-${VERSION}.tar.gz \
	              -o -name \*.egg -o -name \*.whl`; do \
	        if test -f $$f ; then \
	            twine upload -r ${PYPI_REPO} --skip-existing $$f ; \
	        fi \
	done


release: test-all pre-release freeze-release github-release-tool \
         dist tag-release upload-release


clean: test-clean py-clean


dist-clean distclean: clean
	-rm -rf ./dist


maintainer-clean: clean dist-clean


py-clean:
	python setup.py clean
	-rm -rf ./build
	-rm -rf ./Parcyl.egg-info
	find . -type f -name '*.pyc' -delete
	find . -type d -name __pycache__ -prune -exec rm -rf {} \;
	find . -type d -name .eggs -prune -exec rm -rf {} \;


test-clean:
	-rm -rf ./.tox
	-rm -rf ./.coverage
	-rm -rf ./.pytest_cache


GITHUB_USER ?= nicfit
github-release-tool:
	@if test -n "$$VIRTUAL_ENV"; then \
		GOPATH=$$VIRTUAL_ENV go get github.com/aktau/github-release; \
	else\
		echo "Must have an active virtualenv to install github-release";\
		false;\
	fi
	@test -n "${GITHUB_USER}" || (echo "GITHUB_USER not set, needed for github" && false)
	@test -n "${GITHUB_TOKEN}" || (echo "GITHUB_TOKEN not set, needed for github" && false)

