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

from db_mgmt import DBGateway
from sdhasher import make_sdhash


class JSHasher(object):
    name = 'JSHasher'
    # query = "select rowid, js, de_js, swf, actionscript from clarified where (rowid > %s and rowid <= %s) limit 1;"
    # update = "update clarified set js_sdhash=?, de_js_sdhash=?, swf_sdhash=?, actionscript_sdhash=? where rowid is ?"
    query = "select rowid, js, swf from clarified where (rowid > %s and rowid <= %s) limit 1;"
    update = "update clarified set js_sdhash=?, swf_sdhash=? where rowid is ?"
    rowid = -1
    sdhash = ''
    setup = ('alter table clarified add column js_sdhash text;', 'alter table clarified add column swf_sdhash text;')
    proceed = True
    subs = None

    def __init__(self, MIN=-1, MAX=1000000):
        self.lastrow = MIN
        self.MAX = MAX

    def run(self, row):
        if not row:
            print 'Complete'
            proceed = False
        self.lastrow = row['rowid']
        jssdhash = make_sdhash(row['js'])
        # de_jssdhash = make_sdhash(row['de_js'])
        swfsdhash = make_sdhash(row['swf'])
        # actionscriptsdhash = make_sdhash(row['actionscript'])
        # self.subs = (jssdhash, de_jssdhash, swfsdhash, actionscriptsdhash, row['rowid'])
        self.subs = (jssdhash, swfsdhash, row['rowid'])
        self.verbose(row, 'js', jssdhash)
        # self.verbose(row, 'de_Js', de_jssdhash)
        self.verbose(row, 'swf', swfsdhash)
        # self.verbose(row, 'actionscript', actionscriptsdhash)

    def verbose(self, row, key, sdh):
        try:
            print 'SdHashed %s R:%s\t(%s)\t[%s]' % (key, self.lastrow, row[key][:16], sdh[:16])
        except TypeError:
            pass

    def query_cmd(self):
        return self.query % (self.lastrow, self.MAX)


class Mapper(object):
    def __init__(self, dbgateway, func_list):
        self.db = dbgateway
        self.funcs = func_list

    def setup(self, cmds):
        for cmd in cmds:
            if not self.db.query(cmd):
                err = self.db.get_error()
                sys.stderr.write("\tsetup: %s\n" % err)
                if 'duplicate' not in err:
                    return False
        return True

    def start(self):
        for func in self.funcs:
            print 'Mapping: %s' % func.name
            if func.setup:
                print '\tsetup:\t%s\n\t\t%s' % func.setup
                if not self.setup(func.setup):
                    continue
            while func.proceed:
                if not self.db.query(func.query_cmd()):
                    sys.stderr.write("query: %s\n" % self.db.get_error())
                else:
                    func.run(self.db.db_curr.fetchone())
                    if not self.db.query(func.update, func.subs):
                        sys.stderr.write("update: %s\n" % self.db.get_error())


if __name__ == '__main__':
    try:
        dbpath = sys.argv[1]
        if not os.path.exists(dbpath):
            raise IndexError
        MIN = sys.argv[2]
        MAX = sys.argv[3]
    except IndexError as e:
        print 'Invalid args: %s' % e
        sys.exit(0)
    else:
        db = DBGateway(os.path.basename(dbpath), os.path.dirname(dbpath))
        functions = [JSHasher(MIN, MAX), ]
        mapper = Mapper(db, functions)
        mapper.start()
        db.disconnect()
