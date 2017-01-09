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

import re

from util.str_utils import unescapeHTMLEntities

# Determine the type of tag used and return its value accordingly
def get_value(elem, root):
    if elem.tag == "literal" or elem.tag == "number" or elem.tag == "keyword":
        return unescapeHTMLEntities(elem.text)
    elif elem.tag == "string":
        return unescapeHTMLEntities(elem.text.decode('base64'))
    elif elem.tag == "ref":
        # find the referenced object and return its value
        obj = get_ref_object(elem.get('id'), root)
        return get_value(obj[0], root)
    elif elem.tag == "stream":
        return unescapeHTMLEntities(elem[1].text.decode('base64'))
    elif elem.tag == "dict":
        # build the dictionary
        ret = {}
        size = elem.get("size")
        size = re.sub("%", "", size)
        dict_elems = elem.getchildren()
        for i in range(int(size)):
            val = get_value(dict_elems[i][0], root)
            if val is not None:
                ret[dict_elems[i].tag] = val
    elif elem.tag == "list":
        # build the list
        ret = []
        size = elem.get("size")
        size = re.sub("%", "", size)
        list_elems = elem.getchildren()
        for i in range(int(size)):
            val = get_value(list_elems[i], root)
            if val is not None:
                ret.append(val)
    else:
        # some tags not accounted for: Rect, field, xfa, Media, etc
        ret = None
    return ret


# find the object referenced in another object
def get_ref_object(id, root):
    for obj in root.iterfind(".//object"):
        if obj.get("id") == id:
            return obj
    else:
        return None


# Get any annotation objects in the PDF and store in the app object
def get_annots(app, root):
    for annot in root.iterfind(".//Annots"):
        annot_list = annot[0]
        for ref in annot_list:
            id = ref.get("id")
            obj = get_ref_object(id, root)
            new = get_value(obj[0], root)
            if new is not None:
                new["subject"] = new.pop("Subj")
                app['doc']['annots'].append(new)


# Mimic the Adobe event object by parsing the PDF for commonly found attributes
def create_event_obj(tree):
    event_attrs = ["author", "calculate", "creator", "creationDate", "delay", "dirty", "external", "filesize",
                   "keywords", "modDate", "numFields", "numPages", "numTemplates", "path", "pageNum", "producer",
                   "subject", "title", "zoom", "zoomType"]
    event = {}
    event["target"] = {}
    for item in event_attrs:
        for elem in tree.iterfind('.//' + item[0].upper() + item[1:]):
            val = get_value(elem[0], tree)
            if val is not None:
                event["target"][item] = val
    # print event
    return event


# Mimic the Adobe app object by parsing the PDF for commonly found attributes
def create_app_obj(tree):
    app = {}
    app_attrs = ["calculate", "formsVersion", "fullscreen", "language", "numPlugins", "openInPlace", "platform",
                 "toolbar", "toolbarHorizontal", "toolbarVertical"]
    doc = {}
    for item in app_attrs:
        for elem in tree.iterfind('.//' + item[0].upper() + item[1:]):
            val = get_value(elem[0], tree)
            if val is not None:
                doc[item] = val
    app['doc'] = doc;

    # Many app values are dependent on the reader
    # set some common defaults here
    app['doc']['viewerType'] = 'Reader'
    app['viewerType'] = 'Reader'
    app['viewerVersion'] = 5.0
    app['plugIns'] = [{'version': 6.0}, {'version': 7.5}, {'version': 8.7}, {'version': 9.1}, {'version': 10}]
    if not 'language' in app.keys():
        app['language'] = "ENU"
    if not 'platform' in app.keys():
        app['platform'] = "WIN"

    # store the annotation objects so they can be retrieved later
    app['doc']['annots'] = []
    get_annots(app, tree)
    # print app
    return app


# Mimic the Adobe info object by parsing the PDF for commonly found attributes
def create_info_obj(tree):
    info_attrs = ["author", "creator", "creationDate", "Date", "keywords", "modDate", "producer", "subject", "title",
                  "trapped"]
    info = {}
    for item in info_attrs:
        for elem in tree.iterfind('.//' + item[0].upper() + item[1:]):
            val = get_value(elem[0], tree)
            if val is not None:
                info[item] = val
    # print info
    return info
