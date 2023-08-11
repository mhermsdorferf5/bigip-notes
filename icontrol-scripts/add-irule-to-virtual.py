#!/usr/bin/python
################################################################################
### add-irule-to-virtual.py
#
# Description:
# Python script designed to add iRule(s) to virtual server(s).
# 
# Example Usage:
#[mhermsdorfer@bigip-0:Active:Disconnected] ~ # python /var/tmp/add-irule-virtual.py --host <host> --username admin --password '<password>' --irule /Common/block-url --virtuals "/Common/test_https_vip /Tenant1/Application1/serviceMain"
#### FOUND iRule /Common/block-url with the following iRule: ###
#when HTTP_REQUEST {
#
#if { [HTTP::uri] contains "/url/to/block" } {
#    reject
#}
#
#}
#### END iRule /Common/block-url ###
#Existing iRules on virtual /Common/test_https_vip: [u'/Common/delay-refresh']
#Updated iRules on virtual /Common/test_https_vip: [u'/Common/delay-refresh', u'/Common/block-url']
#Existing iRules on virtual /Tenant1/Application1/serviceMain: none
#Updated iRules on virtual /Tenant1/Application1/serviceMain: [u'/Common/block-url']
#Configuration Saved
#
#
# Requirements:
#     python2.7 or python3 with requests & json libs.
#
# Note: Can be run on the BIG-IP directly, as of v15.1.x
#
# Generated Configuration Requires: BIG-IP LTM version 12.1 or later.
#
# Author: Mark Hermsdorfer <m.hermsdorfer@f5.com>
# Version: 1.0
# Version History:
# v1.0: Initial Version.
#
# (c) Copyright 2010-2023 F5 Networks, Inc.
#
# This software is confidential and may contain trade secrets that are the
# property of F5 Networks, Inc. No part of the software may be disclosed
# to other parties without the express written consent of F5 Networks, Inc.
# It is against the law to copy the software. No part of the software may
# be reproduced, transmitted, or distributed in any form or by any means,
# electronic or mechanical, including photocopying, recording, or information
# storage and retrieval systems, for any purpose without the express written
# permission of F5 Networks, Inc. Our services are only available for legal
# users of the program, for instance in the event that we extend our services
# by offering the updating of files via the Internet.
#
# DISCLAIMER:
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY EXPRESSED OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY
# AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL F5
# NETWORKS OR ANY CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION), HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# IMPORTANT NOTE: Any use of this software implies acceptance of the terms as
# detailed above. If you do not agree to the terms as detailed above DO NOT
# USE THE SOFTWARE!
#
################################################################################





# Sub to get F5 auth-token:
def getToken(bigip, url_base, creds):
    payload = {}
    payload['username'] = creds[0]
    payload['password'] = creds[1]
    payload['loginProviderName'] = 'tmos'

    url_auth = '%s/shared/authn/login' % url_base

    response = bigip.post(url_auth, json.dumps(payload))
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        print(error)
        print(error.response.text)
    token = response.json()['token']['token']
    return token
# End getToken sub

# Sub to saveConfig
def saveConfig(bigip, url_base):

    uri = '{}/tm/sys/config'.format(url_base)

    # Build JSON payload for install POST:
    payload = {
        "command": "save",
    }

    response = bigip.post(uri, data=json.dumps(payload))
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        print(error)
        print(error.response.text)
# end sub saveConfig

# Sub to getRule:
def getRule(bigip, url_base, iRuleName):

    sanitizedRuleName = iRuleName.replace('/', '~')

    uri = '{}/tm/ltm/rule/{}'.format(url_base,sanitizedRuleName)

    response = bigip.get(uri)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        print(error)
        print(error.response.text)

    return(response.json()['apiAnonymous'])
# end sub getRule

# Sub to getVirtualRules(bigip, url_base, virtual)
def getVirtualRules(bigip, url_base, virtual):

    sanitizedVirtualName = virtual.replace('/', '~')

    uri = '{}/tm/ltm/virtual/{}'.format(url_base,sanitizedVirtualName)

    response = bigip.get(uri)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        print(error)
        print(error.response.text)

    if "rules" in response.json():
        return(response.json()['rules'])
    else:
        return("none")
# end sub getVirtualRules

# Sub to updateVirtualRules
def updateVirtualRules(bigip, url_base, virtual, rulesList):

    sanitizedVirtualName = virtual.replace('/', '~')

    uri = '{}/tm/ltm/virtual/{}'.format(url_base,sanitizedVirtualName)
    # Build JSON payload for install PATCH:
    payload = {
        "rules": rulesList
    }
    response = bigip.patch(uri, data=json.dumps(payload))
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        print(error)
        print(error.response.text)

    if "rules" in response.json():
        return(response.json()['rules'])
    else:
        return("none")
# end sub updateVirtualRules

# Sub to updateDataGroup:
def updateExtDataGroupFile(bigip, url_base, dataGroupFileName, dataGroupFileURI):

    uri = '{}/tm/sys/file/data-group/{}'.format(url_base,dataGroupFileName)

    # Build JSON payload for install PATCH:
    payload = {
        "name": dataGroupFileName,
        "sourcePath": dataGroupFileURI
    }

    response = bigip.patch(uri, data=json.dumps(payload))
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        print(error)
        print(error.response.text)
# end sub updateDataGroup


if __name__ == "__main__":
    import requests, argparse, getpass, json, logging, urllib3, time

    parser = argparse.ArgumentParser(description='Trigger External Data-Group update on BIG-IP')

    parser.add_argument("--host", help='BIG-IP IP or Hostname', required=True )
    parser.add_argument("--username", help='BIG-IP Username', required=True )
    parser.add_argument("--password", help='BIG-IP Password', required=False )
    parser.add_argument("--debug", action='store_true', help='Enable debuging on this script.')

    parser.add_argument("--irule", help='Name of the iRule to add to each virtual', required=True)
    parser.add_argument("--virtuals", help='list of virtuals to add iRule to.', required=True)
    args = vars(parser.parse_args())

    hostname = args['host']
    username = args['username']
    iRuleName = args['irule']
    listOfVirtuals = args['virtuals'].split()

    if args['debug']:
        # These two lines enable debugging at httplib level (requests->urllib3->http.client)
        # You will see the REQUEST, including HEADERS and DATA, and RESPONSE with HEADERS but without DATA.
        # The only thing missing will be the response.body which is not logged.
        try:
            import http.client as http_client
        except ImportError:
            # Python 2
            import httplib as http_client
        http_client.HTTPConnection.debuglevel = 1

        # You must initialize logging, otherwise you'll not see debug output.
        logging.basicConfig()
        logging.getLogger().setLevel(logging.DEBUG)
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True

    if args['password'] is None:
        print("%s, enter your password: " % args['username'])
        password = getpass.getpass()
    else:
        password = args['password']

    url_base = 'https://%s/mgmt' % hostname

    # Disable/supress warnings about unverified SSL:
    requests.packages.urllib3.disable_warnings()
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


    # Create a new requests session for our big-ip:
    bigip = requests.session()
    bigip.headers.update({'Content-Type':'application/json'})
    bigip.auth = (username, password)
    bigip.verify = False

    token = getToken(bigip, url_base, (username, password))

    bigip.auth = None
    bigip.headers.update({'X-F5-Auth-Token': token})

    iRuleContent = getRule(bigip, url_base, iRuleName)
    print("### FOUND iRule %s with the following iRule: ###" % iRuleName)
    print(iRuleContent)
    print("### END iRule %s ###" % iRuleName)

    for virtual in listOfVirtuals:
        existingRules = getVirtualRules(bigip, url_base, virtual)
        print("Existing iRules on virtual %s: %s" % (virtual, existingRules))
        if existingRules == "none":
            updatedRules = [iRuleName]
        else:
            updatedRules = existingRules
            updatedRules.append(iRuleName)
        updatedRulesFromBigIP = updateVirtualRules(bigip, url_base, virtual, updatedRules)
        print("Updated iRules on virtual %s: %s" % (virtual, updatedRulesFromBigIP))


    saveConfig(bigip, url_base)
    print("Configuration Saved")
