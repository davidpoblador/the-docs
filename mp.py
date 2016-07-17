#!/usr/bin/env python

import logging
import shlex
import sys
from pprint import pprint

current_module = sys.modules[__name__]

class Parser(object):
    cc = {'\'', '.'}
    ignored = {'PD', 'in', 'ft', 'sp'}

    def __init__(self, file):
        self.file = file
        self.content = []
        self.pointer = None
        self.section_pointer = None

    def line(self):
        c = 0
        with open(self.file) as fp:
            for line in fp:
                c += 1

                l = self.process_raw_line(c, line.rstrip())
                if not l:
                    continue

                yield l

    @classmethod
    def process_raw_line(cls, c, line):
            macro = data = None
            comment = False

            if "\\\"" in line:
                l = line.split("\\\"",1)[0]
            else:
                l = line

            if l and l[0] in cls.cc:
                if len(l) == 1:
                    # Full Comment Line
                    logging.debug("(%s): Comment: %s", c, line)
                    comment = True
                else:
                    # Macro
                    chunks = l[1:].lstrip().split(" ", 1)
                    if len(chunks) == 2:
                        # With arguments
                        data = chunks[1]

                    macro = chunks[0]

                    logging.debug("(%s): Macro (%s) Args: %s", c, macro, data)
            elif l:
                data = l
                logging.debug("(%s): Data: %s", c, l)
            else:
                data = ""
                logging.debug("(%s): Empty", c)
                # Empty line

            if not comment:
                return (c, line, macro, data)
            else:
                return False

    def parse(self):
        self.lines = list(self.line())

        for i, (c, line, macro, data) in enumerate(self.lines):
            self.cl = tuple()

            add_to_buffer = None

            logging.info("(%s/%s): (%s) %s", i, c, macro, data)
            if macro:
                if macro not in self.ignored:
                    if data:
                        args = toargs(data)
                    else:
                        args = tuple()
                    p = getattr(self.__class__, "p_%s" % macro, None)
                    s = getattr(self.__class__, "s_%s" % macro, None)
                    if not p and not s:
                        raise MissingParser("Missing parser for macro (%s) (line(%s): %s)" % (macro, c, line))
                    elif p:
                        self.cl = (i, macro, args, add_to_buffer)
                        p(self)
                    elif s:
                        self.cl = (i, macro, args, add_to_buffer)
                        d = s(self)
                        if d: # Should not be necessary
                            add_to_buffer = d
                        else:
                            print "DEBUG", line
                            raise Exception("Empty content in style macro")
                    else:
                        raise Exception("Impossible case")
            else:
                # Only data
                add_to_buffer = data
                args = (data, )
                self.cl = (i, macro, args, add_to_buffer)

            if add_to_buffer:
                self.p_text()

    # Line Properties
    @property
    def macro(self):
        return self.cl[1]
    
    @property
    def args(self):
        return self.cl[2]

    @property
    def data(self):
        return " ".join(self.args)
    
    @property
    def text(self):
        return self.cl[3]

    @property
    def i(self):
        return self.cl[0]

    # Header
    def p_TH(self):
        print "HOLA", self.cl
        pass

    # Sections
    def p_SH(self):
        section = Section(self.data)
        self.content.append(section)

        self.clean_state()

        self.add = section.add
        self.current = type(section)

    def p_SS(self):
        subsection = Subsection(self.data)
        self.add(subsection)

        self.clean_state()

        self.add = subsection.add
        self.current = type(subsection)

    ## Bullets
    def p_TP(self):
        if self.current != DefinitionList:
            definition_list = DefinitionList()
            self.add(definition_list)
            self.current = type(definition_list)
            self.add = definition_list.add

        #self.get_next_line()
        next_line = self.lines[self.i+1][1]
        #print "NEXT", self.process_line(None, next_line)
        #print "NEXT", self.process_line(None, self.lines[self.i+1])

        self.add(bullet = "**")
            # first

    #def p_IP(self):
    #    pass
#
    ## Indentation
    def p_RS(self):
        rs_section = RSSection()
        self.add(rs_section)
        self.save_state()

        self.current = type(rs_section)
        self.add = rs_section.add
#
    def p_RE(self):
        self.restore_state()
#
    ## Preformatted text
    #def p_nf(self):
    #    pass
#
    #def p_fi(self):
    #    pass
#
    ## Paragraphs and line breaks
    #def p_br(self):
    #    pass

    # Styles
    def s_simple_style(self):
        return self.data

    def s_compound_style(self):
        return self.data

    # Plain text
    def p_text(self):
        self.add(self.data)

    s_I = s_B = s_simple_style
    s_IR = s_RI = s_BR = s_RB = s_compound_style

    def save_state(self):
        self.state.append((self.current, self.add))

    def restore_state(self):
        self.current, self.add = self.state.pop(-1)

    def clean_state(self):
        self.state = []

class MissingParser(Exception):
    pass

class Section(object):
    def __init__(self, name):
        self.name = name
        self.content = []

    def add(self, content):
        self.content.append(content)

    def __repr__(self):
        return "SECTION: %s: %s" % (self.name, self.content, )

class Subsection(Section):
    def __repr__(self):
        return "SUBSECTION: %s: %s" % (self.name, self.content, )

class DefinitionList(object):
    def __init__(self):
        self.content = []

    def add_bullet(self, bullet):
        self.content.append([bullet, []])
        self.pointer = self.content[-1][1]

    def add(self, content = None, bullet = "*"):
        if content:
            self.pointer.append(content)
        elif bullet:
            self.add_bullet(bullet)
        else:
            raise

class RSSection(object):
    def __init__(self):
        self.content = []

    def add(self, content):
        self.content.append(content)

# FIXME: Make it fast
def toargs(data):
    def tokenize():
        lexer = shlex.shlex(data, posix=True)
        lexer.commenters = ''
        lexer.quotes = "\""
        lexer.whitespace_split = True
        return tuple(lexer)

    try:
        args = tokenize()
    except:
        data += "\""
        try:
            args = tokenize()
        except:
            raise

    return args

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("manpage", help="the manpage to process")
    parser.add_argument("--log-level", help="choose log level")
    args = parser.parse_args()

    if args.log_level:
        log_level = getattr(logging, args.log_level.upper())
        logging.basicConfig(stream=sys.stdout, level=log_level)

    p = Parser(args.manpage)
    p.parse()

    pprint(p.content)

