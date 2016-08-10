import os.path
import shlex
from string import Template
from repoze.lru import lru_cache
import collections
from itertools import islice
from HTMLParser import HTMLParser

try:
    import re2 as re
except ImportError:
    import re


def tokenize(t):
    # FiXME "\ " is going to break everything
    # https://www.gnu.org/software/groff/manual/html_node/Request-and-Macro-Arguments.html
    if not t:
        tokens = []
    elif ' ' not in t and '"' not in t:
        tokens = [t]
    elif '"' not in t and "\\ " not in t:
        tokens = t.split(None)
    else:
        #print "(%s)" % (t,)

        state = "start"
        arg = ""
        tokens = []
        for char in t:
            if state == "start":
                if char == " ":
                    continue
                elif char == "\"":
                    state = "inarg_quote"
                    continue
                else:
                    state = "inarg"
                    arg += char
                    continue

            if state == "inarg_quote":
                if char == "\"":
                    state = "start"
                    tokens.append(arg)
                    arg = ""
                    continue
                else:
                    arg += char
                    continue

            if state == "inarg":
                if char == " ":
                    tokens.append(arg)
                    arg = ""
                    state = "start"
                    continue
                else:
                    arg += char
                    continue
        else:
            if state in {"inarg", "inarg_quote"}:
                if arg:
                    tokens.append(arg)
                    arg = ""
                    state = "start"
            elif state == "start":
                pass
            else:
                raise Exception("Args should be empty %s" % state)

    return tokens


def consume(iterator, n):
    "Advance the iterator n-steps ahead. If n is none, consume entirely."
    # Use functions that consume iterators at C speed.
    if n is None:
        # feed the entire iterator into a zero-length deque
        collections.deque(iterator, maxlen=0)
    else:
        # advance to the empty slice starting at position n
        next(islice(iterator, n, n), None)


def load_template(template):
    fp = open("templates/%s.tpl" % (template, ))
    out = Template(''.join(fp.readlines()))
    fp.close()
    return out


def get_pagination(prev_page=None, next_page=None):
    content = []
    if prev_page:
        link, text = prev_page
        content.append(
            load_template('pagination-prev').substitute(
                link=link, text=text))

    if next_page:
        link, text = next_page
        content.append(
            load_template('pagination-next').substitute(
                link=link, text=text))

    if not content:
        return ""
    else:
        return load_template('pagination').substitute(
            content="\n".join(content))


def get_breadcrumb(breadcrumbs):
    contents = [populate_breadcrumb_item(1, "Carta.tech", "/")]
    for i, (url, text) in enumerate(breadcrumbs):
        contents.append(populate_breadcrumb_item(i + 2, text, url))

    container_tpl = load_template('breadcrumb-container')
    return container_tpl.substitute(items='\n'.join(contents))


def populate_breadcrumb_item(order, text, url):
    return load_template('breadcrumb-item').substitute(
        url=url, text=text, order=order)


class MLStripper(HTMLParser):
    def __init__(self):
        self.reset()
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return ''.join(self.fed)


def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()


pjoin = os.path.join
dname = os.path.dirname
bname = os.path.basename

#linkifier = re.compile(
#    r"(?:<\w+?>)?(?P<page>\w+[\w\.-]+\w+)(?:</\w+?>)?[(](?P<section>\d)[)]")

linkifier = re.compile(
    r"(?P<pretag><\w+?>)?(?P<page>\w+[\w\.-]+\w+)(?P<posttag></\w+?>)?[(](?P<section>\d)[)]")

SECTIONS = {
    'man1': "Executable programs or shell commands",
    'man2': "System calls",
    'man3': "Library calls",
    'man4': "Special files",
    'man5': "File formats and conventions",
    'man6': "Games",
    'man7': "Miscellaneous",
    'man8': "System administration commands",
}


class Macro(object):
    single_style = {'B', 'I', 'SM'}
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

    @staticmethod
    def process_fonts(content, current_tag=None):
        #print content, current_tag

        if current_tag == 'R':
            current_tag = None

        translate_font = {
            '1': 'R',
            '2': 'I',
            '3': 'B',
            '4': 'B',
            'b': 'B',
            'r': 'R',
            'i': 'I',
        }

        style_map = {
            'B': "strong",
            'I': "em",
            'SM': "small",
            'S': "small",
        }

        previous_tag = None
        if not current_tag:
            out = ""
        elif current_tag in style_map:
            out = "<%s>" % style_map[current_tag]
        else:
            raise Exception("Current tag %s" % current_tag)

        state = "start"
        for c in content:
            if state == "start":
                if c != '\\':
                    out += c
                elif c == '\\':
                    state = "slash"
            elif state == "slash":
                if c == 'f':
                    state = "fontslash"
                else:
                    state = "start"
                    out += '\\' + c
            elif state in {"fontslash", "fontsquare"}:
                if state == "fontsquare":
                    if c != ']':
                        tmp_tag = c
                        continue
                    else:
                        if not tmp_tag:
                            tmp_tag = "R"

                        c = tmp_tag

                if c in translate_font:
                    c = translate_font[c]
                if c in style_map:
                    if current_tag:
                        out += "</%s>" % style_map[current_tag]

                    previous_tag, current_tag = current_tag, c
                    out += "<%s>" % style_map[c]
                    state = "start"
                elif c in {'P'}:
                    if current_tag:
                        out += "</%s>" % style_map[current_tag]
                    previous_tag, current_tag = current_tag, previous_tag

                    if current_tag:
                        out += "<%s>" % style_map[current_tag]

                    state = "start"
                elif c in {'R'}:
                    if current_tag:
                        out += "</%s>" % style_map[current_tag]
                    previous_tag, current_tag = current_tag, None
                    state = "start"
                elif c in {'$', 'C', '7', 'N'}:
                    # So many bugs...
                    state = "start"
                elif c in {'('}:
                    state = "fontparentheses"
                elif c in {'['}:
                    tmp_tag = None
                    state = "fontsquare"
                else:
                    raise Exception()
            elif state == "fontparentheses":
                if c == "C":
                    state = "fontparentheses1"
                elif c == "B":
                    state = "fontparentheses2"
                else:
                    raise Exception()
            elif state == "fontparentheses1":
                if c == "W":
                    state = "start"
                elif c in {"B", "O"}:
                    if current_tag:
                        out += "</%s>" % style_map[current_tag]

                    previous_tag, current_tag = current_tag, "B"

                    out += "<%s>" % style_map["B"]
                    state = "start"
                else:
                    raise Exception()
            elif state == "fontparentheses2":
                if c == "I":
                    if current_tag:
                        out += "</%s>" % style_map[current_tag]

                    previous_tag, current_tag = current_tag, "B"

                    out += "<%s>" % style_map["B"]
                    state = "start"
                else:
                    raise Exception()
        else:
            if current_tag:
                out += "</%s>" % style_map[current_tag]

        return out

    @staticmethod
    def stylize(macro, args):
        if macro in Macro.single_style:
            content = ' '.join(args)

            try:
                return Macro.process_fonts(content, macro)
            except:
                raise Exception("error")

        elif macro in Macro.compound_style:
            out = []
            for i, chunk in enumerate(args):
                style = macro[i % 2]
                try:
                    out.append(Macro.process_fonts(chunk, style))
                except:
                    raise Exception("error")

            return ''.join(out)
        else:
            raise UnexpectedMacro("STYLE", macro, args, "path")


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

    t = t.replace("\\\\0", "&#92;0")

    t = t.replace("\-", "-")
    t = t.replace("\ ", "&nbsp;")
    t = t.replace("\\0", "&nbsp;")

    t = t.replace("\%", "")
    t = t.replace("\:", "")

    t = t.replace("\\(bu", "&bull;")

    t = t.replace("\`", "&#96;")  # Backtick

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

    t = t.replace("\&", "")

    return t
