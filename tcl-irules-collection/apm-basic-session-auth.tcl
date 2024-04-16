when HTTP_REQUEST {
    ### START CONFIGURATION OPTIONS ###
    
    ## Debug logging:
    ##   1 = Enable debug logging (DO NOT USE IN PRODUCTION)
    #        Do not enable debug logging in production, it can be very noisy and cause excessive logging that could impact performance.
    ##   0 = Disable debug logging.
    set debug 1

    # If github token auth should be enabled, then set this to 1, if it should be disabled set it to 0.
    # This considers requests to github with a Bearer token as requests containing a github personal access token.
    # Not this doesn't use duo 2fa nor LDAP auth, it instead relies on the fact that the authenticated indvidual created a github personal access token.
    set githubTokenAuthEnabled 1
    # If github token auth is enabled, then we only want to check for the github domain name
    # update this variable with the dns hostname for the github VIP that users will access.
    set githubDomainName "github"

    ### END CONFIGURATION OPTIONS ###

    # Do not edit below this line #

    # Variable Init:
    set insertResponseCookie 0
    set cliClient 0
    if { $debug } {
        set logPrefix "Client IP: [IP::client_addr] | URI: [HTTP::host][HTTP::uri] | User-Agent: [HTTP::header value User-Agent] |"
    }


    # IF the request is for the /getSessionID URI, then let's respond with a simple html page that contains the session id.
    # Users will access this page to easily get their APM Session ID, that they can use for basic auth.
    if { [string tolower [HTTP::uri]] == "/getsessionid" } {
        if { [HTTP::has_responded] } { return }
        if { [ACCESS::session exists -state_allow [HTTP::cookie value "MRHSession"]] } {
            HTTP::respond 200 content "<html><head><title>APM Session Value Responder</title></html><body><h2>APM SessionID:</h2><h2 id=\"mySessionID\">[HTTP::cookie value "MRHSession"]</h2><button class=\"btn\" onclick=\"copyContent()\">Copy!</button><p><a href=\"https://[HTTP::host]\/\">Return to main site.</a></p><script>let text = document.getElementById('mySessionID').innerHTML; const copyContent = async () => { try { await navigator.clipboard.writeText(text); console.log('Content copied to clipboard') } catch (err) { console.error('Failed to copy: ', err); } } </script></body></html>\n"
            return
        } else {
            HTTP::respond 200 content "<html><head><title>APM Session Value Responder</title></html><body><h2>No Valid APM Session found! <a href=\"https://[HTTP::host]\/\">return to login page.</a></h2></body></html>\n"
            return
        }
    }


    # For non-browser clients, if there isn't a Authorization header, send a 401 to trigger basic auth.
    # For browser clients, bail out of iRule processing and let APM do it's auth/session handling.
    switch -glob -- [string tolower [HTTP::header value User-Agent]] {
        "mozilla*" {
            # Virtually all modern browsers identify themselves as mozilla in some way or form.
            # Bypass this iRule for any full browser, we only want to continue if it's a CLI Client.
            return
        }
        default {
            # If it doesn't contain mozilla, assume it's a cli client, and we may need to prompt for 401 auth.
            # We can add other User-Agent headers here if we need different behavior, but standard 401/basic auth mechanics should work for any CLI client.
            set cliClient 1
        }
    }

    # For CLI Clients we'll handle their logic here:
    if { $cliClient } {
        # if there is no Authorization header or no MRHSession cookie, we need to send a 401.
        if { $debug } { log local0.debug "$logPrefix | Request from non-browser client | Authorization: [HTTP::header value Authorization] | Git-Protocol: [HTTP::header value Git-Protocol] | Headers: [HTTP::header names] | Cookies: [HTTP::header value Cookie]" }
        if { !([HTTP::header names] contains "Authorization" || [HTTP::cookie names] contains "MRHSession") } {
            if { $debug }  { log local0.debug "$logPrefix Sending 401"}
            HTTP::respond 401 WWW-Authenticate "Basic realm=\"[HTTP::host]\""
            return
        }

        # If there is an MRHSession Cookie, then let's check that it's valid, enable clientless mode, if it's invalid send a 403.
        if { [HTTP::cookie names] contains "MRHSession" } {
            set sessionid [HTTP::cookie value "MRHSession"]
            if { [ACCESS::session exists -state_allow ${sessionid}] } {
                if { $debug } { log local0.debug "$logPrefix Request with valid MRH Session Cookie $sessionid" }
                # Insert ClientLess header:
                HTTP::header insert "Clientless-Mode" "1"
                return
            } else {
                if { $debug } { log local0.debug "$logPrefix Request with invalid MRH Session Cookie $sessionid" }
                HTTP::respond 403 content "<html><head><title>No Valid APM Session Found!</title></html><body><h2>No valid APM session found for session id: ${sessionid}</h2></body></html>\n"
            }
        }

        # Check if the request is for github, and github token auth is enabled:
        if { ([string tolower [HTTP::host]] contains $githubDomainName) && $githubTokenAuthEnabled } {
        
            # If we have an Authorization header with bearer auth, and it's a github request, then bypass apm and assume github access token.
            # Not this doesn't use duo 2fa, it relies on the fact that the authenticated indvidual created a github access token.
            if { ([string tolower [HTTP::header value "Authorization"]] contains "bearer") 
                && ([string tolower [HTTP::host]] contains ${githubDomainName})
                && $githubTokenAuthEnabled } {
                # Insert ClientLess header:
                HTTP::header insert "Clientless-Mode" "1"
                if { $debug } { log local0.debug "$logPrefix Request for github with bearer token, bypassing APM. | Authorization: [HTTP::header value Authorization]" }
                return
            }
            
            # If the password starts with ghp_ or github_pat_ then this is a Github Personal Access token.
            # Not this doesn't use duo 2fa, it relies on the fact that the authenticated indvidual created a github access token.
            if { ([HTTP::password] starts_with "ghp_") || ([HTTP::password] starts_with "github_pat_") } {
                # Insert ClientLess header:
                HTTP::header insert "Clientless-Mode" "1"
                if { $debug } { log local0.debug "$logPrefix Request for github with Personal Access token, bypassing APM. | Authorization: [HTTP::header value Authorization]" }
                return
            }
        }
    
        # If we have an Authorization header with basic auth, we need to check the username & password for a valid APM session.
        if { [string tolower [HTTP::header value "Authorization"]] contains "basic" } {
            set username  [HTTP::username]
            set sessionid [HTTP::password]
            if { [ACCESS::session exists -state_allow ${sessionid}] } {
                # If the password contains a valid APM session, then let's get the username for that 
                # session and check it against the username provided in the basic auth header:
                set sessionUsername [ACCESS::session data get -sid ${sessionid} session.sso.token.last.username]
                if { $debug } { log local0.debug "$logPrefix Valid APM Session found for \'${sessionid}\'" }
                if { ${sessionUsername} == ${username} } {
                    # If username matches up with the valid session, then we'll disable APM for this request and 
                    # update the basic HTTP auth header to be the username & password associated with that session.
                    if { $debug } { log local0.debug "$logPrefix APM Session for \'${sessionid}\' matches username \'${username}\' and replacing Auth header with password from APM session DB" }
    
                    # Insert ClientLess header:
                    HTTP::header insert "Clientless-Mode" "1"
                    # Insert APM Cookie:
                    HTTP::cookie insert name "MRHSession" value ${sessionid} path "/"
                    set insertResponseCookie 1
                    # Insert SSO Auth Header:
                    HTTP::header replace "Authorization" "Basic [b64encode "${sessionUsername}:[ACCESS::session data get -sid ${sessionid} -secure session.sso.token.last.password]"]"
                    return
                } else {
                    if { $debug } { log local0.debug "$logPrefix APM Session found for \'${sessionid}\', however APM Session username: \'${sessionUsername}\' does not match http basic auth username: \'${username}\'" }
                    HTTP::respond 403 content "<html><head><title>No Valid APM Session Found!</title></html><body><h2>No valid APM session found for user: ${username} with session id: ${sessionid}</h2></body></html>\n"
                    return
                }
            } else {
                # Don't log the SessionID provided unless it's a valid SessionID, this is because users tend to inadvertently put their password here.
                if { $debug } { log local0.debug "$logPrefix NO valid APM Session found for username \'${username}\', with provided SessionID." }
                HTTP::respond 403 content "<html><head><title>No Valid APM Session Found!</title></html><body><h2>No valid APM session found for user: ${username} with session id: ${sessionid}</h2></body></html>\n"
                    return
            }
        }
    }
}

when HTTP_RESPONSE_RELEASE {
    if { $debug } {
        log local0.debug "$logPrefix Response Status: [HTTP::status] | Server: [HTTP::header value Server] | Response Headers: [HTTP::header names] | Content Length: [HTTP::header value Content-Length]" 
    }
}

when HTTP_RESPONSE {
    if { $insertResponseCookie } {
        if { $debug } { log local0.debug "$logPrefix Inserting set-cookie for session: \'${sessionid}\'" }
        HTTP::cookie insert name "MRHSession" value ${sessionid} path "/"
    }
}