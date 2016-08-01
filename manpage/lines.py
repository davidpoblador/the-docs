from collections import namedtuple
from helpers import entitize

LineItems = namedtuple("LineItems", ['macro', 'data', 'comment'])


class ManPageLine(LineItems):
    def line(self):
        return ".%s %s" % (self.macro,
                           self.data, )

    def contains(self, piece):
        return (piece in self.line())


class Lines(object):
    def __init__(self, iterator):
        self._current = 0
        self._data = []

        extra = []
        for line in iterator:
            if line and len(line) > 2:
                if line[-1] == "\\" and line[
                        -2] != "\\":  # FIXME: Possibly rsplit might work better
                    extra.append(line[:-1])
                    continue
                elif line[-2:] == "\\c":
                    extra.append(line[:-2])
                    continue

            if extra:
                extra.append(line)
                line = ' '.join(extra)
                extra = []

            if line.startswith(".") and len(line) > 1 and line != "..":
                if len(line) > 2 and line[1:3] == "\\\"":
                    # Comment
                    comment = True
                    macro = None
                    data = line[3:]
                else:
                    comment = False
                    if "\\\"" in line:
                        line = line.split("\\\"", 1)[0]

                    chunks = line.split(None, 1)
                    if len(chunks) == 2:
                        macro, data = chunks
                    else:
                        macro, data = chunks[0], None

                    macro = macro[1:]
            else:
                comment = False
                macro = None
                if "\\\"" in line and "\\\\\"" not in line:
                    data = line.split("\\\"", 1)[0]
                    if not data:
                        continue
                else:
                    data = line

            if data:
                data = entitize(data)

            self._data.append(ManPageLine(macro, data, comment))

    def get(self):
        current = self._data[self._current]
        self.fwd()
        return current

    def curr(self):
        return self._data[self._current]

    def prev(self):
        return self._data[self._current - 1]

    def next(self):
        return self._data[self._current + 1]

    def fwd(self):
        self._current += 1

    def rwd(self):
        self._current -= 1
