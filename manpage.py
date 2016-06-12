#!/usr/bin/env python

import shlex
import re
from string import Template
import sys
import os.path

cc = ("'", ".")
single_styles = {'B', 'I'}
compound_styles = {'IR', 'RI', 'BR', 'RB', 'BI', 'IB'}

style_trans = {
    'I': 'em',
    'B': 'strong',
}

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


class ManPage(object):

    def __init__(self, manfile, section=0, redirected_from=False):
        self.title = ""
        self.subtitle = ""

        self.current_section = ""

        self.buff = []
        self.sections_content = []
        self.def_state = 0
        self.in_pre = False
        self.in_table = False
        self.def_buffer = []
        self.pre_buffer = []
        self.list_buffer = []
        self.list_full_buffer = []
        self.table_buffer = []
        self.first_line = True
        self.list_state = False
        self.redirect = []
        self.indent = 0.0
        self.prev_indent = 0.0

        if redirected_from:
            self.manpage_name = os.path.basename(redirected_from)
        else:
            self.manpage_name = os.path.basename(manfile)

        self.header = {
            "title": "",
            "section": "",
            "date": "",
        }

        with open(manfile) as f:
            content = f.read().splitlines()

        extra_line = ""
        c = 0
        for line in content:
            c = c + 1

            if extra_line != "":
                line = "%s %s" % (extra_line, line,)
                extra_line = ""

            if len(line) > 0 and line[-1] == "\\":
                extra_line = line[:-1]
                continue

            if len(line) == 0:
                # FIXME: Empty lines should have a nicer behavior
                # https://www.gnu.org/software/groff/manual/html_node/Implicit-Line-Breaks.html
                if not self.in_pre:
                    self.add_text("\n<p>\n")
            elif line[0] in cc:
                self.line = line[1:]
                self.parse_request()
                if self.redirect:
                    break
            else:
                self.line = line
                # TODO: Text lines can be comments:
                # https://www.gnu.org/software/groff/manual/html_node/Comments.html#index-_005c_0022
                self.add_text(unescape(line))

            if self.first_line:
                self.first_line = False

        if not self.redirect:
            self.flush_section()

    def process_redirect(self):
        self.redirect = self.line_rest.split("/")

    def process_request(self):
        macro = self.line_request

        if macro.startswith('\\"'):
            # Comment
            pass
        elif macro in {'ad', 'PD', 'nh', 'hy', 'HP', 'UE'}:
            # Catchall for ignores. We might need to revisit
            pass
        elif macro in {'ft', 'fam'}:
            # FIXME: Need fixing
            pass
        elif macro in {'so'} and self.first_line:
            self.process_redirect()
        elif macro in {'LP', 'PP', 'P'}:
            self.end_def()
            self.end_list()
            self.add_text("<p>")
        elif macro == 'IP':
            self.start_list()
        elif macro == 'TS':
            self.start_table()
        elif macro == 'TE':
            self.end_table()
        elif macro == 'nf':
            self.start_pre()
        elif macro == 'fi':
            self.end_pre()
        elif macro == 'in':
            self.set_indent()
        elif macro in {'br'}:
            if not self.in_pre:
                self.add_text("<br>")
        elif macro in {'sp'}:
            if self.in_pre:
                self.add_text("\n")
            else:
                self.add_text("<p>")
        elif macro == 'TP':
            self.start_def()
        elif macro == 'RS':
            self.end_def()
            self.add_text("\n<div class=\"inner\">")
        elif macro == 'RE':
            self.end_def()
            self.add_text("</div>")
        elif macro == 'TH':
            self.set_header()
        elif macro == 'SH':
            self.end_def()
            self.end_list()
            self.add_section()
        elif macro == 'SS':
            self.end_def()
            self.end_list()
            self.add_subsection()
        elif macro == 'UR':
            self.add_url()
        elif macro in single_styles | compound_styles:
            self.add_style()
        else:
            raise MissingParser("MACRO %s : %s" % (macro, self.line_rest, ))

    def parse_request(self):
        split = self.line.lstrip().split(None, 1)
        strip_weird_tags = False

        self.line_request = split[0]

        if self.line_request == "BI":
            strip_weird_tags = True

        if len(split) == 2:
            self.line_rest = unescape(split[1], strip_weird_tags)
            self.line_rest_spaced = space_tags(self.line_rest)
        else:
            self.line_rest = ""
            self.line_rest_spaced = ""

        self.process_request()

    def add_text(self, text):
        append_text = text
        buffer_to_append = self.buff

        if self.in_pre:
            buffer_to_append = self.pre_buffer
            append_text = append_text.rstrip()
        elif self.list_state:
            buffer_to_append = self.list_buffer
        elif self.in_table:
            buffer_to_append = self.table_buffer
        elif self.def_state == 1:
            self.def_state = 2
            buffer_to_append = self.def_buffer
            if self.def_buffer:
                append_text = "</dd>\n  <dt>%s</dt>\n    <dd>" % text
            else:
                append_text = "\n  <dt>%s</dt>\n    <dd>" % text
        elif self.def_state == 2:
            buffer_to_append = self.def_buffer

        if append_text:
            buffer_to_append.append(append_text)

    def extract_title(self, content):
        title, subtitle = content.split('-', 1)
        self.title = title.strip()
        self.subtitle = subtitle.strip()

    def add_url(self):
        self.add_text("<a href=\"%s\">%s</a>" % (self.line_rest, self.line_rest,))

    def set_indent(self):
        if not self.line_rest:
            self.indent, self.prev_indent = (self.prev_indent, self.indent)
        else:
            macro_pattern = re.compile("^([+-]?)([\d\.]+).*$")
            sign, num = macro_pattern.search(self.line_rest).groups()
            if sign == '-':
                num = - float(num)
            else:
                num = float(num)

            self.prev_indent, self.indent = self.indent, num

    def start_table(self):
        self.in_table = True

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

    def start_pre(self):
        self.in_pre = True

    def end_pre(self):
        if self.in_pre:
            self.in_pre = False
            self.add_text("\n<pre>%s</pre>" % "\n".join(self.pre_buffer))
            self.pre_buffer = []

    def start_list(self):
        if len(toargs(self.line_rest)):
            if self.list_state:
                self.list_full_buffer.append("<li>%s</li>\n" % " ".join(self.list_buffer).rstrip())
                self.list_buffer = []
            else:
                self.list_state = True
        else:
            # FIXME
            # parse_P(macro, extra, manpage)
            self.add_text("<p class=\"inner\">")

    def end_list(self):
        if self.list_state:
            if self.list_buffer:
                self.list_full_buffer.append("<li>%s</li>\n" % " ".join(self.list_buffer))
                self.list_buffer = []

            self.list_state = False
            self.add_text("\n<ul>%s</ul>\n" % " ".join(self.list_full_buffer))
            self.list_full_buffer = []

    def start_def(self):
        self.def_state = 1

    def end_def(self):
        if self.def_state > 0:
            self.def_state = 0
            self.add_text("\n<dl class=\"dl-vertical inner\">%s</dl>\n" %
                          " ".join(self.def_buffer))
            self.def_buffer = []

    def flush_section(self):
        if self.current_section == "NAME":
            self.extract_title(" ".join(self.buff))
        else:
            self.sections_content.append(
                (self.current_section, " ".join(self.buff), )
            )
        self.buff = []

    def add_style(self):
        style = self.line_request
        if style in single_styles:
            self.add_text(stylize(style, " ".join(toargs(self.line_rest))))
        elif style in compound_styles:
            self.add_text(stylize_odd_even(
                style, toargs(self.line_rest_spaced)))

    def add_section(self):
        self.end_pre()
        if self.current_section != "":
            self.flush_section()

        self.current_section = self.line_rest

    def add_subsection(self):
        # FIXME: Probably we should store a tree for having an index

        self.add_text("\n<h3>%s</h3>\n<p>" % self.line_rest)

    def set_header(self):
        params = toargs(self.line_rest)

        self.header = {
            "title": params[0],
            "section": params[1],
            "date": params[2]
        }

    def html(self):
        #sidebar_tpl = load_template('sidebar')
        header_tpl = load_template('header')
        #nav_tpl = load_template('nav')
        #sidebaritem_tpl = load_template('sidebaritem')
        breadcrumb_tpl = load_template('breadcrumb')
        #content_tpl = load_template('manpage-content')

        section_tpl = load_template('section')

        section_contents = ""
        for title, content in self.sections_content:
            section_contents += section_tpl.safe_substitute(
                title=title,
                content=content,
            )

        base_tpl = load_template('base')

        title, section = self.manpage_name.rsplit('.', 1)

        return base_tpl.safe_substitute(
            # TODO: Fix canonical, nav, breadcrumb
            canonical="",
            nav="",
            breadcrumb=breadcrumb_tpl.substitute(
                section=section,
                section_name=SECTIONS["man" + section],
                manpage=title,
            ),
            title="%s - %s" % (self.title, self.subtitle, ),
            header=header_tpl.substitute(
                section=section,
                title=title,  # FIXME: Mess
                subtitle=self.subtitle,
            ),
            content=section_contents,
        )


def space_tags(text_to_space):
    # TODO: Fix dirty hack for shlex (getent.1 first BR)
    spaced_rest = text_to_space.replace('<em>', ' <em>')
    spaced_rest = spaced_rest.replace('</em>', '</em> ')
    spaced_rest = spaced_rest.replace('<strong>', ' <strong>')
    spaced_rest = spaced_rest.replace('</strong>', '</strong> ')

    return spaced_rest


def load_template(template):
    fp = open("templates/%s.tpl" % (template, ))
    out = Template(''.join(fp.readlines()))
    fp.close()
    return out


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


def unescape(t, strip_weird_tags=False):
    t = t.replace("\-", "-")
    t = t.replace("\ ", "&nbsp;")
    #t = t.replace("\%", "")
    t = t.replace("\:", "")
    #t = t.replace("\}", "")

    #t = t.replace("\`", "`")
    # t = t.replace("\&", " ")  # FIXME: Might need tweaking
    t = t.replace("\\\\", "&#92;")

    # t = t.replace("\[char46]", "&#46;")
    t = t.replace("\\(em", "&ndash;")
    #t = t.replace("\\(en", "&ndash;")

    #t = t.replace("\\*(lq", "&ldquo;")
    #t = t.replace("\\*(rq", "&rdquo;")

    # FIXME: make fancy quotes
    t = t.replace("\\(aq", "'")

    #t = t.replace("\\*(dg", "(!)")
    #t = t.replace("\\e", "\\")

    # Preserve < >
    t = t.replace("<", "&lt;").replace(">", "&gt;")

    # Fixme (when we have time dir_colors.5 shows why this needs fixing)
    t = re.sub(
        r'\\fI(.*?)\\f[PR]',
        r'<em>\1</em>',
        t)

    t = re.sub(
        r'\\fB(.*?)\\f[PR]',
        r'<strong>\1</strong>',
        t)

    # t = re.sub(
    # r'\\f\(CW(.*?)\\fP',
    # r'<strong>\1</strong>',
    # t)

    if strip_weird_tags:
        # FIXME: This is ugly (zdump is broken on BI)
        t = t.replace("\\fB", "")
        t = t.replace("\\fI", "")
        t = t.replace("\\fR", "")

    return t


def toargs(extra):
    try:
        args = shlex.split(extra)
    except:
        try:
            args = shlex.split(extra + "\"")
        except:
            try:
                args = shlex.split(extra + "'")
            except:
                raise

    return args


class MissingParser(Exception):
    pass

if __name__ == '__main__':
    manpage = ManPage(sys.argv[1])

    print manpage.html()
