#!/bin/sh

rsync -a public_html/* dist/
cd dist
git pull
git add --all
git commit -m 'Update pages to new version'
git push
cd ..