#!/usr/bin/env python
"""Man Page Parse Module"""

import time
import logging
import argparse
import os.path

import collections
from itertools import islice
from manpage.helpers import load_template, unescape, get_breadcrumb, entitize
from manpage.helpers import SECTIONS
from cached_property import cached_property
from string import Template


def consume(iterator, n):
    "Advance the iterator n-steps ahead. If n is none, consume entirely."
    # Use functions that consume iterators at C speed.
    if n is None:
        # feed the entire iterator into a zero-length deque
        collections.deque(iterator, maxlen=0)
    else:
        # advance to the empty slice starting at position n
        next(islice(iterator, n, n), None)


class Line(object):
    cc = '.'
    c2 = '\''
    ec = '\\'

    comment = ec + '"'


class Macro(object):
    single_style = {'B', 'I'}
    compound_style = {'BI', 'BR', 'IR', 'RI', 'RB'}

    styles = single_style | compound_style

    ignore = {
        # Tabulation crap
        "ta",
        # Page break stuff
        "ne",
        # Temporary
        "in",
        # Man7 specific
        "UC",
        "PD",
    }

    vertical_spacing = {
        # Kind of new paragraph
        "sp",
        "br",
    }

    new_paragraph = {'PP', 'P', 'LP'}

    style_tpl = {
        "I": Template("<em>${content}</em>"),
        "B": Template("<strong>${content}</strong>"),
        "R": Template("${content}"),
    }


def tokenize(t):
    # FiXME "\ " is going to break everything
    # https://www.gnu.org/software/groff/manual/html_node/Request-and-Macro-Arguments.html
    if not t:
        tokens = []
    elif ' ' not in t and '"' not in t:
        tokens = [t]
    elif '"' not in t and "\\ " not in t:
        tokens = t.split(None)
    else:
        #print "(%s)" % (t,)

        state = "start"
        arg = ""
        tokens = []
        for char in t:
            if state == "start":
                if char == " ":
                    continue
                elif char == "\"":
                    state = "inarg_quote"
                    continue
                else:
                    state = "inarg"
                    arg += char
                    continue

            if state == "inarg_quote":
                if char == "\"":
                    state = "start"
                    tokens.append(arg)
                    arg = ""
                    continue
                else:
                    arg += char
                    continue

            if state == "inarg":
                if char == " ":
                    tokens.append(arg)
                    arg = ""
                    state = "start"
                    continue
                else:
                    arg += char
                    continue
        else:
            if state == "inarg":
                if arg:
                    tokens.append(arg)
                    arg = ""
                    state = "start"
            elif state == "start":
                pass
            else:
                raise Exception("Args should be empty %s" % state)

    return tokens


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
                           self.title,)

    @property
    def page_header(self):
        return load_template('header').substitute(
            section=self.section,
            title=self.name,
            subtitle=self.title,)

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
                                              self.section,),
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
            content=content,)

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

            out = [li_tpl.substitute(content=items.html()) for _, items in self.contents]

            return ul_tpl.substitute(content=''.join(out))
            # UL
        else:
            dtdd_tpl = load_template('dtdd')
            dl_tpl = load_template('dl')

            out = []
            for bullet, items in self.contents:
                out.append(dtdd_tpl.substitute(bullet=bullet, content=items.html()))

            return dl_tpl.substitute(content=''.join(out))


# FIXME Write custom Exception
def unexpected_macro(parser, macro, args):
    exception = "Missing Macro (%s) in parser (%s)" % (macro,
                                                       parser,)
    raise Exception(exception)


def stylize(macro, args):
    if macro in Macro.single_style:
        return Macro.style_tpl[macro].substitute(content=' '.join(args))
    elif macro in Macro.compound_style:
        out = []
        for i, chunk in enumerate(args):
            style = Macro.style_tpl[macro[i % 2]]
            out.append(' '.join([style.substitute(content=subchunk)
                                 for subchunk in chunk.replace('\t',' ').split(' ')]))

        return ''.join(out)
    else:
        unexpected_macro("STYLE", macro, args)


class ManpageParser(object):
    """Man Page Parser Class"""

    def __init__(self, path):
        basename = os.path.basename(path)

        self.name, ext = os.path.splitext(basename)

        self.numeric_section = ext[1:]
        self._path = path
        self.lines = []

        self.readfile()

    def readfile(self):
        with open(self.path) as fp:
            for line in fp:
                line = line.rstrip()

                if Line.comment in line:
                    # Line has comment
                    line = line.split(Line.comment, 1)[0]

                if line == Line.cc or line == Line.c2:
                    # Empty line (cc or c2)
                    continue

                if not line:
                    # Empty line
                    self.lines.append(('', ''))
                    continue

                if line[0] in {Line.cc, Line.c2}:
                    chunks = line[1:].split(None, 1)
                    macro = chunks[0]
                    if len(chunks) == 2:
                        rest = chunks[1]
                    else:
                        rest = ""

                    if macro in Macro.ignore:
                        continue

                    # Macro start
                    if macro == 'if':
                        # FIXME
                        continue

                    if macro in Macro.vertical_spacing:
                        self.lines.append(('', ''))
                    else:
                        self.lines.append((macro, tokenize(rest)))
                else:
                    self.lines.append(('', entitize(line)))

    def process(self, start=0, parser="ROOT"):
        content = None
        iter = enumerate(self.lines[start:])
        for i, (macro, args) in iter:
            #print "LINE (CP: %s): (%s: %s) [%s]" % (parser, macro, args, repr(content))
            #print ">> %s" % (content,)

            if parser == "ROOT":
                if not content:
                    content = Manpage(
                        name=self.name, section=self.numeric_section)
                # ROOT
                if macro == 'TH':
                    continue  # FIXME
                elif macro == 'SH':
                    inc, section_content = self.process(start + i, 'SECTION')
                    content.append(section_content)
                    consume(iter, inc)
                    continue
                elif macro:
                    unexpected_macro(parser, macro, args)
                elif not macro:
                    continue
            else:
                if macro in Macro.styles:
                    args = stylize(macro, args)
                    macro = ''

                if parser == 'SECTION':
                    if macro == 'SH':
                        if content is None:
                            content = Section()
                            content.title = ' '.join(args)
                            continue
                        else:
                            return i - 1, content
                elif parser == 'SUBSECTION':
                    if macro == 'SS':
                        if content is None:
                            content = SubSection()
                            content.title = ' '.join(args)
                            continue
                        else:
                            return i - 1, content
                    elif macro == 'SH':
                        return i - 1, content
                elif parser == 'RS-RE':
                    if content is None:
                        content = IndentedBlock()
                        continue
                    if macro == 'RE':
                        return i, content
                    elif macro in {'SH', 'SS'}:
                        return i - 1, content
                elif parser == 'PRE':
                    if content is None:
                        content = PreformattedBlock()
                        continue
                    if macro == 'fi':
                        return i, content
                elif parser == 'TP':
                    if content is None:
                        content = DefinitionList()

                    if macro == 'TP':
                        content.add_bullet()
                        continue
                    elif macro in {'SH', 'SS', 'RE'}:
                        return i - 1, content
                    elif macro in {'IP', 'RS'}:
                        pass
                    elif macro:
                        unexpected_macro(parser, macro, args)
                elif parser == 'IP':
                    if content is None:
                        content = BulletedList()

                    if macro == 'IP':
                        content.add_bullet(args)
                        continue
                    elif macro in {'SH', 'SS'}:
                        return i - 1, content
                    elif macro in Macro.new_paragraph:
                        return i - 1, content
                    elif macro == 'TP':
                        return i - 1, content
                    elif macro == 'RS':
                        pass
                    elif macro:
                        unexpected_macro(parser, macro, args)
                elif parser == 'TABLE':
                    if content is None:
                        # FIXME We need a proper parser for tables
                        content = Container()
                        continue

                    if macro == 'TE':
                        return i, content

                if not macro:
                    content.append(unescape(args))
                elif macro in Macro.new_paragraph:
                    content.append('')
                elif macro == 'RS':
                    inc, rs_content = self.process(start + i, 'RS-RE')
                    content.append(rs_content)
                    consume(iter, inc)
                elif macro == 'SS':
                    inc, ss_content = self.process(start + i, 'SUBSECTION')
                    content.append(ss_content)
                    consume(iter, inc)
                elif macro == 'nf':
                    inc, nf_content = self.process(start + i, 'PRE')
                    content.append(nf_content)
                    consume(iter, inc)
                elif macro == 'TS':
                    inc, table_content = self.process(start + i, 'TABLE')
                    content.append(table_content)
                    consume(iter, inc)
                elif macro == 'TP':
                    inc, tp_content = self.process(start + i, 'TP')
                    content.append(tp_content)
                    consume(iter, inc)
                elif macro == 'IP':
                    inc, ip_content = self.process(start + i, 'IP')
                    content.append(ip_content)
                    consume(iter, inc)
                else:
                    unexpected_macro(parser, macro, args)

        else:
            if parser == 'ROOT':
                content.pre_process()
                return content

            return None, content

    @property
    def path(self):
        """ self.path property """
        return self._path

def main():
    """Main"""
    start_time = time.time()

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--log-level", help="choose log level")
    parser.add_argument("manpage", help="the manpage you want to process")

    args = parser.parse_args()

    if args.log_level:
        log_level = getattr(logging, args.log_level.upper())
        logging.basicConfig(level=log_level)

    manpage = ManpageParser(args.manpage)
    parsed = manpage.process()

    fp = open("public_html/out.html", 'w')
    fp.write(parsed.html())
    fp.close()

    elapsed = time.time() - start_time
    logging.info("--- Total time: %s seconds ---", elapsed)


if __name__ == '__main__':
    main()
