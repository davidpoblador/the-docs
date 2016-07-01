#!/usr/bin/env bash

apt-get update
apt-get install -y nginx
if ! [ -L /var/www ]; then
  rm -rf /var/www
  ln -fs /vagrant/public_html /var/www
fi
