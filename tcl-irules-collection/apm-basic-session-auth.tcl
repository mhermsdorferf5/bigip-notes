when HTTP_REQUEST {
    # Do not enable debug logging in production, it can be very noisy and cause excessive logging that could impact performance.
    set debug 1

    # Insert MRHSession cookie in responses for some CLI clients that may support state tracking.
    # on every HTTP request, init this this as 0.
    set insertResponseCookie 0

    # IF the request is for the /getSessionID URI, then let's respond with a simple html page that contains the session id.
    # Users will access this page to easily get their APM Session ID, that they can use for basic auth.
    if { [HTTP::uri] == "/getSessionID" } {
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
            # If it doesn't contain mozilla, assume it's a cli client, and we need to prompt for 401 auth.
            # We can add other User-Agent headers here if we need different behavior, but standard 401/basic auth mechanics should work for any CLI client.
            if { $debug } { log local0.debug "Request from non-browser client: [HTTP::host][HTTP::uri] | User-Agent: [HTTP::header value User-Agent] | Authorization: [HTTP::header value Authorization] | Git-Protocol: [HTTP::header value Git-Protocol] | Headers: [HTTP::header names]" }
            if { !([HTTP::header names] contains "Authorization") } {
                if { $debug }  { log local0.debug "Sending 401"}
                HTTP::respond 401 WWW-Authenticate "Basic realm=\"[HTTP::host]\""
                return
            }
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
            if { $debug } { log local0.debug "Valid APM Session found for \'${sessionid}\'" }
            if { ${sessionUsername} == ${username} } {
                # If username matches up with the valid session, then we'll disable APM for this request and 
                # update the basic HTTP auth header to be the username & password associated with that session.
                if { $debug } { log local0.debug "APM Session for \'${sessionid}\' matches username \'${username}\' and replacing Auth header with password from APM session DB" }

                # Insert ClientLess header:
                HTTP::header insert "Clientless-Mode" "1"
                # Insert APM Cookie:
                HTTP::cookie insert name "MRHSession" value ${sessionid} path "/"
                set insertResponseCookie 1
                # Insert SSO Auth Header:
                HTTP::header replace "Authorization" "Basic [b64encode "${sessionUsername}:[ACCESS::session data get -sid ${sessionid} -secure session.sso.token.last.password]"]"
            } else {
                if { $debug } { log local0.debug "APM Session found for \'${sessionid}\', however APM Session username: \'${sessionUsername}\' does not match http basic auth username: \'${username}\'" }
                HTTP::respond 403 content "<html><head><title>No Valid APM Session Found!</title></html><body><h2>No valid APM session found for user: ${username} with session id: ${sessionid}</h2></body></html>\n"
                return
            }
        } else {
            # Don't log the SessionID provided unless it's a valid SessionID, this is because users tend to inadvertently put their password here.
            if { $debug } { log local0.debug "NO valid APM Session found for username \'${username}\', with provided SessionID." }
            HTTP::respond 403 content "<html><head><title>No Valid APM Session Found!</title></html><body><h2>No valid APM session found for user: ${username} with session id: ${sessionid}</h2></body></html>\n"
            return
        }

    }
}

when HTTP_RESPONSE {
    if { $insertResponseCookie } {
        if { $debug } { log local0.debug "Inserting set-cookie for session: \'${sessionid}\'" }
        HTTP::cookie insert name "MRHSession" value ${sessionid} path "/"
    }
}