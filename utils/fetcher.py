#!/usr/bin/env python

from debian import debfile, deb822
import logging
import requests
from tempfile import mkstemp
import os
import gzip

package_directory = os.path.dirname(os.path.abspath(__file__))

output_dir = os.path.join(package_directory, "..", "src")

packages_file = os.path.join(output_dir, "Packages")
contents_file = os.path.join(output_dir, "Contents")
repo_base_url = "http://ftp.se.debian.org/debian/"


class DebianManpageFetcher(object):
    """docstring for DebianManpageFetcher"""

    def __init__(self, manpage, packages_to_ignore = set()):
        self.missing_manpage = manpage
        self.packages_to_ignore = packages_to_ignore

    def fetch(self):
        search_string = "/%s" % self.missing_manpage

        with open(contents_file) as fp:
            for line in fp:
                if line.startswith("usr/share/man/man"):
                    if search_string in line:
                        self.section, self.package = line.split(
                        )[-1].split(',')[0].split('/')
                        logging.info(
                            "Found missing page %s in package %s",
                            self.missing_manpage,
                            self.package)
                        break
            else:
                logging.info(
                    "Not Found missing page %s",
                    self.missing_manpage,
                )
                return False

        if self.package in self.packages_to_ignore:
            logging.info(
                "Ignoring page %s, it was already fetched (package %s)",
                self.missing_manpage, self.package
            )
        else:
            self.get_package_data()
            self.fetch_manpages()

        return True

    def get_package_data(self):
            #a = deb822.Packages()
        for b in deb822.Packages.iter_paragraphs(sequence=open(packages_file)):
            if b["Package"] == self.package and b["Section"] == self.section:
                if "Source" not in b:
                    self.namespace = self.package
                else:
                    # We must split, in case it includes the version string
                    self.namespace = b["Source"].split()[0]
                self.filename = b["Filename"]
                break

    def fetch_manpages(self):
        logging.debug("Fetching package %s", self.filename)

        r = requests.get("%s%s" % (repo_base_url, self.filename,))
        _, tmpfile = mkstemp()

        fp = open(tmpfile, 'w')
        fp.write(r.content)
        fp.close()

        data_file = debfile.DebFile(tmpfile).data

        for file in data_file:
            if file.startswith("./usr/share/man/man"):
                file_contents = data_file.get_file(file)

                if file_contents:
                    self.extract_file(file, file_contents)

    def extract_file(self, file, contents):
        path, basename = os.path.split(file)
        mandir = os.path.basename(path)

        compressed = False
        if basename.endswith(".gz"):
            compressed = True
            basename = basename.rsplit('.', 1)[0]

        final_page_directory = os.path.join(output_dir, self.namespace, mandir)

        try:
            os.makedirs(final_page_directory)
        except OSError:
            pass

        final_path = os.path.join(final_page_directory, basename)

        if compressed:
            contents = gzip.GzipFile(fileobj=contents)

        logging.debug("Writing new page %s", final_path)
        fp = open(final_path, "w")
        fp.write(contents.read())
        fp.close()

if __name__ == '__main__':
    import time
    import argparse
    start_time = time.time()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "missing_manpage",
        help="the manpage you are looking for")
    parser.add_argument("--log-level", help="choose log level")
    args = parser.parse_args()

    if args.log_level:
        log_level = getattr(logging, args.log_level.upper())
        logging.basicConfig(level=log_level)

    fetcher = DebianManpageFetcher(args.missing_manpage)
    fetcher.fetch()

    elapsed = time.time() - start_time
    logging.info("--- Total time: %s seconds ---" % (elapsed, ))
