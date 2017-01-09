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

import htmlentitydefs


def unescapeHTMLEntities(text):
    """

    Removes HTML or XML character references and entities from a text string.
    @param text The HTML (or XML) source text.
    @return The plain text, as a Unicode string, if necessary.
    Author: Fredrik Lundh
    Source: http://effbot.org/zone/re-sub.htm#unescape-html
    """

    def fixup(m):
        text = m.group(0)
        if text[:2] == '&#':
            # character reference
            try:
                if text[:3] == '&#x':
                    return unichr(int(text[3:-1], 16))
                else:
                    return unichr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text  # leave as is

    return str(re.sub('&#?\w+;', fixup, text))


def isFlash(content):
    """

    Check for swf content in a string by searching for CWS or FWS
    in the first three characters
    :param content: Stream content from an XML/HTML doc
    :return: True if content has a correct flash header value of 'CWS' or 'FWS'
    """
    content = unescapeHTMLEntities(content)
    return content.startswith("CWS") or content.startswith("FWS")
