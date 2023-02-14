#!/bin/bash

cd ./docs

vale .

notebooks=$(find . -name "*.ipynb" -not -name "*checkpoint*")

for notebook in ${notebooks}
do
  python -m nbqa vale ${notebook} --nbqa-shell --nbqa-md
done
