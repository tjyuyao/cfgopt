import inspect
import os
import sys

PARSE_ROOT = [None]

def root(relpath, chdir=True):
    dirname = os.path.dirname(os.path.abspath(inspect.stack()[1][1]))
    newpath = os.path.abspath(os.path.join(dirname, relpath))
    sys.path.insert(0, newpath)
    PARSE_ROOT[0] = newpath
    if chdir:
        os.chdir(newpath)