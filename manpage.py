#!/usr/bin/env python

import shlex
import re
from string import Template
import sys

cc = ("'", ".")
single_styles = {'B', 'I'}
compound_styles = {'IR', 'RI', 'BR', 'RB', 'BI', 'IB'}

style_trans = {
    'I': 'em',
    'B': 'strong',
}

class ManPage(object):
    def __init__(self, manfile, section = 0):
        self.title = ""
        self.subtitle = ""
        
        self.current_section = ""

        self.buff = []
        self.sections_content = []
        self.list_state = 0
        self.in_pre = False
        self.list_buffer = []
        self.pre_buffer = []

        self.header = {
            "title" : "",
            "section" : "",
            "date" : "",
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
            else:
                self.line = line
                # TODO: Text lines can be comments:
                # https://www.gnu.org/software/groff/manual/html_node/Comments.html#index-_005c_0022
                self.add_text(unescape(line))

        self.flush_section()

    def process_request(self):
        macro = self.line_request

        if macro == '\\"':
            # Comment
            pass
        elif macro in {'LP', 'PP', 'P'}:
            self.end_list()
            self.add_text("<p>")
        elif macro == 'nf':
            self.start_pre()
        elif macro == 'fi':
            self.end_pre()
        elif macro in {'br'}:
            if not self.in_pre:
                self.add_text("<br>")
        elif macro in {'sp'}:
            if self.in_pre:
                self.add_text("\n")
            else:
                self.add_text("<p>")
        elif macro == 'TP':
            self.start_list()
        elif macro == 'RS':
            self.add_text("\n<p class=\"inner\">")
        elif macro == 'RE':
            self.add_text("</p>")
        elif macro == 'TH':
            self.set_header()
        elif macro == 'SH':
            self.end_list()
            self.add_section()
        elif macro in single_styles|compound_styles:
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

        if self.in_pre == True:
            buffer_to_append = self.pre_buffer
            append_text = append_text.rstrip()
        elif self.list_state == 1:
            self.list_state = 2
            buffer_to_append = self.list_buffer
            append_text = "\n  <dt>%s</dt>\n    <dd>" % text
        elif self.list_state == 2:
            buffer_to_append = self.list_buffer

        buffer_to_append.append(append_text)

    def extract_title(self, content):
        title, subtitle = content.split('-', 1)
        self.title = title.strip()
        self.subtitle = subtitle.strip()

    def start_pre(self):
        self.in_pre = True

    def end_pre(self):
        if self.in_pre == True:
            self.in_pre = False
            self.add_text("\n<pre>%s</pre>" % "\n".join(self.pre_buffer))
            self.pre_buffer = []

    def start_list(self):
        self.list_state = 1

    def end_list(self):
        if self.list_state > 0:
            self.list_state = 0
            self.add_text("\n<dl class=\"dl-vertical inner\">%s</dl>\n" % " ".join(self.list_buffer))
            self.list_buffer = []

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
            self.add_text(stylize_odd_even(style, toargs(self.line_rest_spaced)))

    def add_section(self):
        if self.current_section != "":
            self.flush_section()

        self.current_section = self.line_rest

    def set_header(self):
        params = toargs(self.line_rest)

        self.header = {
            "title" : params[0],
            "section" : params[1],
            "date" : params[2]
        }

    def html(self):
        #sidebar_tpl = load_template('sidebar')
        header_tpl = load_template('header')
        #nav_tpl = load_template('nav')
        #sidebaritem_tpl = load_template('sidebaritem')
        #breadcrumb_tpl = load_template('breadcrumb')
        #content_tpl = load_template('manpage-content')

        section_tpl = load_template('section')

        section_contents = ""
        for title, content in self.sections_content:
            section_contents += section_tpl.safe_substitute(
                title = title,
#                content = linkify(content),
                content = content,
                )

        base_tpl = load_template('base')

        return base_tpl.safe_substitute(
            # TODO: Fix canonical, nav, breadcrumb
            canonical = "",
            nav = "",
            breadcrumb = "",
            title = "%s - %s" % (self.title, self.subtitle, ),
            header = header_tpl.substitute(
                section = self.header['section'],
                title = self.title,
                subtitle = self.subtitle,
                ),
            content = section_contents,
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
        buff += stylize(style[c%2], arg)
        c = c + 1

    return buff

def unescape(t, strip_weird_tags = False):
    t = t.replace("\-", "-")
    t = t.replace("\ ", "&nbsp;")
    #t = t.replace("\%", "")
    #t = t.replace("\:", "")
    #t = t.replace("\}", "")

    #t = t.replace("\`", "`")
    #t = t.replace("\&", " ")  # FIXME: Might need tweaking
    t = t.replace("\\\\", "&#92;")

    #t = t.replace("\[char46]", "&#46;")
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

    #t = re.sub(
        #r'\\f\(CW(.*?)\\fP',
        #r'<strong>\1</strong>',
        #t)

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
