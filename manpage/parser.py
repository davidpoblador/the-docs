#!/usr/bin/env python
"""Man Page Parse Module"""

import time
import logging
import argparse
import os.path

from helpers import unescape, entitize
from helpers import consume, tokenize
from string import Template

from manpage import Manpage, Section, SubSection, BulletedList, DefinitionList
from manpage import Container, IndentedBlock, PreformattedBlock, Table
from manpage import Url, Mailto

try:
    import re2 as re
except ImportError:
    import re


class Line(object):
    cc = '.'
    c2 = '\''
    ec = '\\'

    comment = ec + '"'


class CustomMacros(object):
    def __init__(self):
        self.macros = dict()
        self.current_macro = None
        pass

    def add_line(self, line):
        self.macros[self.current_macro].append(line)

    def add_macro(self, macro):
        self.macros[macro] = []
        self.current_macro = macro


class Macro(object):
    single_style = {'B', 'I', 'SM', 'R'}
    compound_style = {'BI', 'BR', 'IR', 'RI', 'RB', 'IB', 'SB'}

    styles = single_style | compound_style

    conditional = {'if', 'ie', 'el'}

    ignore = {
        # Tabulation crap
        "ta",
        "DT",
        # Page break stuff
        "ne",
        "pc",
        "bp",
        # Temporary
        "in",
        # Man7 specific
        "UC",
        "PD",
        # Font. FIXME
        "ft",
        "fam",
        "ul",
        "ps",
        "ns",
        "bd",
        # Margin adjustment
        "ad",
        "ll",
        # Others,
        "nh",
        "hy",
        "IX",
        "ev",
        "nr",
        # Probably FIX (paragraph)
        "HP",
        "ti",
        "rs",
        "na",
        "ce",
        "Op",
        "Vb",
        "Ve",
        # Fix IF
        "ds",
        "tr",
        # Author...
        "BY",
        # Crap
        "\{{{}}}",
        "it",
        "zZ",
        "zY",
        "rm",
        "Sp",
        # grep.in.i has lots of weird things
        "MTO",
        "URL",
    }

    vertical_spacing = {
        # Kind of new paragraph
        "sp",
        "br",
    }

    new_paragraph = {'PP', 'P', 'LP'}

    style_tpl = {
        "SM": Template("<small>${content}</small>"),
        "S": Template("<small>${content}</small>"),
        "I": Template("<em>${content}</em>"),
        "B": Template("<strong>${content}</strong>"),
        "R": Template("${content}"),
    }


class RedirectedPage(Exception):
    def __init__(self, page, redirect):
        message = "Page %s redirects to %s" % (page,
                                               redirect, )
        self.redirect = redirect

        super(RedirectedPage, self).__init__(message)


class UnexpectedMacro(Exception):
    def __init__(self, parser, macro, args, file=""):
        message = "Missing Macro (%s) in parser (%s) in file (%s)" % (macro,
                                                                      parser,
                                                                      file, )
        super(UnexpectedMacro, self).__init__(message)


class NotSupportedFormat(Exception):
    def __init__(self, file):
        message = "Not Supported Format in file (%s)" % (file, )

        super(NotSupportedFormat, self).__init__(message)


class FileMacroIterator(object):
    def __init__(self, fp):
        self.lines = fp.readlines()
        self.current = 0
        self.high = len(self.lines)
        self.buffered_lines = []

    def __iter__(self):
        return self

    def __next__(self):  # Compatibility with python 3
        return self.next()

    def next(self):
        if self.buffered_lines:
            return self.buffered_lines.pop(0)
        elif self.current == self.high:
            raise StopIteration
        else:
            self.current += 1
            return self.lines[self.current - 1]

    def add_lines(self, lines):
        self.buffered_lines = lines


class ManpageParser(object):
    """Man Page Parser Class"""

    def __init__(self, path):
        basename = os.path.basename(path)

        self.name, ext = os.path.splitext(basename)

        self.numeric_section = ext[1:]
        self._path = path
        self.lines = []
        self.parser = None
        self.custom_macros = CustomMacros()

        self.readfile()

    def stylize(self, macro, args):
        if macro in Macro.single_style:
            return Macro.style_tpl[macro].substitute(content=' '.join(args))
        elif macro in Macro.compound_style:
            out = []
            for i, chunk in enumerate(args):
                style = Macro.style_tpl[macro[i % 2]]
                out.append(' '.join([style.substitute(content=subchunk)
                                     for subchunk in chunk.replace(
                                         '\t', ' ').split(' ')]))

            return ''.join(out)
        else:
            raise UnexpectedMacro("STYLE", macro, args, self.path)

    def url(self, data):
        if re.match(r"[^@]+@[^@]+\.[^@]+", data):
            return "<a href=\"mailto:%s\">%s</a>" % (data,
                                                     data, )
        else:
            return "<a href=\"%s\">%s</a>" % (data,
                                              data, )

    def mailto(self, data):
        return "<a href=\"mailto:%s\">%s</a>" % (data,
                                                 data, )

    @property
    def path(self):
        """ self.path property """
        return self._path

    def readfile(self):
        with open(self.path) as fp:
            extra = []
            iterator = FileMacroIterator(fp)
            for line in iterator:
                line = line.rstrip()

                if line and len(line) > 2:
                    if line[-1] == "\\":
                        if line[-2] != "\\" and line[-2] != "{":
                            extra.append(line[:-1])
                            continue
                    elif line[-2:] == "\\c":
                        extra.append(line[:-2])
                        continue

                if extra:
                    extra.append(line)
                    line = ' '.join(extra)
                    extra = []

                # Fix exception in tc-flower.8
                if line == '.splitfont':
                    line = 'splitfont'

                if Line.comment in line:
                    # Line has comment
                    line = line.split(Line.comment, 1)[0]

                if line == Line.cc or line == Line.c2 or line == '\'.':
                    # Empty line (cc or c2)
                    continue

                if not line:
                    # Empty line
                    self.lines.append(('', ''))
                    continue

                if line[0] in {Line.cc, Line.c2}:
                    chunks = line[1:].lstrip().split(None, 1)

                    if not chunks:
                        # Very special case lvm2create_initrd.8
                        continue

                    macro = chunks[0]

                    if macro == '"':
                        # Bug in run.1
                        continue

                    if macro == 'b':
                        # Bug in devlink-sb.8
                        macro = 'B'

                    if macro in self.custom_macros.macros:
                        iterator.add_lines(self.custom_macros.macros[macro])
                        continue

                    if len(chunks) == 2:
                        rest = chunks[1]
                    else:
                        rest = ""

                    if macro == 'so':
                        raise RedirectedPage(self.path, rest)

                    if line.startswith(".el\\{\\"):
                        # There is a lot of crap in pages (isag.1, for instance)
                        macro = "el"
                        rest = "\\{\\" + rest

                    if macro in Macro.conditional:
                        # FIXME: This needs reworking
                        braces = 0

                        if "\\{" in rest:
                            braces += 1

                        while braces:
                            macro_line = next(iterator)
                            if "\\{" in macro_line:
                                braces += 1

                            if "\\}" in macro_line:
                                braces -= 1

                            if not braces:
                                break

                        continue

                    if self.parser is None:
                        if macro == "TH":
                            self.parser = ManpageParser.process_man7
                        elif macro == "Dd":
                            self.parser = False

                    if macro == 'ig':
                        while True:
                            macro_line = next(iterator)
                            if macro_line.rstrip() == "..":
                                break

                        continue

                    if macro in {'de', 'de1'}:
                        self.custom_macros.add_macro(rest.strip())
                        while True:
                            macro_line = next(iterator)
                            if macro_line.rstrip() == "..":
                                break
                            else:
                                self.custom_macros.add_line(macro_line)

                        continue

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

    def process(self, *args, **kwargs):
        if self.parser is None:
            raise NotSupportedFormat(self.path)
        elif not callable(self.parser):
            raise NotSupportedFormat(self.path)

        return self.parser(self, *args, **kwargs)

    def process_man7(self, start=0, parser="ROOT"):
        content = None
        iter = enumerate(self.lines[start:])
        for i, (macro, args) in iter:
            logging.debug("LINE (CP: %s): (%s: %s) [%s]", parser, macro, args,
                          repr(content))
            #print ">> %s" % (content,)

            if parser == "ROOT":
                if not content:
                    content = Manpage(
                        name=self.name,
                        section=self.numeric_section)

                # ROOT
                if macro == 'TH':
                    continue  # FIXME
                elif macro == 'SH':
                    inc, section_content = self.process(start + i, 'SECTION')
                    content.append(section_content)
                    consume(iter, inc)
                    continue
                elif macro == 'SS':
                    inc, section_content = self.process(start + i,
                                                        'SS-SECTION')
                    content.append(section_content)
                    consume(iter, inc)
                    continue
                elif macro:
                    raise UnexpectedMacro(parser, macro, args, self.path)
                elif not macro:
                    continue
            else:
                if macro in Macro.styles:
                    args = self.stylize(macro, args)
                    macro = ''
                elif macro in {'CW'}:
                    macro = ''
                    args = ' '.join(args)

                if parser == 'SECTION':
                    if macro == 'SH':
                        if content is None:
                            content = Section()
                            content.title = ' '.join(args)
                            continue
                        else:
                            return i - 1, content
                    elif macro in {'RS', 'IP'} and content.title == "NAME":
                        # Very nasty bug in yum-copr.8
                        continue
                    elif macro in {'RE', 'fi'}:
                        # Plenty of pages with bugs
                        continue
                if parser == 'SS-SECTION':
                    if macro == 'SS':
                        if content is None:
                            content = Section()
                            content.title = ' '.join(args)
                            continue
                        else:
                            return i - 1, content
                    elif macro in {'RE', 'fi'}:
                        # Plenty of pages with bugs
                        continue
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
                    elif macro in {'RE'}:
                        # This is to fix a bug in proc.5 FIXME
                        continue
                elif parser == 'RS-RE':
                    if content is None:
                        content = IndentedBlock()
                        continue

                    if macro == 'RE':
                        return i, content
                    elif macro in {'SH', 'SS'}:
                        return i - 1, content
                    elif macro in {'fi'}:
                        # This is to fix a bug in proc.5 FIXME
                        return i - 1, content
                elif parser == 'EXAMPLE':
                    if content is None:
                        content = PreformattedBlock()
                        continue

                    if macro == 'EE':
                        return i, content
                    elif macro in {'nf', 'fi'}:
                        continue
                    elif macro:
                        raise UnexpectedMacro(parser, macro, args, self.path)
                elif parser == 'PRE':
                    if content is None:
                        content = PreformattedBlock()
                        continue

                    if macro == 'fi':
                        return i, content
                    elif macro in {'SH', 'SS', 'RE'}:
                        return i - 1, content
                    elif macro in Macro.new_paragraph:
                        pass
                    elif macro in {'RS', 'TP', 'IP', 'nf'}:
                        # This is to fix a bug in proc.5 and many others
                        continue
                    elif macro:
                        raise UnexpectedMacro(parser, macro, args, self.path)
                elif parser == 'TP':
                    if content is None:
                        content = DefinitionList()

                    if macro == 'TP':
                        content.add_bullet()
                        continue
                    elif macro == 'TQ':
                        content.expect_bullet()
                        continue
                    elif macro in {'SH', 'SS', 'RE'}:
                        return i - 1, content
                    elif macro in {'IP', 'RS', 'nf', 'TS', 'UR', 'EX'}:
                        pass
                    elif macro in {'fi'}:
                        continue
                    elif macro in Macro.new_paragraph:
                        return i - 1, content
                    elif macro:
                        raise UnexpectedMacro(parser, macro, args, self.path)
                elif parser == 'IP':
                    if content is None:
                        content = BulletedList()

                    if macro == 'IP':
                        content.add_bullet(args)
                        continue
                    elif macro in {'SH', 'SS', 'RE'}:
                        return i - 1, content
                    elif macro in Macro.new_paragraph:
                        return i - 1, content
                    elif macro == 'TP':
                        return i - 1, content
                    elif macro in {'RS', 'nf', 'TS', 'UR'}:
                        pass
                    elif macro:
                        raise UnexpectedMacro(parser, macro, args, self.path)
                elif parser == 'TABLE':
                    if content is None:
                        content = Table()
                        continue

                    if macro == 'TE':
                        return i, content
                    elif macro in {'nf', 'fi', 'IP'}:
                        # Errors, errors...
                        continue
                elif parser == 'MAILTO':
                    # FIXME: Missing processor
                    if content is None:
                        content = Mailto()
                        continue

                    if macro == 'ME':
                        return i, content
                elif parser == 'URL':
                    # FIXME: Missing processor
                    if content is None:
                        content = Url()
                        continue

                    if macro == 'UE':
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
                elif macro == 'EX':
                    inc, ex_content = self.process(start + i, 'EXAMPLE')
                    content.append(ex_content)
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
                elif macro == 'MT':
                    inc, mt_content = self.process(start + i, 'MAILTO')
                    content.append(mt_content)
                    consume(iter, inc)
                elif macro == 'UR':
                    inc, ur_content = self.process(start + i, 'URL')
                    content.append(ur_content)
                    consume(iter, inc)
                else:
                    raise UnexpectedMacro(parser, macro, args, self.path)
        else:
            if parser == 'ROOT':
                content.pre_process()
                return content

            return None, content


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
