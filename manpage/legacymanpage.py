#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging

from parsers import ManPageStates

from helpers import tagify, unescape, toargs
from helpers import load_template
from helpers import MissingParser, NotSupportedFormat, RedirectedPage, UnexpectedState
from helpers import SECTIONS
from helpers import bname, dname

from html import ManPageHTML

from lines import Lines

try:
    import re2 as re
except ImportError:
    import re


class ManPage(object):
    single_styles = {'B', 'I'}
    compound_styles = {'IR', 'RI', 'BR', 'RB', 'BI', 'IB'}

    @property
    def package(self):
        try:
            return bname(dname(dname(self.full_path)))
        except:
            return None

    @property
    def basename(self):
        return os.path.basename(self.full_path)

    @property
    def full_section(self):
        return "man%s" % self.section

    def __init__(self, filename):
        self.full_path = filename
        self.name, section = os.path.splitext(self.basename)
        self.section = section[1:]
        self.section_description = SECTIONS[self.full_section]

        self.load_lines(filename)
        self.initialize_state()

    def load_lines(self, filename):
        with open(filename) as fp:
            self.lines = Lines([line.rstrip() for line in fp])

    def initialize_state(self):
        self.in_pre = False
        self.in_dl = False
        self.in_li = False
        self.in_table = False

        self.table_buffer = []
        self.pre_buffer = []

        self.content_buffer = []
        self.spaced_lines_buffer = []
        self.preserve_next_line = 0

        self.depth = 0
        self.state = []

        self.current_buffer = []

        # Needed
        self.sections = []
        self.subtitle = ""

        self.next_page = None
        self.previous_page = None

        self.broken_links = set()
        self.section_counters = set()

        self.set_state(ManPageStates.HEADER)

    def parse(self):
        try:
            while True:
                try:
                    line = self.lines.get()
                except IndexError:
                    break

                if self.spaced_lines_buffer:
                    self.process_spaced_lines(line.data)

                self.state_parser()(line, self).process()
        except RedirectedPage:
            self.load_lines(
                os.path.join(
                    os.path.dirname(os.path.dirname(self.full_path)),
                    self.redirect))
            self.initialize_state()
            del (self._redirect)
            self.parse()
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

    def set_previous(self, page):
        self.previous_page = page

    def set_next(self, page):
        self.next_page = page

    def process_spaced_lines(self, line):
        if (not line) or (not line.startswith(" ")):
            self.blank_line = False
            self.add_text("\n<pre>%s</pre>\n" %
                          '\n'.join(self.spaced_lines_buffer))
            self.spaced_lines_buffer = []

    @property
    def redirect(self):
        try:
            if '/' not in self._redirect:
                # Relative
                return "%s/%s" % (self.full_section,
                                  self._redirect, )
            else:
                return self._redirect
        except:
            # Impossible redirect
            raise

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
        if re.match(r"[^@]+@[^@]+\.[^@]+", data):
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
        if not self.in_table:
            return

        state = 0
        cells = []
        splitter = '\t'
        for line in self.table_buffer:
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
        self.preserve_next_line = 0

    def start_pre(self):
        if not self.in_pre:
            self.save_state()
            self.in_pre = True
            self.pre_buffer = []

    def end_pre(self):
        if self.in_pre:
            self.in_pre = False
            if self.pre_buffer:
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

        self.flush_containers()

        if self.sections:
            self.sections[-1][1] = self.current_buffer

        self.current_buffer = []

    def get_sections(self):
        return [(title, ''.join(content)) for title, content in self.sections]

    def html(self):
        return ManPageHTML(
            name=self.name,
            section=self.section,
            subtitle=self.subtitle,
            sections=self.get_sections()).get()


def stylize(style, text):
    style_trans = {'I': 'em',
                   'B': 'strong', }
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
        print "Page %s contains a redirection to %s" % (manpage.full_path,
                                                        manpage.redirect[1])
    else:
        print(manpage.html())