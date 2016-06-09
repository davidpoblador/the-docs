#!/usr/bin/env python

from manpage import ManPage
from manpage import MissingParser
import sys
import glob
import os.path
import os
from collections import Counter

root_html = "public_html/"

def main():
    _, src = sys.argv

    cnt = Counter()
    errors, mps, oks = (0, 0, 0)

    for file in glob.iglob("%s/man?/*.?" % src):
        print ""
        print "Processing man page %s..." % (file, )
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
        dstdir = os.path.join(root_html, os.path.dirname(file))
        dstfile = os.path.join(dstdir, basename) + ".html"

        if not os.path.exists(dstdir):
            os.makedirs(dstdir)

        print " * OK: %s" % (dstfile,)
        oks += 1
        file = open(dstfile, "w")
        file.write(content)
        file.close()

    print ""
    print "> Total processed: %s (OK: %s / MP: %s / ERR: %s)" % \
        (errors + oks + mps, oks, mps, errors, )
    print cnt

if __name__ == '__main__':
    main()