from helpers import load_template, get_breadcrumb
from cached_property import cached_property
from helpers import SECTIONS

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
                    if not strings:
                        pass
                    else:
                        out.append(p_tpl.substitute(content=' '.join(strings)))
                        strings = []
                else:
                    strings.append(item)
            else:
                if strings:
                    out.append(p_tpl.substitute(content=' '.join(strings)))
                    strings = []

                out.append(item.html())
        else:
            if strings:
                out.append(p_tpl.substitute(content=' '.join(strings)))
                strings = []

        return ''.join(out)


class Container(BaseContainer):
    pass

class Section(BaseContainer):
    """docstring for Section"""
    tpl = load_template('section')

    def __init__(self):
        super(Section, self).__init__()
        self.title = None

    def html(self):
        out = super(Section, self).html()

        return self.tpl.substitute(title=self.title, content=out)

class Manpage(BaseContainer):
    """docstring for Manpage"""

    def __init__(self, name, section):
        super(Manpage, self).__init__()
        self.name = name
        self.section = section

        self.title = None

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
            content = section.contents[0]
            chunks = content.split('-', 1)
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

        return '\n'.join(breadcrumbs)

    def html(self):
        content = super(Manpage, self).html()

        return load_template('base').substitute(
            breadcrumb=self.breadcrumbs,
            title=self.descriptive_title,
            metadescription=self.title,
            header=self.page_header,
            content=content, )

        pass


class IndentedBlock(BaseContainer):
    pass


class PreformattedBlock(BaseContainer):
    def html(self):
        out = [item for item in self.contents]
        return load_template('pre').substitute(content='\n'.join(out))


class SubSection(Section):
    tpl = load_template('subsection')


class DefinitionList(BaseContainer):
    def append(self, object):
        if self.contents[-1][0] is None:
            self.contents[-1][0] = object
        else:
            self.contents[-1][1].append(object)

    def html(self):
        dtdd_tpl = load_template('dtdd')
        dl_tpl = load_template('dl')

        out = [dtdd_tpl.substitute(
            bullet=bullet, content=items.html())
               for bullet, items in self.contents]
        return dl_tpl.substitute(content=''.join(out))

    def add_bullet(self):
        self.contents.append([None, Container()])


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