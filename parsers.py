import shlex
import itertools

from repoze.lru import lru_cache

try:
    import re2 as re
except ImportError:
    import re

from base import load_template, get_pagination
from base import MissingParser, NotSupportedFormat, RedirectedPage, UnexpectedState


class MacroParser(object):
    # FIXME
    # Revisit ME
    macros_to_ignore = {
        'ad',
        'PD',
        'nh',
        'hy',
        'HP',
        'UE',
        'ft',
        'fam',
        'ne',
        'UC',
        'nr',
        'IX',
        'fi',
        'ns',
        'ds',
        'na',
        'DT',
        'bp',
        'nr',
        'll',
        'c2',
        'ps',
        'ta',
        'in',
        'ME',
        'tr',
        'ti',
    }

    def __init__(self, line, manpage):
        self.data = line.data
        self.macro = line.macro
        self.comment = line.comment
        self.manpage = manpage

    def state(self, state):
        self.manpage.set_state(state)

    def skip_until(self, items):
        while not self.manpage.lines.get().data in items:
            pass

    def skip_until_contains(self, item):
        #while not item in self.manpage.lines.get().data: pass
        while not self.manpage.lines.get().contains(item):
            pass

    def process(self):
        getattr(self, "p_%s" % self.macro, self.default)()

    def p_Dd(self):
        raise NotSupportedFormat

    def p_ig(self):
        self.skip_until({'..', '.end'})

    def p_de(self):
        self.skip_until({'..'})

    def p_if(self):
        if "{" in self.data:
            self.skip_until_contains('}')

    p_ie = p_if
    p_el = p_if

    def default(self):
        if self.comment:
            pass
        elif not self.macro:
            self.process_text()
        elif self.macro not in self.macros_to_ignore:
            self.missing_parser()

    def process_text(self):  # FIXME: Rewrite in body
        pass

    def consume_iterator(self, steps):
        next(itertools.islice(self.manpage.line_iterator, steps, steps), None)

    def split_iterator(self):
        self.manpage.line_iterator, tmp_iter = itertools.tee(
            self.manpage.line_iterator)
        return tmp_iter

    def missing_parser(self):
        raise MissingParser("MACRO %s : %s" % (self.macro,
                                               self.data, ))


class BodyMacroParser(MacroParser):
    def __bool__(self):
        return not bool(self.comment)

    __nonzero__ = __bool__

    def process(self):
        if self:
            if self.macro:
                self.manpage.blank_line = False

            super(BodyMacroParser, self).process()

    def process_text(self):
        if not self.data:
            self.p_spacer()
        elif self.manpage.in_table:
            self.manpage.table_buffer.append(self.unescaped_data)
        else:
            self.manpage.blank_line = False
            if self.unescaped_data.startswith(
                    " ") and not self.manpage.preserve_next_line and not self.manpage.in_pre:
                self.manpage.spaced_lines_buffer.append(self.unescaped_data)
            else:
                self.manpage.add_content(self.data)

    def p_SH(self):
        if not self.data:
            section = self.manpage.lines.get().data
        else:
            section = self.data

        self.manpage.add_section(section)

    def p_SS(self):
        if self.data:
            self.manpage.add_subsection(self.data)

    def p_SM(self):
        if self.data:
            # FIXME: Make font smaller
            self.manpage.add_content(self.data)

    def p_nf(self):
        self.manpage.start_pre()

    p_Vb = p_nf

    def p_fi(self):
        self.manpage.end_pre()

    p_Ve = p_fi

    def p_UR(self):
        self.manpage.add_url(self.unescaped_data)

    def p_MT(self):
        self.manpage.add_mailto(self.unescaped_data)

    def p_TS(self):  # Process table quickly
        self.manpage.in_table = True

    def p_TE(self):
        self.manpage.end_table()

    def p_IP(self):
        if self.manpage.in_li:
            self.manpage.add_text("</dd>", 2)
        self.manpage.process_li(self.unescaped_data)

    def p_bP(self):
        self.data = "\\(bu"
        self.p_IP()

    def p_RS(self):
        self.manpage.save_state()

    def p_RE(self):
        self.manpage.restore_state()

    def p_paragraph(self):
        self.manpage.flush_dl()
        self.manpage.flush_li()
        self.p_spacer()

    p_LP = p_paragraph
    p_PP = p_paragraph
    p_P = p_paragraph
    p_Sp = p_paragraph

    def p_TP(self):
        self.manpage.preserve_next_line = 1  # FIXME (now we can do better)
        if self.manpage.in_dl:
            self.manpage.add_text("</dd>", 2)

    def p_style(self):
        if self.data:
            self.manpage.add_content(self.manpage.add_style(self.macro,
                                                            self.data))

    # Simple styles
    p_I = p_style
    p_B = p_style

    # Compound styles
    p_BR = p_style
    p_RB = p_style
    p_BI = p_style
    p_IB = p_style
    p_IR = p_style
    p_RI = p_style

    def p_spacer(self):
        self.manpage.add_spacer()

    p_br = p_spacer
    p_sp = p_spacer

    @property
    def unescaped_data(self):
        return unescape(self.data)


class TitleMacroParser(MacroParser):
    def __bool__(self):
        return bool(not self.comment)

    def process(self):
        if self:
            super(TitleMacroParser, self).process()

    def p_SH(self):
        if self.joined_data == "NAME":
            name_section = []
            while True:
                line = self.manpage.lines.get()
                if line.data and not line.comment:
                    name_section.append(unescape(line.data))

                if self.manpage.lines.curr().macro == "SH":
                    break

            self.extract_title(name_section)
            self.manpage.set_state(ManPageStates.BODY)
        else:
            raise NotSupportedFormat

    @property
    def joined_data(self):
        return ' '.join(toargs(self.data))

    def extract_title(self,
                      title_buffer):  # FIXME: big format difference in ext2.5
        try:
            self.manpage.title, self.manpage.subtitle = map(
                str.strip, " ".join(title_buffer).split(' - ', 1))
        except:
            try:
                self.manpage.title, self.manpage.subtitle = map(
                    str.strip, " ".join(title_buffer).split(' -- ', 1))
            except:
                try:
                    self.manpage.title, self.manpage.subtitle = map(
                        str.strip, " ".join(title_buffer).split('-', 1))
                except:
                    raise NotSupportedFormat

        self.manpage.subtitle = self.manpage.subtitle.capitalize()


class HeaderMacroParser(MacroParser):
    def __bool__(self):
        if self.comment or not self.macro:
            return False
        else:
            return True

    __nonzero__ = __bool__

    valid_macros = ("TH", "so", "Dd")

    def p_TH(self):
        try:
            headers = toargs(self.data)

            self.manpage.header = {
                "title": headers[0],
                "section": headers[1],
            }
        except:
            raise NotSupportedFormat

        self.state(ManPageStates.TITLE)

    def p_so(self):
        chunks = self.data.split("/", 1)
        if len(chunks) == 1:
            base_dir, page = "", chunks[0]
        else:
            base_dir, page = chunks

        self.manpage._redirect = (base_dir,
                                  page, )

        raise RedirectedPage(
            "Page %s redirects to %s" %
            (self.manpage.filename, "/".join(self.manpage.redirect)))

    def process(self):
        if self.macro in self.valid_macros:
            super(HeaderMacroParser, self).process()


class ManPageStates(object):
    HEADER, TITLE, BODY = range(3)

    parser = {
        HEADER: HeaderMacroParser,
        TITLE: TitleMacroParser,
        BODY: BodyMacroParser,
    }


# Helper functions
def entitize(line):
    return line.replace("<", "&lt;").replace(">", "&gt;")


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


def unescape(t):
    if not t:
        return t

    if "\\" not in t:
        return t

    t = t.replace("\\*(dg", "(!)")

    t = t.replace("\{", "{")

    t = t.replace("\-", "-")
    t = t.replace("\ ", "&nbsp;")
    t = t.replace("\\0", "&nbsp;")

    t = t.replace("\%", "")
    t = t.replace("\:", "")

    t = t.replace("\\(bu", "&bull;")

    t = t.replace("\`", "&#96;")  # Backtick

    t = t.replace("\&", "")

    t = t.replace("\\\\", "&#92;")

    t = t.replace("\[char46]", "&#46;")

    t = t.replace("\\(co", "&copy;")

    t = t.replace("\\(em", "&ndash;")
    t = t.replace("\\(en", "&ndash;")

    t = t.replace("\\(dq", "&quot;")
    t = t.replace("\\(aq", "&apos;")
    t = t.replace("\\*(Aq", "&apos;")

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
    t = re.sub(r'\\fI(.*?)\\f[PR]', r'<em>\1</em>', t)

    t = re.sub(r'\\fB(.*?)\\f[PR]', r'<strong>\1</strong>', t)

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
