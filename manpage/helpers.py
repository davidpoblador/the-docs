import os.path
from string import Template

try:
    import re2 as re
except ImportError:
    import re

def load_template(template):
    fp = open("templates/%s.tpl" % (template,))
    out = Template(''.join(fp.readlines()))
    fp.close()
    return out


def get_pagination(prev_page=None, next_page=None):
    content = []
    if prev_page:
        link, text = prev_page
        content.append(load_template('pagination-prev').substitute(link=link,
                                                                   text=text))

    if next_page:
        link, text = next_page
        content.append(load_template('pagination-next').substitute(link=link,
                                                                   text=text))

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
    return load_template('breadcrumb-item').substitute(url=url,
                                                       text=text,
                                                       order=order)


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