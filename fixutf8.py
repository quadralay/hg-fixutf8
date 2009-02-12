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

#
# How it works:
#
#  There are 2 ways for strings to get into HG, either
# via that command line or filesystem filename. We want
# to make sure that both of those work.
#
#  We use the WIN32 GetCommandLineW() to get the unicode
# version of the command line. And we wrapp all the
# places where we send or get filenames from the os and
# make sure we send UCS-16 to windows and convert back
# to UTF8.
#
#  There are bugs in Python that make print() and
# sys.stdout.write() barf on unicode or utf8 when the
# output codepage is set to 65001 (UTF8). So we do all
# outputing via WriteFile() with the code page set to
# 65001. The trick is to save the existing codepage,
# and restore it before we return back to python.
#
#  The result is that all of our strings are UTF8 all
# the time, and never explicitly converted to anything
# else.
#

import sys, os, shutil

stdout = sys.stdout

from mercurial import util, osutil, dispatch, extensions, i18n
import stat as _stat
import mercurial.ui as _ui

try:
    from ctypes import *
except:
    pass

def test():
    print win32getargs()
    print sys.argv

    uargs = ['P:\\hg-fixutf8\\fixutf8.py', 'thi\xc5\x9b', 'i\xc5\x9b',
            '\xc4\x85', 't\xc4\x99\xc5\x9bt']
    for s in uargs:
        rawprint(hStdOut, s + "\n")

# Using ctypes we can call the unicode versions of win32 api calls that 
# python does not call.
if sys.platform == "win32" and windll:
    LPCWSTR = c_wchar_p
    LPCSTR = c_char_p
    INT = c_int
    UINT = c_uint
    BOOL = INT
    DWORD = UINT
    HANDLE = c_void_p

    prototype = WINFUNCTYPE(LPCWSTR)
    GetCommandLine = prototype(("GetCommandLineW", windll.kernel32))

    prototype = WINFUNCTYPE(POINTER(LPCWSTR), LPCWSTR, POINTER(INT))
    CommandLineToArgv = prototype(("CommandLineToArgvW", windll.shell32))

    prototype = WINFUNCTYPE(BOOL, UINT)
    SetConsoleOutputCP = prototype(("SetConsoleOutputCP", windll.kernel32))

    prototype = WINFUNCTYPE(UINT)
    GetConsoleOutputCP = prototype(("GetConsoleOutputCP", windll.kernel32))

    prototype = WINFUNCTYPE(DWORD)
    GetLastError = prototype(("GetLastError", windll.kernel32))

    prototype = WINFUNCTYPE(HANDLE, DWORD)
    GetStdHandle = prototype(("GetStdHandle", windll.kernel32))

    prototype = WINFUNCTYPE(BOOL, HANDLE, LPCSTR, DWORD,
            POINTER(DWORD), DWORD)
    WriteFile = prototype(("WriteFile", windll.kernel32))

    hStdOut = GetStdHandle(0xFFFFfff5)
    hStdErr = GetStdHandle(0xFFFFfff4)

    def rawprint(h, s):
        try:
            oldcp = GetConsoleOutputCP()
            SetConsoleOutputCP(65001)
            limit = 0x4000
            l = len(s)
            start = 0
            while start < l:
                end = start + limit
                buffer = s[start:end]
                c = DWORD(0)
                if not WriteFile(h, buffer, len(buffer), byref(c), 0):
                    raise pywintypes.error(err, "WriteFile",
                            win32api.FormatMessage(err))
                start = start + c.value + 1
        finally:
            SetConsoleOutputCP(oldcp)

    def win32getargs():
        '''
        win32getargs() -> [args]

        Returns an array of utf8 encoded arguments passed on the command line.
        '''
        c = INT(0)
        pargv = CommandLineToArgv(GetCommandLine(), byref(c))
        return [fromunicode(pargv[i]) for i in xrange(1, c.value)]
else:
    rawprint = False
    win32getargs = False
    hStdOut = 0
    hStdErr = 0

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
    lambda s: makesafe(s.encode('utf-8')),
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

def makesafe(s):
    fromlocalresults.append(s)
    return s

oldtolocal = util.tolocal
def _tolocal(s):
    return s

def utf8wrapper(orig, *args, **kargs):
    return fromunicode(orig(*tounicode(args), **kargs))

def gettextwrapper(orig, message):
    s = orig(message)
    return s.decode(util._encoding).encode("utf-8")

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
    if sys.platform != 'win32':
        return

    convert =  mapconvert(
        lambda s: oldtolocal(s),
        lambda s: isinstance(s, str),
        "Converts to local codepage")
    def localize(h):
        def f(orig, ui, *args):
            if not ui.buffers:
                if rawprint:
                    rawprint(h, ''.join(args))
                else:
                    orig(ui, *convert(args))
            else:
                orig(ui, *args)
        return f

    extensions.wrapfunction(_ui.ui, "write", localize(hStdOut))
    extensions.wrapfunction(_ui.ui, "write_err", localize(hStdErr))
    extensions.wrapfunction(i18n, "gettext", gettextwrapper)
    extensions.wrapfunction(i18n, "_", gettextwrapper)

def extsetup():
    if sys.platform != 'win32':
        return

    oldlistdir = osutil.listdir
    osutil.listdir = listdir # force pure listdir
    extensions.wrapfunction(osutil, "listdir", utf8wrapper)

    extensions.wrapfunction(util, "fromlocal", safefromlocal)
    util.tolocal = _tolocal
    
    if win32getargs:
        extensions.wrapfunction(dispatch, "_parse",
                lambda orig, ui, args: orig(ui, win32getargs()[-len(args):]))
    else:
        extensions.wrapfunction(dispatch, "_parse",
                lambda orig, ui, args: orig(ui, map(util.fromlocal, args)))

    class posixfile_utf8(file):
        def __init__(self, name, mode='rb'):
            super(posixfile_utf8, self).__init__(tounicode(name), mode)
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


if __name__ == "__main__":
    test()
