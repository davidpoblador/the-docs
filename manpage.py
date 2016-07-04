#!/usr/bin/env python

import shlex
from string import Template
import os
from repoze.lru import lru_cache
import re
try:
    import re2 as re
except ImportError:
    pass
import logging


class ManPage(object):
    cc = ("'", ".")
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

        self.sections = []
        self.current_buffer = None

        self.capture_name_section = False

        self.preserve_next_line = False
        self.in_dl = False
        self.in_li = False
        self.in_pre = False
        self.in_table = False
        self.table_buffer = []
        self.pre_buffer = []
        self.spaced_lines_buffer = []
        self.blank_line = False  # Previous line was blank
        self.content_buffer = []

        self.state = []
        self.depth = 0

        self.redirect = []

        self.list_of_pages = set()

        if redirected_from:
            self.manpage_name = os.path.basename(redirected_from)
        else:
            self.manpage_name = os.path.basename(filename)

        self.macros_to_ignore = {
            'ad', 'PD', 'nh', 'hy', 'HP', 'UE', 'ft', 'fam'}
        self.macros_to_space = {'br', 'sp'}
        self.style_macros = self.single_styles | self.compound_styles

        self.next_page = None
        self.previous_page = None
        self.base_url = base_url

    def set_pages(self, list_of_pages):
        self.list_of_pages = list_of_pages

    def set_previous(self, manfile, description):
        self.previous_page = (manfile, description)

    def set_next(self, manfile, description):
        self.next_page = (manfile, description)

    def process_spaced_lines(self, line):
        if (not line) or (not line.startswith(" ")):
            self.blank_line = False
            self.add_text(
                "\n<pre>%s</pre>\n" %
                '\n'.join(
                    self.spaced_lines_buffer))
            self.spaced_lines_buffer = []

    def parse(self):
        yield_subtitle = False
        for line in self.get_line():

            if self.redirect:
                break

            if not yield_subtitle and self.subtitle:
                yield_subtitle = True
                yield self.redirect, self.subtitle

            if self.spaced_lines_buffer:
                self.process_spaced_lines(line)

            if not line:
                if self.sections:
                    self.add_spacer()
            elif line[0] in self.cc:
                self.blank_line = False
                self.parse_macro(line[1:])
            elif self.in_table:
                self.table_buffer.append(unescape(line))
            elif self.capture_name_section:
                self.name_section_buffer.append(unescape(line))
            elif line.startswith(" ") and not self.in_pre:
                self.blank_line = False
                self.spaced_lines_buffer.append(unescape(line))
            else:
                self.blank_line = False
                self.add_content(line)
        else:
            self.flush_current_section()

        if self.redirect:
            yield self.redirect, None

    def process_redirect(self, data):
        self.redirect = data.split("/")

    def get_line(self):
        with open(self.filename) as fp:
            extra_line = None
            for line in fp:
                comment_start = line.find("\\\"")
                if comment_start in (0, 1):
                    continue
                elif comment_start > -1 and line[comment_start - 1] != "\\":
                    line = line[0:comment_start]

                line = line.rstrip()

                if extra_line:
                    line = "%s %s" % (extra_line, line,)
                    extra_line = None

                if not line:
                    yield line
                elif line[-1] == "\\" and (line[0] in self.cc or not self.in_pre):
                    extra_line = line[:-1]
                    continue
                elif line[-2:] == "\\c" and (line[0] in self.cc or not self.in_pre):
                    extra_line = line[:-2]
                    continue
                else:
                    yield entitize(line)

    def add_spacer(self):
        if self.in_pre:
            self.append_to_pre_buffer(None)
        elif not self.blank_line:
            self.blank_line = True
            self.add_text("\n<p class='spacer'>\n")

    def save_state(self):
        self.state.append((self.in_dl, self.in_li,))
        self.depth += 1

        self.in_dl = False
        self.in_li = False

    def restore_state(self):
        self.flush_dl()
        self.flush_li()

        self.in_dl, self.in_li = self.state.pop(-1)
        self.depth -= 1

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

    def parse_macro(self, line):
        if " " in line:
            macro, data = line.split(None, 1)
        else:
            macro, data = line, None

        if macro in self.macros_to_ignore:
            return

        if macro == "SH":
            self.add_section(data)
            return
        elif macro == "SS":
            self.add_subsection(data)
            return
        elif macro in {'so'}:
            self.process_redirect(data)
            return

        if macro in self.style_macros:
            if data:
                self.add_content(self.add_style(macro, data))
            return

        if data:
            data = unescape(data)

        if macro in self.macros_to_space:
            self.add_spacer()
        elif macro == 'TS':
            self.in_table = True
        elif macro == 'TE':
            self.end_table()
        elif macro == "TH":
            self.set_header(data)
        elif macro == "TP":
            if self.in_dl:
                self.add_text("</dd>", 2)
            self.preserve_next_line = True
        elif macro == 'IP':
            if self.in_li:
                self.add_text("</dd>", 2)
            self.process_li(data)
        elif macro in {'LP', 'PP', 'P'}:
            self.flush_dl()
            self.flush_li()
            self.add_spacer()
        elif macro == 'in':
            # We do not mess with indents
            pass
        elif macro == "nf":
            self.start_pre()
        elif macro == 'fi':
            self.end_pre()
        elif macro == "RS":
            self.save_state()
        elif macro == "RE":
            self.restore_state()
        elif macro == 'UR':
            self.add_url(data)
        else:
            raise MissingParser("MACRO %s : %s" % (macro, data, ))
            pass

    def add_url(self, data):
        self.add_content("<a href=\"%s\">%s</a>" % (data, data,))

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
            bullet = data.split()[0]

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
        headers = shlex.split(data)

        self.header = {
            "title": headers[0],
            "section": headers[1],
        }

    def add_section(self, data):
        self.flush_containers()
        if data == 'NAME':
            self.capture_name_section = True
            self.name_section_buffer = []
            # FIXME: Time to parse name
            pass
        else:
            self.flush_current_section()
            self.sections.append([data, None])

    def add_subsection(self, data):
        self.flush_containers()
        self.add_text("<h3>%s</h3>" % unescape(data), 2)

    def flush_containers(self):
        self.end_pre()
        self.flush_dl()
        self.flush_li()

    def flush_current_section(self):
        if self.capture_name_section:
            self.extract_title()
            del self.name_section_buffer
            self.capture_name_section = False

        if self.content_buffer:
            self.flush_paragraph()

        if self.sections:
            self.sections[-1][1] = self.current_buffer

        self.current_buffer = []

    def extract_title(self):
        title, subtitle = " ".join(self.name_section_buffer).split('-', 1)
        self.title = title.strip()
        self.subtitle = subtitle.strip()

    def repl(self, m):
        manpage = m.groupdict()['page']
        section = m.groupdict()['section']
        page = '.'.join([manpage, section])

        out = "<strong>%s</strong>(%s)" % (manpage, section, )

        if page in self.list_of_pages:
            out = "<a href=\"../man%s/%s.%s.html\">%s</a>" % (
                section, manpage, section, out, )
        return out

    def linkify(self, text):
        return linkifier.sub(self.repl, text)

    def html(self):
        if self.redirect:
            return "REDIRECTION %s" % self.redirect

        section_tpl = load_template('section')
        section_contents = ""
        for title, content in self.sections:
            section_contents += section_tpl.safe_substitute(
                title=title,
                content=''.join(content),
            )

        section_contents = self.linkify(section_contents)

        header_tpl = load_template('header')
        base_tpl = load_template('base')
        breadcrumb_tpl = load_template('breadcrumb')

        if self.next_page or self.previous_page:
            links = ""
            if self.previous_page:
                links += "<li class=\"previous\"><a href=\"%s.html\"><span aria-hidden=\"true\">&larr;</span> %s: %s</a></li>" % (
                    self.previous_page[0], self.previous_page[0], self.previous_page[1])
            if self.next_page:
                links += "<li class=\"next\"><a href=\"%s.html\">%s: %s <span aria-hidden=\"true\">&rarr;</span></a></li>" % (
                    self.next_page[0], self.next_page[0], self.next_page[1])

            pager_tpl = load_template('pager')
            pager_contents = pager_tpl.safe_substitute(
                links=links,
            )

            section_contents += pager_contents

        title, section = self.manpage_name.rsplit('.', 1)
        return base_tpl.safe_substitute(
            # TODO: Fix canonical, nav, breadcrumb
            canonical="",
            nav="",
            breadcrumb=breadcrumb_tpl.substitute(
                section=section,
                section_name=self.SECTIONS["man" + section],
                manpage=title,
                base_url=self.base_url,
                page=self.manpage_name,
            ),
            title="%s - %s" % (self.title, self.subtitle, ),
            header=header_tpl.safe_substitute(
                section=section,
                title=title,  # FIXME: Mess
                subtitle=self.subtitle,
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


@lru_cache(maxsize=100000)
def toargs(data):
    def tokenize():
        lexer = shlex.shlex(data, posix=True)
        lexer.commenters = ''
        lexer.quotes = "\""
        lexer.whitespace_split = True
        return list(lexer)

    try:
        args = tokenize()
    except:
        data += "\""
        try:
            args = tokenize()
        except:
            raise

    return args


def stylize(style, text):
    if style == 'R':
        return text
    else:
        return "<%s>%s</%s>" % (style_trans[style], text, style_trans[style], )


def stylize_odd_even(style, args):
    buff = ""
    c = 0
    for arg in args:
        buff += stylize(style[c % 2], arg)
        c = c + 1

    return buff


def unescape(t):
    if not t:
        return t

    if "\\" not in t:
        return t

    t = t.replace("\-", "-")
    t = t.replace("\ ", "&nbsp;")
    t = t.replace("\\0", "&nbsp;")

    t = t.replace("\%", "")
    t = t.replace("\:", "")

    t = t.replace("\\(bu", "&bull;")

    t = t.replace("\`", "&#96;")  # Backtick

    t = t.replace("\&", " ")

    t = t.replace("\\\\", "&#92;")

    t = t.replace("\[char46]", "&#46;")
    t = t.replace("\\(em", "&ndash;")
    t = t.replace("\\(en", "&ndash;")

    t = t.replace("\\(dq", "&quot;")
    t = t.replace("\\(aq", "&apos;")

    t = t.replace("\\(+-", "&plusmn;")

    t = t.replace("\\(:A", "&Auml;")

    t = t.replace("\\('a", "&aacute;")
    t = t.replace("\\(`a", "&agrave;")
    t = t.replace("\\(:a", "&auml;")
    t = t.replace("\\(^a", "&acirc;")

    t = t.replace("\\(12", "&frac12;")
    t = t.replace("\\.", ".")
    t = t.replace("\\(mc", "&micro;")

    t = t.replace("\\*(lq", "&ldquo;").replace("\\(lq", "&ldquo;")
    t = t.replace("\\*(rq", "&rdquo;").replace("\\(rq", "&rdquo;")

    t = t.replace("\\e", "&#92;")
    t = tagify(t)

    return t


def tagify(t):
    # Fixme (when we have time dir_colors.5 shows why this needs fixing)
    t = re.sub(
        r'\\fI(.*?)\\f[PR]',
        r'<em>\1</em>',
        t)

    t = re.sub(
        r'\\fB(.*?)\\f[PR]',
        r'<strong>\1</strong>',
        t)

    t = t.replace("\\fB", "")
    t = t.replace("\\fI", "")
    t = t.replace("\\fR", "")
    t = t.replace("\\fP", "")

    # t = re.sub(
    # r'\\f\(CW(.*?)\\fP',
    # r'<strong>\1</strong>',
    # t)

    t = t.replace('*NEWLINE*', "\n")

    return t


def entitize(line):
    return line.replace("<", "&lt;").replace(">", "&gt;")

linkifier = re.compile(
    r"(?:<\w+?>)?(?P<page>\w+[\w\.-]+\w+)(?:</\w+?>)?[(](?P<section>\d)[)]")


class MissingParser(Exception):
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
    g = manpage.parse()

    try:
        while True:
            next(g)
    except StopIteration:
        pass

    print(manpage.html())
