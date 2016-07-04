#!/bin/sh

ts=$(date +"%F %T")

cd ../the-docs-publish
git checkout gh-pages
git pull
cd -

rsync -a --delete --exclude .git public_html/ ../the-docs-publish/

cd ../the-docs-publish
git add --all
git commit -m "Update pages to new version ${ts}"
git push
cd -

git pull
