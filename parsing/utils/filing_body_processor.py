# django independent entry process; no db abstraction; this is built for postgresql

import sys, time

sys.path.append('../../')

from parsing.filing import filing
from parsing.form_parser import form_parser, ParserMissingError
from form_mappers import *

from write_csv_to_db import CSV_dumper

from parsing.utils.fec_import_logging import fec_logger

from db_utils import get_connection
verbose = True

class FilingHeaderDoesNotExist(Exception):
    pass
    
class FilingHeaderAlreadyProcessed(Exception):
    pass


def process_body_row(linedict, filingnum, line_sequence, is_amended, cd, filer_id):
    form = linedict['form_parser']
    
    # this will be the arg passed to csv dumper: ('skedletter', datadict)
    result = None
    
    ## Mark memo-ized rows as being superceded by an amendment.
    try:
        if linedict['memo_code']=='X':
            linedict['superceded_by_amendment'] = True
    except KeyError:
        pass
    
    #print "processing form type: %s" % (form)
    if form=='SchA':
        result = ['A', skeda_from_skedadict(linedict, filingnum, line_sequence, is_amended)]

    elif form=='SchB':
        result = ['B', skedb_from_skedbdict(linedict, filingnum, line_sequence, is_amended)]

    elif form=='SchE':
        result = ['E', skede_from_skededict(linedict, filingnum, line_sequence, is_amended)]

    # Treat 48-hour contribution notices like sked A.
    # Requires special handling for amendment, since these are superceded
    # by regular F3 forms. 
    elif form=='F65':
        result = ['A', skeda_from_f65(linedict, filingnum, line_sequence, is_amended)]

    # disclosed donor to non-commmittee. Sorta rare, but.. 
    elif form=='F56':
        result = ['A', skeda_from_f56(linedict, filingnum, line_sequence, is_amended)]

    # disclosed electioneering donor
    elif form=='F92':
        result = ['A', skeda_from_f92(linedict, filingnum, line_sequence, is_amended)]   

    # inaugural donors
    elif form=='F132':
        result = ['A', skeda_from_f132(linedict, filingnum, line_sequence, is_amended)]

    #inaugural refunds
    elif form=='F133':
        result = ['A', skeda_from_f133(linedict, filingnum, line_sequence, is_amended)]

    # IE's disclosed by non-committees. Note that they use this for * both * quarterly and 24- hour notices. There's not much consistency with this--be careful with superceding stuff. 
    elif form=='F57':
        result = ['E', skede_from_f57(linedict, filingnum, line_sequence, is_amended)]

    # Its another kind of line. Just dump it in Other lines.
    else:
        result = ['O', otherline_from_line(linedict, filingnum, line_sequence, is_amended, filer_id)]
    
    # write it to the db using csv to db (which will only actually write every 1,000 rows)
    
    print "Result of process_body_row is: %s" % (result)
    cd.writerow(result[0], result[1])

def process_filing_body(filingnum, fp=None, logger=None):
    
    
    #It's useful to pass the form parser in when running in bulk so we don't have to keep creating new ones. 
    if not fp:
      fp = form_parser()
      
    if not logger:
        logger=fec_logger()
    msg = "process_filing_body: Starting # %s" % (filingnum)
    #print msg
    logger.info(msg)
      
    connection = get_connection()
    cursor = connection.cursor()
    cmd = "select fec_id, is_superceded, data_is_processed from fec_alerts_new_filing where filing_number=%s" % (filingnum)
    cursor.execute(cmd)
    
    cd = CSV_dumper(connection)
    
    result = cursor.fetchone()
    if not result:
        msg = 'process_filing_body: Couldn\'t find a new_filing for filing %s' % (filingnum)
        logger.error(msg)
        raise FilingHeaderDoesNotExist(msg)
        
    # will throw a TypeError if it's missing.
    line_sequence = 1
    is_amended = result[1]
    is_already_processed = result[2]
    if is_already_processed:
        msg = 'process_filing_body: This filing has already been entered.'
        logger.error(msg)
        raise FilingHeaderAlreadyProcessed(msg)
    
    #print "Processing filing %s" % (filingnum)
    f1 = filing(filingnum)
    form = f1.get_form_type()
    version = f1.get_version()
    filer_id = f1.get_filer_id()
    
    # only parse forms that we're set up to read
    
    if not fp.is_allowed_form(form):
        if verbose:
            msg = "process_filing_body: Not a parseable form: %s - %s" % (form, filingnum)
            # print msg
            logger.error(msg)
        return None
        
    linenum = 0
    while True:
        linenum += 1
        row = f1.get_body_row()
        if not row:
            break
        
        #print "row is %s" % (row)
        #print "\n\n\nForm is %s" % form
        try:
            linedict = fp.parse_form_line(row, version)
            #print "\n\n\nform is %s" % form
            process_body_row(linedict, filingnum, line_sequence, is_amended, cd, filer_id)
        except ParserMissingError:
            msg = 'process_filing_body: Unknown line type in filing %s line %s: type=%s Skipping.' % (filingnum, linenum, row[0])
            logger.warn(msg)
            continue
        
    # commit all the leftovers
    cd.commit_all()
    cd.close()
    counter = cd.get_counter()
    total_rows = 0
    for i in counter:
        total_rows += counter[i]
        
    msg = "process_filing_body: Filing # %s Total rows: %s Tally is: %s" % (filingnum, total_rows, counter)
    # print msg
    logger.info(msg)
    
    
    """
    # this data has been moved here. At some point we should pick a single location for this data. 
    header_data = dict_to_hstore(counter)
    cmd = "update fec_alerts_new_filing set lines_present='%s'::hstore where filing_number=%s" % (header_data, filingnum)
    cursor.execute(cmd)
    
    # mark file as having been entered. 
    cmd = "update fec_alerts_new_filing set data_is_processed = True where filing_number=%s" % (filingnum)
    cursor.execute(cmd)
    
    # flag this filer as one who has changed. 
    cmd = "update summary_data_committee_overlay set is_dirty=True where fec_id='%s'" % (filer_id)
    cursor.execute(cmd)
    """




"""
t0 = time.time()
process_filing_body(864353)
# 869853, 869866
#for fn in [869888]:
#    process_filing_body(fn, fp)
t1 = time.time()
print "total time = " + str(t1-t0)
# long one: 767168
#FAILS WITH STATE ADDRESS PROBLEM:  biggest one on file: 838168 (510 mb) - act blue - 2012-10-18         | 2012-11-26
# second biggest: 824988 (217.3mb) - act blue - 2012-10-01         | 2012-10-17 - 874K lines
# 840327 - 169MB  C00431445 - OFA   | 2012-10-18         | 2012-11-26
# 821325 - 144 mb Obama for america 2012-09-01         | 2012-09-30
# 798883 - 141 mb
# 804867 - 127 mb
# 827978 - 119 mb
# 754317 - 118 mb

"""


