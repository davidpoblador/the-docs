#!/usr/bin/env bash

apt-get update
apt-get install -y nginx
if ! [ -L /var/www ]; then
  rm -rf /var/www
  ln -fs /vagrant/public_html /var/www
fi

rm /etc/nginx/sites-available/default
ln -s /vagrant/nginx-default-conf /etc/nginx/sites-available/default
/etc/init.d/nginx restart
