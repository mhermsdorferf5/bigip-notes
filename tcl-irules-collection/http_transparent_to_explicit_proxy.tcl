when CLIENT_ACCEPTED priority 50 {

    ## Debug logging:
    ##   1 = Enable debug logging (DO NOT USE IN PRODUCTION)
    ##   0 = Disable debug logging.
    set debug 0

    ## TLS Client Hello wait timers:
    ## These timers get used when we're trying to parse the TLS Handshake/Client Hello, but we haven't yet recieved the full handshake and need to wait for large handshakes to come in.
    ##   loop_time controls how long each count through the loop waits, in milliseconds.
    ##   max_loop_count controls how many times we'll wait, total delay could be: $loop_time * $max_loop_count
    ## In this case, total max wait time is: 2*2500 = 5000ms or 5 seconds:
    set loop_time 2
    set max_loop_count 2500
} ;#END CLIENT_ACCEPTED priority 50

######################################################
######## NO CUSTOMIZATION BELOW THIS LINE v4 #########
######################################################

when CLIENT_ACCEPTED priority 250 {

    # Init variables:
    set srcIP [IP::client_addr]
    set dstIP [IP::local_addr]
    set srcPort [TCP::client_port]
    set dstPort [TCP::local_port]
    set ctx(SNI) ""
    set ctx(ptcl) "unknown"
    set ctx(xpinfo) ""
    set SNI ""

    # Setup Logging vars based on debug value:
    #  Debug Logging is log level 2
    #  Normal Logging is log level 1: This should be minimal logging of unexpected conditions.
    #  To disable all logging use: set ctx(log) 0
    if { $debug } {
        set ctx(log) 2
        set logPrefix "$srcIP:$srcPort => $dstIP:$dstPort "
    } else {
        set ctx(log) 1
        set logPrefix "$srcIP:$srcPort => $dstIP:$dstPort "
    }

    if {[set x [lsearch -integer -sorted [list 21 22 25 53 80 110 115 143 443 465 587 990 993 995 3128 8080] [TCP::local_port]]] >= 0} {
        set ctx(ptcl) [lindex [list "ftp" "ssh" "smtp" "dns" "http" "pop3" "sftp" "imap" "https" "smtps" "smtp" "ftps" "imaps" "pop3s" "http" "http"] $x]
    }
    if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: CLIENT_ACCEPTED L7 guess=$ctx(ptcl) ExplicitProxy=${ctx(xpinfo)}" }

} ;#END CLIENT_ACCEPTED priority 250

when CLIENT_ACCEPTED priority 600 {
    ## Start with HTTP disabled
    HTTP::disable

    set THIS_POOL [LB::server pool]

    ## Set the option and detect_handshake flags
    set option 0
    set detect_handshake 1

    ## Collect the request payload -> trigger CLIENT_DATA
    TCP::collect

} ;#END CLIENT_ACCEPTED priority 600

when CLIENT_DATA priority 600 {

    sharedvar bypass
    if { ![info exists bypass] } {
        if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: bypass set to 0" }
        set bypass 0
    } else {
        if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: bypass already set: ${bypass}" }
    }

    ## Collect SNI from caller (sharedvar or binary parse)
    if { [info exists SEND_SNI] } {
        ## fetch SNI from client rule (sharedvar)
        set SNI ${SEND_SNI}
    } else {
        if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: no SNI from client, do binary scan!" }
        ## no SNI provided, binary parse TLS ClientHello (22) to get SNI
        set type ""
        binary scan [TCP::payload] c type
        if { ${type} == 22 } {
            set option 1

            ## Store the original payload
            set orig ""
            binary scan [TCP::payload] H* orig

            ## Check for a properly formatted handshake request
            set tls_xacttype ""
            set tls_version ""
            set tls_recordlen ""
            if { [binary scan [TCP::payload] cSS tls_xacttype tls_version tls_recordlen] < 3 } {
                if { $ctx(log) } { log local0.notice "${logPrefix}: reject for bad tls version/record length" }
                reject
                return
            }

            if { $ctx(log) > 1} { log local0.debug "${logPrefix}: TLS Version detected: ${tls_version} TLS Record Length: $tls_recordlen" }

            switch -- $tls_version {
                "769" -
                "770" -
                "771" {
                    if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: TLS Exchange Type: ${tls_xacttype}" }
                    if { ($tls_xacttype == 22) } {
                        # We have a TLS handshake, now check if it's a clienthello (handshake type = 1):
                        set tls_handshake_type ""
                        binary scan [TCP::payload] @5c tls_handshake_type
                        # If the handshake type is 1 & we don't have the full tls record length, we should wait.
                        if { $tls_handshake_type == 1 && [TCP::payload length] < $tls_recordlen } {
                            if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: WARNING: Handshake Detected, but full TLS Record NOT in TCP payload." }
                            # If we don't, then we need try and wait for it using loop timer vars set at iRule/connection init...
                            #     loop_time controls how long each count through the loop waits, in milliseconds.
                            #     max_loop_count controls how many times we'll wait, total delay could be: $loop_time * $max_loop_count
                            set loop_count 0
                            while { $loop_count < $max_loop_count }{
                                if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: TLS Record Length: $tls_recordlen | TCP Payload size: [TCP::payload length] | Loop Counter: $loop_count" }
                                if { [TCP::payload length] >= $tls_recordlen } { break }
                                after $loop_time
                                incr loop_count
                            }
                            if { [TCP::payload length] < $tls_recordlen  } {
                                set detect_handshake 0
                                if { $ctx(log) } {
                                    log local0.warning "${logPrefix}: ERROR: Client Hello Handshake Detected, but full TLS Record NOT in TCP payload, even after waiting for: [expr {$loop_time * $loop_count}] ms"
                                }
                            } else {
                                if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: Client Hello Handshake Detected, full TLS Record collected after waiting for: [expr {$loop_time * $loop_count}] ms" }
                                set detect_handshake 1
                            }
                        }
                    }
                }
                "768" { set detect_handshake 0 }
                default { set detect_handshake 0 }
            }

            if { ($detect_handshake) } {
                if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: TLS Handshake Detected." }
                # skip past the session id
                set record_offset 43
                set tls_sessidlen ""
                binary scan [TCP::payload] @${record_offset}c tls_sessidlen
                set record_offset [expr {$record_offset + 1 + $tls_sessidlen}]

                # skip past the cipher list
                set tls_ciphlen ""
                binary scan [TCP::payload] @${record_offset}S tls_ciphlen
                set record_offset [expr {$record_offset + 2 + $tls_ciphlen}]

                # skip past the compression list
                set tls_complen ""
                binary scan [TCP::payload] @${record_offset}c tls_complen
                set record_offset [expr {$record_offset + 1 + $tls_complen}]

                # check for the existence of ssl extensions
                if { ([TCP::payload length] > $record_offset) } {
                    if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: SSL Extensions Found." }
                    # skip to the start of the first extension
                    set tls_extenlen ""
                    binary scan [TCP::payload] @${record_offset}S tls_extenlen
                    set record_offset [expr {$record_offset + 2}]
                    # read all the extensions into a variable
                    set tls_extensions ""
                    binary scan [TCP::payload] @${record_offset}a* tls_extensions

                    # for each extension
                    for { set ext_offset 0 } { $ext_offset < $tls_extenlen } { incr ext_offset 4 } {
                        set etype ""
                        set elen ""
                        binary scan $tls_extensions @${ext_offset}SS etype elen
                        if { ($etype == 0) } {
                            # if it's a servername extension read the servername
                            set grabstart [expr {$ext_offset + 9}]
                            set grabend [expr {$elen - 5}]
                            set tls_servername_orig ""
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
            } else {
                if { $ctx(log) } { log local0.notice "${logPrefix}: WARNING: No TLS Handshake Detected, traffic falling through iRule." }
            }
            if { [info exists tls_servername] } {
                set SNI ${tls_servername}
            }
        }
    }

    if { $ctx(ptcl) eq "https" } {
        if { ${SNI} ne "" } {
            if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: SNI previously detected: $SNI" }
            ## HTTPS proxy chaining can only work if the request contains an SNI
            set option 1

            ## Store the original payload (would normally be the client TLS handshake)
            set orig ""
            binary scan [TCP::payload] H* orig

            ## Point the traffic to the proxy server
            pool ${THIS_POOL}

            # Drop the client handshake
            TCP::payload replace 0 [TCP::payload length] ""

            # Form up the CONNECT call
            set px_connect "CONNECT ${SNI}:[TCP::local_port] HTTP/1.1\r\n\r\n"

            # Send the CONNECT
            if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: replacing payload with CONNECT command: ${px_connect}" }
            TCP::payload replace 0 0 $px_connect
            TCP::release
            if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: released payload" }
        } elseif { ${SNI} eq "" } {
            if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: SNI not previously detected, will connect to IP:Port" }
            ## IF there is no SNI extension, then assume we're connecting to the IP.
            set option 1

            ## Store the original payload (would normally be the client TLS handshake)
            set orig ""
            binary scan [TCP::payload] H* orig

            ## Point the traffic to the proxy server
            pool ${THIS_POOL}

            # Drop the client handshake
            TCP::payload replace 0 [TCP::payload length] ""

            # Form up the CONNECT call
            ## Given No SNI extension, then assume we're connecting to the IP.
            set px_connect "CONNECT [IP::local_addr]:[TCP::local_port] HTTP/1.1\r\n\r\n"

            # Send the CONNECT
            if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: replacing payload with CONNECT command: ${px_connect}" }
            TCP::payload replace 0 0 $px_connect
            TCP::release
            if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: released payload" }
        }
    } elseif { $ctx(ptcl) eq "http" } {
        ## Enable HTTP processing
        if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: Detected HTTP, enabling HTTP profile, & release tcp." }
        HTTP::enable
        TCP::release
    } else {
        if { $ctx(log) } { log local0.notice "${logPrefix}: catchall reject" }
        reject
        return
    }
} ;#END CLIENT_DATA priority 600

when HTTP_REQUEST priority 500 {
    if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: Firing HTTP_REQUEST on server irule" }
    if { [HTTP::header exists Host] } {
        set http_hostname [HTTP::host]
    } else {
        set http_hostname [IP::local_addr]:[TCP::local_port]
    }

    ## Point the traffic to the proxy server
    pool ${THIS_POOL}

    # Rewrite to proxified HTTP request
    HTTP::uri http://${http_hostname}:[TCP::local_port][HTTP::uri]
} ;#END HTTP_REQUEST priority 500

when HTTP_RESPONSE priority 300 {
    if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: Firing HTTP_RESPONSE on server irule, proxy responded with HTTP protocol parsing enabled." }
    switch -glob -- [HTTP::status] {
        "2*" -
        "3*" {
            # drop the proxy status and replay the original handshake
        }
        "400" {
            # Bad Request
            if { $ctx(log) } { log local0.notice "${logPrefix}: reject for http 400 from proxy" }
            #reject
            #return
        }
        "403" {
            # Forbidden
            if { $ctx(log) } { log local0.notice "${logPrefix}: reject for http 403 from proxy" }
            # reject
            # return
        }
        "407" {
            if { $ctx(log) } { log local0.notice "${logPrefix}: 407 response from proxy replace with 401 from proxy" }
            # stub for when authentication is required
            HTTP::header replace ":S" "401 Unauthorized"
        }
        "502" {
            # Bad Gateway (proxy error)
            if { $ctx(log) } { log local0.notice "${logPrefix}: reject for http 502 from proxy" }
            # reject
            # return
        }
        "503" {
            # Service Unavailable
            if { $ctx(log) } { log local0.notice "${logPrefix}: reject for http 503 from proxy" }
            # reject
            # return
        }
        "504" {
            # Gateway Timeout
            if { $ctx(log) } { log local0.notice "${logPrefix}: reject for http 504 from proxy" }
            # reject
            # return
        }
        default {
            if { $ctx(log) } { log local0.notice "${logPrefix}: catchall reject from proxy" }
            # reject
            # return
        }
    }
} ;#END HTTP_RESPONSE priority 300

when SERVER_CONNECTED priority 900 {
    ## Only do this for TLS traffic, where we're going to replay the TLS CLient Handshake
    if { ${option} } {
        if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: Option TCP Collection on SERVER_CONNECTED" }
        TCP::collect 12
    }
} ;#END SERVER_CONNECTED priority 900

when SERVER_DATA priority 900 {
    # This only fires when TCP::collect is used, so no reason to check $option
    if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: Firing SERVER_DATA on server irule, proxy responded without HTTP protocol parsing enabled." }
    switch -glob -- [TCP::payload] {
        "HTTP/1.? 200*" {
            if { $ctx(log) > 1 } { log local0.debug "${logPrefix}: SERVER_DATA with 200 response from proxy, replaying SSL Client Hello: ${orig}" }
            # Now now effectively have a TCP connection to the origin server, given how explicit forward proxy works.
            # drop the proxy status and replay the original handshake
            TCP::payload replace 0 [TCP::payload length] ""
            # Attempt to send the payload (orig tls handshake), but catch in case we lost connection or such.
            if { [catch { TCP::respond [binary format H* ${orig} ] } returnCode ] } {
                if { $ctx(log) } { log local0.warning "${logPrefix}: ERROR: Replay of TLS Handshake failed, likely connection to proxy dropped, return value: ${returnCode}" }
            }
        }
        "HTTP/1.? 400*" {
            # Bad Request
            if { $ctx(log) } { log local0.notice "${logPrefix}: reject for http 400 from proxy" }
            # reject
            # return
        }
        "HTTP/1.? 403*" {
            # Forbidden
            if { $ctx(log) } { log local0.notice "${logPrefix}: reject for http 403 from proxy" }
            # reject
            # return
        }
        "HTTP/1.? 407*" {
            # stub for when authentication is required
            if { $ctx(log) } { log local0.notice "${logPrefix}: reject for http 407 from proxy" }
            # reject
            # return
        }
        "HTTP/1.? 502*" {
            # Bad Gateway (proxy error)
            if { $ctx(log) } { log local0.notice "${logPrefix}: reject for http 502 from proxy" }
            # reject
            # return
        }
        "HTTP/1.? 503*" {
            # Service Unavailable
            if { $ctx(log) } { log local0.notice "${logPrefix}: reject for http 503 from proxy" }
            # reject
            # return
        }
        "HTTP/1.? 504*" {
            # Gateway Timeout
            if { $ctx(log) } { log local0.notice "${logPrefix}: reject for http 504 from proxy" }
            # reject
            # return
        }
        default {
            if { $ctx(log) } { log local0.notice "${logPrefix}: catchall reject from proxy" }
            # reject
            # return
        }
    }
    # Release the TCP collection:
    TCP::release
    # Unset our orig var, which could contain a fair bit of data (The Full TLS Handshake, 300-10k bytes typical ):
    unset -- orig
} ;# END SERVER_DATA priority 900