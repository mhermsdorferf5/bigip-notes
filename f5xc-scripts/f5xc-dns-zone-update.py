#!/bin/python3

#import http.client
#import logging
import requests
import ipaddress
import fqdn
import os
import argparse


# Set debug level for http.client (1 for headers)
#http.client.HTTPConnection.debuglevel = 2

# Configure logging for 'requests' and 'urllib3'
#logging.basicConfig()
#logging.getLogger().setLevel(logging.DEBUG)
#requests_log = logging.getLogger("requests.packages.urllib3")
#requests_log.setLevel(logging.DEBUG)
#requests_log.propagate = True

parser = argparse.ArgumentParser(
                    prog='f5xc-dns-zone-update.py',
                    description='Creates or Updates DNS records in a F5 Distributed Cloud DNS Zone',
                    epilog='F5XC_TENANT and F5XC_API_KEY must be provided via OS Environment Variable or optional arguments')
parser.add_argument("zone", type=str, help="F5 Distributed Cloud Zone to update.")
parser.add_argument("record", type=str, help="DNS Record To add.")
parser.add_argument("value", type=str, help="Value of IP Address or FQDN for Record.")
parser.add_argument("--tenant", type=str, help="By default the F5 Tenant is read from the OS Variable: F5XC_TENANT, but this can be overridden with this argument.")
parser.add_argument("--apikey", type=str, help="By default the F5 Tenant is read from the OS Variable: F5XC_API_KEY, but this can be overridden with this argument.")
args = parser.parse_args()

dnsZone = args.zone
dnsRecord = args.record
recordValue = args.value

if args.apikey:
    f5xcApiKey = args.apikey
else:
    if "F5XC_API_KEY" in os.environ:
        f5xcApiKey = os.getenv('F5XC_API_KEY')
    else:
        parser.print_help()
        exit(1)

if args.tenant:
    f5xcTenant =  args.tenant
else:
    if "F5XC_TENANT" in os.environ:
        f5xcTenant =  os.getenv('F5XC_TENANT')
    else:
        parser.print_help()
        exit(1)

##################
def getRecordName(record):
    if "a_record" in record:
        if "" == record['a_record']['name']:
            return "root_a_record"
        else:
            return record['a_record']['name']
    elif "cname_record" in record:
        return record['cname_record']['name']
    elif "lb_record" in record:
        if "" == record['lb_record']['name']:
            return "root_lb_record"
        else:
            return record['lb_record']['name']
    elif "txt_record" in record:
        if "" == record['txt_record']['name']:
            return "root_txt_record"
        else:
            return record['txt_record']['name']
    elif "ns_record" in record:
        if "" == record['ns_record']['name']:
            return "root_ns_record"
        else:
            return record['ns_record']['name']
    elif "ptr_record" in record:
        return record['ptr_record']['name']
    else:
        print(f"Name not found for record: {record}")
        raise

##################
def checkDnsZone(dnsZone):
    recordList = []
    for set in dnsZone['primary']['rr_set_group']:
        for record in set['rr_set']:
            name = getRecordName(record)
            if name in recordList:
                print(f"ERROR: Duplicate Record Found: {name}\n {record}")
                raise
            recordList.append(name)

    for record in dnsZone['primary']['default_rr_set_group']:
        name = getRecordName(record)
        if name in recordList:
            print(f"ERROR: Duplicate Record Found: {name}\n {record}")
            raise
        recordList.append(name)

##################
def getDnsZone(dnsZone):
    headers = {
        'Authorization': f'APIToken {f5xcApiKey}',
        'Content-Type': 'application/json'
    }
    try:
        zoneResponse = requests.get(f'https://{f5xcTenant}.console.ves.volterra.io/api/config/dns/namespaces/system/dns_zones/{dnsZone}?response_format=0', headers=headers)
    except Exception as e:
        print(f"Zone GET Failed: {e}")
        exit(1)

    try:
        zoneJson = zoneResponse.json()['spec']
    except Exception as e:
        print(f"Parsing Zone GET response as JSON Failed: {e}")
        print(f"Likely failed due to missing/incorrect F5XC Tenant/API Key.")
        exit(1)
        
    return zoneJson

##################
def updateDnsZone(dnsZone, updateJsonPayload):
    headers = {
        'Authorization': f'APIToken {f5xcApiKey}',
        'Content-Type': 'application/json'
    }
    try:
        updateResponse = requests.put(f'https://{f5xcTenant}.console.ves.volterra.io/api/config/dns/namespaces/system/dns_zones/{dnsZone}', headers=headers, json=updateJsonPayload)
        if updateResponse.status_code != 200:
            print(f"Update Failed Response: {updateResponse.json()}")
            exit(1)
        exit
    except Exception as e:
        print(f"Update PUT Failed: {e}")
        exit(1)

##################
def createDnsARecord(dnsZone, dnsRecord, ipAddress):

    zoneJson = getDnsZone(dnsZone)
    checkDnsZone(zoneJson)

    idx = 0
    foundRecord = 0
    for record in zoneJson['primary']['default_rr_set_group']:
        if "a_record" in record:
            if record['a_record']['name'] == dnsRecord:
                foundRecord = 1
                zoneJson['primary']['default_rr_set_group'][idx]['a_record']['values'] = [ipAddress]
        idx = idx+1

    updateJsonPayload = {}

    if foundRecord:
        updateJsonPayload['spec'] = zoneJson
    else:
        updateJsonPayload['spec'] = zoneJson
        dnsRecord = {
            'ttl': 300,
            'description': "",
            'a_record': {
                'name': dnsRecord,
                'values': [
                    ipAddress
                ]
            }
        }
        updateJsonPayload['spec']['primary']['default_rr_set_group'].append(dnsRecord)
        
    updateDnsZone(dnsZone, updateJsonPayload)
    
##################
def createDnsCNAMERecord(dnsZone, dnsRecord, cnameTarget):

    zoneJson = getDnsZone(dnsZone)
    checkDnsZone(zoneJson)

    idx = 0
    foundRecord = 0
    for record in zoneJson['primary']['default_rr_set_group']:
        if "cname_record" in record:
            if record['cname_record']['name'] == dnsRecord:
                foundRecord = 1
                zoneJson['primary']['default_rr_set_group'][idx]['cname_record']['value'] = cnameTarget
        idx = idx+1

    updateJsonPayload = {}

    if foundRecord:
        updateJsonPayload['spec'] = zoneJson
    else:
        updateJsonPayload['spec'] = zoneJson
        dnsRecord = {
            'ttl': 300,
            'description': "",
            'cname_record': {
                'name': dnsRecord,
                'value': cnameTarget
            }
        }
        updateJsonPayload['spec']['primary']['default_rr_set_group'].append(dnsRecord)
        
    updateDnsZone(dnsZone, updateJsonPayload)

##################
def isValidIp(ip):
    try:
        ip = ipaddress.IPv4Address(ip)
        return True
    except ValueError:
        return False

##################
def isValidFqdn(domain):
    try:
        test_fqdn = fqdn.FQDN(domain)
        if test_fqdn.is_valid:
            return True
        else:
            return False
    except ValueError:
        return False

##################
###### MAIN ######
if isValidIp(recordValue):
    print("Updating DNS...")
    createDnsARecord(dnsZone, dnsRecord, recordValue)
elif isValidFqdn(recordValue):
    print("Updating DNS...")
    createDnsCNAMERecord(dnsZone, dnsRecord, recordValue)
else:
    print(f"Verification Failed: {recordValue} does not appear to be a valid IP or FQDN.")