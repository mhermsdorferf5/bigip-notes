when CLIENT_ACCEPTED {
    # This iRule will validate that the client has a valid x509 client certificate and then insert that client certificate into the HTTP request header to be passed to the backend servers.
    # See: https://my.f5.com/manage/s/article/K95338243
    # NOTE: must use v11.4 or later to have access to certs stored in SSL session table for the durration of any long lived sessions.
    # see note in: https://clouddocs.f5.com/api/irules/SSL__cert.html


    # Set variables:
    # Name of the HTTP header to insert the client certificate into.
    set httpHeaderName "X-Client-Cert"

    # Option to block HTTP requests with no client certificate.
    set blockHttpRequestsWithNoCert 0

    # Debug logging, don't enable this in production.
    set debugLogging 0
}

when HTTP_REQUEST {
    # Remove any existing headers that the client might have sent.
    HTTP::header remove $httpHeaderName

    # Check if a client certificate was presented:
    if {[SSL::cert count] > 0}{
        # Check if the client certificate is valid:
        if { [SSL::verify_result] eq 0 } {
            # Extract the client certificate and b64 encode it:
            set client_cert [b64encode [SSL::cert 0]]
            # Insert the client certificate into the HTTP request headers
            HTTP::header insert $httpHeaderName $client_cert
            if {$debugLogging} {
                log local0. "[IP::client_addr]:[TCP::client_port]: Client certificate verification successful inserting $httpHeaderName for session: [SSL::sessionid]"
            }
        } else {
            if {$debugLogging} {
                log local0. "[IP::client_addr]:[TCP::client_port]: Client certificate verification failed with error: [X509::verify_cert_error_string [SSL::verify_result]] for session: [SSL::sessionid]"
            }
            if { $blockHttpRequestsWithNoCert == 1 } {
                HTTP::respond 403 content "Forbidden: Invalid client certificate."
                return
            }
        }
    } else {
        if {$debugLogging} {
            log local0. "[IP::client_addr]:[TCP::client_port]: No client certificate presented for Session: [SSL::sessionid]."
        }
        if { $blockHttpRequestsWithNoCert == 1 } {
            HTTP::respond 403 content "Forbidden: No client certificate presented."
            return
        }
    }
}