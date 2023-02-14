#!/bin/bash

cd ./docs

vale .

notebooks=$(find . -name "*.ipynb")

for notebook in ${notebooks}
do
  python -m nbqa vale ${notebook} --nbqa-shell --nbqa-md || exit 1
done
