#!/usr/bin/env python

import dirparse
import logging
from utils.fetcher import DebianManpageFetcher

manpage_directory = "src/man-pages"

def main():
    parser = dirparse.ManDirectoryParser(manpage_directory)
    parser.parse_directory()

    packages_to_ignore = set()
    for page, _ in parser.get_missing_links():
        fetcher = DebianManpageFetcher(page, packages_to_ignore = packages_to_ignore)
        if fetcher.fetch():
            packages_to_ignore.add(fetcher.package)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
