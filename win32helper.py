#
# Unicode WIN32 api calls
#

import sys
from ctypes import *

# Using ctypes we can call the unicode versions of win32 api calls that 
# python does not call.
if sys.platform == "win32" and windll:
    LPWSTR = c_wchar_p
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

    prototype = WINFUNCTYPE(INT)
    GetLastError = prototype(("GetLastError", windll.kernel32))

    prototype = WINFUNCTYPE(HANDLE, DWORD)
    GetStdHandle = prototype(("GetStdHandle", windll.kernel32))

    prototype = WINFUNCTYPE(BOOL, HANDLE, LPCSTR, DWORD,
            POINTER(DWORD), DWORD)
    WriteFile = prototype(("WriteFile", windll.kernel32))

    prototype = WINFUNCTYPE(DWORD, DWORD, LPWSTR)
    GetCurrentDirectory = prototype(("GetCurrentDirectoryW", windll.kernel32))

    hStdOut = GetStdHandle(0xFFFFfff5)
    hStdErr = GetStdHandle(0xFFFFfff4)

    def getcwdwrapper(orig):
        chars = GetCurrentDirectory(0, None) + 1
        p = create_unicode_buffer(chars)
        if 0 == GetCurrentDirectory(chars, p):
            err = GetLastError()
            if err < 0:
                raise pywintypes.error(err, "GetCurrentDirectory",
                        win32api.FormatMessage(err))
        return fromunicode(p.value)

    def rawprint(h, s):
        try:
            oldcp = GetConsoleOutputCP()
            try:
                if oldcp != 65001:
                    s = s.decode('utf-8').encode('cp%d' % oldcp)
            except UnicodeError:
                SetConsoleOutputCP(65001)
            limit = 0x4000
            l = len(s)
            start = 0
            while start < l:
                end = start + limit
                buffer = s[start:end]
                c = DWORD(0)
                if not WriteFile(h, buffer, len(buffer), byref(c), 0):
                    err = GetLastError()
                    if err < 0:
                        raise pywintypes.error(err, "WriteFile",
                                win32api.FormatMessage(err))
                    start = start + c.value + 1
                else:
                    start = start + len(buffer)
        finally:
            if oldcp != GetConsoleOutputCP():
                SetConsoleOutputCP(oldcp)

    def getargs():
        '''
        getargs() -> [args]

        Returns an array of utf8 encoded arguments passed on the command line.
        '''
        c = INT(0)
        pargv = CommandLineToArgv(GetCommandLine(), byref(c))
        return [fromunicode(pargv[i]) for i in xrange(1, c.value)]
else:
    win32rawprint = False
    win32getargs = False
    hStdOut = 0
    hStdErr = 0

