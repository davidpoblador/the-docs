#!/bin/sh

# Cleanup
rm -rf man-pages

# Clone the repo
git clone  --depth=1 http://git.kernel.org/pub/scm/docs/man-pages/man-pages man-pages
# Remove the .git directory
rm -rf !$/.git