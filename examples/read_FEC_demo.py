"""
Parse some .fec forms.

"""

from parsing.form_parser import form_parser, ParserMissingError
from parsing.filing import filing

# load up a form parser
fp = form_parser()

filingnumbers=[1021457,]

for filingnum in filingnumbers:
    
    # This will fail if the filings haven't already been downloaded 
    # to the location specified in parsing.read_FEC_settings.py
    f1 = filing(filingnum)
    
    formtype = f1.get_form_type()
    version = f1.version

    print "Got form number %s - type=%s version=%s is_amended: %s" % (f1.filing_number, formtype, version, f1.is_amendment)
    print "headers are: %s" % f1.headers
    
    if f1.is_amendment:
        print "Original filing is: %s" % (f1.headers['filing_amended'])
    
    
    if not fp.is_allowed_form(formtype):
        print "skipping form %s - %s isn't parseable" % (f1.filing_number, formtype)
        continue
        
    print "Version is: %s" % (version)
    firstrow = fp.parse_form_line(f1.get_first_row(), version)    
    print "First row is: %s" % (firstrow)
    
    # if we only need info from the first row a.k.a. the form line, we're done.
    # otherwise, continue to keep reading the actual rows. 
    
    
    linenum = 0
    while True:
        linenum += 1
        row = f1.get_body_row()
        if not row:
            break
        
        try:
            linedict = fp.parse_form_line(row, version)
            print linedict
        except ParserMissingError:
            msg = 'process_filing_body: Unknown line type in filing %s line %s: type=%s Skipping.' % (filingnum, linenum, row[0])
            continue