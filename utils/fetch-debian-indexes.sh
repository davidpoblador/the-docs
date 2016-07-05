#!/bin/sh

base_url="http://ftp.se.debian.org/debian/dists/stable/main/"
contents="Contents-i386.gz"
packages="binary-i386/Packages.gz"

cd ../src

curl ${base_url}${contents} | gunzip > Contents
curl ${base_url}${packages} | gunzip > Packages

cd -