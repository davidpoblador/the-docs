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

class UnexpectedMacro(Exception):
    def __init__(self, parser, macro, args):
        message = "Missing Macro (%s) in parser (%s)" % (macro, parser, )
        super(UnexpectedMacro, self).__init__(message)

def stylize(macro, args):
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
        raise UnexpectedMacro("STYLE", macro, args)

class ManpageParser(object):
    """Man Page Parser Class"""

    def __init__(self, path):
        basename = os.path.basename(path)

        self.name, ext = os.path.splitext(basename)

        self.numeric_section = ext[1:]
        self._path = path
        self.lines = []

        self.readfile()

    @property
    def path(self):
        """ self.path property """
        return self._path

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
                    raise UnexpectedMacro(parser, macro, args)
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
                        raise UnexpectedMacro(parser, macro, args)
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
                        raise UnexpectedMacro(parser, macro, args)
                elif parser == 'TABLE':
                    if content is None:
                        # FIXME We need a proper parser for tables
                        content = Table()
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
                    raise UnexpectedMacro(parser, macro, args)
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
