#!/usr/bin/env python

from manpage import ManPage
from manpage import MissingParser
import sys
import glob
import os.path
import os
from collections import Counter, defaultdict

root_html = "public_html/"
base_host = "http://localhost:8000/"

def main():
    _, src = sys.argv

    cnt = Counter()
    errors, mps, oks = (0, 0, 0)

    pages = defaultdict()
    mandirpages = defaultdict(list)

    for file in glob.iglob("%s/man?/*.?" % src):
        print "Processing man page %s ..." % (file, )
        try:
            manpage = ManPage(file)
            content = manpage.html()
        except MissingParser as e:
            mps += 1
            print " * MP: %s" % (file, )
            mp = str(e).split(" ", 2)[1]
            cnt[mp] += 1
            continue
        except:
            errors += 1
            print " * ERR: %s" % (file, )
            continue


        basename = os.path.basename(file)
        dstdir = os.path.dirname(file)
        filepath = os.path.join(dstdir, basename) + ".html"

        manbasedir = os.path.basename(dstdir)

        dstdir = os.path.join(root_html, os.path.dirname(file))

        if not os.path.exists(dstdir):
            os.makedirs(dstdir)

        dstfile = os.path.join(root_html, filepath)
        url = "%s%s" % (base_host, filepath)

        print " * OK: %s - %s" % (url, dstfile,)
        oks += 1
        file = open(dstfile, "w")
        file.write(content)
        file.close()

        pages[basename] = (manpage.subtitle, manbasedir)
        mandirpages[manbasedir].append(basename)

    print "\n> Total processed: %s (OK: %s / MP: %s / ERR: %s)" % \
        (errors + oks + mps, oks, mps, errors, )

    # DEBUG:

    # Missing parsers
    # print cnt

    # print pages
    # print mandirpages

    for directory, page_files in mandirpages.items():
        content = ""
        for page_file in page_files:
            content += "<li><a href='%s'>%s</a> - %s\n" % (page_file + ".html", page_file, pages[page_file][0])
        content = "<ul>\n%s</ul>" % content

        file = open(os.path.join(root_html, src, directory, "index.html"), "w")
        file.write(content)
        file.close()


if __name__ == '__main__':
    import time
    start_time = time.time()
    main()
    print("--- %s seconds ---" % (time.time() - start_time))
