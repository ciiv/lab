#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = "Mathieu Cadet <mcadet at novell>"
__version__ = "$Revision: 1.0 $"

# ======================
# CONFIG VARIABLES START
# ======================
# PlateSpin URL is http://myserver/portabilitysuite (V8)
# or  http://myserver/PlatespinMigrate (V9)
PLATESPIN_SERVER_URL = "http://myserver/PlatespinMigrate"
PLATESPIN_SERVER_USER = "administrator"
PLATESPIN_SERVER_PASSWD = "novell"
PLATESPIN_SERVER_NETWORK = "Default"
ESX_SERVER_USER = "root"
ESX_SERVER_PASSWD = "novell"
VMWARE_CLI_VIFS = r"C:\Program Files\VMware\VMware vSphere CLI\bin\vifs.pl"

POLLING_TIMEOUT = 60   # in seconds
DEBUG_MODE = True
# ====================
# CONFIG VARIABLES END
# ====================

import os, sys
import time
import re
import xml
import urllib, urllib2, urlparse
import subprocess
from xml.etree.ElementTree import ElementTree

# HTTP authentication setup for the default urllib opener
password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
password_mgr.add_password (None, PLATESPIN_SERVER_URL, PLATESPIN_SERVER_USER, PLATESPIN_SERVER_PASSWD)
urllib2.install_opener (urllib2.build_opener (urllib2.HTTPBasicAuthHandler (password_mgr)))

PLATESPIN_NETWORK_ID = None
PLATESPIN_XML_NS = "http://schemas.platespin.com/athens/ws/"

def check_platespin_connectivity ():
    global PLATESPIN_NETWORK_ID
    got_connectivity = False
    print  "[*] PlateSpin URL is %s" % PLATESPIN_SERVER_URL
    try:
        # Retrieve server product version
        tree = ElementTree ()
        tree.parse (urllib2.urlopen (PLATESPIN_SERVER_URL))
        product_name = tree.getiterator ('h1')[0].text
        product_version = xml.etree.ElementTree.tostring (tree.getiterator ('span')[0]
                ).replace (' ', '').replace('\n','').rsplit ('>', 1)[1]
        
        # Retrieve Network ID
        tree = ElementTree ()
        tree.parse (urllib2.urlopen (PLATESPIN_SERVER_URL + "/Network.asmx/GetNetworks"))
        for network in tree.getiterator ('{%s}Network' % PLATESPIN_XML_NS):
            if network.find ('{%s}name' % PLATESPIN_XML_NS).text == PLATESPIN_SERVER_NETWORK:
                PLATESPIN_NETWORK_ID = network.find ('{%s}id' % PLATESPIN_XML_NS).text
                got_connectivity = True
                break

    except urllib2.HTTPError as herror:
        print "[E] Unable to open %s: %s (HTTP %s)." % (PLATESPIN_SERVER_URL , herror.msg, herror.code)
        if herror.code == 401:
            print "[E] Is Basic Authentication enabled in IIS?"
    except urllib2.URLError as uerror:
        print "[E] Unable to open %s: %s." % (PLATESPIN_SERVER_URL, uerror.reason)
    
    if not got_connectivity:
        print "[E] Unable to connect to the PlateSpin Server."
        sys.exit (1)
        
    print "[*] Connected to %s v.%s." % (product_name, product_version)
    print "[*] Network ID for %s is %s." % (PLATESPIN_SERVER_NETWORK, PLATESPIN_NETWORK_ID)

def check_vcli_setup ():
    if not os.path.isfile (VMWARE_CLI_VIFS):
        print "[E] %s was not found." % VMWARE_CLI_VIFS
        print "[E] Have you installed VMware vSphere CLI?"
        sys.exit (1)

def check_migrate_state ():
    print "[*] Started continuous monitoring of PlateSpin Server."
    print "[*] Polling interval set to %s seconds." % POLLING_TIMEOUT
    print "[!] Press Ctrl-C at any time to stop the program."
    
    op_id_blacklist = {}
    re_path_matcher = re.compile (r"https://(?P<esx>.+)/folder/(?P<path>[^?]+)\?dsName=(?P<datastore>[^.]+)\.?")
    while True:
        try:
            # Get currently running jobs
            query_string = urllib.urlencode ({'networkId': PLATESPIN_NETWORK_ID,
                                'pageSize': 20,
                                'pageIndex': 1,
                                'operationTypes': ['Migration','Replication'],
                                'operationStatus': 'Running'}, doseq=True)
            tree = ElementTree ()
            tree.parse (urllib2.urlopen ("%s%s?%s" % (PLATESPIN_SERVER_URL,
                                                      "/Operation.asmx/GetOperationsPage",
                                                      query_string)))
            operations_list = tree.getiterator ("{%s}OperationIds" % PLATESPIN_XML_NS)
            running_operations_id_list = []
            for operation in operations_list:
                running_operations_id_list.append (operation.text)
            if DEBUG_MODE:
                print "[D] Running OPIDs: %s" % ', '.join (running_operations_id_list)
                
            # Now deal with all running operations
            query_string = urllib.urlencode ({'id': r'%s',
                                              'locale': 'en-us'})
            for operation_id in running_operations_id_list:
                tree = ElementTree ()
                tree.parse (urllib2.urlopen ("%s%s?%s" % (PLATESPIN_SERVER_URL,
                                                      "/Operation.asmx/GetOperation",
                                                      query_string % operation_id)))

                # Check if operation is in RequiresUserIntervention state
                if not tree.find ("{%s}status" % PLATESPIN_XML_NS).text == "RequiresUserIntervention":
                    continue
                    
                if DEBUG_MODE:     
                    print "[D] Processing job: %s" % operation_id
                
                for step in tree.find("{%s}operations" % PLATESPIN_XML_NS).getiterator ("{%s}operation" % PLATESPIN_XML_NS):
                    # Check if step is in RequiresUserIntervention state                      
                    if not step.find  ("{%s}status" % PLATESPIN_XML_NS).text == "RequiresUserIntervention":
                        continue
                    
                    # Check if step is in HttpsFailedToPutFile state
                    if not step.getiterator ("{%s}reportElement" % PLATESPIN_XML_NS)[0].attrib.get ("reportCode") == "HttpsFailedToPutFile":
                        continue
                    
                    step_number =  step.find  ("{%s}stepNumber" % PLATESPIN_XML_NS).text
                    
                    # Check if already in the black list
                    if (op_id_blacklist.get (operation_id, False) and 
                      step_number in op_id_blacklist[operation_id]):
                        if DEBUG_MODE:
                            print "[D] Already in the blacklist: %s." % operation_id
                        continue
                    
                    # Find path to create
                    error_msg_value = None
                    for value in step.getiterator ("{%s}value" % PLATESPIN_XML_NS):
                        if value.text.startswith ("Failed to put file from"):
                            error_msg_value = value.text
                            break
                    
                    if not error_msg_value:
                        if DEBUG_MODE:
                            print "[D] Failed to find an error message for job: %s." % operation_id
                        continue
                        
                    result = re_path_matcher.search (error_msg_value)
                    
                    target_datastore = urllib.url2pathname (result.group ('datastore'))
                    path_to_create = urllib.url2pathname (result.group ('path')).rsplit ('/', 1)[0]
                    path_to_create = "[%s]/%s" % (target_datastore, path_to_create)
                    target_esx = result.group ('esx')
                        
                    # Create path                    
                    env_vars = os.environ.copy ()
                    env_vars ["VI_USERNAME"] = ESX_SERVER_USER
                    env_vars ["VI_PASSWORD"] = ESX_SERVER_PASSWD
                    env_vars ["VI_SERVER"] = target_esx
                    vifs_cmd = subprocess.Popen (['perl', VMWARE_CLI_VIFS, '-M', path_to_create],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        env=env_vars, universal_newlines=True)
                    (stdout, stderr) = vifs_cmd.communicate ()
                    
                    # Test result
                    if vifs_cmd.returncode != 0:
                        for line in stderr.rstrip ().split ("\n"):
                            print "[W] %s" % line
                        print "[W] Failed to create path %s." % path_to_create
                        break
                    
                    for line in stdout.rstrip ().split ("\n"):
                        print "[*] %s" % line
                    print "[*] Path created on ESX Server %s." % target_esx
                        
                    # Add to black list
                    entry = op_id_blacklist.get (operation_id, [])
                    entry.append (step_number)
                    op_id_blacklist [operation_id] = entry
                    print "[*] Blacklisted OPID %s at step %s." % (operation_id, step_number)
                    
                    # All done!
                    break
            
            time.sleep (POLLING_TIMEOUT)
        except urllib2.HTTPError as herror:
            print "[E] Unable to open %s: %s (HTTP %s)." % (PLATESPIN_SERVER_URL, herror.msg, herror.code)
            break
        except KeyboardInterrupt:
            print "[*] Stopped."
            break

def main ():
    print
    check_vcli_setup ()
    check_platespin_connectivity ()
    check_migrate_state ()
    if sys.platform == "win32":
        os.system ("pause")

if __name__ == "__main__":
    main ()