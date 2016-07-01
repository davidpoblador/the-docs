#!/usr/bin/env python

from manpage import ManPage
from manpage import MissingParser
import sys
import glob
import os.path
import os
from collections import Counter, defaultdict
from string import Template


root_html = "public_html/"
base_host = "http://localhost:8000/"

# FIXME: Horrible hack
SECTIONS = {
    'man1': "Executable programs or shell commands",
    'man2': "System calls",
    'man3': "Library calls",
    'man4': "Special files",
    'man5': "File formats and conventions",
    'man6': "Games",
    'man7': "Miscellaneous",
    'man8': "System administration commands",
    'man0': "ERROR. Section 0",
}


def main():
    _, src = sys.argv
    list_of_manfiles = list(glob.iglob("%s/man?/*.?" % src))
    list_of_manpages = dict()
    mandirpages = defaultdict(set)
    pages = defaultdict()

    for manfile in list_of_manfiles:
        print("Processing man page %s ..." % (manfile, ))
        try:
            manpage = ManPage(manfile)
            g = manpage.parse()

            redirect, subtitle = next(g)

            while redirect:
                redirection = get_redirection_file(src, redirect)
                print(" * Page %s has a redirection to %s..." % (manfile, redirection))
                manpage = ManPage(redirection, redirected_from=manfile)
                g = manpage.parse()

                redirect, subtitle = next(g)

        except MissingParser as e:
            mp = str(e).split(" ", 2)[1]
            print(" * MP(%s): %s" % (mp, manfile, ))
            continue
        except:
            print(" * ERR: %s" % (manfile, ))
            raise

        basename = os.path.basename(manfile)
        dstdir = os.path.dirname(manfile)
        manbasedir = os.path.basename(dstdir)

        mandirpages[manbasedir].add(basename)
        pages[basename] = (subtitle, manbasedir)

        list_of_manpages[basename] = [manpage, g]

    del(list_of_manfiles)

    # Write and Linkify
    list_of_pages = set(pages.keys())
    for directory, page_files in list(mandirpages.items()):
        for page_file in sorted(page_files):
            final_page = os.path.join(
                root_html, src, directory, page_file) + ".html"
            print(" * Writing page: %s" % final_page)

            try:
                next(list_of_manpages[page_file][1])
            except StopIteration:
                pass
            except MissingParser as e:
                mp = str(e).split(" ", 2)[1]
                print(" * MP(%s): %s" % (mp, manfile, ))
                continue

            list_of_manpages[page_file][0].set_pages(list_of_pages)

            file = open(final_page, "w")
            file.write(list_of_manpages[page_file][0].html())
            file.close()

    # Directory Indexes
    for directory, page_files in list(mandirpages.items()):
        print(" * Generating indexes for %s" % directory)
        content = "<dl class=\"dl-vertical\">"
        for page_file in sorted(page_files):
            desc = pages[page_file][0]
            term = "<a href=\"%s.html\">%s</a>" % (
                page_file, format_name(page_file), )
            content += "<dt>%s</dt>" % (term, )
            content += "<dd>%s</dd>" % (desc, )

        content += "</dl>"

        base_tpl = load_template('base')
        header_tpl = load_template('header')
        breadcrumb_tpl = load_template('breadcrumb-section')

        full_section = SECTIONS[directory]
        numeric_section = directory.replace('man', '', 1)

        out = base_tpl.safe_substitute(
            title="Linux Man Pages - %s" %
            full_section,
            canonical="",
            header=header_tpl.safe_substitute(
                title=full_section,
                section=numeric_section,
                subtitle=""),
            breadcrumb=breadcrumb_tpl.substitute(
                section_name=full_section,
                section=numeric_section),
            content=content,
            metadescription=full_section.replace(
                "\"",
                "\'"),
        )

        f = open(os.path.join(root_html, src, directory, 'index.html'), 'w')
        f.write(out)
        f.close()

    # Generate base index
    base_tpl = load_template('base')
    index_tpl = load_template('index-contents')

    index = base_tpl.safe_substitute(
        # FIXME: Naming templates should be better
        metadescription="Linux Man Pages",
        title="Linux Man Pages",
        # FIXME: Remove nav
        nav="",
        canonical="",
        header="",
        breadcrumb="",
        content=index_tpl.substitute(),
    )

    f = open("%s/index.html" % (os.path.join(root_html, src), ), 'w')
    f.write(index)
    f.close()


def get_redirection_file(src, manpage_redirect):
    return os.path.join(src, *manpage_redirect)


def format_name(manpage):
    base, section = manpage.rsplit('.', 1)
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
    elapsed = time.time() - start_time

    print(("--- %s seconds ---" % (elapsed)))
