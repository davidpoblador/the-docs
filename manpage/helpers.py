import os.path
import shlex
from string import Template
from repoze.lru import lru_cache
import collections
from itertools import islice

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
            if state == "inarg":
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


class UnexpectedState(Exception):
    pass


class MissingParser(Exception):
    pass


class NotSupportedFormat(Exception):
    pass


class RedirectedPage(Exception):
    pass


pjoin = os.path.join
dname = os.path.dirname
bname = os.path.basename

linkifier = re.compile(
    r"(?:<\w+?>)?(?P<page>\w+[\w\.-]+\w+)(?:</\w+?>)?[(](?P<section>\d)[)]")

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

    t = t.replace('*NEWLINE*', "\n")

    return t
