#!/usr/bin/env python

from string import Template

def load_template(template):
    # FIXME: Use with
    fp = open("templates/%s.tpl" % (template, ))
    out = Template(''.join(fp.readlines()))
    fp.close()
    return out

class ManTree(object):
    def __init__(self, node_type = None, value = None):
        self.children = []
        self.value = value

        if not node_type:
            self.root_pointer = self.children
            self.node_type = "ROOT"
        else:
            self.node_type = node_type

        self.clean_state()
        self.previous_node_type = None

        self.section_pointer = None
        self.current_pointer = None

    def get_children(self):
        return self.children

    def add_section(self, name):
        self.clean_state()
        self.add_child("SECTION", value = name, pointer = self.root_pointer)
        self.section_pointer = self.current_pointer

    def add_subsection(self, name):
        self.clean_state()
        self.add_child("SUBSECTION", value = name, pointer = self.section_pointer)

    def add_content(self, content):
        if (not self.in_pre and len(self.current_pointer) and
            self.current_pointer[-1].node_type == "CONTENT"):
            self.current_pointer[-1].value += " " + content
        else:    
            self.current_pointer.append(ManTree(node_type = "CONTENT", value = content))

    def add_dt(self, text):
        if self.previous_node_type == "DT":
            self.add_child(node_type = "DT", value = text, pointer = self.dt_pointer)
        else:
            self.add_child(node_type = "DL")
            self.dt_pointer = self.current_pointer
            self.add_child(node_type = "DT", value = text)

    def add_list(self, bullet):
        if self.previous_node_type == "LI":
            self.add_child(node_type = "LI", value = bullet, pointer = self.list_pointer)
        else:
            self.add_child(node_type = "UL")
            self.list_pointer = self.current_pointer
            self.add_child(node_type = "LI", value = bullet )

    def save_state(self):
        self.state_stack.append((self.in_pre, self.dt_pointer, self.list_pointer, self.current_pointer, self.previous_node_type, ))

    def restore_state(self):
        self.in_pre, self.dt_pointer, self.list_pointer, self.current_pointer, self.previous_node_type = self.state_stack.pop(-1) 

    def clean_state(self):
        self.state_stack = []
        self.dt_pointer = None
        self.list_pointer = None
        self.in_pre = False

        self.state_stack = []

    def add_pre(self):
        self.save_state()
        self.add_child("PRE")
        self.in_pre = True

    def end_pre(self):
        self.restore_state()

    def add_rs(self):
        self.save_state()
        self.add_child("RE")

    def add_re(self):
        self.restore_state()

    def add_child(self, node_type, value = None, pointer = None):
        child = ManTree(node_type = node_type, value = value)

        if pointer is None:
            pointer = self.current_pointer

        try:
            pointer.append(child)
        except AttributeError:
            pass

        self.current_pointer = child.get_children()
        self.previous_node_type = node_type

    def traverse_tree(self, depth = 0):
        if self.node_type == "CONTENT":
            return self.value

        buff = []
        for child in self.get_children():
            buff.append(child.traverse_tree(depth+1))

        prepend = ((depth + 1) * "  ") + " "

        if self.node_type == "RE":
            output = "\n".join(buff)
        elif self.node_type in ("DL","UL"):
            output = "<dl class='dl-vertical'>%s</dl>" % "\n".join(buff)
        elif self.node_type == "PRE":
            output = "<pre>%s</pre>" % "\n".join(buff)
        elif self.node_type == "SECTION":
            section_tpl = load_template('section')

            output = section_tpl.safe_substitute(
                title = self.value,
                content = "\n".join(buff))
        elif self.node_type == "SUBSECTION":
            output = "<h3>%s</h3>" % self.value
            output += "\n".join(buff)
        elif self.node_type in ("DT", "LI"):
            output = "<dt>%s</dt>\n" % self.value
            output += "<dd>%s</dd>" % "\n".join(buff)
        elif self.node_type == "ROOT":
            output = "\n".join(buff)
        else:
            raise MissingNodeType("MNT %s : %s" % (self.node_type, self.value, ))
            buff.insert(0, "%s: %s" % (self.node_type, self.value, ))
            glue = "\n" + prepend
            output = glue.join(buff)

        return output

class MissingNodeType(Exception):
    pass

def main():
    a = ManTree()

    print a.traverse_tree()


if __name__ == '__main__':
    main()