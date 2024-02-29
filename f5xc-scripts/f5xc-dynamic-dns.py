import requests
import ipaddress
import dns.resolver  # dnspython

# Update the vars below for your env:
dnsZone = '<f5xc-dns-zone>'
dnsRecord = '<fqdn>'
f5xcApiKey = '<f5xc-api-key>'
f5xcTenant = '<f5xc-tenant>'

def getExternalIp():
    sources = [
        'https://checkip.amazonaws.com',
        'https://ipinfo.io/ip',
        'https://api.ipify.org'
    ]
    ips = [requests.get(url, timeout=5).text.strip() for url in sources]
    if ips.count(ips[0]) >= 2:
        return ips[0]
    elif ips.count(ips[1]) >= 2:
        return ips[1]
    else:
        print(f"Failed to get quorum on external IP: AWS: {ips[0]} IPINFO: {ips[1]} IPIFY: {ips[2]}")
        exit(1)

def isValidIp(ip):
    try:
        ipaddress.ip_address(ip)
        return True 
    except ValueError:
        return False

def getCurrentDnsIp():
    try:
        answers = dns.resolver.resolve(dnsRecord, 'A')
        return answers[0].to_text()
    except Exception as e:
        print(f"Error resolving DNS: {e}")
        exit(1)

def updateDnsRecord(dnsZone, dnsRecord, externalIp):
    headers = {
        'Authorization': f'APIToken {f5xcApiKey}',
        'Content-Type': 'application/json'
    }
    zoneResponse = requests.get(f'https://{f5xcTenant}.console.ves.volterra.io/api/config/dns/namespaces/system/dns_zones/{dnsZone}?response_format=0', headers=headers)
    zoneJson = zoneResponse.json()['spec']
    idx = 0
    for record in zoneJson['primary']['default_rr_set_group']:
        if "a_record" in record:
            if record['a_record']['name'] == dnsRecord.split('.')[0]:
                zoneJson['primary']['default_rr_set_group'][idx]['a_record']['values'] = [externalIp]
        idx = idx+1
    updateJsonPayload = {}
    updateJsonPayload['spec'] = zoneJson
    try:
        updateResponse = requests.put(f'https://{f5xcTenant}.console.ves.volterra.io/api/config/dns/namespaces/system/dns_zones/{dnsZone}', headers=headers, json=updateJsonPayload)
        print(f"Update PUT result: {updateResponse.json()}")
        exit
    except Exception as e:
        print(f"Update PUT result: {updateResponse.json()}")
        exit(1)

externalIp = getExternalIp()

if isValidIp(externalIp):
    currentDnsIp = getCurrentDnsIp()
    if externalIp == currentDnsIp:
        print(f"Current IP: {externalIp} matches DNS entry {dnsRecord}: {currentDnsIp}")
        print("No update needed, exiting...")
    else:
        print(f"Current IP: {externalIp} DOES NOT match DNS entry {dnsRecord}: {currentDnsIp}")
        print("Updating DNS...")
        updateDnsRecord(dnsZone, dnsRecord, externalIp)
else:
    print(f"IP Verification Failed: {externalIp} does not appear to be a valid IP.")
