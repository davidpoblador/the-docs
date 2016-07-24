#!/usr/bin/env python

import os
import glob
import marshal
import logging
import datetime

from collections import defaultdict, Counter

from manpage import ManPage

from base import load_template, get_pagination, get_breadcrumb
from base import MissingParser, NotSupportedFormat, RedirectedPage, UnexpectedState

package_directory = os.path.dirname(os.path.abspath(__file__))

root_html = os.path.join(package_directory, "public_html")
base_manpage_src = "man-pages"
base_packages_src = "packages"
base_url = "https://www.carta.tech/"

base_manpage_dir = os.path.join(root_html, base_manpage_src)
base_packages_dir = os.path.join(root_html, base_packages_src)

base_manpage_url = base_url + base_manpage_src
base_packages_url = base_url + base_packages_src

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


class ManDirectoryParser(object):
    """docstring for ManDirectoryParser"""

    now = datetime.datetime.today().strftime('%Y-%m-%d')

    def __init__(self, source_dir):
        self.pages = dict()

        self.source_dir = source_dir

        self.missing_parsers = Counter()
        self.number_missing_parsers = 10

        self.missing_links = Counter()
        self.number_missing_links = 10

        self.section_counters = Counter()
        self.number_section_counters = 10

    def get_dir_pages(self):
        mandirpages = defaultdict(set)
        for page, v in self.pages.iteritems():
            if 'errors' not in v and 'missing-parser' not in v:
                mandirpages[v['section-dir']].add(page)

        return mandirpages

    def get_package_pages(self):
        packagepages = defaultdict(set)
        for page, v in self.pages.iteritems():
            if 'errors' not in v and 'missing-parser' not in v:
                packagepages[v['package']].add(page)

        return packagepages

    def get_pages(self):
        for page, v in self.pages.iteritems():
            if 'errors' not in v and 'missing-parser' not in v:
                yield v['instance'], v['final-page'], v

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
        self.clean_directory()

        # Parse pages
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
            cp['page-url'] = self.get_section_url(
                sd) + basename + ".html"  # DEBUG

            first_pass = True
            try:
                while (first_pass or mp.redirect):
                    if first_pass:
                        logging.debug("Processing man page %s ..." % (fp, ))
                        mp = cp['instance'] = ManPage(
                            fp, base_url=base_manpage_url,
                            package=package)
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
                            redirected_from=fp,
                            package=package)

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

        self.set_previous_next_links(self.get_dir_pages().iteritems(), p)
        self.write_pages()
        sm_urls = self.generate_sitemaps_and_indexes(
            iterator=self.get_dir_pages().iteritems(),
            pages=p)

        self.generate_package_indexes(source_dir=self.source_dir,
                                      package_items=self.get_package_pages(),
                                      pages=p)

        self.generate_sitemap_indexes(sm_urls=sm_urls)
        self.generate_manpage_index()
        self.generate_base_index()

        self.fix_missing_links()

    @classmethod
    def clean_directory(cls):
        import shutil
        shutil.rmtree(base_manpage_dir, ignore_errors=True)
        shutil.rmtree(base_packages_dir, ignore_errors=True)

    @classmethod
    def generate_manpage_index(cls):
        # Generate man-pages index
        base_tpl = load_template('base')
        index_tpl = load_template('index-manpage')

        index = base_tpl.safe_substitute(
            # FIXME: Naming templates should be better
            metadescription="Linux Man Pages",
            title="Linux Man Pages",
            canonical="",
            header="",
            breadcrumb="",
            content=index_tpl.substitute(), )

        f = open(os.path.join(base_manpage_dir, "index.html"), 'w')
        f.write(index)
        f.close()

    @classmethod
    def generate_base_index(cls):
        # Generate base index
        base_tpl = load_template('base')
        index_tpl = load_template('index-contents')

        index = base_tpl.safe_substitute(
            metadescription="Carta.tech: The home for open documentation",
            title="Carta.tech: The home for open documentation",
            canonical="",
            header="",
            breadcrumb="",
            content=index_tpl.substitute(), )

        f = open(os.path.join(root_html, "index.html"), 'w')
        f.write(index)
        f.close()

    @classmethod
    def generate_sitemap_indexes(cls, sm_urls):
        # Generate sitemap indexes
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

    @classmethod
    def get_section_url(cls, section):
        return base_manpage_url + "/" + section + "/"

    @classmethod
    def generate_package_indexes(cls, source_dir, package_items, pages):
        packages = set()
        for package in os.listdir(source_dir):
            if os.path.isdir(os.path.join(source_dir,
                                          package)) and package != "man-pages":
                packages.add(package)

        empty_packages = set()
        for package in packages:
            if not package_items[package]:
                empty_packages.add(package)

        packages_to_index = []
        packages = sorted(packages.difference(empty_packages))
        for i, package in enumerate(packages):
            package_directory = os.path.join(base_packages_dir, package)
            try:
                os.makedirs(package_directory)
            except OSError:
                pass

            pages_in_package = package_items[package]
            section_pages = defaultdict(set)
            for page in pages_in_package:
                section_pages[pages[page]['section']].add(page)

            item_tpl = load_template('package-index-item')
            package_index_tpl = load_template('package-index')
            package_index_section_tpl = load_template('package-index-section')
            package_index_contents_tpl = load_template(
                'package-index-contents')

            package_index = []
            for section in sorted(section_pages):
                pages_in_section = section_pages[section]

                if not pages_in_section:
                    continue

                numeric_section, section = section, "man%s" % (section, )
                base_dir = "/man-pages/%s/" % section

                package_list = [
                    item_tpl.substitute(link=base_dir + page + ".html",
                                        name=page,
                                        description=pages[page]['subtitle'])
                    for page in pages_in_section
                ]

                amount_of_pages_in_section = len(pages_in_section)
                package_index.append(package_index_section_tpl.substitute(
                    amount=amount_of_pages_in_section,
                    numeric_section=numeric_section,
                    section=SECTIONS[section],
                    section_url=cls.get_section_url(section),
                    content=package_index_tpl.substitute(items='\n'.join(
                        package_list))))

            prev_page = next_page = None

            if i > 0:
                prev_page = ("../%s/" % (packages[i - 1], ), packages[i - 1])

            if i < len(packages) - 1:
                next_page = ("../%s/" % (packages[i + 1], ), packages[i + 1])

            contents = package_index_contents_tpl.substitute(
                contents="\n".join(package_index)) + get_pagination(prev_page,
                                                                    next_page)

            breadcrumb = [
                ("/packages/", "Packages"),
                ("/packages/%s/" % package, package),
            ]

            out = load_template('base').safe_substitute(
                title="Man Pages in %s" % package,
                canonical="",
                header=load_template('header-package').substitute(
                    title=package),
                breadcrumb=get_breadcrumb(breadcrumb),
                content=contents,
                metadescription="Man Pages in %s" % package, )

            package_index_file = os.path.join(package_directory, "index.html")

            f = open(package_index_file, 'w')
            f.write(out)
            f.close()

            packages_to_index.append(package)

        if not packages_to_index:
            return

        sm_item_tpl = load_template('sitemap-url-nolastmod')
        package_list_item_tpl = load_template('package-list-item')

        sm_urls = []
        package_list_items = []
        for package in packages_to_index:
            sm_urls.append(sm_item_tpl.substitute(url="%s/%s/" % (
                base_packages_url, package)))
            package_list_items.append(package_list_item_tpl.substitute(
                url="%s/" % (package, ),
                package=package))

        # Generate package sitemap
        sitemap = load_template('sitemap').substitute(
            urlset="\n".join(sm_urls))
        sitemap_path = os.path.join(base_packages_dir, "sitemap.xml")

        f = open(sitemap_path, 'w')
        f.write(sitemap)
        f.close()

        # Generate package index
        breadcrumb = [("/packages/", "Packages"), ]

        index = load_template('ul').substitute(
            content="\n".join(package_list_items))
        index_path = os.path.join(base_packages_dir, "index.html")

        out = load_template('base').safe_substitute(
            title="Packages with man pages",
            canonical="",
            header=load_template('header-package-index').substitute(
                title="Packages with man pages"),
            breadcrumb=get_breadcrumb(breadcrumb),
            content=index,
            metadescription="List of packages with man pages", )

        f = open(index_path, 'w')
        f.write(out)
        f.close()

    @classmethod
    def generate_sitemaps_and_indexes(cls, iterator, pages):
        # Generate directory Indexes & Sitemaps
        sm_urls = []
        last_update = None
        for directory, page_files in iterator:
            logging.debug(" * Generating indexes and sitemaps for %s" %
                          directory)

            section_item_tpl = load_template('section-index-item')
            sm_item_tpl = load_template('sitemap-url')

            section_items, sitemap_items = ("", "")
            for page in sorted(page_files):
                d = pages[page]
                lastmod = d['last-modified']
                if d['package'] == "man-pages":
                    section_items += load_template(
                        'section-index-item-manpage').substitute(
                            link=page,
                            name=d['name'],
                            section=d['section'],
                            description=d['subtitle'],
                            package=d['package'], )
                else:
                    section_items += section_item_tpl.substitute(
                        link=page,
                        name=d['name'],
                        section=d['section'],
                        description=d['subtitle'],
                        package=d['package'], )

                sitemap_items += sm_item_tpl.substitute(url=d['page-url'],
                                                        lastmod=lastmod)

                if not last_update:
                    last_update = lastmod
                else:
                    last_update = max(lastmod, last_update)
            else:
                if not last_update:
                    last_update = cls.now

                sitemap_items += sm_item_tpl.substitute(
                    url=cls.get_section_url(directory),
                    lastmod=last_update)

            section_content = load_template('section-index').substitute(
                items=section_items)
            sitemap = load_template('sitemap').substitute(urlset=sitemap_items)

            sitemap_path = os.path.join(base_manpage_dir, directory,
                                        "sitemap.xml")
            f = open(sitemap_path, 'w')
            f.write(sitemap)
            f.close()

            sm_urls.append(cls.get_section_url(directory) + "sitemap.xml")

            full_section = SECTIONS[directory]
            numeric_section = directory[3:]

            breadcrumb = [
                ("/man-pages/", "Man Pages"),
                ("/man-pages/man%s/" % numeric_section, full_section),
            ]

            out = load_template('base').safe_substitute(
                title="Linux Man Pages - %s" % full_section,
                canonical="",
                header=load_template('header').safe_substitute(
                    title=full_section,
                    section=numeric_section,
                    subtitle=""),
                breadcrumb=get_breadcrumb(breadcrumb),
                content=section_content,
                metadescription=full_section.replace("\"", "\'"), )

            f = open(
                os.path.join(base_manpage_dir, directory, 'index.html'), 'w')
            f.write(out)
            f.close()

        return sm_urls

    def write_pages(self):
        # Write pages
        try:
            page_hashes_file = open('page_hashes.dat', 'rb')
            page_hashes = marshal.load(page_hashes_file)
            page_hashes_file.close()
        except:
            page_hashes = dict()

        found_pages = self.get_pages_without_errors()
        for mp, final_page, instance in self.get_pages():
            out = mp.html(pages_to_link=found_pages)
            self.missing_links.update(mp.broken_links)
            self.section_counters.update(mp.section_counters)
            if (final_page in page_hashes
                ) and mp.unique_hash == page_hashes[final_page][0]:
                # Has not changed
                pass
            else:
                # Has changed
                page_hashes[final_page] = (mp.unique_hash, self.now)

            file = open(final_page, "w")
            file.write(out)
            file.close()

            instance['last-modified'] = page_hashes[final_page][1]

        page_hashes_file = open('page_hashes.dat', 'wb')
        marshal.dump(page_hashes, page_hashes_file)
        page_hashes_file.close()

    @classmethod
    def set_previous_next_links(cls, iterator, pages):
        # Calculate previous-next links
        for directory, page_files in iterator:
            man_directory = os.path.join(base_manpage_dir, directory)
            try:
                os.makedirs(man_directory)
            except OSError:
                pass

            previous = None
            for page in sorted(page_files):
                d = pages[page]
                d['final-page'] = os.path.join(man_directory, page) + ".html"
                logging.debug(" * Writing page: %s" % page)
                if previous:
                    d['instance'].set_previous(previous[1])
                    next_page = ("%s.html" % (page, ),
                                 "%s: %s" % (page,
                                             d['subtitle'], ))
                    pages[previous[0]]['instance'].set_next(next_page)

                previous = (page, ("%s.html" % (page, ),
                                   "%s: %s" % (page,
                                               d['subtitle'], )))

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

    def get_section_counters(self):
        return self.section_counters.most_common(self.number_section_counters)

    def get_missing_parsers(self):
        return self.missing_parsers.most_common(self.number_missing_parsers)


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
    parser.add_argument("--section-counters",
                        help="choose the amount of section titles to display",
                        type=int)
    args = parser.parse_args()

    if args.log_level:
        log_level = getattr(logging, args.log_level.upper())
        logging.basicConfig(level=log_level)

    parser = ManDirectoryParser(source_dir=args.source_dir)

    if args.missing_links:
        parser.number_missing_links = args.missing_links

    if args.section_counters:
        parser.number_section_counters = args.missing_links

    if args.missing_parsers:
        parser.number_missing_parsers = args.missing_parsers

    parser.parse_directory()

    print "Missing Links: %s" % parser.get_missing_links()
    print "Missing Parsers: %s" % parser.get_missing_parsers()
    print "Pages With Missing Parsers", parser.get_pages_with_missing_parsers()
    print "Section Counter", parser.get_section_counters()

    elapsed = time.time() - start_time
    logging.info("--- Total time: %s seconds ---" % (elapsed, ))
