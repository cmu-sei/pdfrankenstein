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

import os
import re
import sys

import lxml.etree as ET
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfparser import PDFParser
from pdfminer.pdftypes import PDFStream, PDFObjRef
from pdfminer.pdftypes import PDFObjectNotFound
from pdfminer.psparser import PSKeyword, PSLiteral
from pdfminer.utils import isnumber
from JSAnalysis import isJavascript
from util.str_utils import isFlash
from lib.scandir import scandir

'''
    Parse a pdf and build an xml tree based on the object structure
'''


class FrankenParser(object):
    def __init__(self, pdf, debug=False):
        self.errors = ''
        self.debug = debug
        self.pdf = pdf
        self.xml = ''
        self.javascript = []
        self.deobfuscated = []
        self.swf = []
        self.found_eof = False
        self.bin_blob = ''
        self.malformed = {}
        self.parse()
        self.tree = self.tree_from_xml(self.xml)

    def e(self, s):
        ESC_PAT = re.compile(r'[\000-\037&<>()"\042\047\134\177-\377]')
        return ESC_PAT.sub(lambda m: '&#%d;' % ord(m.group(0)), s)

    '''
        Convert a pdf object into xml
    '''

    def dump(self, obj):
        res = ""
        if obj is None:
            res += '<null />'
            return res

        if isinstance(obj, dict):
            res += '<dict size="%' + str(len(obj)) + '">\n'
            for (k, v) in obj.iteritems():
                k = re.sub(r'\W+', '', k)
                if k.isdigit() or not k:
                    k = 'xml_creator_' + k
                res += '<' + k + '>'
                res += self.dump(v)
                res += '</' + k + '>\n'
            res += '</dict>'
            return res

        if isinstance(obj, list):
            res += '<list size="' + str(len(obj)) + '">\n'
            for v in obj:
                res += self.dump(v)
                res += '\n'
            res += '</list>'
            return res

        if isinstance(obj, str):
            self.check_js(obj)
            # encode base64 to avoid illegal xml characters
            res += '<string>' + self.e(obj).encode('base64') + '</string>'
            return res

        if isinstance(obj, PDFStream):
            res += '<stream>\n'
            try:
                res += '<props>\n'
                res += self.dump(obj.attrs)
                res += '\n</props>\n'
                data = obj.get_data()
                self.check_js(str(data))
                self.check_swf(str(data))
                res += '<data size="' + str(len(data)) + '">' + self.e(data).encode('base64') + '</data>\n'
            # Throws an exception if the filter is unsupported, etc
            except Exception as e:
                # print e.message
                res += '<StreamException>%s</StreamException>' % str(e)
            # make sure the tag is closed appropriately
            res += '</stream>'
            return res

        if isinstance(obj, PDFObjRef):
            res += '<ref id="' + str(obj.objid) + '" />'
            return res

        if isinstance(obj, PSKeyword):
            self.check_js(obj.name)
            res += '<keyword>' + obj.name + '</keyword>'
            return res

        if isinstance(obj, PSLiteral):
            self.check_js(obj.name)
            res += '<literal>' + obj.name + '</literal>'
            return res

        if isnumber(obj):
            self.check_js(str(obj))
            res += '<number>' + str(obj) + '</number>'
            return res

        raise TypeError(obj)

    '''
        Add the PDF trailers to the xml
    '''

    def dumptrailers(self, doc):
        res = ""
        for xref in doc.xrefs:
            res += '<trailer>\n'
            res += self.dump(xref.trailer)
            res += '\n</trailer>\n\n'
        return res

    '''
    Records information into a dictionary.
    All key values are lists, and the paramter is appended.
    '''

    def takenote(self, dic, key, val):
        try:
            dic[key].append(val)
        except KeyError:
            dic[key] = []
            dic[key].append(val)

    def getmalformed(self, key=''):
        if not key:
            return self.malformed
        else:
            return self.malformed.get(key)

    '''
        Parse the pdf and build the xml
    '''

    def parse(self):
        fp = file(self.pdf, 'rb')
        parser = PDFParser(fp, dbg=self.debug)
        doc = PDFDocument(parser, dbg=self.debug)
        # extract blob of data after EOF (if it exists)
        if doc.found_eof and doc.eof_distance > 3:
            self.bin_blob = parser.read_from_end(doc.eof_distance)
        res = '<pdf>'
        visited = set()  # keep track of the objects already visited
        for xref in doc.xrefs:
            for objid in xref.get_objids():
                if objid in visited:
                    continue
                visited.add(objid)
                try:
                    obj = doc.getobj(objid)
                    res += '<object id="' + str(objid) + '">\n'
                    res += self.dump(obj)
                    res += '\n</object>\n\n'
                except PDFObjectNotFound as e:
                    mal_obj = parser.read_n_from(xref.get_pos(objid)[1], 4096)
                    mal_obj = mal_obj.replace('<', '0x3C')
                    res += '<object id="%d" type="malformed">\n%s\n</object>\n\n' % (objid, mal_obj)
                    self.takenote(self.malformed, 'objects', objid)
                except Exception as e:
                    res += '<object id="%d" type="exception">\n%s\n</object>\n\n' % (objid, e.message)
        fp.close()
        res += self.dumptrailers(doc)
        res += '</pdf>'
        self.xml = res
        self.errors = doc.errors
        self.bytes_read = parser.BYTES
        return

    '''
        Check string for javascript content
    '''

    def check_js(self, content):
        if isJavascript(content):
            # pull out js between script tags
            reJSscript = '<script[^>]*?contentType\s*?=\s*?[\'"]application/x-javascript[\'"][^>]*?>(.*?)</script>'
            res = re.findall(reJSscript, content, re.DOTALL | re.IGNORECASE)
            if res != []:
                self.javascript.append('\n'.join(res))
            else:
                self.javascript.append(content)
        return

    '''
        Check string for flash content
    '''

    def check_swf(self, content):
        if isFlash(content):
            self.swf.append(content)
        return

    '''
        Create an lxml tree from the xml string
    '''

    def tree_from_xml(self, xml):
        try:
            tree = ET.fromstring(xml)
            return tree
        except Exception as e:
            sys.stderr.write("xml_creator cannot create tree: %s\n" % e)
            return 'TREE_ERROR: %s' % str(e)

    '''
        Calls edges to recursively create the graph string
    '''

    def make_graph(self, tree):
        res = []
        # Explicit check for None to avoid FutureWarning
        if tree is not None:
            self.edges(tree, res, 0)
        return res

    def edges(self, parent, output, id):
        """

        creates string showing connections between objects
        """
        for child in list(parent):
            if isinstance(child, str):
                return
            elif child.get("id") != None:
                cid = child.get("id")
                output.append(str(id) + ' ' + cid + '\n')
                self.edges(child, output, cid)
            else:
                res = self.edges(child, output, id)
        return


if __name__ == "__main__":
    try:
        dirin = sys.argv[1]
        dirout = sys.argv[2]
    except IndexError:
        sys.exit(0)
    else:
        if not os.path.isdir(dirin) or not os.path.isdir(dirout):
            sys.exit(0)

        sys.stdout.write("%s/*.pdf  -->  %s/*.swf\n\n" % (dirin, dirout))

        try:
            fdone = open(os.path.join(dirout, "done.txt"), 'a+')
            ferr = open(os.path.join(dirout, "error.txt"), 'a')
        except IOError as e:
            sys.stderr.write("parser done file error: %s\n" % e)
        else:
            completed = set()
            fdone.seek(0)
            for line in fdone:
                completed.add(line.rstrip())

            pdfs = scandir(dirin)

            for pdf in pdfs:

                if pdf.name in completed:
                    sys.stdout.write("skipping: %s\n" % pdf.name)
                    continue

                sys.stdout.write("%s\n" % pdf.name)

                try:
                    parsed = FrankenParser(pdf.path)
                except Exception as e:
                    try:
                        ferr.write("%s:%s\n" % (pdf.name, str(e)))
                    except Exception:
                        ferr.write("%s: ferr write() BIG-TIME ERROR\n" % pdf.name)
                        sys.stderr.write("ferr write error pdf: %s := %s\n" % (pdf.name, e))
                else:
                    if parsed.swf:
                        try:
                            fout = open(os.path.join(dirout, "%s.swf" % pdf.name), 'wb')
                        except IOError as e:
                            sys.stderr.write("parser output file error: %s\n" % e)
                        else:
                            fout.write(''.join(parsed.swf))
                            fout.close()
                finally:
                    try:
                        fdone.write("%s\n" % pdf.name)
                    except Exception as e:
                        sys.stderr.write("fdone write error pdf: %s := %s\n" % (pdf.name, e))
            sys.stdout.write("\n")
            fdone.close()
            ferr.close()
