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
import os
import re
import glob
import shutil
import select
import fileinput
from subprocess import Popen, PIPE

ERRMSG = ''


def errmsg():
    global ERRMSG
    tmp = ERRMSG
    ERRMSG = ''
    return tmp


def simple_name(filepath):
    return os.path.splitext(os.path.basename(filepath))[0]


def frame_id(string):
    mobj = re.match(r'.*([\d]+)\).*"(\w*)"', string, re.U)
    if mobj:
        return (mobj.groups())
    else:
        return None


def get_frame_ids(fin):
    frame_nums = []
    listcmd = 'furnace-swf -i %s abclist' % fin
    proc = Popen(listcmd, shell=True, stdout=PIPE, stderr=PIPE, close_fds=True)
    for line in iter(proc.stdout.readline, b''):
        line = str(line, encoding='utf-8')
        num_name = frame_id(line)
        if num_name:
            frame_nums.append(num_name)
    proc.communicate()
    return frame_nums


def extract_frame(fin, dout, num_name):
    if num_name[1]:
        abcfile = "%s-%s.abc" % (simple_name(fin), num_name[1])
    else:
        abcfile = "%s-%s.abc" % (simple_name(fin), num_name[0])
    extractcmd = 'furnace-swf -i %s abcextract -o %s -n %s' % (fin, os.path.join(dout, abcfile), num_name[0])
    proc = Popen(extractcmd, shell=True, close_fds=True)
    proc.wait()
    return abcfile


def furnace_bytecode(fin, dout):
    abcfiles = []
    name = simple_name(fin)
    frames = get_frame_ids(fin)
    for num_name in frames:
        abcfiles.append(extract_frame(fin, dout, num_name))
    return abcfiles


def furnace_actionscript(abcfiles, dout):
    asfiles = []
    for bytecode in abcfiles:
        name = "%s.as" % simple_name(bytecode)
        decompilecmd = 'furnace-avm2-decompiler -d -i %s > %s' % (
        os.path.join(dout, bytecode), os.path.join(dout, name))
        proc = Popen(decompilecmd, shell=True, close_fds=True)
        proc.wait()
        asfiles.append(os.path.join(dout, name))
    return asfiles


def concat_scripts(scripts, fout):
    with open(fout, 'w') as fout:
        for line in fileinput.input(scripts, mode='rb'):
            fout.write(line)


def furnace_extract(fin, dirname):
    name = simple_name(fin)
    dout = os.path.join(dirname, name + '-furnace')
    try:
        os.mkdir(dout)
    except OSError as e:
        if e.errno == 17:
            pass
        else:
            print(e)
            ERRMSG = str(e)
            return None
    abcfiles = furnace_bytecode(fin, dout)
    asfiles = furnace_actionscript(abcfiles, dout)
    if len(asfiles) > 1:
        concat_scripts(asfiles, os.path.join(dout, "%s-all.as" % name))
    return True


def jpexs_extract(fin, dirname):
    global ERRMSG
    name = ''
    script = ''
    extracted = []
    fname = fin
    dout = os.path.join(dirname, os.path.splitext(os.path.basename(fname))[0] + '-jpexs')
    # javacmd = ['java', '-jar', 'ffdec.jar', '-export', 'script', dout, fname ]
    # javacmd = 'java -Djava.awt.headless=true -jar /Users/honey/src/work/pdf/thisneedsacoolname/ffdec.jar -format script:pcode -export script %s %s' % (dout, fname)
    javacmd = 'java -Djava.awt.headless=true -jar /Users/honey/src/work/pdf/thisneedsacoolname/ffdec.jar -export script %s %s' % (
    dout, fname)

    try:
        os.mkdir(dout)
    except OSError as e:
        if e.errno == 17:
            pass
        else:
            print('jpexs_extract mkdir(%s): %s' % (dout, e))
            ERRMSG = str(e)
            return None

    proc = Popen(javacmd, shell=True, stdout=PIPE, stderr=PIPE, close_fds=True, cwd=dout)

    p = select.poll()
    p.register(proc.stderr.fileno(), select.POLLIN | select.POLLPRI)
    for line in iter(proc.stdout.readline, b''):
        line = str(line, encoding='utf-8')
        if line.startswith('Exported'):
            mobj = re.match(r"^Exported\s[^\d]*[\d]+/[\d]+\s([^,]+)\,\s", line, re.U)
            if mobj:
                name = mobj.group(1).replace('.', '/').replace(' ', '\ ')
                extracted.append(name)
        if p.poll(1):
            err = str(proc.stderr.readline(), encoding='utf-8')
            if err.startswith('FAIL') or err.startswith('SEVERE'):
                proc.kill()
                sys.stderr.write("jpexs_extract error %s\n" % err)
                shutil.rmtree(dout)
                ERRMSG = err
                return None

    out, err = proc.communicate()
    if err:
        ERRMSG = err

    for srcfile in extracted:
        try:
            fin = open('%s/%s.as' % (dout, srcfile), 'r')
        except IOError as e:
            print('jpexs_extract open(srcfile): %s' % e)
            ERRMSG = str(e)
            return None
        else:
            script += '\n'.join([line.rstrip() for line in fin.readlines()])
            script += '\n'
            fin.close()

    if not script:
        return None

    try:
        fout = open('%s/%s-all.as' % (dout, os.path.splitext(os.path.basename(fname))[0]), 'w')
    except IOError as e:
        print('jpexs_extract open(fout): %s' % e)
        ERRMSG = str(e)
        return None
    else:
        fout.write(script)
        fout.close()
        return True


def main(din, dout='', tool='jpexs'):
    if not dout:
        dout = din
    if not os.path.isdir(dout):
        sys.stderr.write("Invalid directory: %s\n" % dout)
        return None
    files = glob.glob(os.path.join(din, '*.swf'))

    fdone = None
    ferr = None
    completed = set()
    try:
        fdone = open("%s/done.txt" % dout, "r")
    except IOError as e:
        if e.errno != 2:
            sys.stderr.write("%s\n" % e)
            sys.exit(0)
    else:
        completed = set([l.rstrip() for l in fdone.readlines()])
        fdone.close()

    total = 0
    errors = 0
    for f in files:
        md5name = os.path.splitext(os.path.basename(f))[0]
        if md5name not in completed:
            total += 1
            sys.stdout.write("Processing:\t%s\t" % md5name)
            if tool == 'jpexs':
                rv = jpexs_extract(f, dout)
            elif tool == 'furnace':
                rv = furnace_extract(f, dout)
            if rv:
                sys.stdout.write("complete\n")
                try:
                    fdone = open("%s/done.txt" % dout, "a")
                    fdone.write("%s\n" % md5name)
                except IOError as e:
                    sys.stderr.write("Unable to write to log file, done.txt: %s\n" % e)
                else:
                    fdone.close()
            else:
                errors += 1
                sys.stdout.write("error\n")
                try:
                    ferr = open("%s/err.txt" % dout, "a")
                    ferr.write("%s\n%s\n\n" % (md5name, errmsg()))
                except IOError as e:
                    sys.stderr.write("Unable to write to log file, err.txt: %s\n" % e)
                    continue
                else:
                    ferr.close()
        else:
            sys.stdout.write("Skipping:\t%s\n" % md5name)

    sys.stdout.write("Complete:\t%d\nFailures:\t%d\nTotal jobs:\t%d\n" % (total - errors, errors, total))


if __name__ == '__main__':
    try:
        dir_in = sys.argv[1]
    except IndexError:
        dir_in = './'

    try:
        dir_out = os.path.abspath(os.path.expandvars(os.path.expanduser(sys.argv[2])))
    except IndexError:
        dir_out = './'

    try:
        tool = sys.argv[3]
    except IndexError:
        tool = 'jpexs'

    if os.path.isdir(dir_in):
        main(dir_in, dir_out, tool)
