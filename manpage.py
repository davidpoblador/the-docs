#!/usr/bin/env python

import shlex
from string import Template
import os
from repoze.lru import lru_cache
try:
    import re2 as re
except ImportError:
    import re
import logging
from parsers import MacroParser, BodyMacroParser, TitleMacroParser, HeaderMacroParser
from parsers import LineParser, ManPageStates
from parsers import RedirectedPage
from parsers import tagify, unescape, toargs, entitize


class ManPage(object):
    single_styles = {'B', 'I'}
    compound_styles = {'IR', 'RI', 'BR', 'RB', 'BI', 'IB'}

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

    def __init__(self, filename, redirected_from=False, base_url=""):
        self.filename = filename
        self.subtitle = ""

        self.preserve_next_line = False

        if redirected_from:
            self.manpage_name = os.path.basename(redirected_from)
        else:
            self.manpage_name = os.path.basename(filename)

        self.next_page = None
        self.previous_page = None
        self.base_url = base_url

        self.broken_links = set()

        # New stuff
        self.set_state(ManPageStates.HEADER)
        self.line_iterator = self.line()

    def parse(self):
        self.parse_header()
        self.parse_title()
        self.parse_body()

    def parse_title(self):
        self.must_have_state(ManPageStates.TITLE)

        for line in self.line_iterator:
            self.state_parser()(line, self).process()

            if not self.is_state(ManPageStates.TITLE):
                break

    def parse_header(self):
        self.must_have_state(ManPageStates.HEADER)

        for line in self.line_iterator:
            self.state_parser()(line, self).process()

            if not self.is_state(ManPageStates.HEADER):
                break

    def parse_body(self):
        self.in_dl = False
        self.in_li = False
        self.in_pre = False
        self.in_table = False
        self.table_buffer = []
        self.pre_buffer = []

        self.current_buffer = []

        self.spaced_lines_buffer = []
        self.blank_line = False  # Previous line was blank
        self.content_buffer = []

        self.state = []
        self.depth = 0

        self.sections = []

        self.must_have_state(ManPageStates.BODY)

        for line in self.line_iterator:
            if self.spaced_lines_buffer:
                self.process_spaced_lines(line)

            self.state_parser()(line, self).process()

        else:
            self.flush_current_section()

    def state_parser(self):
        return ManPageStates.parser[self.parsing_state]

    def must_have_state(self, state):
        if not self.is_state(state):
            raise UnexpectedState(self.parsing_state)

    def is_state(self, state):
        return (self.parsing_state == state)

    def set_state(self, state):
        self.parsing_state = state

    def line(self):
        with open(self.filename) as fp:
            extra_line = False
            for line in fp:
                comment_start = line.find("\\\"")
                if comment_start in (0, 1):
                    continue
                elif comment_start > -1 and line[comment_start - 1] != "\\":
                    line = line[0:comment_start]

                if extra_line:
                    line = " ".join((extra_line,
                                     line, ))
                    extra_line = False

                parsed_line = LineParser(entitize(line.rstrip()))

                if parsed_line.extra and (
                    ((self.is_state(ManPageStates.BODY) and not self.in_pre) or
                     parsed_line.macro) or self.is_state(ManPageStates.TITLE)):
                    extra_line = parsed_line.extra
                    continue

                yield parsed_line

    def set_previous(self, manfile, description):
        self.previous_page = (manfile, description)

    def set_next(self, manfile, description):
        self.next_page = (manfile, description)

    def process_spaced_lines(self, line):
        if (not line) or (not line.startswith(" ")):
            self.blank_line = False
            self.add_text("\n<pre>%s</pre>\n" %
                          '\n'.join(self.spaced_lines_buffer))
            self.spaced_lines_buffer = []

    @property
    def redirect(self):
        try:
            return self._redirect
        except:
            return False

    def add_spacer(self):
        if self.in_pre:
            self.append_to_pre_buffer(None)
        elif not self.blank_line:
            self.blank_line = True
            self.add_text("\n<p class='spacer'>\n")

    def save_state(self):
        self.state.append((self.in_dl,
                           self.in_li, ))
        self.depth += 1

        self.in_dl = False
        self.in_li = False

    def restore_state(self):
        if self.state:
            self.flush_dl()
            self.flush_li()

            try:
                self.in_dl, self.in_li = self.state.pop(-1)
                self.depth -= 1
            except:
                pass

    def flush_dl(self):
        if self.in_dl:
            self.add_text("</dd>", 2)
            self.add_text("</dl>", 1)
            self.in_dl = False
            self.restore_state()

    def flush_li(self):
        if self.in_li:
            self.add_text("</dd>", 2)
            self.add_text("</dl>", 1)
            self.in_li = False
            self.restore_state()

    def add_url(self, data):
        if re.match("[^@]+@[^@]+\.[^@]+", data):
            self.add_content("<a href=\"mailto:%s\">%s</a>" % (data,
                                                               data, ))
        else:
            self.add_content("<a href=\"%s\">%s</a>" % (data,
                                                        data, ))

    def add_mailto(self, data):
        self.add_content("<a href=\"mailto:%s\">%s</a>" % (data,
                                                           data, ))

    def add_content(self, data):
        if not self.sections:
            return

        if self.preserve_next_line:
            self.process_dl(data)
            return

        if self.in_pre:
            self.append_to_pre_buffer(data)
        elif self.in_table:
            self.table_buffer.append(data)
        else:
            self.content_buffer.append(data)

    def add_text(self, data, indent=0):
        if self.in_pre:
            self.append_to_pre_buffer(data)
        else:
            self.append_to_current_buffer(data, indent)

    def append_to_pre_buffer(self, data):
        if data is None:
            self.pre_buffer.append("")
        else:
            self.pre_buffer.append(unescape(data))

    def end_table(self):
        if self.in_table:
            state = 0
            cells = []
            splitter = '\t'
            for line in self.table_buffer:
                row = line.split(splitter)
                if state == 0 and row[-1].endswith('.'):
                    columns = len(row[0].split())
                    state = 2
                elif state == 0 and row[0].startswith('tab('):
                    splitter = re.sub(r'^tab\((.+)\);', r'\1', row[0])
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
                        out += "\n<th>%s</th>" % cell
                    else:
                        out += "\n<td>%s</td>" % cell
                del cells[0:columns]
                first = False
                out += "</tr>\n"
            out = "<table class=\"table table-striped\">%s</table>" % out

            self.add_text("\n%s\n" % out)

            self.table_buffer = []
            self.in_table = False

    def process_dl(self, data):
        if not self.in_dl:
            self.save_state()
            self.in_dl = True
            if len(data) > 6:
                self.append_to_current_buffer("<dl class='dl-vertical'>", 1)
            else:
                self.append_to_current_buffer("<dl class='dl-horizontal'>", 1)

        self.append_to_current_buffer("<dt>%s</dt>" % unescape(data), 2)
        self.append_to_current_buffer("<dd>", 2)
        self.preserve_next_line = False

    def start_pre(self):
        if self.in_pre:
            raise
        else:
            self.save_state()
            self.in_pre = True
            self.pre_buffer = []

    def end_pre(self):
        if not self.in_pre:
            pass
        else:
            self.in_pre = False
            self.add_text("\n<pre>%s</pre>\n" %
                          tagify('*NEWLINE*'.join(self.pre_buffer)))
            self.pre_buffer = []
            self.restore_state()

    def flush_paragraph(self):
        paragraph = "<p>%s</p>" % unescape(' '.join(self.content_buffer))
        self.content_buffer = []
        self.append_to_current_buffer(paragraph, 1)

    def append_to_current_buffer(self, data, nl=0):
        if self.content_buffer:
            self.flush_paragraph()

        if nl:
            data = "\n" + ("  " * (self.depth + nl - 1)) + data

        self.current_buffer.append(data)

    def process_li(self, data):
        if data:
            bullet = toargs(data)[0]

            if not self.in_li:
                self.save_state()
                self.in_li = True
                self.append_to_current_buffer("<dl class='dl-horizontal'>", 1)
            self.append_to_current_buffer("<dt>%s</dt>" % unescape(bullet), 2)
            self.append_to_current_buffer("<dd>", 2)
        else:
            self.add_spacer()

    def add_style(self, style, data):
        data = unescape(data)
        if style in self.single_styles:
            return stylize(style, ' '.join(toargs(data)))
        elif style in self.compound_styles:
            return stylize_odd_even(style, toargs(data))

    def set_header(self, data):
        headers = toargs(data)

        self.header = {
            "title": headers[0],
            "section": headers[1],
        }

    def add_section(self, data):
        data = ' '.join(toargs(data))
        self.flush_containers()
        self.flush_current_section()
        self.sections.append([data, None])

    def add_subsection(self, data):
        data = ' '.join(toargs(data))
        self.flush_containers()
        self.add_text("<h3>%s</h3>" % unescape(data), 2)

    def flush_containers(self):
        self.end_pre()
        self.flush_dl()
        self.flush_li()

    def flush_current_section(self):
        if self.content_buffer:
            self.flush_paragraph()

        if self.sections:
            self.sections[-1][1] = self.current_buffer

        self.current_buffer = []

    def linkify(self, text, pages_to_link=set()):
        def repl(m):
            manpage = m.groupdict()['page']
            section = m.groupdict()['section']
            page = '.'.join([manpage, section])

            out = "<strong>%s</strong>(%s)" % (manpage,
                                               section, )

            if page in pages_to_link:
                out = "<a href=\"../man%s/%s.%s.html\">%s</a>" % (section,
                                                                  manpage,
                                                                  section,
                                                                  out, )
            else:
                self.broken_links.add(page)

            return out

        if pages_to_link:
            return linkifier.sub(repl, text)
        else:
            return text

    def html(self, pages_to_link=set()):
        section_tpl = load_template('section')
        contents = []
        for title, content in self.sections:
            contents.append(section_tpl.substitute(title=title, content=''.join(content), ))

        section_contents = self.linkify(''.join(contents), pages_to_link)

        if self.next_page or self.previous_page:
            links = ""
            if self.previous_page:
                links += "<li class=\"previous\"><a href=\"%s.html\"><span aria-hidden=\"true\">&larr;</span> %s: %s</a></li>" % (
                    self.previous_page[0], self.previous_page[0],
                    self.previous_page[1])
            if self.next_page:
                links += "<li class=\"next\"><a href=\"%s.html\">%s: %s <span aria-hidden=\"true\">&rarr;</span></a></li>" % (
                    self.next_page[0], self.next_page[0], self.next_page[1])

            pager_contents = load_template('pager').substitute(links=links, )
            section_contents += pager_contents

        title, section = self.manpage_name.rsplit('.', 1)
        return load_template('base').substitute(
            breadcrumb=load_template('breadcrumb').substitute(
                section=section,
                section_name=self.SECTIONS["man" + section],
                manpage=title,
                base_url=self.base_url,
                page=self.manpage_name,
            ),
            title="%s - %s" % (title, self.subtitle, ),
            metadescription = self.subtitle.capitalize(),
            header=load_template('header').substitute(
                section=section,
                title=title,
                subtitle=self.subtitle.capitalize(),
            ),
            content=section_contents,
        )

def load_template(template):
    fp = open("templates/%s.tpl" % (template, ))
    out = Template(''.join(fp.readlines()))
    fp.close()
    return out

style_trans = {
    'I': 'em',
    'B': 'strong',
}

def stylize(style, text):
    if style == 'R':
        return text
    else:
        return "<%s>%s</%s>" % (style_trans[style],
                                text,
                                style_trans[style], )


def stylize_odd_even(style, args):
    buff = ""
    c = 0
    for arg in args:
        buff += stylize(style[c % 2], arg)
        c = c + 1

    return buff


linkifier = re.compile(
    r"(?:<\w+?>)?(?P<page>\w+[\w\.-]+\w+)(?:</\w+?>)?[(](?P<section>\d)[)]")


class UnexpectedState(Exception):
    pass


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("manpage", help="the manpage to process")
    parser.add_argument("--log-level", help="choose log level")
    args = parser.parse_args()

    if args.log_level:
        getattr(logging, args.log_level.upper())

    manpage = ManPage(args.manpage)
    try:
        manpage.parse()
    except RedirectedPage:
        print "Page %s contains a redirection to %s" % (manpage.filename,
                                                        manpage.redirect[1])
    else:
        print(manpage.html())
