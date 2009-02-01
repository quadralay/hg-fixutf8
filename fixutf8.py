# fixutf8.py - Make Mercurial compatible with non-utf8 locales
#
# Copyright 2009 Stefan Rusek
#
# This software may be used and distributed according to the terms
# of the GNU General Public License, incorporated herein by reference.
#
# To load the extension, add it to your .hgrc file:
#
#   [extension]
#   hgext.fixutf8 =
#
# This module needs no special configuration.

'''
Fix incompatibilities with non-utf8 locales

No special configuration is needed.
'''

import sys, os, shutil
from mercurial import util, osutil, dispatch, extensions
import stat as _stat
import mercurial.ui as _ui


def mapconvert(convert, canconvert, doc):
    '''
    mapconvert(convert, canconvert, doc) ->
        (a -> a)

    Returns a function that converts arbitrary arguments
    using the specified conversion function.

    convert is a function to do actual convertions.
    canconvert returns true if the arg can be converted.
    doc is the doc string to attach to created function.

    The resulting function will return a converted list or
    tuple if passed a list or tuple.

    '''
    def _convert(arg):
        if canconvert(arg):
            return convert(arg)
        elif isinstance(arg, tuple):
            return tuple(map(_convert, arg))
        elif isinstance(arg, list):
            return map(_convert, arg)
        return arg
    _convert.__doc__ = doc
    return _convert

tounicode = mapconvert(
    lambda s: s.decode('utf-8'), 
    lambda s: isinstance(s, str),  
    "Convert a UTF-8 byte string to Unicode")

fromunicode = mapconvert(
    lambda s: s.encode('utf-8'),
    lambda s: isinstance(s, unicode),
    "Convert a Unicode string to a UTF-8 byte string")

fromlocalresults = []
def safefromlocal(orig, s):
    # don't double decode
    if s in fromlocalresults:
        return s
    r = orig(s)
    fromlocalresults.append(r)
    return r

oldtolocal = util.tolocal
def _tolocal(s):
    return s

def utf8wrapper(orig, *args, **kargs):
    return fromunicode(orig(*tounicode(args), **kargs))

# The following 2 functions are copied from mercurial/pure/osutil.py.
# The reasons is that the C version of listdir is not unicode safe, so
# we have to use the pure python version. If speed ends up being a
# problem, a unicode safe version of the C module can be written.
def _mode_to_kind(mode):
    if _stat.S_ISREG(mode): return _stat.S_IFREG
    if _stat.S_ISDIR(mode): return _stat.S_IFDIR
    if _stat.S_ISLNK(mode): return _stat.S_IFLNK
    if _stat.S_ISBLK(mode): return _stat.S_IFBLK
    if _stat.S_ISCHR(mode): return _stat.S_IFCHR
    if _stat.S_ISFIFO(mode): return _stat.S_IFIFO
    if _stat.S_ISSOCK(mode): return _stat.S_IFSOCK
    return mode

def listdir(path, stat=False, skip=None):
    '''listdir(path, stat=False) -> list_of_tuples

    Return a sorted list containing information about the entries
    in the directory.

    If stat is True, each element is a 3-tuple:

      (name, type, stat object)

    Otherwise, each element is a 2-tuple:

      (name, type)
    '''
    result = []
    prefix = path
    if not prefix.endswith(os.sep):
        prefix += os.sep
    names = os.listdir(path)
    names.sort()
    for fn in names:
        st = os.lstat(prefix + fn)
        if fn == skip and _stat.S_ISDIR(st.st_mode):
            return []
        if stat:
            result.append((fn, _mode_to_kind(st.st_mode), st))
        else:
            result.append((fn, _mode_to_kind(st.st_mode)))
    return result

def uisetup(ui):
    convert =  mapconvert(
        lambda s: oldtolocal(s),
        lambda s: isinstance(s, str),
        "Converts to local codepage")
    def localize(orig, ui, *args):
        if ui.isatty():
            orig(ui, *convert(args))
        else:
            orig(ui, *args)

    extensions.wrapfunction(_ui.ui, "write", localize)
    extensions.wrapfunction(_ui.ui, "write_err", localize)

def extsetup():
    if util._encoding.lower() == "utf-8":
        # this will never happen on windows and allows
        # us to not fix non-windows where the default 
        # locale is already UTF-8
        return

    oldlistdir = osutil.listdir
    osutil.listdir = listdir # force pure listdir
    extensions.wrapfunction(osutil, "listdir", utf8wrapper)

    extensions.wrapfunction(util, "fromlocal", safefromlocal)
    util.tolocal = _tolocal
    
    extensions.wrapfunction(dispatch, "_parse",
            lambda orig, ui, args: orig(ui, map(util.fromlocal, args)))

    posixfile__init__ = util.posixfile.__init__
    class posixfile_utf8(util.posixfile):
        def __init__(self, name, mode='rb'):
            posixfile__init__(self, tounicode(name), mode)
    util.posixfile = posixfile_utf8

    if util.atomictempfile:
        class atomictempfile_utf8(posixfile_utf8):
            """file-like object that atomically updates a file

            All writes will be redirected to a temporary copy of the original
            file.  When rename is called, the copy is renamed to the original
            name, making the changes visible.
            """
            def __init__(self, name, mode, createmode):
                self.__name = name
                self.temp = util.mktempcopy(name, emptyok=('w' in mode),
                                       createmode=createmode)
                posixfile_utf8.__init__(self, self.temp, mode)

            def rename(self):
                if not self.closed:
                    posixfile_utf8.close(self)
                    util.rename(self.temp, util.localpath(self.__name))

            def __del__(self):
                if not self.closed:
                    try:
                        os.unlink(self.temp)
                    except: pass
                    posixfile_utf8.close(self)

        util.atomictempfile = atomictempfile_utf8

    # wrap the os and path functions
    def wrapnames(mod, *names):
        for name in names:
            if hasattr(mod, name):
                newfunc = extensions.wrapfunction(mod, name, utf8wrapper)

    wrapnames(os.path, 'join', 'split', 'splitext', 'splitunc',
            'normpath', 'normcase', 'islink', 'dirname', 'isdir',
            'exists')
    wrapnames(os, 'makedirs', 'lstat', 'unlink', 'chmod', 'stat',
            'mkdir', 'rename', 'removedirs')
    wrapnames(shutil, 'copyfile', 'copymode')

