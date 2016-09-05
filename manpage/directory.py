import glob
import shutil
import logging
import os.path
import sqlite3
import datetime
from cached_property import cached_property
from collections import Counter, defaultdict
from PIL import Image, ImageDraw, ImageFont
from textwrap import wrap

from helpers import pjoin, dname, bname
from helpers import SECTIONS
from helpers import load_template, get_breadcrumb

from parser import ManpageParser
from parser import NotSupportedFormat, UnexpectedMacro, RedirectedPage

from manpage import AvailablePages, AvailableSections

package_directory = dname(os.path.abspath(__file__))


class DirectoryIterator(object):
    def __init__(self, iterator):
        self.items = [(file, None) for file in iterator]
        self.current = 0
        self.high = len(self.items)
        self.extra_items = []

    def __iter__(self):
        return self

    def __next__(self):  # Compatibility with python 3
        return self.next()

    def next(self):
        if self.extra_items:
            return self.extra_items.pop(0)

        if self.current == self.high:
            raise StopIteration
        else:
            self.current += 1
            return self.items[self.current - 1]

    def add_item(self, file, redirection):
        self.extra_items.append((file, redirection))


class ManDirectoryParser(object):
    """docstring for ManDirectoryParser"""

    now = datetime.datetime.today().strftime('%Y-%m-%d')

    def __init__(self, database):
        self.conn = sqlite3.connect(
            pjoin(package_directory, "..", database), isolation_level=None)
        self.conn.text_factory = str
        self.cursor = self.conn.cursor()

        self.pages = dict()

        self.missing_parsers = Counter()

    @property
    def missing_links(self):
        return AvailablePages.unavailable

    @property
    def section_counters(self):
        return AvailableSections.titles

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

        iterator = DirectoryIterator(glob.iglob("%s/*/*.*" % source_dir))

        for page_file, redirected_from in iterator:
            print(page_file)
            logging.debug("Processing man page %s ...", page_file)
            try:
                parser = ManpageParser(page_file)
                manpage = parser.process()
            except NotSupportedFormat:
                logging.info("Skipping %s, not supported format...", page_file)
                continue
            except RedirectedPage as e:
                redirect_to = e.redirect
                logging.info("Page %s, has a redirection to %s...", page_file,
                             redirect_to)

                parent_dirs = redirect_to.count('/')
                base_dir = dname(page_file)
                while parent_dirs:
                    base_dir = dname(base_dir)
                    parent_dirs -= 1

                redirection_full_path = pjoin(base_dir, redirect_to)

                if not redirected_from:
                    original_file = page_file
                else:
                    original_file = redirected_from

                iterator.add_item(redirection_full_path, original_file)
                continue
            except IOError:
                logging.info("Skipping %s, file (%s) does not exist",
                             redirected_from, page_file)
                continue
            except UnexpectedMacro as e:
                macro = str(e).split('(', 1)[1].split(')', 1)[0]
                logging.info("Skipping %s, missing macro (%s)", page_file,
                             macro)
                self.missing_parsers[macro] += 1
                continue

            if not redirected_from:
                name, section = manpage.name, manpage.section
            else:
                name, ext = os.path.splitext(bname(redirected_from))
                section = ext[1:]

            package = bname(dname(page_file))

            self.conn.execute(
                "INSERT INTO manpages (package, name, section, subtitle, file) VALUES (?, ?, ?, ?, ?)",
                (package, name, section, manpage.title, page_file))

            logging.debug("Man page %s processed correctly...", page_file)

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
                          group_concat(package) as packages,
                          file
                   FROM manpages
                   GROUP by name, section
                   ORDER by section ASC, name ASC"""

        pages = []
        current_section = None
        for name, section, amount, packages, file in self.conn.execute(query):
            first_page_in_section = (section != current_section)
            if first_page_in_section:
                current_section = section
                prev_page = None

            parent_dir = "man%s" % section

            page_dict = {
                "name": name,
                "section": section,
                "parent_dir": parent_dir,
                "file": file
            }

            if amount > 1:
                # Aliases needed
                packages = packages.split(',')
                for package in packages:
                    package_dict = page_dict.copy()
                    package_dict['package'] = package
                    package_dict['prefix'] = package

                    current_page = self.get_pagination_link(
                        package, name, section, aliases=True)

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
                   file,
                   prefix=None,
                   prev_page=None,
                   next_page=None):
        filename = "%s.%s.html" % (name, section)

        logging.info("Creating manpage %s.%s", name, section)

        if prefix:
            filename = "%s-%s" % (prefix, filename)

        full_path = pjoin(self.manpages_dir, parent_dir, filename)

        mp = ManpageParser(file).process()
        mp.package = package
        mp.prev_page = prev_page
        mp.next_page = next_page
        mp.url = "https://www.carta.tech/man-pages/man%s/%s" % (section,
                                                                filename, )
        AvailablePages.pages = self.available_pages

        logging.debug("Writing %s" % full_path)
        f = open(full_path, 'w')
        f.write(mp.html())
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
            urls.append(
                sm_item_tpl.substitute(url="%s/%s/" % (self.manpages_url,
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
            for section, pages in sorted(sections.items()):
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

                    items.append(
                        item_tpl.substitute(
                            name=name, description=subtitle,
                            link=relative_url))

                package_index.append(
                    package_index_section_tpl.substitute(
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

            out = load_template('base').substitute(
                title="Man Pages in %s" % package,
                canonical="",
                extraheaders="",
                header=load_template('header-package').substitute(
                    title=package),
                breadcrumb=get_breadcrumb(breadcrumb),
                content=contents,
                metadescription="Man Pages in %s" % package, )

            f = open(pjoin(package_directory, "index.html"), 'w')
            f.write(out)
            f.close()

            package_list_items.append(
                package_list_item_tpl.substitute(
                    url="%s/" % (package, ), package=package))

            sitemap_urls.append(
                sm_item_tpl.substitute(url="%s/%s/" % (self.packages_url,
                                                       package)))

        f = open(pjoin(self.packages_dir, "sitemap.xml"), 'w')
        f.write(
            load_template('sitemap').substitute(urlset="\n".join(
                sitemap_urls)))
        f.close()

        # Generate package index
        breadcrumb = [("/packages/", "Packages"), ]

        index = load_template('ul').substitute(
            content="\n".join(package_list_items))
        index_path = pjoin(self.packages_dir, "index.html")

        out = load_template('base').substitute(
            title="Packages with man pages",
            canonical="",
            extraheaders="",
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
                        items[section].append(
                            section_item_tpl.substitute(
                                link=page,
                                name=name,
                                section=section,
                                description=subtitle,
                                package=package))

            else:
                subtitle = self.subtitles[(packages, name, section)]

                if packages == "man-pages":
                    items[section].append(
                        section_item_manpage_tpl.substitute(
                            link=page,
                            name=name,
                            section=section,
                            description=subtitle,
                            package=packages))
                else:
                    items[section].append(
                        section_item_tpl.substitute(
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

            out = load_template('base').substitute(
                title="Linux Man Pages - %s" % section_description,
                canonical="",
                extraheaders="",
                header=load_template('header').substitute(
                    title=section_description, section=section, subtitle=""),
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

        index = base_tpl.substitute(
            metadescription="Linux Man Pages",
            title="Linux Man Pages",
            canonical="",
            extraheaders="",
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

        index = base_tpl.substitute(
            metadescription="Carta.tech: The home for open documentation",
            title="Carta.tech: The home for open documentation",
            canonical="",
            extraheaders="",
            header="",
            breadcrumb="",
            content=index_tpl.substitute(), )

        f = open(pjoin(self.root_html, "index.html"), 'w')
        f.write(index)
        f.close()

    def generate_images(self, output_dir):
        images_dir = pjoin(output_dir, "images")

        shutil.rmtree(images_dir, ignore_errors=True)
        ManDirectoryParser.makedirs(images_dir)

        for (package, name,
             section), description in self.subtitles.iteritems():

            filename = "%s-%s-%s.png" % (package,
                                         name,
                                         section, )
            ManDirectoryParser.write_image(
                pjoin(images_dir, filename), name, section, description)

    @staticmethod
    def write_image(filename, name, section, description):
        if not description:
            description = ""
        else:
            description = '\n'.join(wrap(description, 46))

        title = wrap( "%s (%s)" % (name, section,), 24)[0]

        base = Image.open('imaging/base-image.png').convert('RGBA')
        txt = Image.new('RGBA', base.size, (255,255,255,0))

        # get a font
        fnt = ImageFont.truetype('imaging/FiraMono-Medium.ttf', 36)
        fnt2 = ImageFont.truetype('imaging/FiraMono-Medium.ttf', 18)

        d = ImageDraw.Draw(txt)
        d.text((30,30), title, font=fnt, fill=(173,52,62,255))
        d.text((30,100), description, font=fnt2, fill=(0,0,0,255))

        out = Image.alpha_composite(base, txt)
        out.save(filename)

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
