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

try:
    import PyV8
except ImportError as e:
    print str(e)
    PyV8 = None

import re

import build_pdf_objects
from util.str_utils import unescapeHTMLEntities

reJSscript = '<script[^>]*?contentType\s*?=\s*?[\'"]application/x-javascript[\'"][^>]*?>(.*?)</script>'

def create_objs(context, tree):
    """

    Mimic native Adobe objects and add them to the context
    :param context: JavaScript context, like a namespace at runtime
    :param tree: XML tree of the pdf to reference objects
    :return:
    """
    try:
        app = build_pdf_objects.create_app_obj(tree)
        context.eval("app = " + str(app) + ";")
        context.eval("app.doc.syncAnnotScan = function () {}")
        context.eval("app.doc.getAnnots = function () { return app.doc.annots;}")
        context.eval("app.eval = function (string) { eval(string);}")
        context.eval("app.newDoc = function () { return '';}")
        context.eval("app.getString = function () { ret = \"\"; for(var prop in app){ ret += app[prop]; } return ret;}")
    except Exception as e:
        # print "App: " + e.message
        pass
    try:
        info = build_pdf_objects.create_info_obj(tree)
        context.eval("this.info = " + str(info) + ";")
        for key in info:
            context.eval("this." + key + "= '" + re.escape(info[key]) + "';")
        context.eval("this.eval = eval")
        # print info
    except Exception as e:
        print "Info: " + e.message
        pass
    try:
        event = build_pdf_objects.create_event_obj(tree)
        context.eval("event = " + str(event) + ";")
        context.eval("event.target.info = this.info")
    except Exception as e:
        # print "Event: " + e.message
        pass


def eval_loop(code, context, old_msg="", limit=10):
    """

    Eval the code and handle any exceptions it throws
    :param code: String of code to evaluate
    :param context: JavaScript context object
    :param old_msg:
    :param limit: Recursive limit
    :return:
    """
    try:
        context.eval(code)
        return context.eval("evalCode")
    # catch exceptions and attempt to fix them
    except ReferenceError as e:
        # print e.message
        if e.message == old_msg:
            return context.eval("evalCode")
        elif e.message.find('$') > -1:
            context.eval("$ = this;")
        else:
            # try commenting out line
            line_num = re.findall("@\s(\d*?)\s", e.message)
            line_num = int(line_num[0])
            i = 0
            for item in code.split("\n"):
                i += 1
                if i == line_num:
                    code = re.sub(item, "//" + item, code)
                    break
        return eval_loop(code, context, e.message)
    except TypeError as te:
        # print te.message
        if te.message == old_msg:
            return context.eval("evalCode")
        elif te.message.find("called on null or undefined") > -1:
            # in Adobe undefined objects become app object
            line = re.findall("->\s(.*)", te.message)
            sub, count = re.subn("=\s?.\(.*?\)", "=app", line[0])
            if count < 1:
                sub = re.sub("=.*", "=app", line[0])
            line = re.escape(line[0])
            code = re.sub(line, sub, code)
        elif te.message.find("undefined is not a function") > -1:
            # sub in eval as a guess
            line = re.findall("->\s(.*)", te.message)
            match = re.findall("[\s=]?(.*?)\(", line[0])
            if len(match) > 0:
                sub = re.sub(match[0], "eval", line[0])
                line = re.escape(line[0])
                code = re.sub(line, sub, code)
            else:
                return context.eval("evalCode")
        elif te.message.find("Cannot read property") > -1:
            # undefined becomes app
            line = re.findall("->\s(.*)", te.message)
            match = re.findall("[=\s](.*?)\[", line[0])
            if len(match) > 0:
                sub = re.sub(match[0], "app", line[0])
                line = re.escape(line[0])
                code = re.sub(line, sub, code)
            else:
                return context.eval("evalCode")
        else:
            return context.eval("evalCode")
        return eval_loop(code, context, te.message)
    except SyntaxError as se:
        # print se.message
        if se.message == old_msg:
            return context.eval("evalCode")
        line_num = re.findall("@\s(\d*?)\s", se.message)
        if len(line_num) > 0:
            line_num = int(line_num[0])
            i = 0
            # try commenting out the line number with the error
            for item in code.split("\n"):
                i += 1
                if i == line_num:
                    esc_item = re.escape(item)
                    code, n = re.subn(esc_item, "//" + item, code)
                    break
        else:
            return context.eval('evalCode')
        return eval_loop(code, context, se.message)
    except Exception as e1:
        # print e1.message
        return context.eval("evalCode")


def analyse(js, tree):
    """

    Main function called from pdfrankenstein. Analyzes javascript in order to deobfuscate the code.
    :param js: String of code to analyze
    :param tree: Tree xml object to use as reference for objects called from the code.
    :return: String of deobfuscated code
    """
    if not PyV8:
        return ''
    with PyV8.JSIsolate():
        context = PyV8.JSContext()
        context.enter()
        context.eval('evalCode = \'\';')
        context.eval('evalOverride = function (expression) { evalCode += expression; return;}')
        context.eval('eval=evalOverride')
        try:
            if tree is not None:
                create_objs(context, tree)
            ret = eval_loop(js, context)
            context.leave()
            if ret == None:
                return ''
            else:
                return ret
        except Exception as e:
            context.leave()
            # return 'Error with analyzing JS: ' + e.message
            return ''


def isJavascript(content):
    """
    Given an string this method looks for typical Javscript strings and try to identify if the string contains Javascript code or not.

    :param content: A string
    :return: A boolean, True if it seems to contain Javascript code or False in the other case
    """
    JSStrings = ['var ', ';', ')', '(', 'function ', '=', '{', '}', 'if ', 'else', 'return', 'while ', 'for ', ',',
                 'eval', 'unescape', '.replace']
    keyStrings = [';', '(', ')']
    stringsFound = []
    limit = 15
    minDistinctStringsFound = 5
    results = 0
    content = unescapeHTMLEntities(content)
    if re.findall(reJSscript, content, re.DOTALL | re.IGNORECASE) != []:
        return True
    for char in content:
        if (ord(char) < 32 and char not in ['\n', '\r', '\t', '\f', '\x00']) or ord(char) >= 127:
            return False

    for string in JSStrings:
        cont = content.count(string)
        results += cont
        if cont > 0 and string not in stringsFound:
            stringsFound.append(string)
        elif cont == 0 and string in keyStrings:
            return False

    if results > limit and len(stringsFound) >= minDistinctStringsFound:
        return True
    else:
        return False
