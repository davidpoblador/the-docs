#!/bin/sh

ts=$(date +"%F %T")
rsync -a public_html/ dist/
cd dist
git pull
git add --all
git commit -m "Update pages to new version %{ts}"
git push
cd ..
git pull
