import requests
import ipaddress
import os
import argparse

parser = argparse.ArgumentParser(
                    prog='f5xc-dns-zone-update.py',
                    description='Creates or Updates DNS records in a F5 Distributed Cloud DNS Zone',
                    epilog='F5XC_TENANT and F5XC_API_KEY must be provided via OS Environment Variable or optional arguments')
parser.add_argument("zone", type=str, help="F5 Distributed Cloud Zone to update.")
parser.add_argument("record", type=str, help="DNS Record To add.")
parser.add_argument("address", type=str, help="IP Address for Record.")
parser.add_argument("--tenant", type=str, help="By default the F5 Tenant is read from the OS Variable: F5XC_TENANT, but this can be overridden with this argument.")
parser.add_argument("--apikey", type=str, help="By default the F5 Tenant is read from the OS Variable: F5XC_API_KEY, but this can be overridden with this argument.")
args = parser.parse_args()

dnsZone = args.zone
dnsRecord = args.record
ipAddress = args.address

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
def isValidIp(ip):
    try:
        ipaddress.ip_address(ip)
        return True 
    except ValueError:
        return False

##################
def createDnsRecord(dnsZone, dnsRecord, ipAddress):
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
if isValidIp(ipAddress):
    print("Updating DNS...")
    createDnsRecord(dnsZone, dnsRecord, ipAddress)
else:
    print(f"IP Verification Failed: {ipAddress} does not appear to be a valid IP.")
