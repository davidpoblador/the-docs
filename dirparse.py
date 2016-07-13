#!/usr/bin/env python

from manpage import ManPage
from parsers import MissingParser, NotSupportedFormat, RedirectedPage
import glob
import os
from collections import defaultdict, Counter
from string import Template
import marshal
import logging
import shutil

package_directory = os.path.dirname(os.path.abspath(__file__))

root_html = os.path.join(package_directory, "public_html")
base_src = "man-pages"
base_url = "https://www.carta.tech/"

base_manpage_dir = os.path.join(root_html, base_src)
base_manpage_url = base_url + base_src

# To skip
broken_files = set()

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


def get_section_url(section):
    return base_manpage_url + "/" + section + "/"


class ManDirectoryParser(object):
    """docstring for ManDirectoryParser"""

    def __init__(self, source_dir):
        self.pages = dict()

        self.source_dir = source_dir

        self.missing_parsers = Counter()
        self.number_missing_parsers = 10

        self.missing_links = Counter()
        self.number_missing_links = 10

    def get_dir_pages(self):
        mandirpages = defaultdict(set)
        for page, v in self.pages.iteritems():
            if 'errors' not in v and 'missing-parser' not in v:
                mandirpages[v['section-dir']].add(page)

        return mandirpages

    def get_pages(self):
        for page, v in self.pages.iteritems():
            if 'errors' not in v and 'missing-parser' not in v:
                yield v['instance'], v['final-page']

    def get_pages_without_errors(self):
        manpages = set()
        for page, v in self.pages.iteritems():
            if 'errors' not in v and 'missing-parser' not in v:
                manpages.add(page)

        return manpages

    def get_pages_with_errors(self):
        for page, v in self.pages.iteritems():
            if 'errors' in v or 'missing-parser' in v:
                yield page

    def get_pages_with_missing_parsers(self):
        pages_with_missing_parsers = []
        for page, v in self.pages.iteritems():
            if 'missing-parser' in v:
                pages_with_missing_parsers.append(page)

        return pages_with_missing_parsers

    def parse_directory(self):
        shutil.rmtree(base_manpage_dir, ignore_errors=True)
        p = self.pages

        for item in list(glob.iglob("%s/*/man?/*.?" % self.source_dir)):
            #print "DEBUG", item
            page_directory, basename = os.path.split(item)
            redirection_base_dir, section_directory = os.path.split(
                page_directory)
            package_name = os.path.basename(redirection_base_dir)

            if basename in broken_files:
                continue

            cp = p[basename] = dict()  # Current page
            sd = cp['section-dir'] = section_directory  # Section Directory
            package = cp['package'] = package_name  # Package
            rd = cp['red-dir'] = redirection_base_dir  # Redirection base dir
            fp = cp['full-path'] = item  # Full Path

            cp['name'], cp['section'] = basename.rsplit('.', 1)
            cp['page-url'] = get_section_url(sd) + basename + ".html"

            first_pass = True
            try:
                while (first_pass or mp.redirect):
                    if first_pass:
                        logging.debug("Processing man page %s ..." % (fp, ))
                        mp = cp['instance'] = ManPage(
                            fp, base_url=base_manpage_url)
                        first_pass = False
                    else:
                        red_section, red_page = mp.redirect
                        if not red_section:
                            red_section = sd

                        red = os.path.join(rd, red_section, red_page)

                        logging.debug(
                            " * Page %s has a redirection to %s. Processing..."
                            % (fp, red))
                        mp = cp['instance'] = ManPage(
                            red,
                            base_url=base_manpage_url,
                            redirected_from=fp)

                    try:
                        mp.parse()
                        subtitle = cp['subtitle'] = mp.subtitle
                    except NotSupportedFormat:
                        raise NotSupportedFormat
                    except RedirectedPage:
                        continue

            except MissingParser as e:
                macro = str(e).split(" ", 2)[1]
                logging.warning(" * Missing Parser (%s): %s" % (macro,
                                                                fp, ))
                self.missing_parsers[macro] += 1
                cp['errors'] = True
                cp['missing-parser'] = True
                continue
            except NotSupportedFormat:
                logging.warning(" * Not supported format: %s" % (fp, ))
                cp['errors'] = True
                continue
            except IOError:
                cp['errors'] = True
                if mp.redirect:
                    self.missing_links[red_page] += 1
                continue
            except:
                logging.error(" * Unknown error: %s" % (fp, ))
                cp['errors'] = True
                raise

        found_pages = self.get_pages_without_errors()
        for directory, page_files in self.get_dir_pages().iteritems():
            man_directory = os.path.join(base_manpage_dir, directory)
            try:
                os.makedirs(man_directory)
            except OSError:
                pass

            previous = None
            for page in sorted(page_files):
                d = p[page]
                d['final-page'] = os.path.join(man_directory, page) + ".html"
                logging.debug(" * Writing page: %s" % page)
                if previous:
                    d['instance'].set_previous(previous[0], previous[1])
                    p[previous[0]]['instance'].set_next(page, d['subtitle'])

                previous = (page, d['subtitle'])

        for mp, final_page in self.get_pages():
            out = mp.html(pages_to_link=found_pages)
            self.missing_links.update(mp.broken_links)
            file = open(final_page, "w")
            file.write(out)
            file.close()

        # Directory Indexes & Sitemaps
        sm_urls = []
        for directory, page_files in self.get_dir_pages().iteritems():
            logging.debug(" * Generating indexes and sitemaps for %s" %
                          directory)

            section_item_tpl = load_template('section-index-item')
            sm_item_tpl = load_template('sitemap-url')

            section_items, sitemap_items = ("", "")
            for page in sorted(page_files):
                d = p[page]

                section_items += section_item_tpl.substitute(
                    link=page,
                    name=d['name'],
                    section=d['section'],
                    description=d['subtitle'],
                    package=d['package'], )

                sitemap_items += sm_item_tpl.substitute(url=d['page-url'])
            else:
                sitemap_items += sm_item_tpl.substitute(
                    url=get_section_url(directory))

            section_content = load_template('section-index').substitute(
                items=section_items)
            sitemap = load_template('sitemap').substitute(urlset=sitemap_items)

            sitemap_path = os.path.join(base_manpage_dir, directory,
                                        "sitemap.xml")
            f = open(sitemap_path, 'w')
            f.write(sitemap)
            f.close()

            sm_urls.append(get_section_url(directory) + "sitemap.xml")

            full_section = SECTIONS[directory]
            numeric_section = directory[3:]

            out = load_template('base').safe_substitute(
                title="Linux Man Pages - %s" % full_section,
                canonical="",
                header=load_template('header').safe_substitute(
                    title=full_section,
                    section=numeric_section,
                    subtitle=""),
                breadcrumb=load_template('breadcrumb-section').substitute(
                    section_name=full_section,
                    base_url=base_manpage_url,
                    section=numeric_section),
                content=section_content,
                metadescription=full_section.replace("\"", "\'"), )

            f = open(
                os.path.join(base_manpage_dir, directory, 'index.html'), 'w')
            f.write(out)
            f.close()

        sitemap_index_url_tpl = load_template('sitemap-index-url')
        sitemap_index_content = ""
        for sitemap_url in sm_urls:
            sitemap_index_content += sitemap_index_url_tpl.substitute(
                url=sitemap_url)

        sitemap_index_tpl = load_template('sitemap-index')
        sitemap_index_content = sitemap_index_tpl.substitute(
            sitemaps=sitemap_index_content)

        f = open(os.path.join(base_manpage_dir, "sitemap.xml"), 'w')
        f.write(sitemap_index_content)
        f.close()

        # Generate base index
        base_tpl = load_template('base')
        index_tpl = load_template('index-manpage')

        index = base_tpl.safe_substitute(
            # FIXME: Naming templates should be better
            metadescription="Linux Man Pages",
            title="Linux Man Pages",
            # FIXME: Remove nav
            nav="",
            canonical="",
            header="",
            breadcrumb="",
            content=index_tpl.substitute(), )

        f = open(os.path.join(base_manpage_dir, "index.html"), 'w')
        f.write(index)
        f.close()

        index_tpl = load_template('index-contents')
        index = base_tpl.safe_substitute(
            # FIXME: Naming templates should be better
            metadescription="Carta.tech: The home for open documentation",
            title="Carta.tech: The home for open documentation",
            # FIXME: Remove nav
            nav="",
            canonical="",
            header="",
            breadcrumb="",
            content=index_tpl.substitute(), )

        f = open(os.path.join(root_html, "index.html"), 'w')
        f.write(index)
        f.close()

        self.fix_missing_links()

    def fix_missing_links(self):
        for page in self.get_pages_with_errors():
            if page in self.missing_links:
                del self.missing_links[page]

        try:
            ignore_page_file = open('ignore_page_file.dat', 'rb')
            pages_to_ignore = marshal.load(ignore_page_file)
            ignore_page_file.close()
            for page in pages_to_ignore:
                if page in self.missing_links:
                    del self.missing_links[page]
        except IOError:
            pass

    def get_missing_links(self):
        return self.missing_links.most_common(self.number_missing_links)

    def get_missing_parsers(self):
        return self.missing_parsers.most_common(self.number_missing_parsers)


def load_template(template):
    fp = open("templates/%s.tpl" % (template, ))
    out = Template(''.join(fp.readlines()))
    fp.close()
    return out


if __name__ == '__main__':
    import time
    import argparse
    start_time = time.time()

    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir",
                        help="the directory you want to use as source")
    parser.add_argument("--log-level", help="choose log level")
    parser.add_argument("--missing-links",
                        help="choose the amount of broken links to display",
                        type=int)
    parser.add_argument("--missing-parsers",
                        help="choose the amount of missing parsers to display",
                        type=int)
    args = parser.parse_args()

    if args.log_level:
        log_level = getattr(logging, args.log_level.upper())
        logging.basicConfig(level=log_level)

    parser = ManDirectoryParser(source_dir=args.source_dir)

    if args.missing_links:
        parser.number_missing_links = args.missing_links

    if args.missing_parsers:
        parser.number_missing_parsers = args.missing_parsers

    parser.parse_directory()

    print "Missing Links: %s" % parser.get_missing_links()
    print "Missing Parsers: %s" % parser.get_missing_parsers()
    print "Pages With Missing Parsers", parser.get_pages_with_missing_parsers()

    elapsed = time.time() - start_time
    logging.info("--- Total time: %s seconds ---" % (elapsed, ))
