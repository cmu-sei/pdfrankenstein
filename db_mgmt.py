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
import sqlite3

import cfg


class DBGateway(object):
    def __init__(self, db='', path=''):
        self.error = ''
        self.cfg = cfg.Config()
        
        if not db:
            self.db_dir = self.cfg.setting('database', 'path')
            self.db_name = self.cfg.setting('database', 'db')
        elif db is 'test':
            self.db_dir = os.getcwd()
            self.db_name = 'testdb.sqlite'
        else:
            if not path:
                self.db_dir = self.cfg.setting('database', 'path')
            else:
                self.db_dir = path
            self.db_name = db

        if not self.db_dir or not (os.path.isdir(self.db_dir)) or not self.db_name:
            sys.stderr.write("GError in database path or name. Check frankenstein.cfg file\n")
            sys.exit(1)

        self.db_path = os.path.join(self.db_dir, self.db_name)
        print('DBGateway connecting: %s' % self.db_path)
        self.connect(self.db_path)

    def query(self, cmd, params=''):
        try:
            if params:
                self.db_curr.execute(cmd, params)
            else:
                self.db_curr.execute(cmd)
            self.commit()
            return True
        except Exception as e:
            self.error = str(e)
            return False

    def queryblock(self, cmd, params='', n=30):
        done = False
        tries = 0
        while not done and tries < n:
            tries += 1
            try:
                if params:
                    self.db_curr.execute(cmd, params)
                else:
                    self.db_curr.execute(cmd)
            except Exception as e:
                self.error = str(e)
            else:
                done = True
        return done

    def get_error(self):
        err = self.error
        self.error = ''
        return err

    def attach(self, db_name):
        db = "'" + os.path.join(config.SETTINGS.get('DB_DIR'), db_name) + "'"
        self.db_curr.execute('ATTACH DATABASE ' + db + ' AS ' + db_name)
        self.db_conn.commit()

    def has_table(self, table):
        cmd = "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='%s'" % table
        if self.query(cmd):
            return self.db_curr.fetchone()[0]

    def create_table(self, table, **kwargs):
        try:
            kwargs = self.format_args(**kwargs)
            cmd = 'CREATE TABLE IF NOT EXISTS ' + table
            if kwargs.get('select'):
                cmd += ' AS SELECT ' + kwargs.get('select') + ' FROM ' + kwargs.get('from') + ' WHERE ' + kwargs.get(
                    'where') + '=' + kwargs.get('is')
            else:
                cmd += ' (' + kwargs.get('cols') + ', PRIMARY KEY(' + kwargs.get('primary') + '))'
        except TypeError as e:
            print 'Invalid arguments passed to database gateway:', kwargs
            raise e
        else:
            try:
                self.db_curr.execute(cmd)
            except sqlite3.OperationalError as error:
                print 'Invalid operation in database gateway:', error
                print 'Occurred during cmd:', cmd
                raise error
            else:
                self.db_conn.commit()
                # self.dump()

    def connect(self, path):
        try:
            self.db_conn = sqlite3.connect(path, 30)
        except Exception as e:
            sys.stderr.write("DBGateway connect: %s\n" % e)
            return None
        self.db_conn.text_factory = str
        self.db_conn.row_factory = sqlite3.Row
        self.db_curr = self.db_conn.cursor()

    def commit(self):
        self.db_conn.commit()

    def disconnect(self):
        self.commit()
        self.db_conn.close()

    def drop_tables(self):
        self.db_curr.execute("SELECT name FROM sqlite_master WHERE type='table'")
        for row in self.db_curr.fetchall():
            self.drop(row[0])

    def drop(self, name):
        self.db_curr.execute("DROP TABLE IF EXISTS " + name)
        self.db_conn.commit()

    def format_args(self, **kwargs):
        if isinstance(kwargs.get('primary'), (tuple, list)):
            kwargs['primary'] = ', '.join(kwargs['primary'])
        if isinstance(kwargs.get('cols'), (tuple, list)):
            kwargs['subs'] = ', '.join(['?' for arg in kwargs['cols']])
            kwargs['cols'] = ', '.join(kwargs['cols'])
        else:
            kwargs['subs'] = '?'
        return kwargs

    def insert(self, table, **kwargs):
        kwargs = self.format_args(**kwargs)
        cmd = 'INSERT OR REPLACE INTO ' + table + '(' + kwargs.get('cols') + ') VALUES (' + kwargs.get('subs') + ')'
        try:
            self.db_curr.execute(cmd, kwargs.get('vals'))
            self.db_conn.commit()
        except Exception as e:
            self.error = repr(e)
            return False
        else:
            return True

    def select(self, cmd_str):
        cmd = 'SELECT %s' % cmd_str
        self.db_curr.execute(cmd)
        return self.db_curr

    def count(self, table, key, val):
        cmd = "SELECT COUNT (*) FROM %s WHERE %s is '%s'" % (table, key, val)
        self.db_curr.execute(cmd)
        return self.db_curr.fetchone()[0]

    def update(self, dic):
        cmd = "UPDATE {tbl} SET {col} ='{val}' WHERE {key} ='{kval}'".format(**dic)
        print cmd
        try:
            # self.db_curr.execute(cmd, dic)
            self.db_curr.execute(cmd)
            self.db_conn.commit()
        except Exception as e:
            self.error = str(e)
            return False
        else:
            return True

    def delete(self, *ids):
        pass

    def dump(self, n=0):
        print ':MEMORY DB DUMP:'
        cnt = 0
        for val in self.db_conn.iterdump():
            cnt += 1
            if 0 < n <= cnt:
                break
            print val
        print ':MEMORY DB DUMP END:'

