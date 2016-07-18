from string import Template


def load_template(template):
    fp = open("templates/%s.tpl" % (template, ))
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


class UnexpectedState(Exception):
    pass


class MissingParser(Exception):
    pass


class NotSupportedFormat(Exception):
    pass


class RedirectedPage(Exception):
    pass
