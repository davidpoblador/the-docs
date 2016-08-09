from helpers import load_template, get_breadcrumb, strip_tags, linkifier
from helpers import get_pagination, unescape
from cached_property import cached_property
from helpers import SECTIONS
from collections import Counter

try:
    import re2 as re
except ImportError:
    import re


def linkify(item):
    if not AvailablePages.pages:
        return item

    must_appear = {'(', ')'}
    if not all(x in item for x in must_appear):
        # Speed optimization
        return item

    def repl(m):
        manpage = m.groupdict()['page']
        section = m.groupdict()['section']

        page = '.'.join([manpage, section])

        pretag = m.groupdict()['pretag']
        posttag = m.groupdict()['posttag']

        if posttag and not pretag:
            append = posttag
        else:
            append = ""

        if page in AvailablePages.pages:
            out = "<strong>%s</strong>(%s)" % (manpage,
                                               section, )
            out = "<a href=\"../man%s/%s.%s.html\">%s</a>%s" % (section,
                                                                manpage,
                                                                section,
                                                                out,
                                                                append, )
        elif page.lower() in AvailablePages.pages:
            out = "<strong>%s</strong>(%s)" % (manpage,
                                               section, )
            out = "<a href=\"../man%s/%s.%s.html\">%s</a>%s" % (section,
                                                                manpage.lower(),
                                                                section,
                                                                out,
                                                                append, )
        else:
            out = "<strong>%s</strong>(%s)%s" % (manpage,
                                                 section,
                                                 append, )
            AvailablePages.unavailable[page] += 1

        return out

    return linkifier.sub(repl, item)


class AvailablePages(object):
    pages = None
    unavailable = Counter()


class BaseContainer(object):
    def __init__(self):
        self.contents = []

    def __bool__(self):
        return bool(self.contents)

    def append(self, object):
        self.contents.append(object)

    def prepend(self, object):
        self.contents.insert(0, object)

    def html(self):
        p_tpl = load_template('p')
        out = []
        strings = []
        for item in self.contents:
            if isinstance(item, str):
                if not item:
                    if strings:
                        content = linkify(' '.join(strings))
                        strings = []
                        out.append(p_tpl.substitute(content=content))
                else:
                    strings.append(item)
            else:
                if strings:
                    content = linkify(' '.join(strings))
                    strings = []
                    out.append(p_tpl.substitute(content=content))

                out.append(item.html())
        else:
            if strings:
                content = linkify(' '.join(strings))
                strings = []
                out.append(p_tpl.substitute(content=content))

        return ''.join(out)


class Container(BaseContainer):
    pass


class Table(BaseContainer):
    def html(self):
        # FIXME: At some point we need to rewrite this. screen.1 contains
        # some problems
        state = 0
        cells = []
        splitter = '\t'
        for line in self.contents:
            row = line.split(splitter)
            if state == 0 and row[-1].endswith('.'):
                columns = len(row[0].split())
                state = 2
            elif state == 0 and 'tab(' in row[0]:
                splitter = re.sub(r'^.*tab\((.+)\);', r'\1', row[0])
            elif state == 2:
                if len(row) == 1 and row[0] == '_':
                    pass
                else:
                    if 'T{' not in line and 'T}' not in line:
                        while len(row) < columns:
                            row.append('')
                    cells.extend(row)
        try:
            while True:
                s, e = cells.index('T{'), cells.index('T}')
                cells[s:e + 1] = [' '.join(cells[s + 1:e])]
        except:
            pass

        out = ""
        first = True
        while cells:
            out += "\n<tr>"
            for cell in cells[0:columns]:
                cell = cell.replace("\\0", "")
                if first:
                    out += "\n<th>%s</th>" % linkify(cell)
                else:
                    out += "\n<td>%s</td>" % linkify(cell)
            del cells[0:columns]
            first = False
            out += "</tr>\n"
        out = "<table class=\"table table-striped\">%s</table>" % out

        return out


class Section(BaseContainer):
    """docstring for Section"""
    tpl = load_template('section')

    def __init__(self):
        super(Section, self).__init__()
        self.title = None

    def html(self):
        out = super(Section, self).html()

        return self.tpl.substitute(title=linkify(self.title), content=out)


class Manpage(BaseContainer):
    """docstring for Manpage"""

    def __init__(self, name, section):
        super(Manpage, self).__init__()
        self.name = name
        self.section = section

        self.title = None

        self.package = None
        self.prev_page = None
        self.next_page = None

    @cached_property
    def pager_contents(self):
        pager = get_pagination(self.prev_page, self.next_page)
        if not pager:
            return ""
        else:
            return pager

    @cached_property
    def descriptive_title(self):
        return "%s: %s" % (self.name,
                           self.title, )

    @property
    def page_header(self):
        return load_template('header').substitute(
            section=self.section,
            title=self.name,
            subtitle=self.title, )

    def pre_process(self):
        self.contents = filter(self.process_sections, self.contents)

    def process_sections(self, section):
        if section.title == 'NAME':
            try:
                content = strip_tags(' '.join(section.contents))
            except:
                raise
            chunks = content.split(' - ', 1)

            if len(chunks) == 1:
                chunks = content.split(' -- ', 1)

            if len(chunks) == 1:
                self.title = content.strip().capitalize()
            else:
                self.title = chunks[-1].strip().capitalize()
            return False
        elif section.title == 'SEE ALSO':
            section.title = "RELATED TO %s&hellip;" % self.name

        return True

    @cached_property
    def section_description(self):
        return SECTIONS[self.full_section]

    @cached_property
    def full_section(self):
        return "man%s" % self.section

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

    def html(self):
        content = super(Manpage, self).html()

        return load_template('base').substitute(
            breadcrumb=self.breadcrumbs,
            title=self.descriptive_title,
            metadescription=self.title,
            header=self.page_header,
            content=content + self.pager_contents, )


class IndentedBlock(BaseContainer):
    pass


class PreformattedBlock(BaseContainer):
    def html(self):
        out = [linkify(item) for item in self.contents]
        return load_template('pre').substitute(content='\n'.join(out))

    def append(self, object):
        if not self.contents and not object.strip():
            return

        super(PreformattedBlock, self).append(object)

class SpacedBlock(BaseContainer):
    def html(self):
        out = [linkify(item) for item in self.contents]
        return load_template('pre').substitute(content='\n'.join(out))


class SubSection(Section):
    tpl = load_template('subsection')


class DefinitionList(BaseContainer):
    def __init__(self):
        super(DefinitionList, self).__init__()
        self.next_is_bullet = False

    def append(self, object):
        if self.next_is_bullet:
            self.contents[-1][0].append(object)
            self.next_is_bullet = False
        else:
            self.contents[-1][1].append(object)

    def html(self):
        dtdd_tpl = load_template('dtdd')
        dl_tpl = load_template('dl')

        out = [dtdd_tpl.substitute(
            bullet=bullets.html(), content=items.html())
               for bullets, items in self.contents]
        return dl_tpl.substitute(content=''.join(out))

    def add_bullet(self):
        self.contents.append([Container(), Container()])
        self.expect_bullet()

    def expect_bullet(self):
        self.next_is_bullet = True


class Mailto(BaseContainer):
    pass


class Url(BaseContainer):
    pass


class BulletedList(BaseContainer):
    def append(self, object):
        self.contents[-1][1].append(object)

    def add_bullet(self, args):
        if not args or not args[0]:
            bullet = ''
        elif args[0] == "\\(bu":
            bullet = '*'
        else:
            bullet = args[0]

        self.contents.append([bullet, Container()])

    def html(self):
        bullets = set([bullet for bullet, _ in self.contents])
        n_bullets = len(bullets)

        if not n_bullets:
            return ""
        elif n_bullets == 1 and len(list(bullets)[0]) < 2:
            ul_tpl = load_template('ul')
            li_tpl = load_template('li')

            out = [li_tpl.substitute(content=items.html())
                   for _, items in self.contents]

            return ul_tpl.substitute(content=''.join(out))
            # UL
        else:
            dtdd_tpl = load_template('dtdd')
            dl_tpl = load_template('dl')

            out = []
            for bullet, items in self.contents:
                out.append(
                    dtdd_tpl.substitute(
                        bullet=bullet, content=items.html()))

            return dl_tpl.substitute(content=''.join(out))
