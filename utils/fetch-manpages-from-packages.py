#!/usr/bin/env python

import os
import git
import magic
import logging
from collections import defaultdict
import shutil

pjoin = os.path.join


package_directory = os.path.dirname(os.path.abspath(__file__))
output_dir = pjoin(package_directory, "..", "sources")
dest_dir = pjoin(package_directory, "..", "src")

def main():
    packages = dict()
    packages['acl'] = ("git://git.savannah.nongnu.org/acl.git", )
    packages['man-pages'] = ("http://git.kernel.org/pub/scm/docs/man-pages/man-pages", )

    for package in packages:
        logging.info("Processing package %s", package)
        package_dir = os.path.relpath(pjoin(output_dir, package))
        if os.path.isdir(package_dir):
            repo = git.Repo(package_dir)
            #repo.remotes[0].pull()
        else:
            url = packages[package][0]
            logging.info("%s not found, cloning from %s", package, url)

            repo = git.Repo.clone_from(url, package_dir, depth=1)


        manpages = defaultdict(set)
        for (dirpath, dirnames, filenames) in os.walk(package_dir, topdown = True):
            basename = os.path.basename(dirpath)
            if '.git' in dirnames:
                dirnames.remove('.git')

            for filename in filenames:
                if '.' in filename:
                    base, ext = filename.rsplit('.', 1)
                    if not ext:
                        continue

                    numbers = map(str, range(1,10))
                    section = ext[0]
                    if section in numbers:
                        file = pjoin(dirpath, filename)
                        ft = magic.Magic(keep_going = True)
                        file_type = ft.from_file(file)
                        print "DEBUG", filename, file, file_type
                        if "troff" in file_type:
                            non_numeric_section = "man%s" % (section, )
                            manpages[non_numeric_section].add(file)

        if not manpages:
            continue

        package_dir = pjoin(dest_dir, package)
        shutil.rmtree(package_dir, ignore_errors=True)

        for section in manpages:
            man_directory = pjoin(package_dir, section)
            try:
                os.makedirs(man_directory)
            except OSError:
                pass

            for page in manpages[section]:
                shutil.copy(page, man_directory)

if __name__ == '__main__':
    import time
    import argparse
    start_time = time.time()

    parser = argparse.ArgumentParser()
    parser.add_argument("--log-level", help="choose log level")
    args = parser.parse_args()

    if args.log_level:
        log_level = getattr(logging, args.log_level.upper())
        logging.basicConfig(level=log_level)

    main()

    elapsed = time.time() - start_time
    logging.info("--- Total time: %s seconds ---" % (elapsed, ))
