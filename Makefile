all: clean test publish

clean:
	rm -rf dist/

test:
	python setup.py test

publish: clean
	python3 setup.py bdist_wheel --universal
	gpg --detach-sign -a dist/*.whl
	twine upload dist/*
