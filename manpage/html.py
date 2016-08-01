from cached_property import cached_property
from helpers import load_template, get_breadcrumb, linkifier, get_pagination
from helpers import SECTIONS


class ManPageHTML(object):
    """docstring for Manpage"""

    def __init__(self, name, section, subtitle, sections):
        self.name = name
        self.section = section
        self._subtitle = subtitle
        self._sections = sections

    @property
    def subtitle(self):
        return self._subtitle

    @property
    def sections(self):
        return self._sections

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

    @property
    def contents(self):
        return self.section_contents

    def get(self):
        return load_template('base').substitute(breadcrumb=self.breadcrumbs,
                                                title=self.descriptive_title,
                                                metadescription=self.subtitle,
                                                header=self.page_header,
                                                content=self.contents, )


class ManPageHTMLDB(ManPageHTML):
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

    @cached_property
    def subtitle(self):
        return self.subtitles[(self.package, self.name, self.section)]

    @property
    def page_id(self):
        return (self.package, self.name, self.section)

    @cached_property
    def pager_contents(self):
        pager = get_pagination(self.prev_page, self.next_page)
        if not pager:
            return ""
        else:
            return pager

    @property
    def contents(self):
        return self.linkified_contents + self.pager_contents

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
