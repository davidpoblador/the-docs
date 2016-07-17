#!/usr/bin/env python

import logging
import shlex
import sys

current_module = sys.modules[__name__]

class Section(object):
    def __init__(self, name):
        self.name = name
        self.contents = []

class SubSection(Section):
    pass

class ManPage(object):
    """docstring for ManPage"""
    def __init__(self, filename):
        self.filename = filename
        self.c = 0

        self.header = None

        self.sections = []
        self.current_section = self.current_pointer = None

    def set_counter(self, c):
        self.c = c

    def set_header(self, name, section):
        logging.info("Setting header for %s: %s %s", self.filename, name, section)
        if self.header:
            raise Exception
        else:
            self.header = (name, section)

    def add_section(self, name):
        self.flush_section()
        self.current_section = Section(name)
        self.current_pointer = self.current_section.contents

    def add_subsection(self, name):
        self.current_section.contents.append(SubSection(name))
        self.current_pointer = self.current_section.contents[-1].contents

    def flush_section(self):
        if self.current_section:
            self.sections.append(self.current_section)
            self.current_section = self.current_pointer = None

    def has_header(self):
        return bool(self.header)

    def add(self, data):
        self.current_pointer.append(data)

    
class Parser(object):
    """docstring for Parser"""
    cc = set([".", "'"])

    def __init__(self, lines, manpage, counter = -1):
        self.lines = lines
        self.size = len(self.lines)
        self.mp = manpage
        self.c = self.initial_c = counter
        self.c_delta = None
        logging.info("Instantiating %s" % (self.__class__.__name__, ))
        self.contents = []

    def parse(self):
        if type(self) == Parser:
            logging.info("Starting parsing of %s" % (self.mp.filename, ))

        while self.c_delta is None:
            # Increment line
            self.c += 1

            if self.c == self.size:
                break

            l = self.lines[self.c]

            logging.debug("LINE [%s] (%s): %s", self.__class__.__name__, self.c, l)

            # Remove comments
            l = l.split("\\\"", 1)[0]
            if l == '.': # Comment
                logging.debug("Comment")
                continue

            macro = None
            args = []

            if not l:
                # Empty
                logging.info("Request %s", l)
            elif l[0] in self.cc:
                chunks = l[1:].lstrip().split(None, 1)
                macro = chunks[0]
                if len(chunks) == 2:
                    args = toargs(chunks[1])

                parser = getattr(self, "p_%s" % macro, None)
                if not callable(parser):
                    #raise MissingParser("Missing parser: %s [LINE: %s]" % (macro, l, ))
                    pass
                else:
                    parser(args)
            else:
                # Data only line
                self.add(l)

            # Request
            #logging.info("Request macro: %s data: %s", macro, args)

        if self.c_delta is not None:
            logging.info("Ending parsing in %s" % (self.__class__.__name__,))
            c = (self.c - self.initial_c) + self.c_delta # Return new c delta
            return (c, self.contents)
        else: # Probably this can happen in the SectionParser
            self.mp.flush_section()
            return self.c

    def p_TH(self, args):
        if self.mp.has_header(): raise
        self.mp.set_header(args[0], args[1])

    def p_SH(self, args):
        print "HOLA", args
        _ = self.sub_parse("SectionParser", args)

    def sub_parse(self, parser, *args):
        parser = getattr(current_module, parser)
        c, contents = parser(lines = self.lines, manpage = self.mp, counter = self.c, *args).parse()
        self.c += c
        return contents

    def add(self, line):
        raise Exception("Must be reimplemented")

class SectionParser(Parser):
    """docstring for SectionParser"""
    def __init__(self, *args, **kwargs):
        super(SectionParser, self).__init__(**kwargs)
        if not self.mp.has_header(): raise

        name = args[0]
        if not name:
            raise Exception("Empty argument list in SH")

        self.mp.add_section(' '.join(name))

    def add(self, data):
        self.mp.add(data)

    def p_SH(self, args):
        self.mp.flush_section()
        self.c_delta = -1

    def p_SS(self, args):
        self.c_delta = 0
        contents = self.sub_parse("SubSectionParser", args)
        print "HOLA", contents

    def p_I(self, args):
        if len(args) > 1:
            raise

        if args:
            self.add(args[0])

    def p_multi_styles(self, args):
        self.add(" ".join(args))

    p_IR = p_BR = p_multi_styles

    def p_TP(self, args):
        self.contents.append(self.sub_parse("TPSectionParser", args))

    def p_RS(self, args):
        self.contents.append(self.sub_parse("RSSectionParser", args))

    def p_RE(self, data):
        self.c_delta = 0

class SubSectionParser(SectionParser):
    def __init__(self, *args, **kwargs):
        super(SectionParser, self).__init__(**kwargs) # Calling parent of SectionParser

        name = args[0]
        if not name:
            raise Exception("Empty argument list in SS")

        self.mp.add_subsection(' '.join(name))

class TPSectionParser(SectionParser):
    def __init__(self, *args, **kwargs):
        super(SectionParser, self).__init__(**kwargs) # Calling parent of SectionParser
        self.contents = []
        self.pointer = None

    def p_TP(self, args):
        self.pointer = None

    def add(self, data):
        if self.pointer is None:
            self.contents.append([data, []])
            self.pointer = self.contents[-1][1]
        else:
            self.pointer.append(data)

class RSSectionParser(SectionParser):
    def __init__(self, *args, **kwargs):
        super(SectionParser, self).__init__(**kwargs) # Calling parent of SectionParser
        self.contents = []

    def add(self, data):
        self.contents.append(data)

class MissingParser(Exception):
    pass

# FIXME: Make it fast
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

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("manpage", help="the manpage to process")
    parser.add_argument("--log-level", help="choose log level")
    args = parser.parse_args()

    if args.log_level:
        log_level = getattr(logging, args.log_level.upper())
        logging.basicConfig(level=log_level)

    filename = args.manpage
    manpage = ManPage(filename)

    with open(filename) as fp:
        lines = [line.rstrip() for line in fp]

    c = Parser(lines = lines, manpage = manpage).parse()

    logging.info("Parsed %s lines", c)


