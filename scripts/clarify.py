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
import sys
import time
import Queue
import multiprocessing
from subprocess import Popen, PIPE

import lxml.etree as ET
from jsbeautifier import beautify, default_options
from sdhasher import make_sdhash
from db_mgmt import DBGateway
from JSAnalysis import analyse

PID = os.getpid()

try:
    JSFLASH = sys.argv[1].lower()
    DBin_NAME = sys.argv[2]
    MIN = sys.argv[3]
    MAX = sys.argv[4]
except IndexError:
    sys.exit(1)

LASTROW = MIN

try:
    verbose = sys.argv[5].lower()
    print 'Spamming terminal'
except IndexError:
    verbose = ''

try:
    log = open('/media/sf_voodo_db/%s-%s.log' % (JSFLASH, PID), 'a')
except IOError:
    print 'Error opening log file. No logging'
    log = None


def logmsg(log, msg):
    if log:
        log.write(msg)
        log.flush()
    if verbose:
        sys.stdout.write(msg)
        sys.stdout.flush()


db_name = 'clarified-%s-%d.sqlite' % (JSFLASH, PID)
logmsg(log, 'Creating: %s\n\n' % db_name)

if JSFLASH == 'js':
    cmd = "select rowid, pdf_md5, tree, obf_js from parsed_pdfs where obf_js is not '' and de_js is ''  and (rowid > %s and rowid <= %s) order by rowid limit 1" % (
    '%s', MAX)
    update = "update parsed_pdfs set de_js='%s' where rowid is %s" % (db_name, '%s')
elif JSFLASH == 'flash':
    cmd = "select rowid, pdf_md5, tree, swf from parsed_pdfs where swf is not '' and (rowid > %s and rowid <= %s) order by rowid limit 1" % (
    '%s', MAX)
    update = "update parsed_pdfs set actionscript='%s' where rowid is %s" % (db_name, '%s')
logmsg(log, "%s\n%s\n" % (cmd, update))

jsopts = default_options()
jsopts.preserve_new_lines = False
jsopts.break_chained_methods = True

DB = DBGateway(DBin_NAME, '/media/sf_voodo_db/')
DBout = DBGateway(db_name, '/media/sf_voodo_db/')
if not DBout.query(
        'create table if not exists clarified (pdf_md5 TEXT, js TEXT, de_js TEXT, de_js_sdhash TEXT, swf TEXT, abc TEXT, actionscript TEXT, actionscript_sdhash TEXT, primary key(pdf_md5))'):
    err = DBout.get_error()
    logmsg(log, "%s\n" % err)
    sys.exit(1)

'''
Create an lxml tree from the xml string
'''


def tree_from_xml(xml):
    try:
        return ET.fromstring(xml)
    except Exception:
        return None


'''
Get JS/SWF from DB
'''


def get_row(log):
    global LASTROW
    if not DB.query(cmd % LASTROW):
        rv = ('', '', '', '')
        err = DB.get_error()
        logmsg(log, 'Get error: %s\n' % err)
    else:
        result = DB.db_curr.fetchone()
        try:
            rv = (result['rowid'], result['pdf_md5'], result['tree'], result['obf_js'])
            LASTROW = result['rowid']
        except IndexError:
            rv = (result['rowid'], result['pdf_md5'], result['tree'], result['swf'])
            LASTROW = result['rowid']
        except TypeError:
            rv = ('', '', '', '')
            LASTROW = result['rowid']
        else:
            pass
            '''
            LASTROW = result['rowid']
            upd = update % result['rowid']
            print upd
            if not DB.query(upd):
                err = DB.get_error()
                logmsg(log,'Update error: %s' % err)
            '''
    return rv


'''
Store clarified js
'''


def store(log, table, columns, values):
    if not DBout.insert(table, cols=columns, vals=values):
        err = DB.get_error()
        logmsg(log, 'Store error: %s\n' % err)


'''
Store a flash string in a file, call the tool on the file, and then read
from the stdout what was extracted. Store each.
'''


def decompile_flash(swf):
    javacmd = ['java', '-jar', 'ffdec.jar', '-export', 'script', '/tmp/actionscript', '/tmp/tmp.swf']
    if not swf:
        return 'None'
    try:
        fout = open('/tmp/tmp.swf', 'wb')
    except IOError as e:
        if verbose:
            print 'Error writing %s' % str(e)
        return 'Error: %s' % str(e)
    else:
        extracted = []
        script = ''
        fout.write(swf)
        fout.close()
        proc = Popen(javacmd, stdout=PIPE, stderr=PIPE)
        out, err = proc.communicate()
        proc.wait()
        for line in out.split('\n'):
            if line.startswith('Exported'):
                name = line.split(' ')[3].rstrip(',').replace('.', '/')
                extracted.append(name)
        for ext in extracted:
            try:
                fin = open('/tmp/actionscript/%s.as' % ext, 'r')
            except IOError as e:
                logmsg(log, 'Error reading: %s\n' % str(e))
            else:
                script = '\n'.join([script, fin.read()])
                fin.close()
        return script


qu = multiprocessing.Queue()


def run_analysis(code, etree, results):
    res = analyse(code, etree)
    results.put(res)
    results.close()


def clarify_js(code, etree):
    global qu
    rv = ''
    attempts = 0
    proc = multiprocessing.Process(target=run_analysis, args=(code, etree, qu))
    try:
        proc.start()
        proc.join(10)
        if proc.is_alive():
            logmsg(log, 'Timeout...')
            if not qu.empty():
                logmsg(log, 'getting large response...')
                rv = qu.get(False, 30)
            else:
                logmsg(log, 'inserting dummy response...')
                qu.put('Timeout')
            while proc.is_alive() and attempts < 10000:
                proc.terminate()
                time.sleep(.1)
                attempts += 1
            logmsg(log, 'Killed\n')
    except Exception as e:
        logmsg(log, str(e))
        qu.put(str(e))
    finally:
        if not rv:
            logmsg(log, 'getting response...')
            try:
                rv = qu.get(False, 30)
            except Queue.Empty:
                rv = 'None'
                logmsg(log, rv)
            logmsg(log, '\n')
        return rv


'''
While DB has rows with JS and clarified JS is not empty string
'''
cnt = 0
code = ''
de_js = ''
de_js_sdhash = ''
ascript = ''
as_sdhash = ''
etree = ''
logmsg(log, 'Begin loop\n')
while (True):

    rid, pdf, xml, code = get_row(log)
    if not pdf:
        logmsg(log, '%s: No pdf returned\n' % JSFLASH)
        break
    if not code:
        logmsg(log, '%s: No code returned %s\n' % (JSFLASH, pdf))
        continue
    cnt += 1

    if JSFLASH == 'js':
        msg = 'JS CNT: %6d\tRID: %6d\tFile: %s\n' % (cnt, rid, pdf)
        logmsg(log, msg)

        try:
            etree = tree_from_xml(xml)
            de_js = clarify_js(code, etree)
            de_js = beautify(de_js, jsopts)
            de_js_sdhash = make_sdhash(de_js, log)
        except Exception as e:
            de_js = 'error: %s' % e
            logmsg(log, 'Clarification error [%s]: %s\n' % (pdf, str(e)))

        col = ('pdf_md5', 'js', 'de_js', 'de_js_sdhash')
        val = (pdf, code, de_js, de_js_sdhash)
        store(log, 'clarified', col, val)

    elif JSFLASH == 'flash':
        msg = 'FL CNT: %6d\tRID: %6d\tFile: %s\n' % (cnt, rid, pdf)
        logmsg(log, msg)

        try:
            ascript = decompile_flash(code)
            as_sdhash = make_sdhash(ascript, log)
        except Exception as e:
            ascript = 'error: %s' % e
            logmsg(log, 'Decompilation error [%s]: %s\n' % (pdf, str(e)))

        col = ('pdf_md5', 'swf', 'actionscript', 'actionscript_sdhash')
        val = (pdf, code, ascript, as_sdhash)
        store(log, 'clarified', col, val)

try:
    log.close()
except Exception:
    pass

'''
Finish
'''
DB.commit()
DBout.commit()
DB.disconnect()
DBout.disconnect()
