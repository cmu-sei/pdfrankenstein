#  Copyright 2011-2015 by Carnegie Mellon University
# 
#  NO WARRANTY
# 
#  THIS CARNEGIE MELLON UNIVERSITY AND SOFTWARE ENGINEERING INSTITUTE
#  MATERIAL IS FURNISHED ON AN "AS-IS" BASIS.  CARNEGIE MELLON
#  UNIVERSITY MAKES NO WARRANTIES OF ANY KIND, EITHER EXPRESSED OR
#  IMPLIED, AS TO ANY MATTER INCLUDING, BUT NOT LIMITED TO, WARRANTY
#  OF FITNESS FOR PURPOSE OR MERCHANTABILITY, EXCLUSIVITY, OR RESULTS
#  OBTAINED FROM USE OF THE MATERIAL.  CARNEGIE MELLON UNIVERSITY
#  DOES NOT MAKE ANY WARRANTY OF ANY KIND WITH RESPECT TO FREEDOM
#  FROM PATENT, TRADEMARK, OR COPYRIGHT INFRINGEMENT.

import sys
import re

'''
For testing run the module without arguments. (Can also be run on arbitrary files.)

'''


class Test(object):
    tests = ['ftp', 'http']
    ftp = "6674703a2f2f676f6f676c652e636f6d"
    http = "6674703a2f2f676f6f676c652e636f6d687474703a2f2f676f6f676c652e636f6df1"


'''
This function makes no assumptions on the validity of the string values
'''


def ascii2hex(string):
    if isinstance(string, str):
        return ''.join([hex(ord(c))[2:] for c in string])
    else:
        return ''


'''
Convert a string from hex to ascii. Starting from the first position, and
stopping on the first invalid (not-printable) character or invalid input,
whichever comes first.
'''


def hex2ascii(string):
    letters = ''
    for idx in range(0, len(string), 2):
        try:
            c1 = string[idx]
            c2 = string[idx + 1]
            i = int(c1 + c2, 16)
            if i < 32 or i > 127:
                break
            ch = chr(i)
        except (ValueError, TypeError, IndexError):
            break
        else:
            letters += ch
    return letters


def get_unicode(h2):
    res = []
    res = re.findall('[\'\"]((%u[0-9a-f]{4})*)[\'\"]', h2)
    return res


'''
Return a list of strings found in the hexstring. Should not return overlapping
results. Needle is converted from ASCII to HEX on the first line.
'''


def find_in_hex(needle, hexstack):
    needle = ascii2hex(needle)
    results = []
    total = 0
    while True:
        idx = hexstack.find(needle)
        if idx < 0:
            break
        total += idx
        results.append((total, hex2ascii(hexstack[idx:])))
        hexstack = hexstack[idx + 1:]
        total += 1
    return results


def verify(vals, string):
    for val in vals:
        sys.stdout.write('Verifying [%s] @ [%d]...' % (val[1], val[0]))
        if string[val[0]:len(val[1])].startswith(hex2ascii(val[1])):
            sys.stdout.write('pass\n')
        else:
            sys.stdout.write('fail. string[%d]==[%s]...\n' % (val[0], val[1][val[0]:val[0] + 32]))


'''
Return a list of urls found in the unicode string. Should not return overlapping
results. Needle is converted from ASCII to UNICODE on the first line.
'''


def find_unicode(needle, haystack):
    needle = ascii2uni(needle)
    results = []
    total = 0
    while True:
        idx = haystack.find(needle)
        if idx < 0:
            break
        total += idx
        quote_2 = haystack[idx:].find('"')
        quote_1 = haystack[idx:].find('\'')
        if quote_1 < quote_2 and quote_1 > -1:
            quote = quote_1
        else:
            quote = quote_2
        results.append((total, haystack[idx:idx + quote]))
        haystack = haystack[idx + 1:]
        total += 1
    res = []
    for r in results:
        res.append((r[0], uni2ascii(r[1])))
    return res


'''
    Convert a string from ascii to unicode
'''


def ascii2uni(string):
    string = ascii2hex(string)
    res = re.findall('([0-9a-f]{2})([0-9a-f]{2})', string)
    string = ''
    for i in res:
        string += '%u' + i[1] + i[0]
    return string


'''
    Convert a string form unicode to ascii
'''


def uni2ascii(string):
    string = re.sub("%u", "", string)
    res = re.findall('([0-9a-f]{2})([0-9a-f]{2})', string)
    string = ''
    for i in res:
        string += i[1] + i[0]
    return hex2ascii(string)


'''
Find h1 in h2 | h1 == ASCII && h2 == HEX
'''


def main(h1, h2):
    if not isinstance(h2, str):
        print 'Invalid input:', type(h2)
        print str(h2)
        return

    print 'Searching for "%s" in "%s"...' % (h1, h2[:32])

    urls = find_in_hex(h1, h2)
    urls += find_unicode(h1, h2)
    print urls
    print 'Found: %d occurrences' % len(urls)
    if len(urls):
        verify(urls, h2)


if __name__ == "__main__":
    try:
        needle = sys.argv[1]
        fin = open(sys.argv[2], 'r')
    except IndexError:
        print 'Invalid or no arguments. Usage: huntterp.py needle haystack.txt'
        print 'Beginning tests'
        t = Test()
        for needle in t.tests:
            haystack = getattr(t, needle)
            main(needle, haystack)
    except IOError as e:
        print e
    else:
        main(needle, fin.read())
