#!/usr/bin/env python

from manpage import ManPage
from manpage import MissingParser
import sys
import glob
import os.path
import os
from collections import Counter, defaultdict
import re
from string import Template

# FIXME: Horrible hack
SECTIONS = {
    'man1' : "Executable programs or shell commands", 
    'man2' : "System calls", 
    'man3' : "Library calls", 
    'man4' : "Special files", 
    'man5' : "File formats and conventions", 
    'man6' : "Games", 
    'man7' : "Miscellaneous", 
    'man8' : "System administration commands",
    'man0' : "ERROR. Section 0",
}

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
            mp = str(e).split(" ", 2)[1]
            print " * MP(%s): %s" % (mp, file, )

            cnt[mp] += 1
            continue
        except:
            errors += 1
            print " * ERR: %s" % (file, )
            continue


        basename = os.path.basename(file)
        dstdir = os.path.dirname(file)
        filepath = os.path.join(dstdir, basename) + ".tmp.html"

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
    print "Missing Parsers"
    print cnt

    # print pages
    # print mandirpages

    for directory, page_files in mandirpages.items():
        content = "<dl class=\"dl-vertical\">"
        for page_file in page_files:
            desc = pages[page_file][0]
            term = "<a href=\"%s.html\">%s</a>" % (page_file, format_name(page_file), )
            content += "<dt>%s</dt>" % (term, )
            content += "<dd>%s</dd>" % (desc, )

        content += "</dl>"

        base_tpl = load_template('base')
        header_tpl = load_template('header')

        out = base_tpl.safe_substitute(
            title="Linux Man Pages - %s" % SECTIONS[directory],
            canonical="",
            header=header_tpl.safe_substitute(
                title=SECTIONS[directory],
            ),
            content=content,
            metadescription=SECTIONS[directory].replace("\"", "\'"),
        )

        f = open(os.path.join(root_html, src, directory, 'index.html'), 'w')
        f.write(out)
        f.close()

    list_of_pages = pages.keys()

    # Linkify
    for directory, page_files in mandirpages.items():
        for page_file in sorted(page_files):

            tmp_page = os.path.join(root_html, src, directory, page_file) + ".tmp.html"
            final_page = os.path.join(root_html, src, directory, page_file) + ".html"

            with open(tmp_page) as f:
                content = f.read()

            file = open(final_page, "w")
            file.write(linkify(content, list_of_pages))
            file.close()

            os.unlink(tmp_page)

    # Generate base index
    base_tpl = load_template('base')
    index_tpl = load_template('index-contents')

    index = base_tpl.safe_substitute(
        # FIXME: Naming templates should be better
        metadescription="Linux Man Pages",
        title="Linux Man Pages",
        # FIXME: Remove nav
        nav = "",
        canonical="",
        header="",
        breadcrumb="",
        content=index_tpl.substitute(),
    )

    f = open("%s/index.html" % (os.path.join(root_html, src), ), 'w')
    f.write(index)
    f.close()


linkifier = re.compile(
    r"(?:<\w+?>)?(?P<page>\w+[\w\.-]+\w+)(?:</\w+?>)?[(](?P<section>\d)[)]")

def linkify(text, pages):
    def repl(m):
        manpage = m.groupdict()['page']
        section = m.groupdict()['section']
        page = '.'.join([manpage, section])

        out = "<strong>%s</strong>(%s)" % (manpage, section, )

        if page in pages:
            out = "<a href=\"../man%s/%s.%s.html\">%s</a>" % (
                section, manpage, section, out, )
        return out

    return linkifier.sub(repl, text)

def split_manpage(manpage):
    return manpage.rsplit('.', 1)

def format_name(manpage):
    base, section = split_manpage(manpage)
    return "<strong>%s</strong>(%s)" % (base, section, )

def load_template(template):
    fp = open("templates/%s.tpl" % (template, ))
    out = Template(''.join(fp.readlines()))
    fp.close()
    return out

if __name__ == '__main__':
    import time
    start_time = time.time()
    main()
    print("--- %s seconds ---" % (time.time() - start_time))
