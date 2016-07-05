#!/usr/bin/env python

from manpage import ManPage
from manpage import MissingParser
import glob
import os
from collections import defaultdict, Counter
from string import Template
from hashlib import md5
import marshal
import logging

package_directory = os.path.dirname(os.path.abspath(__file__))

root_html = os.path.join(package_directory, "public_html")
base_url = "https://www.carta.tech/"

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

    def __init__(self, source_dir):
        self.source_dir = source_dir
        self.number_missing_parsers = 10

        self.missing_links = Counter()
        self.number_missing_links = 10

        self.pages_with_missing_parsers = set()

    def parse_directory(self):
        list_of_manfiles = list(glob.iglob("%s/*/man?/*.?" % self.source_dir))
        base_src = "man-pages"
        list_of_manpages = dict()
        mandirpages = defaultdict(set)
        pages = defaultdict()

        manpage_parent_url = base_url + base_src

        missing_parsers = Counter()
        for manfile in list_of_manfiles:
            basename = os.path.basename(manfile)
            dstdir = os.path.dirname(manfile)
            manbasedir = os.path.basename(dstdir)
            package = os.path.split(os.path.split(dstdir)[0])[1]
            redirection_base_dir = os.path.split(dstdir)[0]

            logging.debug("Processing man page %s ..." % (manfile, ))
            try:
                manpage = ManPage(manfile, base_url=manpage_parent_url)
                g = manpage.parse()

                redirect, subtitle = next(g)

                while redirect:
                    redirection = get_redirection_file(
                        redirection_base_dir, redirect)
                    logging.debug(
                        " * Page %s has a redirection to %s..." %
                        (manfile, redirection))
                    manpage = ManPage(
                        redirection,
                        base_url=manpage_parent_url,
                        redirected_from=manfile)
                    g = manpage.parse()

                    redirect, subtitle = next(g)

            except MissingParser as e:
                mp = str(e).split(" ", 2)[1]
                self.pages_with_missing_parsers.add(os.path.basename(manfile))
                logging.warning(" * Missing Parser (%s): %s" % (mp, manfile, ))
                missing_parsers[mp] += 1
                continue
            except IOError:
                if redirect:
                    self.missing_links[redirect[0]] += 1
                    continue
                else:
                    raise
            except:
                logging.error(" * ERR: %s" % (manfile, ))
                continue

            mandirpages[manbasedir].add(basename)
            pages[basename] = (subtitle, manbasedir, package)

            list_of_manpages[basename] = [manpage, g]

        del(list_of_manfiles)

        try:
            checksum_file = open('checksums.dat', 'rb')
            checksums = marshal.load(checksum_file)
            checksum_file.close()
        except IOError:
            checksums = {}

        # Write and Linkify
        list_of_pages = set(pages.keys())
        for directory, page_files in list(mandirpages.items()):
            man_directory = os.path.join(root_html, base_src, directory)
            try:
                os.makedirs(man_directory)
            except OSError:
                pass

            previous = None
            pages_to_process = []
            for page_file in sorted(page_files):
                logging.debug(" * Writing page: %s" % page_file)

                try:
                    next(list_of_manpages[page_file][1])
                except StopIteration:
                    pass
                except MissingParser as e:
                    mp = str(e).split(" ", 2)[1]
                    self.pages_with_missing_parsers.add(
                        os.path.basename(page_file))
                    logging.warning(
                        " * Missing Parser (%s): %s" %
                        (mp, list_of_manpages[page_file][0].filename, ))
                    missing_parsers[mp] += 1
                    continue
                except:
                    logging.error(" * ERR: %s" %
                                  (list_of_manpages[page_file][0].filename, ))
                    continue

                if previous:
                    list_of_manpages[page_file][0].set_previous(
                        previous[0], previous[1])
                    list_of_manpages[previous[0]][0].set_next(
                        page_file, pages[page_file][0])

                previous = (page_file, pages[page_file][0])
                list_of_manpages[page_file][0].set_pages(list_of_pages)

                pages_to_process.append(page_file)

            for page_file in pages_to_process:
                final_page = os.path.join(man_directory, page_file) + ".html"
                out = list_of_manpages[page_file][0].html()
                self.missing_links.update(
                    list_of_manpages[page_file][0].broken_links)
                checksum = md5(out).hexdigest()

                if checksum != checksums.get(final_page, None):
                    checksums[final_page] = checksum
                    file = open(final_page, "w")
                    file.write(out)
                    file.close()

        checksum_file = open('checksums.dat', 'wb')
        marshal.dump(checksums, checksum_file)
        checksum_file.close()

        del(checksums)

        # Directory Indexes & Sitemaps
        sitemap_urls = []
        for directory, page_files in list(mandirpages.items()):
            logging.debug(
                " * Generating indexes and sitemaps for %s" %
                directory)

            section_item_tpl = load_template('section-index-item')
            sitemap_url_item_tpl = load_template('sitemap-url')

            section_items, sitemap_items = ("", "")
            for page_file in sorted(page_files):
                name, section = page_file.rsplit('.', 1)

                section_items += section_item_tpl.substitute(
                    link=page_file,
                    name=name,
                    section=section,
                    description=pages[page_file][0],
                    package=pages[page_file][2],
                )

                item_url = base_url + base_src + "/" + directory + "/" + name + "." + section + ".html"
                sitemap_items += sitemap_url_item_tpl.substitute(url=item_url)
            else:
                item_url = base_url + base_src + "/" + directory + "/"
                sitemap_items += sitemap_url_item_tpl.substitute(url=item_url)

            section_index_tpl = load_template('section-index')
            section_content = section_index_tpl.substitute(items=section_items)

            sitemap_tpl = load_template('sitemap')
            sitemap = sitemap_tpl.substitute(urlset=sitemap_items)

            sitemap_path = os.path.join(
                root_html, base_src, directory, "sitemap.xml")
            f = open(sitemap_path, 'w')
            f.write(sitemap)
            f.close()

            sitemap_url = base_url + base_src + "/" + directory + "/" + "sitemap.xml"
            sitemap_urls.append(sitemap_url)

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
                    base_url=manpage_parent_url,
                    section=numeric_section),
                content=section_content,
                metadescription=full_section.replace(
                    "\"",
                    "\'"),
            )

            f = open(
                os.path.join(
                    root_html,
                    base_src,
                    directory,
                    'index.html'),
                'w')
            f.write(out)
            f.close()

        sitemap_index_url_tpl = load_template('sitemap-index-url')
        sitemap_index_content = ""
        for sitemap_url in sitemap_urls:
            sitemap_index_content += sitemap_index_url_tpl.substitute(
                url=sitemap_url)

        sitemap_index_tpl = load_template('sitemap-index')
        sitemap_index_content = sitemap_index_tpl.substitute(
            sitemaps=sitemap_index_content)

        f = open("%s/sitemap.xml" % (os.path.join(root_html, base_src), ), 'w')
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
            content=index_tpl.substitute(),
        )

        f = open("%s/index.html" % (os.path.join(root_html, base_src), ), 'w')
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
            content=index_tpl.substitute(),
        )

        f = open("%s/index.html" % root_html, 'w')
        f.write(index)
        f.close()

        missing_parsers = ' '.join(
            ["%s:%s" % (k, v) for k, v in missing_parsers.most_common(
                self.number_missing_parsers)])

        logging.info("Top %s Missing Parsers: %s" %
                     (self.number_missing_parsers, missing_parsers))

        self.fix_missing_links()

    def fix_missing_links(self):
        for page in self.pages_with_missing_parsers:
            if page in self.missing_links:
                del self.missing_links[page]

    def get_missing_links(self):
        return self.missing_links.most_common(self.number_missing_links)


def get_redirection_file(src, manpage_redirect):
    return os.path.join(src, *manpage_redirect)


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
    parser.add_argument(
        "source_dir",
        help="the directory you want to use as source")
    parser.add_argument("--log-level", help="choose log level")
    parser.add_argument(
        "--missing-links",
        help="choose the amount of broken links to display",
        type=int)
    parser.add_argument(
        "--missing-parsers",
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
    print "DEBUG", parser.pages_with_missing_parsers

    elapsed = time.time() - start_time
    logging.info("--- Total time: %s seconds ---" % (elapsed, ))
