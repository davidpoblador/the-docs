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
                        packages = line.split()[-1].split(',')
                        self.packages = []

                        for package in packages:
                            self.packages.append(package.split('/'))

                        logging.info(
                            "Found missing page %s in packages %s",
                            self.missing_manpage,
                            self.packages)
                        break
            else:
                logging.info(
                    "Not Found missing page %s",
                    self.missing_manpage,
                )
                return False

        for section, package in self.packages:
            logging.info("Processing %s - %s", section, package)
            if package in self.packages_to_ignore:
                logging.info(
                    "Ignoring page %s, it was already fetched (package %s)",
                    self.missing_manpage, package
                )
            else:
                self.fetch_manpages(section, package)

        return True

    @classmethod
    def fetch_manpages(cls, section, package):
        logging.info("Fetching %s - %s", section, package)
        for b in deb822.Packages.iter_paragraphs(sequence=open(packages_file)):
            if b["Package"] == package and b["Section"] == section:
                if "Source" not in b:
                    namespace = package
                else:
                    # We must split, in case it includes the version string
                    namespace = b["Source"].split()[0]
                filename = b["Filename"]
                break

        logging.info("Fetching package %s", filename)

        r = requests.get("%s%s" % (repo_base_url, filename,))
        _, tmpfile = mkstemp()

        fp = open(tmpfile, 'w')
        fp.write(r.content)
        fp.close()

        data_file = debfile.DebFile(tmpfile).data

        for file in data_file:
            if file.startswith("./usr/share/man/man"):
                try:
                    file_contents = data_file.get_file(file)
                except:
                    continue

                if file_contents:
                    path, basename = os.path.split(file)
                    mandir = os.path.basename(path)

                    compressed = False
                    if basename.endswith(".gz"):
                        compressed = True
                        basename = basename.rsplit('.', 1)[0]

                    final_page_directory = os.path.join(output_dir, namespace, mandir)
    
                    try:
                        os.makedirs(final_page_directory)
                    except OSError:
                        pass

                    final_path = os.path.join(final_page_directory, basename)

                    if compressed:
                        file_contents = gzip.GzipFile(fileobj=file_contents)

                    logging.debug("Writing new page %s", final_path)

                    fp = open(final_path, "w")
                    fp.write(file_contents.read())
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
