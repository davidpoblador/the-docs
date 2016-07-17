#!/usr/bin/env python

import dirparse
import logging
from utils.fetcher import DebianManpageFetcher
import marshal

manpage_source = "src"


def main():
    parser = dirparse.ManDirectoryParser(manpage_source)
    parser.parse_directory()

    try:
        ignore_page_file = open('ignore_page_file.dat', 'rb')
        pages_to_ignore = marshal.load(ignore_page_file)
        ignore_page_file.close()
    except IOError:
        pages_to_ignore = set()

    packages_to_ignore = set()
    for page, _ in parser.get_missing_links():
        fetcher = DebianManpageFetcher(page,
                                       packages_to_ignore=packages_to_ignore)
        if fetcher.fetch():
            for section, package in fetcher.packages:
                packages_to_ignore.add(package)

        # Temporary hack to mitigate the problem with case insensitive filesystems
        # Should only ocurr on error fetching
        pages_to_ignore.add(page)

    ignore_page_file = open('ignore_page_file.dat', 'wb')
    marshal.dump(pages_to_ignore, ignore_page_file)
    ignore_page_file.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
