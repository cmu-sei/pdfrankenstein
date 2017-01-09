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

import cfg
from db_mgmt import DBGateway

TABLE = 'parsed_pdfs'
PRIMARY = 'pdf_md5'
COLUMNS = ('category',
           'pdf_md5',
           'tree_md5',
           'tree',
           'graph',
           'obf_js',
           'obf_js_sdhash',
           'de_js',
           'de_js_sdhash',
           'swf',
           'swf_sdhash',
           'abc',
           'abc_sdhash',
           'actionscript',
           'as_sdhash',
           'shellcode',
           'fsize',
           'pdfsize',
           'bin_blob',
           'urls',
           'malformed',
           'errors')


class StorageFactory(object):

    def __init__(self):
        self.cfg = cfg.Config()

    def new_storage(self, typ, name='', user='', pw=''):
        if not name:
            name = self.cfg.setting("database", "db")
        if not user:
            user = self.cfg.setting("database", "user")
        if not pw:
            ps = self.cfg.setting("database", "pw")
        sys.stderr.write("Storage type,name,user: %s,%s,%s\n" % (typ, name, user))
        
        if typ == 'stdout':
            return StdoutStorage()
        if typ == 'sqlite3':
            return DbStorage(name)
        if typ == 'postgres':
            try:
                import psycopg2
            except ImportError as e:
                sys.stderr.write("Failed to import PostgreSQL Python library 'psycopg2': %s\n" % e)
                return None
            else:
                return PostgresStorage(name, user, pw)
        if typ == 'neo4j':
            return NeoStorage()
        if typ == 'file':
            return FileStorage(name + '.txt')


class Storage(object):
    def __init__(self):
        pass

    def open(self):
        return False

    def store(self):
        pass

    def close(self):
        pass

    def align_kwargs(self, data):
        aligned = []
        for col in COLUMNS:
            aligned.append(data.get(col, ''))
        return tuple(aligned)


class PostgresStorage(Storage):
    insert = "INSERT INTO parsed_pdfs (%s) VALUES (%s)"
    create = "CREATE TABLE IF NOT EXISTS parsed_pdfs (rowid serial, %s TEXT, PRIMARY KEY (rowid, pdf_md5))"

    def __init__(self, dbname, user, pw=''):
        self.dbname = dbname
        self.user = user
        self.pw = pw
        ccols = ' TEXT, '.join(COLUMNS)
        icols = ', '.join(COLUMNS)
        markers = ', '.join(['%s' for x in COLUMNS])
        self.create = self.create % (ccols)
        self.insert = self.insert % (icols, markers)

    def open(self):
        try:
            self.conn = psycopg2.connect(database=self.dbname, user=self.user, password=self.pw)
            cur = self.conn.cursor()
            cur.execute(self.create)
            self.conn.commit()
        except Exception as e:
            sys.stderr.write("Postgres Connect Error\t%s\n" % (str(e)))
            sys.stderr.flush()
            return False
        else:
            cur.close()
            return True

    def store(self, data_dict):
        data_tuple = self.align_kwargs(data_dict)
        try:
            cur = self.conn.cursor()
            cur.execute(self.insert, data_tuple)
        except Exception as e:
            self.conn.rollback()
        else:
            self.conn.commit()
            cur.close()

    def close(self):
        self.conn.commit()
        self.conn.close()


class NeoStorage(Storage):
    pass


class StdoutStorage(Storage):

    def open(self):
        return True

    def store(self, data_dict):
        sys.stdout.write("%s\n" % data_dict)

    def close(self):
        pass

class DbStorage(Storage):
    def __init__(self, db=''):
        self.db = DBGateway(db + '.sqlite')

    def open(self):
        try:
            self.db.create_table(TABLE, cols=[' '.join([col, 'TEXT']) for col in COLUMNS], primary=PRIMARY)
        except Exception:
            return False
        else:
            return True

    def store(self, data_dict):
        data_tuple = self.align_kwargs(data_dict)
        if not self.db.insert(TABLE, cols=COLUMNS, vals=data_tuple):
            err_tuple = (data_dict.get('pdf_md5'), 'DB_ERROR: %s' % self.db.get_error())
            self.db.insert(TABLE, cols=['pdf_md5', 'errors'], vals=err_tuple)

    def close(self):
        self.db.disconnect()

    def contains(self, key, val):
        return self.db.count(TABLE, key, val)


class FileStorage(Storage):
    def __init__(self, path):
        self.path = path
        try:
            self.fd = open(path, 'wb')
        except IOError as e:
            print e
            print 'Unable to create output. Exiting.'
            sys.exit(1)
        else:
            self.fd.close()

    def open(self):
        try:
            self.fd = open(self.path, 'wb')
        except IOError:
            return False
        else:
            return True

    def store(self, data_dict):
        # self.json.dump(data_dict, self.fd, separators=(',', ':'))
        header = '%s\n%s\n%s\n' % ('-' * 80, data_dict.get('pdf_md5', 'N/A'), '-' * 80)
        footer = '\n'

        self.fd.write(header)
        for k, v in data_dict.items():
            try:
                self.fd.write("__%s\n" % k)
                self.fd.write(v)
                self.fd.write("\n\n")
            except IOError as e:
                sys.stderr.write("FileStorage store IO error: %s\n" % e)
                sys.exit(0)
        self.fd.write(footer)

    def close(self):
        self.fd.close()


if __name__ == '__main__':
    tests = ['test.test', 'db', 'pg', 'neo4j']
    for test in tests:
        storage = StorageFactory().new_storage(test, "500k-test")
        print "%s.open()\t%s" % (test, storage.open())
