#!/bin/sh

rsync -a public_html/* dist/
cd dist


cd ..