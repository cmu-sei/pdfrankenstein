import os
import re
import sys
import json
import time
import getopt
import hashlib
import traceback
import multiprocessing
from Queue import Empty

import cfg
from lib.scandir import scandir
from storage import StorageFactory
from sdhasher import make_sdhash
import huntterp
import xml_creator
from util.str_utils import unescapeHTMLEntities as unescapeHTML
from JSAnalysis import analyse

try:
    import argparse
except ImportError:
    print("lack of argparse support")
    argparse = None

LOCK = multiprocessing.Lock()
CFG=cfg.Config()

class ParserFactory(object):
    def new_parser(self):
        parser = None
        try:
            parser = ArgParser()
        except ImportError:
            parser = GetOptParser()
        finally:
            return parser


class ParsedArgs(object):
    """
    This is the namespace for our parsed arguments to keep dot access.
    Otherwise we would create a dictionary with vars(args) in ArgParser,
    or manually in GetOptParser. (6 and 1/2 dozen of the other.)

    Defaults set here for GetOpt's shortcomings.
    """
    pdf_in = None
    out = CFG.setting("general", "output")
    debug = False
    verbose = False
    hasher = 'PDFMiner'


class ArgParser(object):
    def __init__(self):
        if not argparse:
            print('Error in ArgParser. Unable to import argparse')
            sys.exit(1)
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument('pdf_in', help="PDF input for analysis")
        self.parser.add_argument('-d', '--debug', action='store_true', default=False,
                                 help="Print debugging messages")
        self.parser.add_argument('-o', '--out', default='stdout',
                                 help="Analysis output filename or type. Default to 'unnamed-out.*' file in CWD. Options: 'sqlite3'||'postgres'||'stdout'||'file'")
        self.parser.add_argument('-n', '--name', default='',
                                 help="Name for output when database or file is used. *.sqlite is appended to sqlite output.")
        self.parser.add_argument('--hasher', default='pdfminer',
                                 help='Specify which type of hasher to use. PeePDF | PDFMiner (default)')
        self.parser.add_argument('-v', '--verbose', action='store_true', default=False, help="Spam the terminal, TODO")

    def parse(self):
        """
        No need to pass anything; defaults to sys.argv (cli)
        """
        try:
            parsed = ParsedArgs()
            self.parser.parse_args(namespace=parsed)
        except Exception:
            self.parser.exit(status=0, message='Usage: pdfrankenstein.py <input pdf> [-o] [-d] [-v]\n')
        else:
            return parsed


class GetOptParser(object):
    """
    Necessary for outdated versions of Python. Versions that aren't even
    updated, and won't even have src code security updates as of 2013.
    """
    shorts = 'o:h:dv'
    longs = ['out=', 'hasher=', 'debug', 'verbose']

    def parse(self):
        parsed = ParsedArgs()
        opts, remain = self._parse_cli()
        parsed.pdf_in = remain[0]
        for opt, arg in opts:
            if opt in ('-o', '--out'):
                '''
                GetOpt can't recognize the difference between a missing value
                for '-o' and the next flag: '-d', for example. This creates a
                file called '-d' as output, and rm can't remove it since that
                is a flag for rm.
                '''
                if arg[0].isalnum():
                    parsed.out = arg
                else:
                    print('Invalid output name. Using default:' + str(parsed.out))
            elif opt in ('-d', '--debug'):
                parsed.debug = True
            elif opt in ('-v', '--verbose'):
                parsed.verbose = True
        return parsed

    def _parse_cli(self):
        try:
            o, r = getopt.gnu_getopt(sys.argv[1:], self.shorts, self.longs)
        except IndexError:
            print('Usage: pdfrankenstein.py <input pdf> [-o value] [-d] [-v]')
            sys.exit(1)
        else:
            if len(r) != 1:
                print('One PDF file or directory path required')
                print('Usage: pdfrankenstein.py <input pdf> [-o value] [-d] [-v]')
                sys.exit(1)
            return o, r


class HasherFactory(object):
    def get_hasher(self, hasher, **kwargs):
        typ = intern(hasher.lower())
        if typ is "peepdf":
            return PeePDFHasher(**kwargs)
        if typ is "pdfminer":
            return PDFMinerHasher(**kwargs)


class Hasher(multiprocessing.Process):
    """
    Hashers generally make hashes of things
    """

    def __init__(self, qin, qout, counter, debug):
        multiprocessing.Process.__init__(self)
        self.qin = qin
        self.qout = qout
        self.counter = counter
        self.debug = debug

    '''
    This loop is the main process of the hasher. It is automatically called
    when you call multiprocessing.Process.start()

    All variables should be local to the loop, and returned as strings
    suitable for inserting into the database.
    '''

    def run(self):
        while True:
            pdf = self.qin.get()
            if not pdf:
                '''
                This terminates the process by receiving a poison sentinel, None.
                '''
                self.qout.put(None)
                self.qin.task_done()
                return 0

            '''
            Reset the values on each pdf.
            '''
            err = []
            urls = ''
            t_hash = ''
            t_str = ''
            graph = ''
            obf_js = ''
            de_js = ''
            obf_js_sdhash = ''
            de_js_sdhash = ''
            swf_sdhash = ''
            swf = ''
            fsize = ''
            pdfsize = ''
            bin_blob = ''
            malformed = {}

            '''
            Arguments are validated when Jobber adds them to the queue based
            on the Validators valid() return value. We can assume these will
            succeed. However, this process must reach the task_done() call,
            and so we try/catch everything
            '''
            try:
                pdf_name = pdf.rstrip(os.path.sep).rpartition(os.path.sep)[2]
            except Exception as e:
                err.append('UNEXPECTED OS ERROR:\n%s' % traceback.format_exc())
                pdf_name = pdf
            write('H\t#%d\t(%d / %d)\t%s\n' % (self.pid, self.counter.value(), self.counter.ceil(), pdf_name))
            '''
            The parse_pdf call will return a value that evaluates to false if it
            did not succeed. Error messages will appended to the err list.
            '''
            parsed_pdf = self.parse_pdf(pdf, err)

            if parsed_pdf:
                try:
                    fsize = self.get_file_size(pdf)
                    pdfsize = self.get_pdf_size(parsed_pdf, err)
                    graph = self.make_graph(parsed_pdf, err)
                    t_str = self.make_tree_string(parsed_pdf, err)
                    t_hash = self.make_tree_hash(graph, err)
                    obf_js = self.get_js(parsed_pdf, err)
                    de_js = self.get_deobf_js(obf_js, parsed_pdf, err)
                    obf_js_sdhash = make_sdhash(obf_js, err)
                    de_js_sdhash = make_sdhash(de_js, err)
                    urls = self.get_urls(obf_js, err)
                    urls += self.get_urls(de_js, err)
                    swf = self.get_swf(parsed_pdf, err)
                    swf_sdhash = make_sdhash(swf, err)
                    bin_blob = parsed_pdf.bin_blob
                    malformed = parsed_pdf.getmalformed()
                    self.get_errors(parsed_pdf, err)
                except Exception as e:
                    err.append('UNCAUGHT PARSING EXCEPTION:\n%s' % traceback.format_exc())

            err = 'Error: '.join(err)
            malformed['skipkeys'] = False
            try:
                json_malformed = json.dumps(malformed)
            except (TypeError, ValueError):
                malformed['skipkeys'] = True
                json_malformed = json.dumps(malformed, skipkeys=True)

            self.qout.put({'fsize': fsize,
                           'pdf_md5': pdf_name,
                           'tree_md5': t_hash,
                           'tree': t_str,
                           'obf_js': obf_js,
                           'de_js': de_js,
                           'swf': swf,
                           'graph': graph,
                           'pdfsize': pdfsize,
                           'urls': urls,
                           'bin_blob': bin_blob,
                           'obf_js_sdhash': obf_js_sdhash,
                           'de_js_sdhash': de_js_sdhash,
                           'swf_sdhash': swf_sdhash,
                           'malformed': json_malformed,
                           'errors': err})
            self.counter.inc()
            self.qin.task_done()

    def parse_pdf(self, pdf, err=''):
        return None, 'Hasher: Unimplemented method, %s' % sys._getframe().f_code.co_name

    def get_file_size(self, pdf):
        try:
            size = os.path.getsize(pdf)
        except OSError:
            '''
            This should never actually happen if we were able to parse it
            '''
            size = 0
        return str(size)

    def get_pdf_size(self, pdf):
        return 'Hasher: Unimplemented method, %s' % sys._getframe().f_code.co_name

    def make_graph(self, pdf, err=''):
        return 'Hasher: Unimplemented method, %s' % sys._getframe().f_code.co_name

    def make_tree_string(self, pdf, err=''):
        return 'Hasher: Unimplemented method, %s' % sys._getframe().f_code.co_name

    def make_tree_hash(self, t_str, err=''):
        t_hash = ''
        m = hashlib.md5()
        try:
            m.update(t_str)
            t_hash = m.hexdigest()
        except TypeError:
            err.append('<HashException>%s</HashException>' % traceback.format_exc())
        return t_hash

    def get_js(self, pdf, err=''):
        return 'Hasher: Unimplemented method, %s' % sys._getframe().f_code.co_name

    def get_debof_js(self, js, pdf, err=''):
        return 'Hasher: Unimplemented method, %s' % sys._getframe().f_code.co_name

    def get_swf(self, pdf, err=''):
        return 'Hasher: Unimplemented method, %s' % sys._getframe().f_code.co_name

    def get_errors(self, pdf, err=''):
        return 'Hasher: Unimplemented method, %s' % sys._getframe().f_code.co_name

    def get_urls(self, haystack, err='', needle=''):
        urls = ''
        if not needle:
            for needle in huntterp.Test.tests:
                urls = huntterp.find_in_hex(needle, haystack)
                urls += huntterp.find_unicode(needle, haystack)
        else:
            urls = huntterp.find_in_hex(needle, haystack)
            urls += huntterp.find_unicode(haystack)
        return '\n'.join([u[1] for u in urls])


class PDFMinerHasher(Hasher):
    def parse_pdf(self, pdf, err):
        parsed = False
        try:
            parsed = xml_creator.FrankenParser(pdf, self.debug)
        except Exception:
            err.append('<ParseException><pdf="%s">"%s"</ParseException>' % (str(pdf), traceback.format_exc()))
            if self.debug:
                write('\nPDFMinerHasher.parse_pdf():\n\t%s\n' % err[-1])
        return parsed

    def make_tree_string(self, pdf, err):
        if pdf.xml:
            return pdf.xml
        else:
            return '<TreeException>EMPTY TREE</TreeException>'

    def get_js(self, pdf, err):
        js = ''
        try:
            js_list = [self.comment_out(js) for js in pdf.javascript]
            js = '\n\n'.join(js_list)
        except Exception as e:
            err.append('<GetJSException>%s</GetJSException>' % traceback.format_exc())
        return js

    def get_deobf_js(self, js, pdf, err):
        de_js = ''
        try:
            if pdf.tree.startswith('TREE_ERROR'):
                err.append('<DeobfuscateJSException>%s</DeobfuscateJSException>' % pdf.tree)
        except AttributeError:
            try:
                de_js = analyse(js, pdf.tree)
                pass
            except Exception as e:
                err.append('<DeobfuscateJSException>%s</DeobfuscateJSException>' % traceback.format_exc())
        return de_js

    def get_swf(self, pdf, err):
        swf = ''
        if pdf.swf:
            if isinstance(pdf.swf, list):
                swf = ''.join(pdf.swf)
            elif isinstance(pdf.swf, str):
                swf = pdf.swf
        return swf

    def get_pdf_size(self, pdf, err):
        return str(pdf.bytes_read)

    def get_errors(self, pdf, err):
        err.extend(pdf.errors)

    def make_graph(self, pdf, err):
        graph = ''
        try:
            graph = pdf.make_graph(pdf.tree)
            graph = '\n'.join(graph)
        except Exception as e:
            err.append('<GetJSException>%s</GetJSException>' % traceback.format_exc())
        return graph

    def comment_out(self, js):
        return re.sub("^(<)", "//", unescapeHTML(js), flags=re.M)


class PeePDFHasher(Hasher):
    def parse_pdf(self, pdf, err):
        retval = True
        try:
            _, pdffile = self.PDFParser().parse(pdf, forceMode=True, manualAnalysis=True)
        except Exception as e:
            retval = False
            pdffile = '\n'.join([traceback.format_exc(), repr(e)])
        return pdffile

    def get_swf(self, pdf, err):
        swf = ''
        for version in range(pdf.updates + 1):
            for idx, obj in pdf.body[version].objects.items():
                if obj.object.type == 'stream':
                    stream_ident = obj.object.decodedStream[:3]
                    if stream_ident in ['CWS', 'FWS']:
                        swf += obj.object.decodedStream.strip()
        return swf

    def get_js(self, pdf, err):
        js = ''
        for version in range(pdf.updates + 1):
            for obj_id in pdf.body[version].getContainingJS():
                js += self.do_js_code(obj_id, pdf)
        return js

    def make_tree_string(self, pdf, err):
        try:
            t_str = self.do_tree(pdf)
        except Exception as e:
            t_str = 'ERROR: ' + repr(e)
        return t_str

    def do_js_code(self, obj_id, pdf):
        consoleOutput = ''
        obj_id = int(obj_id)
        pdfobject = pdf.getObject(obj_id, None)
        if pdfobject.containsJS():
            jsCode = pdfobject.getJSCode()
            for js in jsCode:
                consoleOutput += js
        return consoleOutput

    def do_tree(self, pdfFile):
        version = None
        treeOutput = ''
        tree = pdfFile.getTree()
        for i in range(len(tree)):
            nodesPrinted = []
            root = tree[i][0]
            objectsInfo = tree[i][1]
            if i != 0:
                treeOutput += os.linesep + ' Version ' + str(i) + ':' + os.linesep * 2
            if root != None:
                nodesPrinted, nodeOutput = self.printTreeNode(root, objectsInfo, nodesPrinted)
                treeOutput += nodeOutput
            for object in objectsInfo:
                nodesPrinted, nodeOutput = self.printTreeNode(object, objectsInfo, nodesPrinted)
                treeOutput += nodeOutput
        return treeOutput

    def printTreeNode(self, node, nodesInfo, expandedNodes=[], depth=0, recursive=True):
        '''
            Given a tree prints the whole tree and its dependencies

            @param node: Root of the tree
            @param nodesInfo: Information abour the nodes of the tree
            @param expandedNodes: Already expanded nodes
            @param depth: Actual depth of the tree
            @param recursive: Boolean to specify if it's a recursive call or not
            @return: A tuple (expandedNodes,output), where expandedNodes is a list with the distinct nodes and output is the string representation of the tree
        '''
        output = ''
        if nodesInfo.has_key(node):
            if node not in expandedNodes or (node in expandedNodes and depth > 0):
                output += '\t' * depth + nodesInfo[node][0] + ' (' + str(node) + ')' + os.linesep
            if node not in expandedNodes:
                expandedNodes.append(node)
                children = nodesInfo[node][1]
                if children != []:
                    for child in children:
                        if nodesInfo.has_key(child):
                            childType = nodesInfo[child][0]
                        else:
                            childType = 'Unknown'
                        if childType != 'Unknown' and recursive:
                            expChildrenNodes, childrenOutput = self.printTreeNode(child, nodesInfo, expandedNodes,
                                                                                  depth + 1)
                            output += childrenOutput
                            expandedNodes = expChildrenNodes
                        else:
                            output += '\t' * (depth + 1) + childType + ' (' + str(child) + ')' + os.linesep
                else:
                    return expandedNodes, output
        return expandedNodes, output


class Stasher(multiprocessing.Process):
    """
    Stashers are the ant from the ant and the grashopper fable. They save
    things up for winter in persistent storage.
    """

    def __init__(self, qin, store_type, store_name, counter, qmsg, nprocs):
        multiprocessing.Process.__init__(self)
        self.qin = qin
        self.counter = counter
        self.qmsg = qmsg
        self.nprocs = nprocs
        self.store_type = store_type
        self.store_name = store_name
        self.storage = None

    def setup(self):
        write("%s" % self.qmsg.get())
        self.storage = StorageFactory().new_storage(self.store_type, name=self.store_name)
        if not self.storage:
            print("Error in storage setup")
            return False
        return self.storage.open()

    def run(self):
        proceed = self.setup()
        write("Proceeding: %s\n" % (str(proceed)))
        nfinished = 0
        while proceed:
            try:
                t_data = self.qin.get()
            except Empty:
                write('S Empty job queue.\n')
                proceed = False
            else:
                if not t_data:
                    nfinished += 1
                    proceed = not nfinished == self.nprocs
                    write('S Received a finished message (%d of %d)\n' % (nfinished, self.nprocs))
                else:
                    write('S\t#%d\t%s\n' % (self.pid, t_data.get('pdf_md5')))
                    try:
                        self.storage.store(t_data)
                    except Exception as e:
                        write('S\t#%d ERROR storing\t%s\t%s\n' % (self.pid, t_data.get('pdf_md5'), str(e)))
                    self.counter.inc()
                self.qin.task_done()

        self.cleanup()
        self.finish()

    def cleanup(self):
        try:
            self.storage.close()
        except AttributeError:
            pass
        self.qmsg.task_done()

    def finish(self):
        write('Stasher: Storage closed. Exiting.\n')


class Counter(object):
    def __init__(self, soft_max=0, name='Untitled'):
        self.counter = multiprocessing.RawValue('i', 0)
        self.hard_max = multiprocessing.RawValue('i', 0)
        self.soft_max = soft_max
        self.lock = multiprocessing.Lock()
        self.name = name

    def inc(self):
        with self.lock:
            self.counter.value += 1

    def value(self):
        with self.lock:
            return self.counter.value

    def complete(self):
        with self.lock:
            if self.hard_max > 0:
                return self.counter.value == self.hard_max.value

    def ceil(self):
        return self.hard_max.value


class Jobber(multiprocessing.Process):
    sample_cols = ['name', 'path', 'family', 'category', 'type', 'set0', 'set1', 'set2', 'set3', 'set4']
    job_cols = ['sample', 'started', 'finished']

    def __init__(self, job_list, job_qu, validator, counters, num_procs):
        multiprocessing.Process.__init__(self)
        self.jobs = job_list
        self.qu = job_qu
        self.qu.cancel_join_thread()
        self.counters = counters
        self.validator = validator
        self.num_procs = num_procs

    def run(self):
        write("Jobber started\n")
        job_cnt = 0
        x = 0
        for job in self.jobs:
            try:
                # Scandir results pass in objects with .path for dirs
                job_path = job.path
            except AttributeError:
                # File list input uses just a path per line
                job_path = job

            if self.validator.valid(job_path):
                self.qu.put(job_path)
                job_cnt += 1
                if job_cnt % 1000 == 0:
                    sys.stdout.write("Jobs: %d+\n" % job_cnt)
                    sys.stdout.flush()
        for n in range(self.num_procs):
            self.qu.put(None)
        for counter in self.counters:
            counter.soft_max = job_cnt
            counter.hard_max.value = job_cnt
        write(
            "\n-------------------------------------------\nJob queues complete: %d processes. Counters set: %d.\n-----------------------------------------------------\n" % (
                self.num_procs, job_cnt))


class ProgressBar(multiprocessing.Process):
    def __init__(self, counters, io_lock, qu):
        multiprocessing.Process.__init__(self)
        self.counters = counters
        self.io_lock = io_lock
        self.msg_qu = qu

    def run(self):
        while any(not c.complete() for c in self.counters):
            time.sleep(.1)
            for counter in self.counters:
                self.progress(counter)
            write('\r')
        write('\n')

    def progress(self, counter):
        cnt = counter.value()
        ceil = counter.ceil()
        prct = cnt * 1.0 / ceil * 100
        write('[%s: %07d of %07d %03.02f%%]\t' % (counter.name, cnt, counter.ceil(), prct))

    def check_msgs(self):
        rv = True
        if not self.msg_qu.empty():
            msg = self.msg_qu.get()
            if not msg:
                rv = False
            else:
                sys.stdout.write('<MSG: %s>' % msg)
            self.msg_qu.task_done()
        return rv


class Validator(object):
    def valid(self, obj):
        return False


class FileValidator(Validator):
    def valid(self, fname):
        return os.path.isfile(fname)


def write(msg):
    with LOCK:
        sys.stdout.write(msg)
        sys.stdout.flush()


if __name__ == '__main__':
    pdfs = []
    args = ParserFactory().new_parser().parse()
    num_procs = multiprocessing.cpu_count() / 2 - 3
    num_procs = num_procs if num_procs > 0 else 1
    print('Running on %d processes' % num_procs)

    if os.path.isdir(args.pdf_in):
        dir_name = os.path.join(args.pdf_in, '*')
        print('Examining directory %s' % dir_name)
        pdfs = scandir(args.pdf_in)
    elif os.path.exists(args.pdf_in):
        print('Analyzing file: %s' % args.pdf_in)
        fin = ''
        try:
            fin = open(args.pdf_in, 'r')
        except IOError as e:
            print("%s" % e)
            sys.exit(0)
        else:
            pdfs = [line.rstrip() for line in fin.readlines()]
            fin.close()
        print('Found %d jobs in file' % len(pdfs))
    else:
        print('Unable to find PDF file/directory: %s' % args.pdf_in)
        sys.exit(1)

    '''
    Locks
    '''
    io_lock = multiprocessing.Lock()

    '''
    Queues
    '''
    jobs = multiprocessing.JoinableQueue()
    results = multiprocessing.JoinableQueue()
    msgs = multiprocessing.JoinableQueue()

    '''
    Counters
    '''
    job_counter = Counter('Hashed')
    result_counter = Counter('Stored')
    counters = [job_counter, result_counter]

    '''
    Jobber and Jobs Validator
    '''
    job_validator = FileValidator()
    jobber = Jobber(pdfs, jobs, job_validator, counters, num_procs)

    '''
    Workers
    '''
    hf = HasherFactory()
    print('Creating hashing processings')
    hashers = [hf.get_hasher(hasher=args.hasher, qin=jobs, qout=results, counter=job_counter, debug=args.debug) for cnt
               in range(num_procs)]
    print('Creating stash process')
    stasher = Stasher(qin=results, store_type=args.out, store_name=args.name, counter=result_counter, qmsg=msgs,
                      nprocs=num_procs)
    # progress = ProgressBar(counters, LOCK, msgs)

    '''
    Begin processing
    '''
    write("Starting jobber...\n")
    jobber.start()

    msgs.put("Starting stashing job process...\n")
    stasher.start()
    time.sleep(5)
    if not stasher.is_alive():
        write("Stasher failed. Exiting\n")
        jobber.terminate()
        sys.exit(0)

    write("Starting hashing job processes...\n")
    for hasher in hashers:
        hasher.start()
    # progress.start()

    jobs.join()
    results.join()

    '''
    Wait on processing
    '''
    msgs.join()
    time.sleep(1)

    '''
    End processes
    '''
    results.put(None)

    write("Collecting hashing processes...\n")
    while len(hashers) > 0:
        for h in hashers:
            if h.is_alive():
                h.terminate()
                h.join(1)
            else:
                hashers.remove(h)
    write("PDFrankenstein Exiting\n")
