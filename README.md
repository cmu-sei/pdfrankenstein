PDFrankenstein
================
Python tool for bulk malicious PDF feature extraction.

Dependencies
------------
* PyV8 (and V8) (optional: if you intend to use JS deobfuscation. Note: JS deobfuscation needs to be run in a safe environment, as you would treat any malware.
* lxml
* [scandir](https://github.com/benhoyt/scandir) (optional: module included in lib folder)
* postgresql and psycopg2 (optional: if you intend to use postgresql backing storage)


Usage
-----

```
$ pdfrankenstein.py --help
```

Output to a file in delimited plain text, parses ALL files in pdf-dir/
```
$ pdfrankenstein.py -o file -n fileoutput.txt ~/pdf-dir
```

Output to an sqlite database 
```
$ pdfrankenstein.py -o sqlite3 -n pdf-db ~/pdf-dir
```

Output to stdout after parsing all files listed inside file-with-pdfs
```
$ pdfrankensetin.py -o stdout ~/file-with-pdfs
```


<table>
<tr>
  <td>pdf_in </td>
  <td>PDF input for analysis. Can be a single PDF file or a directory of files.</td>
</tr>
<tr>
  <td>-d, --debug</td>
  <td>Print debugging messages.</td>
</tr>
<tr>
  <td>-o, --out</td>
  <td>Analysis output filename or type. Default to 'unnamed-out.*' file in CWD. Options: 'sqlite3'||'postgres'||'stdout'||[filename]</td>
</tr>
<tr>
  <td>-n, --name</td><td>Name for output database.</td>
</tr>
<tr>
  <td>--hasher</td><td>Specify which type of hasher to use. PeePDF | PDFMiner (default). PDFMiner option provides better parsing capabilities.</td>
</tr>
<tr>
  <td>-v, --verbose</td><td>Spam the terminal, TODO.</td>
</tr>
</table>

References
-------------
### Open Source PDF Tools
* [PeePDF](http://eternal-todo.com/tools/peepdf-pdf-analysis-tool)
* [PDFMiner](http://www.unixuser.org/~euske/python/pdfminer/index.html)
* [swf mastah](https://github.com/9b/pdfxray_public/blob/master/builder/swf_mastah.py)
