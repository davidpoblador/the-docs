#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import glob
import shutil
import marshal
import logging
import sqlite3
import datetime

from cached_property import cached_property
from collections import defaultdict, Counter

from manpage import ManPage, linkifier

from base import load_template, get_pagination, get_breadcrumb
from base import MissingParser, NotSupportedFormat, RedirectedPage, UnexpectedState

pjoin = os.path.join
dname = os.path.dirname
bname = os.path.basename

package_directory = dname(os.path.abspath(__file__))

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
}


class ManPageHTML(object):
    """docstring for Manpage"""

    def __init__(self, database_connection, available_pages, subtitles,
                 package, name, section, prev_page, next_page):
        self.conn = database_connection
        self.available_pages = available_pages
        self.subtitles = subtitles
        self.name = name
        self.section = section
        self.package = package
        self.prev_page = prev_page
        self.next_page = next_page

    @property
    def page_id(self):
        return (self.package, self.name, self.section)

    @cached_property
    def subtitle(self):
        return self.subtitles[(self.package, self.name, self.section)]

    @cached_property
    def sections(self):
        query = """SELECT title,
                          content
                   FROM manpage_sections
                   WHERE package = ?
                     AND name = ?
                     AND section = ?
                   ORDER BY position ASC"""

        return [(title, content)
                for title, content in self.conn.execute(query, self.page_id)]

    @cached_property
    def section_contents(self):
        section_tpl = load_template('section')

        see_also = None

        contents = []
        for title, content in self.sections:
            if title == "SEE ALSO":
                new_title = "RELATED TO %s&hellip;" % self.name
                see_also = section_tpl.substitute(title=new_title,
                                                  content=content)
            else:
                contents.append(section_tpl.substitute(title=title,
                                                       content=content))

        else:
            if see_also:
                contents.append(see_also + '\n')

        return ''.join(contents)

    @cached_property
    def linkified_contents(self):
        def repl(m):
            manpage = m.groupdict()['page']
            section = m.groupdict()['section']
            page = '.'.join([manpage, section])

            out = "<strong>%s</strong>(%s)" % (manpage,
                                               section, )

            if page in self.available_pages:
                out = "<a href=\"../man%s/%s.%s.html\">%s</a>" % (section,
                                                                  manpage,
                                                                  section,
                                                                  out, )
            else:
                # FIXME: Figure out what to do with missing links
                # self.broken_links.add(page)
                pass

            return out

        if self.available_pages:
            return linkifier.sub(repl, self.section_contents)
        else:
            return self.section_contents

    @property
    def breadcrumbs(self):
        breadcrumb_sections = [
            ("/man-pages/", "Man Pages"),
            ("/man-pages/man%s/" % self.section, self.section_description),
            ("/man-pages/man%s/%s.%s.html" % (self.section,
                                              self.name,
                                              self.section, ),
             self.descriptive_title),
        ]

        breadcrumbs = [get_breadcrumb(breadcrumb_sections)]

        if self.package:
            breadcrumb_packages = [
                ("/packages/", "Packages"),
                ("/packages/%s/" % self.package, self.package),
                ("/man-pages/man%s/%s.%s.html" %
                 (self.section, self.name, self.section),
                 self.descriptive_title),
            ]

            breadcrumbs.append(get_breadcrumb(breadcrumb_packages))

        return '\n'.join(breadcrumbs)

    @cached_property
    def descriptive_title(self):
        return "%s: %s" % (self.name,
                           self.subtitle, )

    @property
    def page_header(self):
        return load_template('header').substitute(section=self.section,
                                                  title=self.name,
                                                  subtitle=self.subtitle, )

    @cached_property
    def full_section(self):
        return "man%s" % self.section

    @cached_property
    def section_description(self):
        return SECTIONS[self.full_section]

    @cached_property
    def pager_contents(self):
        pager = get_pagination(self.prev_page, self.next_page)
        if not pager:
            return ""
        else:
            return pager

    def get(self):
        return load_template('base').substitute(
            breadcrumb=self.breadcrumbs,
            title=self.descriptive_title,
            metadescription=self.subtitle,
            header=self.page_header,
            content=self.linkified_contents + self.pager_contents, )


class ManDirectoryParser(object):
    """docstring for ManDirectoryParser"""

    now = datetime.datetime.today().strftime('%Y-%m-%d')

    def __init__(self, database):
        self.conn = sqlite3.connect(
            pjoin(package_directory, database),
            isolation_level=None)
        self.conn.text_factory = str
        self.cursor = self.conn.cursor()

        self.pages = dict()

        self.missing_parsers = Counter()
        self.missing_links = Counter()
        self.section_counters = Counter()

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

    def parse_directory(self, source_dir):
        self.conn.execute("DELETE FROM manpages")
        self.conn.execute("DELETE FROM manpage_sections")

        for page_file in glob.iglob("%s/*/man?/*.?" % source_dir):
            logging.debug("Processing man page %s ..." % page_file)
            manpage = ManPage(page_file)
            try:
                manpage.parse()
            except MissingParser as e:
                macro = str(e).split(" ", 2)[1]
                logging.warning(" * Missing Parser (%s): %s" % (macro,
                                                                page_file, ))
                self.missing_parsers[macro] += 1
                continue
            except NotSupportedFormat:
                logging.warning(" * Not supported format: %s" % page_file)
                continue
            except IOError:
                logging.warning(" * IOError: %s" % page_file)
                continue
            except:
                raise

            self.conn.execute(
                "INSERT INTO manpages (package, name, section, subtitle) VALUES (?, ?, ?, ?)",
                (manpage.package, manpage.name, manpage.section,
                 manpage.subtitle))

            for i, (title, contents) in enumerate(manpage.get_sections()):
                self.conn.execute(
                    "INSERT INTO manpage_sections (package, name, section, position, title, content) VALUES (?, ?, ?, ?, ?, ?)",
                    (manpage.package, manpage.name, manpage.section, i, title,
                     contents))

    def empty_output_directories(self):
        shutil.rmtree(self.manpages_dir, ignore_errors=True)
        shutil.rmtree(self.packages_dir, ignore_errors=True)

    def create_output_directories(self):
        # Create man page directories
        map(ManDirectoryParser.makedirs,
            [pjoin(self.manpages_dir, directory) for directory in SECTIONS])

    @staticmethod
    def makedirs(directory):
        try:
            os.makedirs(directory)
        except OSError:
            pass

    def get_pagination_link(self, package, name, section, aliases=False):
        basefile = "%s.%s.html" % (name, section)
        if aliases:
            basefile = "%s-%s" % (package, basefile)

        link_text = "%s.%s: %s" % (name, section,
                                   self.subtitles[(package, name, section)])

        return (basefile, link_text)

    def create_manpages(self):
        query = """SELECT name,
                          section,
                          count(package) as amount,
                          group_concat(package) as packages
                   FROM manpages
                   GROUP by name, section
                   ORDER by section ASC, name ASC"""

        pages = []
        current_section = None
        for name, section, amount, packages in self.conn.execute(query):
            first_page_in_section = (section != current_section)
            if first_page_in_section:
                current_section = section
                prev_page = None

            parent_dir = "man%s" % section

            page_dict = {
                "name": name,
                "section": section,
                "parent_dir": parent_dir,
            }

            if amount > 1:
                # Aliases needed
                packages = packages.split(',')
                for package in packages:
                    package_dict = page_dict.copy()
                    package_dict['package'] = package
                    package_dict['prefix'] = package

                    current_page = self.get_pagination_link(package,
                                                            name,
                                                            section,
                                                            aliases=True)

                    if prev_page:
                        package_dict['prev_page'] = prev_page
                        pages[-1]['next_page'] = current_page

                    prev_page = current_page

                    pages.append(package_dict)

                # FIXME Create aliases page
                self.write_aliases_page(name, section, parent_dir, packages)

            else:
                page_dict['package'] = packages

                current_page = self.get_pagination_link(packages, name,
                                                        section)

                if prev_page:
                    page_dict['prev_page'] = prev_page
                    pages[-1]['next_page'] = current_page

                prev_page = current_page

                pages.append(page_dict)

        return map(lambda page: self.write_page(**page), pages)

    def write_page(self,
                   package,
                   name,
                   section,
                   parent_dir,
                   prefix=None,
                   prev_page=None,
                   next_page=None):
        filename = "%s.%s.html" % (name, section)

        if prefix:
            filename = "%s-%s" % (prefix, filename)

        full_path = pjoin(self.manpages_dir, parent_dir, filename)

        mp = ManPageHTML(self.conn, self.available_pages, self.subtitles,
                         package, name, section, prev_page, next_page)

        logging.debug("Writing %s" % full_path)
        f = open(full_path, 'w')
        f.write(mp.get())
        f.close()

        return ("man%s" % section, filename)

    def write_aliases_page(self, name, section, parent_dir, packages):
        filename = "%s.%s.html" % (name, section)
        full_path = pjoin(self.manpages_dir, parent_dir, filename)

        f = open(full_path, 'w')
        f.write(' ')
        f.close()

        return full_path

    @cached_property
    def available_pages(self):
        query = "SELECT DISTINCT name, section FROM manpages"
        return set(["%s.%s" % (name, section)
                    for name, section in self.conn.execute(query)])

    @cached_property
    def subtitles(self):
        query = "SELECT package, name, section, subtitle FROM manpages"
        return {
            (package, name, section): subtitle
            for package, name, section, subtitle in self.conn.execute(query)
        }

    def generate_manpage_sitemaps(self, manpage_list):
        pages_in_section = defaultdict(set)
        for section, page in manpage_list:
            pages_in_section[section].add(page)

        sm_item_tpl = load_template('sitemap-url-nolastmod')

        sitemap_urls = []
        for section in SECTIONS:
            urls = [sm_item_tpl.substitute(url="%s/%s/%s" %
                                           (self.manpages_url, section, page))
                    for page in pages_in_section[section]]
            urls.append(sm_item_tpl.substitute(url="%s/%s/" % (
                self.manpages_url,
                section, )))
            sitemap = load_template('sitemap').substitute(
                urlset="\n".join(urls))
            rel_sitemap_path = pjoin(section, "sitemap.xml")

            f = open(pjoin(self.manpages_dir, rel_sitemap_path), 'w')
            f.write(sitemap)
            f.close()

            sitemap_urls.append("%s/%s" %
                                (self.manpages_url, rel_sitemap_path))

        return sitemap_urls

    def generate_manpage_sitemap_index(self, urls):
        sitemap_index_url_tpl = load_template('sitemap-index-url')
        urls = [sitemap_index_url_tpl.substitute(url=url) for url in urls]
        content = load_template('sitemap-index').substitute(
            sitemaps=''.join(urls))

        f = open(pjoin(self.manpages_dir, "sitemap.xml"), 'w')
        f.write(content)
        f.close()

    def generate_package_indexes(self):
        item_tpl = load_template('package-index-item')
        package_index_tpl = load_template('package-index')
        package_index_section_tpl = load_template('package-index-section')
        package_index_contents_tpl = load_template('package-index-contents')
        package_list_item_tpl = load_template('package-list-item')
        sm_item_tpl = load_template('sitemap-url-nolastmod')

        query = """SELECT name,
                          section,
                          count(package) as amount,
                          group_concat(package) as packages
                   FROM manpages
                   GROUP by name, section
                   ORDER by package ASC, section ASC, name ASC"""

        package_container = defaultdict(lambda: defaultdict(list))

        for name, section, amount, packages in self.conn.execute(query):
            if amount > 1:
                for package in packages.split(','):
                    subtitle = self.subtitles[(package, name, section)]
                    package_container[package][section].append(
                        ("%s.%s" % (name, section), subtitle, True))

            else:
                subtitle = self.subtitles[(packages, name, section)]
                package_container[packages][section].append(
                    ("%s.%s" % (name, section), subtitle, False))

        package_list_items = []
        sitemap_urls = []
        for package, sections in package_container.items():
            package_directory = pjoin(self.packages_dir, package)
            self.makedirs(package_directory)

            package_index = []
            for section, pages in sections.items():
                full_section = "man%s" % (section, )
                section_description = SECTIONS[full_section]
                section_directory = pjoin(package_directory, full_section)
                section_relative_url = pjoin(self.manpages_dir_name,
                                             full_section)
                section_url = self.manpages_url + "/" + full_section + "/"

                self.makedirs(section_directory)
                items = []
                for name, subtitle, aliased in pages:
                    filename = "%s.html" % (name, )
                    if aliased:
                        filename = "%s-%s" % (package,
                                              filename, )

                    relative_url = "/" + pjoin(section_relative_url, filename)

                    items.append(item_tpl.substitute(name=name,
                                                     description=subtitle,
                                                     link=relative_url))

                package_index.append(package_index_section_tpl.substitute(
                    amount=len(pages),
                    numeric_section=section,
                    section=section_description,
                    section_url=section_url,
                    content=package_index_tpl.substitute(items='\n'.join(
                        items))))

            contents = package_index_contents_tpl.substitute(
                contents="\n".join(package_index))

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

            f = open(pjoin(package_directory, "index.html"), 'w')
            f.write(out)
            f.close()

            package_list_items.append(package_list_item_tpl.substitute(
                url="%s/" % (package, ),
                package=package))

            sitemap_urls.append(sm_item_tpl.substitute(url="%s/%s/" % (
                self.packages_url, package)))

        f = open(pjoin(self.packages_dir, "sitemap.xml"), 'w')
        f.write(load_template('sitemap').substitute(urlset="\n".join(
            sitemap_urls)))
        f.close()

        # Generate package index
        breadcrumb = [("/packages/", "Packages"), ]

        index = load_template('ul').substitute(
            content="\n".join(package_list_items))
        index_path = pjoin(self.packages_dir, "index.html")

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

    def generate_manpage_indexes(self):
        query = """SELECT name,
                          section,
                          count(package) as amount,
                          group_concat(package) as packages
                   FROM manpages
                   GROUP by name, section
                   ORDER by section ASC, name ASC"""

        section_item_tpl = load_template('section-index-item')
        section_item_manpage_tpl = load_template('section-index-item-manpage')
        items = defaultdict(list)
        for name, section, amount, packages in self.conn.execute(query):
            page = "%s.%s" % (name, section)
            if amount > 1:
                for package in packages.split(','):
                    subtitle = self.subtitles[(package, name, section)]

                    if package == "man-pages":
                        items[section].append(
                            section_item_manpage_tpl.substitute(
                                link=page,
                                name=name,
                                section=section,
                                description=subtitle,
                                package=package))
                    else:
                        items[section].append(section_item_tpl.substitute(
                            link=page,
                            name=name,
                            section=section,
                            description=subtitle,
                            package=package))

            else:
                subtitle = self.subtitles[(packages, name, section)]

                if packages == "man-pages":
                    items[section].append(section_item_manpage_tpl.substitute(
                        link=page,
                        name=name,
                        section=section,
                        description=subtitle,
                        package=packages))
                else:
                    items[section].append(section_item_tpl.substitute(
                        link=page,
                        name=name,
                        section=section,
                        description=subtitle,
                        package=packages))

        for section in items:
            section_content = load_template('section-index').substitute(
                items=''.join(items[section]))

            section_description = SECTIONS["man%s" % section]

            breadcrumb = [
                ("/man-pages/", "Man Pages"),
                ("/man-pages/man%s/" % section, section_description),
            ]

            out = load_template('base').safe_substitute(
                title="Linux Man Pages - %s" % section_description,
                canonical="",
                header=load_template('header').safe_substitute(
                    title=section_description,
                    section=section,
                    subtitle=""),
                breadcrumb=get_breadcrumb(breadcrumb),
                content=section_content,
                metadescription=section_description.replace("\"", "\'"), )

            f = open(
                pjoin(self.manpages_dir, "man%s" % section, 'index.html'), 'w')
            f.write(out)
            f.close()

    def generate_manpage_index(self):
        # Generate man-pages index
        base_tpl = load_template('base')
        index_tpl = load_template('index-manpage')

        index = base_tpl.safe_substitute(metadescription="Linux Man Pages",
                                         title="Linux Man Pages",
                                         canonical="",
                                         header="",
                                         breadcrumb="",
                                         content=index_tpl.substitute(), )

        f = open(pjoin(self.manpages_dir, "index.html"), 'w')
        f.write(index)
        f.close()

    def generate_base_index(self):
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

        f = open(pjoin(self.root_html, "index.html"), 'w')
        f.write(index)
        f.close()

    def generate_output(self, output_dir, base_url):
        self.root_html = output_dir

        self.manpages_dir_name = "man-pages"
        self.packages_dir_name = "packages"

        self.manpages_dir = pjoin(output_dir, self.manpages_dir_name)
        self.packages_dir = pjoin(output_dir, self.packages_dir_name)
        self.manpages_url = base_url + "man-pages"
        self.packages_url = base_url + "packages"

        # Delete output directories
        self.empty_output_directories()

        # Create placeholder directories
        self.create_output_directories()

        # Create Manpages
        sitemap_manpages = self.create_manpages()

        # Generate sitemaps and indexes for manpages
        sitemap_manpage_urls = self.generate_manpage_sitemaps(sitemap_manpages)
        self.generate_manpage_sitemap_index(sitemap_manpage_urls)
        self.generate_manpage_indexes()
        self.generate_manpage_index()

        # Generate root index.html
        self.generate_base_index()

        # Generate package indexes
        self.generate_package_indexes()

        return

        #self.write_pages()
        #self.generate_sitemap_indexes(sm_urls=sm_urls)
        #self.fix_missing_links()

    @staticmethod
    def generate_sitemap_indexes(sm_urls):
        # Generate sitemap indexes
        sitemap_index_url_tpl = load_template('sitemap-index-url')
        sitemap_index_content = ""
        for sitemap_url in sm_urls:
            sitemap_index_content += sitemap_index_url_tpl.substitute(
                url=sitemap_url)

        sitemap_index_tpl = load_template('sitemap-index')
        sitemap_index_content = sitemap_index_tpl.substitute(
            sitemaps=sitemap_index_content)

        f = open(pjoin(base_manpage_dir, "sitemap.xml"), 'w')
        f.write(sitemap_index_content)
        f.close()

#   def fix_missing_links(self):
#       for page in self.get_pages_with_errors():
#           if page in self.missing_links:
#               del self.missing_links[page]

#       try:
#           ignore_page_file = open('ignore_page_file.dat', 'rb')
#           pages_to_ignore = marshal.load(ignore_page_file)
#           ignore_page_file.close()
#           for page in pages_to_ignore:
#               if page in self.missing_links:
#                   del self.missing_links[page]
#       except IOError:
#           pass

#   def get_missing_links(self):
#       return self.missing_links.most_common(self.number_missing_links)

#   def get_section_counters(self):
#       return self.section_counters.most_common(self.number_section_counters)

#   def get_missing_parsers(self):
#       return self.missing_parsers.most_common(self.number_missing_parsers)


def dirparse(args):
    parser = ManDirectoryParser(database=args.database)
    parser.parse_directory(source_dir=args.source_dir)


def generate(args):
    parser = ManDirectoryParser(database=args.database)
    parser.generate_output(output_dir=args.output_dir, base_url=args.base_url)


def stats(args):
    parser = ManDirectoryParser(database=args.database)
    # FIXME
    #parser.add_argument("--missing-links",
    #                    help="choose the amount of broken links to display",
    #                    type=int,
    #                    default=10)
    #parser.add_argument("--missing-parsers",
    #                    help="choose the amount of missing parsers to display",
    #                    type=int,
    #                    default=10)
    #parser.add_argument("--section-counters",
    #                    help="choose the amount of section titles to display",
    #                    type=int,
    #                    default=10)

    #parser.number_missing_links = args.missing_links
    #parser.number_section_counters = args.section_counters
    #parser.number_missing_parsers = args.missing_parsers
    #

    #print "Missing Links: %s" % parser.get_missing_links()
    #print "Missing Parsers: %s" % parser.get_missing_parsers()
    #print "Pages With Missing Parsers", parser.get_pages_with_missing_parsers()
    #print "Section Counter", parser.get_section_counters()
    pass


if __name__ == '__main__':
    import time
    import argparse
    start_time = time.time()

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--log-level", help="choose log level")
    parser.add_argument("--database",
                        help="the database you want to use",
                        default="manpages.db")
    subparsers = parser.add_subparsers()

    # dirparse option
    parser_dirparse = subparsers.add_parser(
        'dirparse',
        help='Parses directory into a database',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser_dirparse.add_argument(
        "source_dir",
        help="the directory you want to use as source")
    parser_dirparse.set_defaults(func=dirparse)

    # generate option
    parser_generate = subparsers.add_parser(
        'generate',
        help='Generates pages from database',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser_generate.add_argument("--base-url",
                                 help="Base URL",
                                 default="https://www.carta.tech/")

    parser_generate.add_argument(
        "output_dir",
        help="the directory you want to use as a destination")
    parser_generate.set_defaults(func=generate)

    # statistics
    parser_stats = subparsers.add_parser(
        'stats',
        help='Get statistics about the current parsing state',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser_stats.set_defaults(func=stats)

    # Parse arguments
    args = parser.parse_args()

    if args.log_level:
        log_level = getattr(logging, args.log_level.upper())
        logging.basicConfig(level=log_level)

    args.func(args)

    elapsed = time.time() - start_time
    logging.info("--- Total time: %s seconds ---" % (elapsed, ))
