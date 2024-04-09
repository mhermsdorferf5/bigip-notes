when HTTP_REQUEST {
    # Do not enable debug logging in production, it can be very noisy and cause excessive logging that could impact performance.
    set debug 1

    # Enable APM, this handles the case where a TCP connection is re-used
    # if APM was previously disabled, we don't want to blindly allow subsequent http requests through w/o testing them:
    ACCESS::enable

    # IF the request is for the /getSessionID URI, then let's respond with a simple html page that contains the session id.
    # Users will access this page to eaisly get their APM Session ID, that they can use for basic auth.
    if { [HTTP::uri] == "/getSessionID" } {
        if { [HTTP::has_responded] } { return }
        if { [ACCESS::session exists -state_allow [HTTP::cookie value "MRHSession"]] } {
            HTTP::respond 200 content "<html><head><title>APM Session Value Responder</title></html><body><h2>APM SessionID: [HTTP::cookie value "MRHSession"]</h2></body></html>"
            return
        } else {
            HTTP::respond 200 content "<html><head><title>APM Session Value Responder</title></html><body><h2>No Valid APM Session found!</h2></body></html>"
            return
        }
    }


    # If we have an Authoirzation header with basic auth, we need to check the username & password for a valid APM sesion.
    if { [string tolower [HTTP::header value "Authorization"]] contains "basic" } {
        set username  [HTTP::username]
        set sessionid [HTTP::password]
        if { [ACCESS::session exists -state_allow ${sessionid}] } {
            # If the password contains a valid APM session, then let's get the uername for that 
            # session and check it agaisnt the username provided in the basic auth header:
            set sessionUsername [ACCESS::session data get -sid ${sessionid} session.sso.token.last.username]
            if { $debug } { log local0.debug "Valid APM Session found for \'${sessionid}\'" }
            if { ${sessionUsername} == ${username} } {
                # If username matches up with the valid session, then we'll disable APM for this request and 
                # update the basic HTTP auth header to be the username & password associated with that session.
                if { $debug } { log local0.debug "APM Session for \'${sessionid}\' matches username \'${username}\' Disabling APM and replacing Auth header with password from APM session DB" }
                # Disable APM:
                ACCESS::disable
                # Insert SSO Auth Header:
                HTTP::header replace "Authorization" "Basic [b64encode "${sessionUsername}:[ACCESS::session data get -sid ${sessionid} -secure session.sso.token.last.password]"]"
            } else {
                if { $debug } { log local0.debug "APM Session found for \'${sessionid}\' Session Username \'${sessionUsername}\' does not match http basic auth username \'${username}\'" }

            }
        } else {
            if { $debug } { log local0.debug "NO valid APM Session found for \'${sessionid}\' username \'${username}\'" }
        }

    }
}