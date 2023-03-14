ltm rule /Common/http_transparent_to_explicit_proxy {
when CLIENT_ACCEPTED priority 50 {

    ## Debug logging:
    # 1 = Enable debug logging (DO NOT USE IN PRODUCTION)
    # 0 = Disable debug logging.
    set debug 1
}
###################################################
######## NO CUSTOMIZATION BELOW THIS LINE #########
###################################################

when CLIENT_ACCEPTED priority 250 {

if { $debug } { set ctx(log) 1 } else { set ctx(log) 0}
set srcIP [IP::client_addr]
set dstIP [IP::local_addr]
set srcPort [TCP::client_port]
set dstPort [TCP::local_port]
set ctx(SNI) ""
set ctx(ptcl) "unknown"
set ctx(xpinfo) ""

if {[set x [lsearch -integer -sorted [list 21 22 25 53 80 110 115 143 443 465 587 990 993 995 3128 8080] [TCP::local_port]]] >= 0} {
   set ctx(ptcl) [lindex [list "ftp" "ssh" "smtp" "dns" "http" "pop3" "sftp" "imap" "https" "smtps" "smtp" "ftps" "imaps" "pop3s" "http" "http"] $x]
}
if { $ctx(log) } { log local0.debug "CLIENT_ACCEPTED TCP from ${srcIP}:${srcPort} to ${dstIP}:${dstPort} L7 guess=$ctx(ptcl) ExplicitProxy=${ctx(xpinfo)}" }

} ; #CLIENT_ACCEPTED

when CLIENT_ACCEPTED priority 500 {
    ## Start with HTTP disabled
    HTTP::disable

    set THIS_POOL [LB::server pool]

    ## Set the option and detect_handshake flags
    set option 0
    set detect_handshake 1

    ## Set the option and detect_handshake flags
    set option 0
    set detect_handshake 1

    ## Collect the request payload -> trigger CLIENT_DATA
    TCP::collect
}
when CLIENT_DATA priority 500 {
    ## Collect SNI from caller (sharedvar or binary parse)
    if { [info exists SEND_SNI] } { 
        ## fetch SNI from client rule (sharedvar)
        set SNI ${SEND_SNI}
    } else {
        if { $ctx(log) } { log local0.debug "no SNI from client, do binary scan!" }
        ## no SNI provided, binary parse TLS ClientHello (22) to get SNI
        binary scan [TCP::payload] c type
        if { ${type} == 22 } {
            set option 1

            ## Store the original payload
            binary scan [TCP::payload] H* orig

            ## Check for a properly formatted handshake request
            if { [binary scan [TCP::payload] cSS tls_xacttype tls_version tls_recordlen] < 3 } {
                if { $ctx(log) } { log local0.debug "reject for bad tls version/record length" }
                reject
                return
            }

            switch $tls_version {
                "769" -
                "770" -
                "771" {
                    if { ($tls_xacttype == 22) } {
                        binary scan [TCP::payload] @5c tls_action
                        if { not (($tls_action == 1) && ([TCP::payload length] > $tls_recordlen)) } { set detect_handshake 0 }
                    }
                }
                "768" { set detect_handshake 0 }
                default { set detect_handshake 0 }
            }

            if { ($detect_handshake) } {
                if { $ctx(log) } { log local0.debug "TLS Handshake Detected." }
                # skip past the session id
                set record_offset 43
                binary scan [TCP::payload] @${record_offset}c tls_sessidlen
                set record_offset [expr {$record_offset + 1 + $tls_sessidlen}]

                # skip past the cipher list
                binary scan [TCP::payload] @${record_offset}S tls_ciphlen
                set record_offset [expr {$record_offset + 2 + $tls_ciphlen}]

                # skip past the compression list
                binary scan [TCP::payload] @${record_offset}c tls_complen
                set record_offset [expr {$record_offset + 1 + $tls_complen}]

                # check for the existence of ssl extensions
                if { ([TCP::payload length] > $record_offset) } {
                    if { $ctx(log) } { log local0.debug "SSL Extensions Found." }
                    # skip to the start of the first extension
                    binary scan [TCP::payload] @${record_offset}S tls_extenlen
                    set record_offset [expr {$record_offset + 2}]
                    # read all the extensions into a variable
                    binary scan [TCP::payload] @${record_offset}a* tls_extensions

                    # for each extension
                    for { set ext_offset 0 } { $ext_offset < $tls_extenlen } { incr ext_offset 4 } {
                        binary scan $tls_extensions @${ext_offset}SS etype elen
                        if { ($etype == 0) } {
                            # if it's a servername extension read the servername
                            set grabstart [expr {$ext_offset + 9}]
                            set grabend [expr {$elen - 5}]
                            binary scan $tls_extensions @${grabstart}A${grabend} tls_servername_orig
                            set tls_servername [string tolower ${tls_servername_orig}]
                            set ext_offset [expr {$ext_offset + $elen}]
                            break
                        } else {
                            # skip over other extensions
                            set ext_offset [expr {$ext_offset + $elen}]
                        }
                    }
                }
            }
            if { [info exists tls_servername] } {
                set SNI ${tls_servername}
            }
        }
    }



    if { $ctx(ptcl) eq "https" } {
        if { ${SNI} ne "" } {
            ## HTTPS proxy chaining can only work if the request contains an SNI
            set option 1

            ## Store the original payload (would normally be the client TLS handshake)
            binary scan [TCP::payload] H* orig

            ## Point the traffic to the proxy server
            pool ${THIS_POOL}

            # Drop the client handshake
            TCP::payload replace 0 [TCP::payload length] ""

            # Form up the CONNECT call
            set px_connect "CONNECT ${SNI}:[TCP::local_port] HTTP/1.1\r\n\r\n"

            # Send the CONNECT
            if { $ctx(log) } { log local0.debug "replacing payload with CONNECT command: ${px_connect}" }
            TCP::payload replace 0 0 $px_connect
            TCP::release
            if { $ctx(log) } { log local0.debug "released payload" }
        } elseif { ${SNI} eq "" } {
            ## HTTPS proxy chaining must fail without an SNI
            if { $ctx(log) } {  log local0.debug "reject for lack of SNI." } 
            reject
            return
        }
         } elseif { $ctx(ptcl) eq "http" } {
             ## Enable HTTP processing
             HTTP::enable
             TCP::release
         } else {
             if { $ctx(log) } { log local0.debug "catchall reject" }
             reject
             return
         }
}
when HTTP_REQUEST priority 500 {
    if { $ctx(log) } { log local0.debug "Firing HTTP_REQUEST on server irule" }
    if { [HTTP::header exists Host] } {
        set http_hostname [HTTP::host]
    } else {
        set http_hostname [IP::local_addr]:[TCP::local_port]
    }

    ## Point the traffic to the proxy server
    pool ${THIS_POOL}

    # Rewrite to proxified HTTP request
    HTTP::uri http://${http_hostname}:[TCP::local_port][HTTP::uri]
}
when HTTP_RESPONSE priority 300 {
    if { $ctx(log) } { log local0.debug "Firing HTTP_RESPONSE on server irule" }
    switch -glob -- [HTTP::status] {
        "2*" -
        "3*" {
            # drop the proxy status and replay the original handshake
        }
        "400" {
            # Bad Request
            if { $ctx(log) } { log local0.debug "reject for http 400" }
            #reject
            #return
        }
        "403" {
            # Forbidden
            if { $ctx(log) } { log local0.debug "reject for http 403" }
           # reject
           # return
        }
        "407" {
            if { $ctx(log) } { log local0.debug "407 response from proxy replace with 401" }
            # stub for when authentication is required
            HTTP::header replace ":S" "401 Unauthorized"
        }
        "502" {
            # Bad Gateway (proxy error)
            if { $ctx(log) } { log local0.debug "reject for http 502" }
           # reject
           # return
        }
        "503" {
            # Service Unavailable
            if { $ctx(log) } { log local0.debug "reject for http 503" }
           # reject
           # return
        }
        "504" {
            # Gateway Timeout
            if { $ctx(log) } { log local0.debug "reject for http 504" }
           # reject
           # return
        }
        default {
            if { $ctx(log) } { log local0.debug "catchall reject" }
           # reject
           # return
        }
    }
}
when SERVER_CONNECTED priority 900 {
    ## Only do this for TLS traffic
    if { ${option} } {
        if { $ctx(log) } { log local0.debug "Option TCP Collection on SERVER_CONNECTED" }
        TCP::collect 12
    }
}
when SERVER_DATA priority 900 {
    switch -glob -- [TCP::payload] {
        "HTTP/1.[01] 200*" {
            if { $ctx(log) } { log local0.debug "SERVER_DATA replay SSL Client Hello: ${orig}" }
            # drop the proxy status and replay the original handshake
            TCP::payload replace 0 [TCP::payload length] ""
            TCP::respond [binary format H* $orig]
        }
        "HTTP/1.[01] 400*" {
            # Bad Request
            if { $ctx(log) } { log local0.debug "reject for http 400" }
           # reject
           # return
        }
        "HTTP/1.[01] 403*" {
            # Forbidden
            if { $ctx(log) } { log local0.debug "reject for http 403" }
           # reject
           # return
        }
        "HTTP/1.[01] 407*" {
            # stub for when authentication is required
            if { $ctx(log) } { log local0.debug "reject for http 407" }
           # reject
        #    return
        }
        "HTTP/1.[01] 502*" {
            # Bad Gateway (proxy error)
            if { $ctx(log) } { log local0.debug "reject for http 502" }
        #    reject
        #    return
        }
        "HTTP/1.[01] 503*" {
            # Service Unavailable
            if { $ctx(log) } { log local0.debug "reject for http 503" }
        #    reject
        #    return
        }
        "HTTP/1.[01] 504*" {
            # Gateway Timeout
            if { $ctx(log) } { log local0.debug "reject for http 504" }
        #    reject
        #    return
        }
        default {
            if { $ctx(log) } { log local0.debug "catchall reject" }
        #    reject
        #    return
        }
    }
    TCP::release
}
}